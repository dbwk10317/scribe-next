// Approved retry-jitter and GNU shuffle contracts for actual store.cpp.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_TEST_REVIEW_RETRY_SHUFFLE_CONTRACTS_H
#define SCRIBE_TEST_REVIEW_RETRY_SHUFFLE_CONTRACTS_H

#include <algorithm>

class ReviewRetryBuffer : public BufferStore {
 public:
  explicit ReviewRetryBuffer(ScribeContext& context)
      : BufferStore(context, nullptr, "review-retry", false) {}
  void failure() { changeState(DISCONNECTED); }
  void success() { setNewRetryInterval(true); }
  time_t interval() const { return retryInterval; }
  unsigned long continuous() const { return numContSuccess; }
  time_t range() const { return retryIntervalRange; }
  unsigned long offset() const { return maxRandomOffset; }
};

static void testReviewRetry(const std::string& config,
                            const std::string& directory) {
  HandlerFixture fixture(config);
  pStoreConf configuration(new StoreConf);
  configuration->parseConfig(config);
  ReviewRetryBuffer buffer(*fixture.handler);
  buffer.configure(configuration, pStoreConf());
  std::string actions("FFFFF");
  configuration->getString("test_actions", actions);
  unsigned long seed = 42;
  configuration->getUnsigned("test_seed", seed);
  // Record libc's draws separately, then reset before exercising production.
  // The assertions in Python can check positive-jitter math and the next RNG
  // value without assuming a particular libc rand sequence.
  std::ostringstream draws, intervals, continuous;
  srand(seed);
  for (size_t i = 0; i <= actions.size(); ++i) {
    if (i) draws << ',';
    draws << rand();
  }
  srand(seed);
  for (size_t i = 0; i < actions.size(); ++i) {
    if (actions[i] == 'F') buffer.failure();
    else if (actions[i] == 'S') buffer.success();
    else throw std::runtime_error("unknown retry action");
    if (i) { intervals << ','; continuous << ','; }
    intervals << buffer.interval();
    continuous << buffer.continuous();
  }
  std::ostringstream state;
  state << "intervals=" << intervals.str() << "\ncontinuous=" << continuous.str()
        << "\nrange=" << buffer.range() << "\noffset=" << buffer.offset()
        << "\nretries=" << fixture.handler->getCounter("review-retry:retries")
        << "\nlost=" << fixture.handler->getCounter("review-retry:lost")
        << "\ndraws=" << draws.str() << "\nnext-rand=" << rand() << '\n';
  save(directory + "/retry-state.txt", state.str());
}

class ReviewPeriodicChild : public NullStore {
 public:
  ReviewPeriodicChild(ScribeContext& context, uint32_t id, std::vector<uint32_t>& calls)
      : NullStore(context, nullptr, "review-shuffle", false), id_(id), calls_(calls) {}
  void periodicCheck() override { calls_.push_back(id_); }
 private:
  uint32_t id_;
  std::vector<uint32_t>& calls_;
};

class ReviewPeriodicBucket : public BucketStore {
 public:
  ReviewPeriodicBucket(ScribeContext& context, uint32_t size, std::vector<uint32_t>& calls)
      : BucketStore(context, nullptr, "review-shuffle", false) {
    // Populate test children directly. No BucketStore configure/copy/routing
    // path is executed; this fixture owns periodicCheck's order only.
    for (uint32_t i = 0; i < size; ++i) {
      buckets.push_back(std::shared_ptr<Store>(new ReviewPeriodicChild(context, i, calls)));
    }
  }
};

static void testReviewShuffle(const std::string& directory) {
  scribeHandler context(0, "");
  std::ostringstream observations;
  for (uint32_t size : {0u, 1u, 2u, 3u, 4u, 8u, 17u, 100u}) {
    for (unsigned seed : {0u, 1u, 42u, 31337u}) {
      std::vector<uint32_t> calls;
      ReviewPeriodicBucket bucket(context, size, calls);
      srand(seed);
      bucket.periodicCheck();
      bucket.periodicCheck();
      const int next = rand();
      // GNU's old forward shuffle consumes exactly size-1 rand calls per
      // invocation; empty and singleton lists consume none.
      srand(seed);
      for (uint32_t i = 0; i < 2 * (size ? size - 1 : 0); ++i) rand();
      require(rand() == next, "shuffle changed subsequent rand state");
      require(calls.size() == 2 * size, "shuffle changed periodic call count");
      for (uint32_t pass = 0; pass < 2; ++pass) {
        std::vector<uint32_t> sorted(calls.begin() + pass * size,
                                     calls.begin() + (pass + 1) * size);
        std::sort(sorted.begin(), sorted.end());
        for (uint32_t i = 0; i < size; ++i) {
          require(sorted[i] == i, "shuffle did not call each child once");
        }
      }
#if defined(__GLIBCXX__) && _GLIBCXX_USE_DEPRECATED
      // Compare with the actual installed GNU legacy algorithm where exposed.
      // The production removed-API lane is compiled independently without it.
      srand(seed);
      for (uint32_t pass = 0; pass < 2; ++pass) {
        std::vector<uint32_t> legacy(size);
        for (uint32_t i = 0; i < size; ++i) legacy[i] = i;
        std::random_shuffle(legacy.begin(), legacy.end());
        require(std::equal(legacy.begin(), legacy.end(), calls.begin() + pass * size),
                "shuffle changed GNU legacy order");
      }
      require(rand() == next, "shuffle changed GNU legacy RNG consumption");
#endif
      observations << size << ':' << seed << ':';
      for (uint32_t i = 0; i < calls.size(); ++i) {
        if (i) observations << ',';
        observations << calls[i];
      }
      observations << ':' << next << '\n';
    }
  }
  save(directory + "/shuffle-state.txt", observations.str());
}

static bool dispatchReviewRetryShuffle(const std::string& mode,
                                       const std::string& config,
                                       const std::string& directory) {
  if (mode == "review-retry") testReviewRetry(config, directory);
  else if (mode == "review-shuffle") testReviewShuffle(directory);
  else return false;
  return true;
}

#endif // SCRIBE_TEST_REVIEW_RETRY_SHUFFLE_CONTRACTS_H
