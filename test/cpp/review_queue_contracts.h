// Original zero-byte behavior in the real handler/StoreQueue/FileStore path.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_TEST_REVIEW_QUEUE_CONTRACTS_H
#define SCRIBE_TEST_REVIEW_QUEUE_CONTRACTS_H

#include <chrono>
#include <thread>

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
  require(rpc.client.recv_Log() == scribe::thrift::OK, "queue Log ACK changed");
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
  state << "ack=0\nreceived=" << handler->getCounter("accepted:received good")
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
