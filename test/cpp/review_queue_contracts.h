// Original zero-byte queue behavior and concurrent Log throttling in the real
// handler/StoreQueue/FileStore path. Also defines the fixture binary's __wrap_time
// (-Wl,--wrap=time): the real clock unless the throttle test pins it.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_TEST_REVIEW_QUEUE_CONTRACTS_H
#define SCRIBE_TEST_REVIEW_QUEUE_CONTRACTS_H

#include <chrono>
#include <thread>
#include <atomic>

static std::atomic<time_t> reviewFixedTime{0};
extern "C" time_t __real_time(time_t* value);
extern "C" time_t __wrap_time(time_t* value) {
  const time_t fixed = reviewFixedTime.load();
  if (!fixed) return __real_time(value);
  if (value) *value = fixed;
  return fixed;
}

static void testReviewConcurrentThrottle(const std::string& config) {
  // Pinned ahead of the real clock: StoreQueue workers derive their CLOCK_REALTIME
  // timedwait deadline from time(), so a past value would make them busy-spin.
  reviewFixedTime = __real_time(nullptr) + 3600;
  HandlerFixture fixture(config);
  const auto handler = fixture.handler;
  handler->initialize();
  require(handler->getStatus() == facebook::fb303::ALIVE, "throttle fixture not alive");
  unsigned long limit = 0;
  require(handler->getConfig().getUnsigned("max_msg_per_second", limit) &&
              (limit == 0 || limit == 100), "throttle fixture limit");
  const std::vector<LogEntry> message{entry("accepted", "payload")};
  std::atomic<unsigned> ready{0}, accepted{0};
  std::atomic<bool> start{false};
  std::vector<std::thread> callers;
  for (unsigned i = 0; i < 16; ++i) {
    callers.emplace_back([&] {
      ++ready;
      while (!start.load()) std::this_thread::yield();
      for (unsigned attempt = 0; attempt < 64; ++attempt) {
        // Bypass the fixture's single-caller received-vector spy, not production Log.
        if (handler->scribeHandler::Log(message) == scribe::thrift::OK) ++accepted;
      }
    });
  }
  while (ready.load() != 16) std::this_thread::yield();
  start = true;
  for (auto& caller : callers) caller.join();
  const unsigned expected = limit ? 100 : 1024;
  require(accepted == expected, "concurrent throttle quota changed");
  require(handler->getCounter("accepted:received good") == expected,
          "concurrent throttle received counter changed");
  require(handler->getCounter("scribe_overall:denied for rate") == 1024 - expected,
          "concurrent throttle denied counter changed");
  if (limit) {
    // Original half-limit boundary, huge-batch exemption and next-second reset.
    require(handler->scribeHandler::Log(std::vector<LogEntry>(51, message[0])) == scribe::thrift::OK,
            "legacy huge-batch exemption changed");
    require(handler->scribeHandler::Log(message) == scribe::thrift::TRY_LATER,
            "huge batch changed exhausted quota");
    ++reviewFixedTime;
    const std::vector<LogEntry> half(50, message[0]);
    require(handler->scribeHandler::Log(half) == scribe::thrift::OK &&
                handler->scribeHandler::Log(half) == scribe::thrift::OK &&
                handler->scribeHandler::Log(message) == scribe::thrift::TRY_LATER,
            "next-second reset or exact quota boundary changed");
  }
  handler->stopForTest();
  reviewFixedTime = 0;
}

static std::string reviewQueueOutput(const std::string& directory) {
  std::ifstream input((directory + "/data/fixture_00000").c_str(), std::ios::binary);
  return std::string(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
}

static void testReviewQueue(const std::string& mode, const std::string& config,
                            const std::string& directory) {
  HandlerFixture fixture(config);
  const auto handler = fixture.handler;
  handler->initialize();
  require(handler->getStatus() == facebook::fb303::ALIVE, "queue fixture not alive");
  std::vector<LogEntry> messages(3, entry("accepted", ""));
  if (mode == "review-queue-mixed") {
    messages[1].message = std::string("A\0B\n\xff", 5);
    messages[2].message = "ends\n";
  } else if (mode == "review-queue-empty-batch") {
    messages.clear();
  }
  MemoryRpc rpc(handler);
  rpc.client.send_Log(messages);
  rpc.process();
  const auto ack = rpc.client.recv_Log();
  require(ack == scribe::thrift::OK, "queue Log ACK changed");
  require(handler->received == messages, "queue RPC changed payloads");
  require(handler->getCounter("accepted:received good") == static_cast<int64_t>(messages.size()),
          "queue received-good counter changed");

  if (mode == "review-queue-periodic") {
    // Observe the original lack of empty-only delivery across worker intervals.
    // Polling does not replace production max_write_interval scheduling.
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (reviewQueueOutput(directory).empty() &&
           std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    require(reviewQueueOutput(directory).empty(), "empty-only queue was flushed");
    save(directory + "/before-stop.bin", reviewQueueOutput(directory));
  } else {
    // max_write_interval=3600 and target_write_size=16384 keep this small
    // batch queued until stop. OK remains an in-memory acceptance ACK.
    require(reviewQueueOutput(directory).empty(), "batch flushed before stop");
    if (mode == "review-queue-stop") {
      // max_queue_size=0 still permits an empty request with three accepted
      // zero-byte entries queued: queue size remains payload bytes, not count.
      require(handler->Log({}) == scribe::thrift::OK, "zero-byte queue was throttled");
    }
  }

  handler->stopForTest();
  std::ostringstream state;
  state << "ack=" << static_cast<int>(ack)
        << "\nreceived=" << handler->getCounter("accepted:received good")
        << "\nlost=" << handler->getCounter("accepted:lost")
        << "\nrequeue=" << handler->getCounter("accepted:requeue")
        << "\nbytes-lost=" << handler->getCounter("accepted:bytes lost") << "\n";
  save(directory + "/states.txt", state.str());
  require(handler->getCounter("accepted:lost") == 0, "queue unexpectedly counted loss");
  require(handler->getCounter("accepted:requeue") == 0, "queue unexpectedly requeued");
  require(handler->getCounter("accepted:bytes lost") == 0, "FileStore counted lost bytes");
  require(handler->Log({entry("accepted", "after stop")}) == scribe::thrift::TRY_LATER,
          "stopped queue accepted another message");
}

static bool dispatchReviewQueue(const std::string& mode, const std::string& config,
                                const std::string& directory) {
  if (mode != "review-queue-stop" && mode != "review-queue-periodic" &&
      mode != "review-queue-mixed" && mode != "review-queue-empty-batch") return false;
  testReviewQueue(mode, config, directory);
  return true;
}

#endif // SCRIBE_TEST_REVIEW_QUEUE_CONTRACTS_H
