// scribe-next tests for the removed Thrift read/write mutex compatibility API.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "compat_mutex.h"

#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstdlib>
#include <future>
#include <iostream>
#include <string>
#include <thread>
#include <type_traits>

using scribe::concurrency::ReadWriteMutex;
using scribe::concurrency::RWGuard;

static_assert(!std::is_copy_constructible<ReadWriteMutex>::value,
              "a live POSIX mutex must not be copied");
static_assert(!std::is_copy_assignable<ReadWriteMutex>::value,
              "a live POSIX mutex must not be copy-assigned");
static_assert(!std::is_copy_constructible<RWGuard>::value,
              "a guard must not acquire a second owner through copying");
static_assert(!std::is_copy_assignable<RWGuard>::value,
              "a guard must not acquire a second owner through assignment");

namespace {

void require(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << '\n';
    // Exit immediately, rather than destroying a joinable or blocked thread.
    std::exit(EXIT_FAILURE);
  }
}

void await(std::future<void>& event, const char* message) {
  require(event.wait_for(std::chrono::seconds(5)) == std::future_status::ready,
          message);
  event.get();
}

// Only a contender that is expected to encounter an already-held lock sets
// this pointer. The linker wrappers below perform a real nonblocking probe,
// report EBUSY to the owner, then forward to the real blocking pthread call.
// This observes exclusion deterministically instead of treating an unready
// future after an arbitrary sleep as evidence that acquisition was blocked.
thread_local std::promise<void>* expect_contention = nullptr;

void observe_contention(pthread_rwlock_t* mutex, bool write) {
  if (expect_contention == nullptr) {
    return;
  }
  const int result = write ? pthread_rwlock_trywrlock(mutex)
                           : pthread_rwlock_tryrdlock(mutex);
  if (result == 0) {
    pthread_rwlock_unlock(mutex);
  }
  require(result == EBUSY, "contender was not excluded by the held write lock");
  expect_contention->set_value();
  expect_contention = nullptr;
}

void concurrent_readers() {
  const ReadWriteMutex mutex;
  std::promise<void> acquired;
  auto acquired_event = acquired.get_future();
  std::promise<void> finish;
  auto finish_event = finish.get_future();

  RWGuard first_reader(mutex);
  std::thread second_reader([&] {
    RWGuard guard(mutex);
    acquired.set_value();
    await(finish_event, "second reader was never released");
  });
  // first_reader remains held until after the second guard has acquired and
  // released, so this cannot pass if the default guard takes a write lock.
  await(acquired_event, "default read guards did not permit concurrent readers");
  finish.set_value();
  second_reader.join();
}

void exclusive_writer() {
  const ReadWriteMutex mutex;
  std::promise<void> reader_blocked;
  auto reader_blocked_event = reader_blocked.get_future();
  std::promise<void> writer_blocked;
  auto writer_blocked_event = writer_blocked.get_future();
  std::promise<void> reader_acquired;
  auto reader_acquired_event = reader_acquired.get_future();
  std::promise<void> writer_acquired;
  auto writer_acquired_event = writer_acquired.get_future();
  std::atomic<bool> owner_finished{false};
  std::thread reader;
  std::thread writer;

  {
    RWGuard owner(mutex, true);
    reader = std::thread([&] {
      expect_contention = &reader_blocked;
      RWGuard guard(mutex);
      require(owner_finished.load(), "reader entered before owner finished");
      reader_acquired.set_value();
    });
    writer = std::thread([&] {
      expect_contention = &writer_blocked;
      RWGuard guard(mutex, true);
      require(owner_finished.load(), "writer entered before owner finished");
      writer_acquired.set_value();
    });
    await(reader_blocked_event, "reader did not reach the held write lock");
    await(writer_blocked_event, "writer did not reach the held write lock");
    owner_finished.store(true);
  }

  // These waits only bound liveness after release; neither is a negative
  // timing assertion about how long a contender ought to remain blocked.
  await(reader_acquired_event, "reader did not acquire after writer release");
  await(writer_acquired_event, "writer did not acquire after writer release");
  reader.join();
  writer.join();
}

void exception_release() {
  struct ExpectedException {};
  for (bool write : {false, true}) {
    const ReadWriteMutex mutex;
    bool caught = false;
    try {
      RWGuard guard(mutex, write);
      throw ExpectedException{};
    } catch (const ExpectedException&) {
      caught = true;
    }
    require(caught, "exception did not leave the guarded scope");

    std::promise<void> acquired;
    auto acquired_event = acquired.get_future();
    std::thread next_writer([&] {
      RWGuard guard(mutex, true);
      acquired.set_value();
    });
    await(acquired_event, "exception unwinding left a read or write lock held");
    next_writer.join();
  }
}

void recursive_readers() {
  const ReadWriteMutex mutex;
  mutex.acquireRead();
  mutex.acquireRead();
  mutex.release();

  std::promise<void> writer_blocked;
  auto writer_blocked_event = writer_blocked.get_future();
  std::promise<void> writer_acquired;
  auto writer_acquired_event = writer_acquired.get_future();
  std::thread writer([&] {
    expect_contention = &writer_blocked;
    RWGuard guard(mutex, true);
    writer_acquired.set_value();
  });

  // One release must not drop both acquisitions by the same reader thread.
  await(writer_blocked_event, "recursive read lock was lost after one release");
  mutex.release();
  await(writer_acquired_event, "writer stayed blocked after both read releases");
  writer.join();
}

void manual_transition() {
  const ReadWriteMutex mutex;
  std::promise<void> read_released;
  auto read_released_event = read_released.get_future();
  std::promise<void> gap_writer_acquired;
  auto gap_writer_acquired_event = gap_writer_acquired.get_future();
  std::promise<void> write_blocked;
  auto write_blocked_event = write_blocked.get_future();
  std::promise<void> finished;
  auto finished_event = finished.get_future();
  int value = 0;  // Accessed only while holding the compatibility mutex.

  std::thread transition([&] {
    mutex.acquireRead();
    require(value == 0, "initial read did not see the initial value");
    mutex.release();
    read_released.set_value();
    await(gap_writer_acquired_event, "intervening writer did not acquire");
    expect_contention = &write_blocked;
    mutex.acquireWrite();
    require(value == 17, "manual reacquisition missed the intervening writer");
    value = 29;
    mutex.release();
    finished.set_value();
  });

  await(read_released_event, "manual read acquisition/release did not complete");
  {
    RWGuard gap_writer(mutex, true);
    value = 17;
    gap_writer_acquired.set_value();
    // Another writer is deliberately allowed into the release/acquireWrite
    // gap. No atomic lock upgrade or ordering between competing waiters is
    // promised by this API or required by this test.
    await(write_blocked_event, "manual write acquisition did not contend");
  }
  await(finished_event, "manual write acquisition/release did not complete");
  transition.join();
  mutex.acquireRead();
  require(value == 29, "final read missed the manual writer's update");
  mutex.release();
}

}  // namespace

extern "C" int __real_pthread_rwlock_rdlock(pthread_rwlock_t*);
extern "C" int __real_pthread_rwlock_wrlock(pthread_rwlock_t*);

extern "C" int __wrap_pthread_rwlock_rdlock(pthread_rwlock_t* mutex) {
  observe_contention(mutex, false);
  return __real_pthread_rwlock_rdlock(mutex);
}

extern "C" int __wrap_pthread_rwlock_wrlock(pthread_rwlock_t* mutex) {
  observe_contention(mutex, true);
  return __real_pthread_rwlock_wrlock(mutex);
}

int main(int argc, char** argv) {
  require(argc == 2, "expected one fixture case name");
  const std::string name(argv[1]);
  if (name == "concurrent-readers") {
    concurrent_readers();
  } else if (name == "exclusive-writer") {
    exclusive_writer();
  } else if (name == "exception-release") {
    exception_release();
  } else if (name == "recursive-readers") {
    recursive_readers();
  } else if (name == "manual-transition") {
    manual_transition();
  } else {
    require(name == "noncopyable", "unknown fixture case name");
    // All four noncopyability assertions are enforced at compilation above.
  }
  std::cout << name << ": OK\n";
}
