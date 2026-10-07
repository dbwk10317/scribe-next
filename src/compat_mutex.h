// scribe-next compatibility boundary for the removed Thrift read/write mutex.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_COMPAT_MUTEX_H
#define SCRIBE_COMPAT_MUTEX_H

#include <pthread.h>
#include <cassert>

namespace scribe {
namespace concurrency {

// Keep the POSIX read/write lock and the existing call-site acquisition scopes.
// In particular, release-then-acquireWrite is not an atomic lock upgrade.
// As in Thrift 0.5.0, init/destroy are asserted and lock calls forward to POSIX.
// This port does not introduce a different lock-error/exception policy.
class ReadWriteMutex {
 public:
  ReadWriteMutex() {
    const int result = pthread_rwlock_init(&mutex_, NULL);
    assert(result == 0);
    (void)result;
  }
  ~ReadWriteMutex() {
    const int result = pthread_rwlock_destroy(&mutex_);
    assert(result == 0);
    (void)result;
  }

  void acquireRead() const { pthread_rwlock_rdlock(&mutex_); }
  void acquireWrite() const { pthread_rwlock_wrlock(&mutex_); }
  void release() const { pthread_rwlock_unlock(&mutex_); }

  ReadWriteMutex(const ReadWriteMutex&) = delete;
  ReadWriteMutex& operator=(const ReadWriteMutex&) = delete;

 private:
  mutable pthread_rwlock_t mutex_;
};

class RWGuard {
 public:
  explicit RWGuard(const ReadWriteMutex& mutex, bool write = false) : mutex_(mutex) {
    if (write) {
      mutex_.acquireWrite();
    } else {
      mutex_.acquireRead();
    }
  }
  ~RWGuard() { mutex_.release(); }

  RWGuard(const RWGuard&) = delete;
  RWGuard& operator=(const RWGuard&) = delete;

 private:
  const ReadWriteMutex& mutex_;
};

// Read guard whose upgrade() is the same non-atomic release-then-acquireWrite;
// the destructor releases whichever lock is held at scope exit.
class RWUpgradeGuard {
 public:
  explicit RWUpgradeGuard(const ReadWriteMutex& mutex) : mutex_(mutex) {
    mutex_.acquireRead();
  }
  ~RWUpgradeGuard() { mutex_.release(); }
  void upgrade() {
    mutex_.release();
    mutex_.acquireWrite();
  }

  RWUpgradeGuard(const RWUpgradeGuard&) = delete;
  RWUpgradeGuard& operator=(const RWUpgradeGuard&) = delete;

 private:
  const ReadWriteMutex& mutex_;
};

} // namespace concurrency
} // namespace scribe
#endif // SCRIBE_COMPAT_MUTEX_H
