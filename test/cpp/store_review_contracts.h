// Regression contracts for the previously excluded store defects.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_TEST_STORE_REVIEW_CONTRACTS_H
#define SCRIBE_TEST_STORE_REVIEW_CONTRACTS_H

static void testConfigParentOwnership(const std::string& filename) {
  // No workers or sockets: configure the actual nested MultiStore hierarchy.
  HandlerFixture handler(filename);
  const_cast<StoreConf&>(handler.handler->getConfig()).setString("null::global", "global");
  pStoreConf root(new StoreConf);
  root->parseConfig(filename);
  root->setRoot(&handler.handler->getConfig());
  pStoreConf parent, middle, leaf;
  require(root->getStore("store0", parent), "missing top configuration");
  require(parent->getStore("store0", middle), "missing middle configuration");
  require(middle->getStore("store0", leaf), "missing leaf configuration");
  std::weak_ptr<StoreConf> parentWeak(parent), middleWeak(middle), leafWeak(leaf);
  {
    MultiStore store(*handler.handler, nullptr, "fixture", false);
    store.configure(parent, pStoreConf());
    root.reset();
    parent.reset();
    middle.reset();
    leaf.reset();
    require(!parentWeak.expired(), "live Store lost its configuration");
    pStoreConf liveLeaf = leafWeak.lock();
    std::string value;
    require(liveLeaf->getString("local", value) && value == "leaf", "direct inheritance priority");
    require(liveLeaf->getString("qualified", value) && value == "leaf-qualified", "qualified local priority");
    require(liveLeaf->getString("nearest", value) && value == "middle", "nearest ancestor priority");
    require(liveLeaf->getString("outer", value) && value == "parent", "grandparent inheritance");
    require(liveLeaf->getString("global", value) && value == "global", "global fallback");
    require(!liveLeaf->getString("category", value), "category became inheritable");
    require(!liveLeaf->getString("categories", value), "categories became inheritable");
    require(liveLeaf->getString("type", value) && value == "null", "direct type changed");
  }
  require(parentWeak.expired() && middleWeak.expired() && leafWeak.expired(),
          "released Store hierarchy retains cyclic configuration ownership");
}


class ResultNullStore : public NullStore {
 public:
  ResultNullStore(ScribeContext& context, bool result)
      : NullStore(context, nullptr, "fixture", false), result_(result) {}
  bool open() override { return result_; }
  bool isOpen() override { return result_; }
  bool handleMessages(std::shared_ptr<logentry_vector_t>) override { return result_; }
  std::shared_ptr<Store> copy(const std::string&) override {
    return std::shared_ptr<Store>(new ResultNullStore(context, result_));
  }
 private:
  bool result_;
};
class ReportMultiStore : public MultiStore {
 public:
  explicit ReportMultiStore(ScribeContext& context) : MultiStore(context, nullptr, "fixture", false) {}
  void addResult(bool result) { stores.push_back(std::shared_ptr<Store>(new ResultNullStore(context, result))); }
};
static void testMultiReportDefault() {
  scribeHandler context(0, "");
  alignas(MultiStore) unsigned char memory[sizeof(MultiStore)];
  std::memset(memory, 0xa5, sizeof(memory));
  MultiStore* invalid = new(memory) MultiStore(context, nullptr, "fixture", false);
  pStoreConf config(new StoreConf);
  config->setString("report_success", "invalid");
  invalid->configure(config, pStoreConf());
  require(invalid->getStatus() == "MULTI: Invalid report_success value.", "invalid report diagnostic changed");
  require(invalid->isOpen(), "invalid initial configuration has indeterminate report mode");
  require(invalid->open(), "empty all-mode open changed");
  std::shared_ptr<logentry_vector_t> messages(new logentry_vector_t);
  require(invalid->handleMessages(messages), "empty all-mode aggregation changed");
  invalid->~MultiStore();
  for (const char* mode : {"all", "any"}) {
    ReportMultiStore store(context);
    config->setString("report_success", mode);
    store.configure(config, pStoreConf());
    store.addResult(false); store.addResult(true);
    const bool expected = std::string(mode) == "any";
    require(store.open() == expected && store.isOpen() == expected &&
            store.handleMessages(messages) == expected, "valid all/any aggregation changed");
    std::shared_ptr<Store> copy = store.copy("copied");
    require(copy->isOpen() == expected, "copy lost report mode");
  }
}

// GNU link wrapping injects one local allocation failure; every other allocation
// uses the real operator new. It is armed per thread: by the updater driver and
// by testLogExceptionLock (directly, or from the wrlock wrapper in write mode).
static thread_local bool reviewFailNextAllocation = false;
static thread_local std::size_t reviewFailAllocationSize = 0;
extern "C" void* __real__Znwm(std::size_t size);
extern "C" void* __wrap__Znwm(std::size_t size) {
  if (reviewFailNextAllocation && (!reviewFailAllocationSize || size == reviewFailAllocationSize)) {
    reviewFailNextAllocation = false;
    throw std::bad_alloc();
  }
  return __real__Znwm(size);
}

// Observe only the calling thread's actual handler lock; wrappers forward all
// operations. Failure injection is local to that thread and one allocation.
static thread_local bool reviewTrackLogLock = false, reviewFailOnWrite = false;
static thread_local pthread_rwlock_t* reviewLogMutex = nullptr;
static thread_local int reviewLogBalance = 0, reviewLogEventCount = 0;
static thread_local char reviewLogEvents[8];
// Events past the buffer are only counted; the check below rejects that overflow.
static void reviewLogEvent(char event) {
  if (reviewLogEventCount < static_cast<int>(sizeof(reviewLogEvents))) {
    reviewLogEvents[reviewLogEventCount] = event;
  }
  ++reviewLogEventCount;
}
extern "C" int __real_pthread_rwlock_rdlock(pthread_rwlock_t*);
extern "C" int __real_pthread_rwlock_wrlock(pthread_rwlock_t*);
extern "C" int __real_pthread_rwlock_unlock(pthread_rwlock_t*);
extern "C" int __wrap_pthread_rwlock_rdlock(pthread_rwlock_t* mutex) {
  const int result = __real_pthread_rwlock_rdlock(mutex);
  if (reviewTrackLogLock && result == 0) {
    reviewLogMutex = mutex; ++reviewLogBalance;
    reviewLogEvent('R');
  }
  return result;
}
extern "C" int __wrap_pthread_rwlock_wrlock(pthread_rwlock_t* mutex) {
  const int result = __real_pthread_rwlock_wrlock(mutex);
  if (reviewTrackLogLock && mutex == reviewLogMutex && result == 0) {
    ++reviewLogBalance; reviewLogEvent('W');
    if (reviewFailOnWrite) { reviewFailOnWrite = false; reviewFailNextAllocation = true; }
  }
  return result;
}
extern "C" int __wrap_pthread_rwlock_unlock(pthread_rwlock_t* mutex) {
  const int result = __real_pthread_rwlock_unlock(mutex);
  if (reviewTrackLogLock && mutex == reviewLogMutex && result == 0) {
    --reviewLogBalance; reviewLogEvent('U');
  }
  return result;
}
static void testLogExceptionLock(const std::string& filename, bool write) {
  HandlerFixture fixture(filename);
  fixture.handler->initialize();
  require(fixture.handler->getStatus() == facebook::fb303::ALIVE, "Log fixture configuration");
  std::vector<LogEntry> messages;
  if (write) messages.push_back(entry(std::string(128, 'x'), "unknown"));
  messages.push_back(entry("accepted", "payload"));
  reviewLogMutex = nullptr; reviewLogBalance = 0; reviewLogEventCount = 0;
  // Fail the explicit new LogEntry, before StoreQueue acquires its lock.
  // In write mode the earlier unknown category causes the original handoff;
  // its bad-category counter completes before this selected allocation.
  reviewFailAllocationSize = sizeof(LogEntry);
  reviewTrackLogLock = true; reviewFailOnWrite = write; reviewFailNextAllocation = !write;
  bool threw = false;
  try { fixture.handler->scribeHandler::Log(messages); }
  catch (const std::bad_alloc&) { threw = true; }
  reviewTrackLogLock = false; reviewFailOnWrite = false; reviewFailNextAllocation = false;
  reviewFailAllocationSize = 0;
  const int balance = reviewLogBalance;
  // Clean up the pre-fix witness in the same owning thread before reporting,
  // so the failed test never strands workers or blocks its teardown.
  if (balance == 1) __real_pthread_rwlock_unlock(reviewLogMutex);
  require(threw, "Log allocation exception was not exercised");
  require(balance == 0, "Log exception retained its handler lock");
  require(reviewLogEventCount <= static_cast<int>(sizeof(reviewLogEvents)) &&
              std::string(reviewLogEvents, reviewLogEventCount) == (write ? "RUWU" : "RU"),
          "Log read-release-write handoff changed");
  fixture.handler->reinitialize();  // Actual subsequent write lock must succeed.
  require(fixture.handler->getStatus() == facebook::fb303::ALIVE, "Log exception prevented reinitialize");
  messages = {entry("accepted", "payload")};
  require(fixture.handler->scribeHandler::Log(messages) == ResultCode::OK, "Log did not recover");
  require(fixture.handler->getCounter("accepted:received good") == 1, "recovered Log counter changed");
}

static void runUpdaterReviewDriver(const std::string& filename) {
  HandlerFixture fixture(filename);
  fixture.handler->initialize();
  require(fixture.handler->getStatus() == facebook::fb303::ALIVE, "updater driver config");
  unsigned long remotePort = 0;
  require(fixture.handler->getConfig().getUnsigned("remote_port", remotePort) &&
              remotePort > 0 && remotePort <= 65535, "updater driver loopback port");
  std::cout << "READY review-updater-driver" << std::endl;
  std::string command;
  while (std::getline(std::cin, command)) {
    if (command == "QUIT") return;
    require(command == "GET" || command == "FAIL", "unknown updater command");
    std::string host = "keep";
    uint32_t port = 19;
    const std::string category = command == "FAIL" ? "allocation" : "reviewmapping";
    try {
      if (command == "FAIL") reviewFailNextAllocation = true;
      const bool result = DynamicBucketUpdater::getHost(*fixture.handler, category,
          60, 42, host, port, "127.0.0.1", static_cast<uint32_t>(remotePort), 500, 500, 500);
      std::cout << "MAPPING " << result << " " << host << " " << port << std::endl;
    } catch (const std::bad_alloc&) {
      require(command == "FAIL" && !reviewFailNextAllocation, "allocation failure was not injected");
      std::cout << "ALLOCATION FAILED" << std::endl;
    } catch (const apache::thrift::TException&) {
      std::cout << "MAPPING EXCEPTION" << std::endl;
    }
  }
}

static void runConcurrentUpdaterReview(const std::string& filename) {
  HandlerFixture fixture(filename);
  fixture.handler->initialize();
  require(fixture.handler->getStatus() == facebook::fb303::ALIVE, "concurrent updater config");
  unsigned long remotePort = 0;
  require(fixture.handler->getConfig().getUnsigned("remote_port", remotePort) &&
              remotePort > 0 && remotePort <= 65535, "concurrent updater loopback port");
  std::atomic<unsigned> ready{0}, successes{0};
  std::atomic<bool> start{false};
  std::vector<std::thread> callers;
  std::cout << "READY review-updater-concurrent" << std::endl;
  for (unsigned i = 0; i < 16; ++i) {
    callers.emplace_back([&] {
      ++ready;
      while (!start.load()) std::this_thread::yield();
      std::string host = "keep";
      uint32_t port = 19;
      if (DynamicBucketUpdater::getHost(*fixture.handler, "reviewmapping", 60, 42,
          host, port, "127.0.0.1", static_cast<uint32_t>(remotePort), 500, 500, 500)
          && host == "resolved" && port == 1234) ++successes;
    });
  }
  while (ready.load() != 16) std::this_thread::yield();
  start = true;
  for (auto& caller : callers) caller.join();
  require(successes == 16, "concurrent updater changed mapping results");
  std::cout << "CONCURRENT 16 resolved 1234" << std::endl;
  std::string command;
  require(std::getline(std::cin, command) && command == "QUIT", "concurrent updater termination");
}

class ReviewNetworkStore : public NetworkStore {
 public:
  ReviewNetworkStore(ScribeContext& context, const std::string& category)
      : NetworkStore(context, nullptr, category, true) {}
  unsigned long defaultPort() const { return serviceListDefaultPort; }
  size_t serverCount() const { return servers.size(); }
  void useTestResolver() { configmod = &resolver; }
  void failResolver() {
    storeConf->setUnsigned("test_next_port", 0);
    storeConf->setUnsigned("test_copy_port", 0);
  }
 private:
  // Only the resolver result is scripted. Connection/pool open, send, close,
  // copy and periodicCheck below are the real production implementation.
  static bool getHost(ScribeContext&, const std::string& category, const StoreConf* config,
                      std::string& host, uint32_t& port) {
    require(config != nullptr, "copied dynamic store lost configuration");
    unsigned long value = 0;
    require(category == "first" || category == "second", "resolver category");
    config->getUnsigned(category == "first" ? "test_next_port" : "test_copy_port", value);
    if (!value) return false;
    require(value <= 65535, "invalid test resolver port");
    host = "127.0.0.1";
    port = value;
    return true;
  }
  static NetworkDynamicConfigMod resolver;
};

NetworkDynamicConfigMod ReviewNetworkStore::resolver = {"test-only", nullptr,
                                                       ReviewNetworkStore::getHost};

static void testStoreReviewDefaults(const std::string& filename) {
  HandlerFixture fixture(filename);
  // Deterministically expose a missing scalar initializer, including with
  // allocators/stack layouts that would otherwise happen to contain zero.
  alignas(ReviewNetworkStore) unsigned char storage[sizeof(ReviewNetworkStore)];
  memset(storage, 0xa5, sizeof(storage));
  auto* store = new (storage) ReviewNetworkStore(*fixture.handler, "first");
  const auto port = store->defaultPort();
  store->~ReviewNetworkStore();
  require(port == 0, "unconfigured service-list port must be zero");
}

static void testStoreReviewBucket(const std::string& filename) {
  HandlerFixture fixture(filename);
  pStoreConf config(new StoreConf);
  config->parseConfig(filename);
  BucketStore bucket(*fixture.handler, nullptr, "model", false);
  bucket.configure(config, pStoreConf());
  std::string expected;
  config->getString("test_error", expected);
  if (!expected.empty()) {
    require(!bucket.open(), "invalid bucket configuration opened");
    require(bucket.getStatus() == expected, "bucket configuration error changed");
    return;
  }
  require(bucket.open(), "valid bucket configuration failed");
  // Model is already open; its clone uses legacy constructor policy and new files.
  auto copy = bucket.copy("copied");
  require(!copy->isOpen(), "bucket copy inherited live state");
  require(copy->open(), "copied bucket open failed");
  auto messages = fileMessages({entry("category", std::string("15|A\0B\n\xff", 8)),
                                entry("category", "no-key")});
  require(copy->handleMessages(messages), "copied bucket write failed");
  copy->flush();
  copy->close();
  bucket.close();
}

class ReviewRangeBucket : public BucketStore {
 public:
  explicit ReviewRangeBucket(ScribeContext& context) : BucketStore(context, nullptr, "model", false) {}
  using BucketStore::bucketize;
};

static void testStoreReviewBucketRange(const std::string& filename) {
  HandlerFixture fixture(filename);
  pStoreConf config(new StoreConf);
  config->parseConfig(filename);
  ReviewRangeBucket bucket(*fixture.handler);
  bucket.configure(config, pStoreConf());
  // num_buckets=1, bucket_range=2^53+1: key 2^53 % range is 2^53, and both round to the
  // same double, so (key_mod / range) * num_buckets + 1 is 2, one past the last bucket.
  require(bucket.bucketize("9007199254740992|edge") == 1, "key_range bucket not clamped to num_buckets");
  require(bucket.bucketize("0|low") == 1, "key_range low key bucket changed");
  require(bucket.open(), "key_range bucket open failed");
  auto messages = fileMessages({entry("model", "9007199254740992|edge"), entry("model", "0|low")});
  require(bucket.handleMessages(messages), "key_range bucket write failed");
  bucket.flush();
  bucket.close();
}

// StoreQueue::store is private. An explicit template instantiation may name a private
// member, so the copied queue's store is read without changing production access.
struct ReviewQueueStore {
  typedef std::shared_ptr<Store> StoreQueue::*type;
  friend type reviewQueueStore(ReviewQueueStore);
};
template <typename Tag, typename Tag::type Member> struct ReviewExpose {
  friend typename Tag::type reviewQueueStore(Tag) { return Member; }
};
template struct ReviewExpose<ReviewQueueStore, &StoreQueue::store>;

// Protected members of an existing BufferStore, through member pointers named in a derived class.
struct ReviewBufferAccess : BufferStore {
  static auto queue() { return &ReviewBufferAccess::storeQueue; }
  static auto primary() { return &ReviewBufferAccess::primaryStore; }
  static auto secondary() { return &ReviewBufferAccess::secondaryStore; }
  static auto streaming() { return &ReviewBufferAccess::flushStreaming; }
  static auto ratio() { return &ReviewBufferAccess::maxByPassRatio; }
  static void sendingBuffer(BufferStore& buffer) {
    (buffer.*(&ReviewBufferAccess::changeState))(SENDING_BUFFER);
  }
};

static bool reviewFileExists(const std::string& path) {
  return static_cast<bool>(std::ifstream(path.c_str()));
}

static void testStoreReviewQueueRebind(const std::string& filename, const std::string& directory) {
  HandlerFixture fixture(filename);
  fixture.handler->initialize();
  require(fixture.handler->getMaxQueueSize() == 4, "queue rebind max_queue_size");
  // The worker of the copied queue never drains or checks its store during the test:
  // target_write_size/max_write_interval are copied from the model and the queue is never opened.
  save(directory + "/model.conf",
       "target_write_size=1000000\nmax_write_interval=3600\n"
       "<primary>\ntype=null\n</primary>\n<secondary>\ntype=file\nfs_type=std\n"
       "file_path=" + directory + "/spool\nbase_filename=model\nrotate_period=never\n"
       "create_symlink=no\nadd_newlines=0\n</secondary>\n");
  pStoreConf modelConf(new StoreConf);
  modelConf->parseConfig(directory + "/model.conf");
  std::shared_ptr<StoreQueue> model(new StoreQueue(*fixture.handler, "buffer", "model", 1, true));
  model->configureAndOpen(modelConf);
  std::shared_ptr<StoreQueue> copy(new StoreQueue(model, "copied"));
  std::shared_ptr<Store> store = (*copy).*reviewQueueStore(ReviewQueueStore());
  BufferStore& buffer = dynamic_cast<BufferStore&>(*store);
  require(buffer.*ReviewBufferAccess::queue() == copy.get() &&
              (*(buffer.*ReviewBufferAccess::primary())).*ReviewBufferAccess::queue() == copy.get() &&
              (*(buffer.*ReviewBufferAccess::secondary())).*ReviewBufferAccess::queue() == copy.get(),
          "copied store tree still points at the model queue");
  model.reset();  // nothing in the copied tree may use the model queue any more
  copy->addMessage(logentry_ptr_t(new LogEntry(entry("copied", "queued"))));
  require(copy->getSize() == 6, "copied queue size");
  // copy() does not carry flushStreaming; set it so periodicCheck reads storeQueue->getSize().
  buffer.*ReviewBufferAccess::streaming() = true;
  buffer.*ReviewBufferAccess::ratio() = 1.0;  // 6 queued bytes >= 1.0 * 4: yield, keep the spool
  ReviewBufferAccess::sendingBuffer(buffer);
  const std::string spool = directory + "/spool/copied/copied_00000";
  require(reviewFileExists(spool), "copied secondary spool fixture missing");
  buffer.periodicCheck();
  require(reviewFileExists(spool), "replay ignored the copied queue size");
  buffer.*ReviewBufferAccess::ratio() = 2.0;  // 6 < 2.0 * 4: replay the spool now
  buffer.periodicCheck();
  require(!reviewFileExists(spool), "spool was not replayed below the bypass size");
  require(fixture.handler->getCounter("copied:ignored") == 1, "replayed spool entry count");
  copy->stop();
  require(fixture.handler->getCounter("copied:ignored") == 2, "queued message after replay");
}

static void testCategoryPathComponents(const std::string& filename) {
  HandlerFixture fixture(filename);
  fixture.handler->initialize();
  require(fixture.handler->getStatus() == facebook::fb303::ALIVE, "category path config");
  require(fixture.handler->scribeHandler::Log({entry("../x", "up"), entry("a/../b", "middle"),
                                               entry("..", "alone"), entry("a/b", "nested"),
                                               entry("..x", "dots")}) == ResultCode::OK,
          "category path Log result");
  fixture.handler->stopForTest();
  for (const char* category : {"../x", "a/../b", ".."}) {
    require(fixture.handler->getCounter(std::string(category) + ":received bad") == 1 &&
                fixture.handler->getCounter(std::string(category) + ":received good") == 0,
            "parent-directory category was not rejected");
  }
  for (const char* category : {"a/b", "..x"}) {
    require(fixture.handler->getCounter(std::string(category) + ":received good") == 1,
            "ordinary dynamic category was rejected");
  }
  require(fixture.handler->getCounter("scribe_overall:received bad") == 3, "rejected category total");
}

// One-shot, per-thread pthread_create failure (-Wl,--wrap=pthread_create); all other
// thread creation is forwarded unchanged.
static thread_local bool reviewFailThreadCreate = false;
extern "C" int __real_pthread_create(pthread_t*, const pthread_attr_t*, void* (*)(void*), void*);
extern "C" int __wrap_pthread_create(pthread_t* thread, const pthread_attr_t* attributes,
                                     void* (*start)(void*), void* argument) {
  if (reviewFailThreadCreate) {
    reviewFailThreadCreate = false;
    return EAGAIN;
  }
  return __real_pthread_create(thread, attributes, start, argument);
}

static void testCategoryQueueFailure(const std::string& filename) {
  HandlerFixture fixture(filename);
  fixture.handler->initialize();
  require(fixture.handler->getStatus() == facebook::fb303::ALIVE, "queue failure config");
  reviewFailThreadCreate = true;
  ResultCode result = ResultCode::TRY_LATER;
  try {
    result = fixture.handler->scribeHandler::Log({entry("dynamic", "first")});
  } catch (const std::exception&) {
    reviewFailThreadCreate = false;
    throw std::runtime_error("dynamic category queue failure escaped Log");
  }
  require(!reviewFailThreadCreate, "dynamic category queue worker creation was not reached");
  require(result == ResultCode::OK, "failed dynamic category changed the Log result");
  require(fixture.handler->getCounter("dynamic:received bad") == 1 &&
              fixture.handler->getCounter("dynamic:received good") == 0,
          "failed dynamic category counters");
  // The failed category was not registered; the next message creates it normally.
  require(fixture.handler->scribeHandler::Log({entry("dynamic", "second")}) == ResultCode::OK &&
              fixture.handler->getCounter("dynamic:received good") == 1,
          "dynamic category not created after the failure");
}

class ReviewBufferChildren : public BufferStore {
 public:
  explicit ReviewBufferChildren(ScribeContext& context)
      : BufferStore(context, nullptr, "model", false) {}
  const std::string& primaryType() const {
    require(primaryStore != nullptr, "buffer primary fallback is absent");
    return primaryStore->getType();
  }
  const std::string& secondaryType() const {
    require(secondaryStore != nullptr, "buffer secondary fallback is absent");
    return secondaryStore->getType();
  }
};

static void testStoreReviewInvalidChild(const std::string& filename) {
  HandlerFixture fixture(filename);
  pStoreConf config(new StoreConf);
  config->parseConfig(filename);
  std::string kind;
  require(config->getString("test_kind", kind), "missing invalid-child case");
  if (kind == "buffer-primary" || kind == "buffer-secondary") {
    ReviewBufferChildren buffer(*fixture.handler);
    buffer.configure(config, pStoreConf());
    require(buffer.primaryType() == (kind == "buffer-primary" ? "file" : "null"),
            "buffer primary fallback changed");
    require(buffer.secondaryType() == (kind == "buffer-secondary" ? "file" : "null"),
            "buffer secondary fallback changed");
  } else if (kind == "multi") {
    MultiStore multi(*fixture.handler, nullptr, "model", false);
    multi.configure(config, pStoreConf());
    require(!multi.getStatus().empty(), "invalid multi child lacks status");
    multi.close();
  } else {
    require(kind == "category" || kind == "category-missing", "unknown invalid-child case");
    CategoryStore category(*fixture.handler, nullptr, "model", false);
    category.configure(config, pStoreConf());
    require(!category.getStatus().empty(), "invalid category model lacks status");
    auto messages = fileMessages({entry("category", "retain-this-message")});
    require(!category.handleMessages(messages), "invalid category accepted a message");
    require(messages->size() == 1 && messages->front()->message == "retain-this-message",
            "failed category changed retry input");
    auto copy = category.copy("copied");
    require(copy != nullptr, "invalid category copy is absent");
    require(!copy->handleMessages(messages), "invalid category copy accepted a message");
    require(messages->size() == 1 && messages->front()->message == "retain-this-message",
            "failed category copy changed retry input");
    copy->close();
    category.close();
  }
}

static void runStoreReviewDriver(const std::string& filename) {
  HandlerFixture fixture(filename);
  pStoreConf config(new StoreConf);
  config->parseConfig(filename);
  requireRelayDestination(config);
  unsigned long firstPort = 0, otherPort = 0;
  config->getUnsigned("remote_port", firstPort);
  require(config->getUnsigned("test_other_port", otherPort) && otherPort > 0 && otherPort <= 65535,
          "review driver requires assigned other loopback port");
  std::string kind;
  require(config->getString("test_kind", kind), "review driver requires case");
  std::shared_ptr<ReviewNetworkStore> first(new ReviewNetworkStore(*fixture.handler, "first"));
  std::shared_ptr<Store> stores[] = {first, std::shared_ptr<Store>(
      new ReviewNetworkStore(*fixture.handler, "second"))};
  for (unsigned i = 0; i < 2; ++i) {
    pStoreConf policy(new StoreConf(*config));
    if (kind == "list" || kind == "default-list" || kind == "same-list") {
      const auto port = i && kind != "same-list" ? otherPort : firstPort;
      policy->setString("service_list", kind == "default-list" ? "127.0.0.1" :
                         "127.0.0.1:" + std::to_string(port));
      if (kind == "default-list") policy->setUnsigned("list_default_port", port);
    } else {
      require(kind == "dynamic" || kind == "dynamic-owned" || kind == "copy-error",
              "unknown review driver case");
      if (i && kind == "dynamic-owned") policy->setUnsigned("remote_port", otherPort);
    }
    stores[i]->configure(policy, pStoreConf());
  }
  if (kind == "dynamic" || kind == "dynamic-owned") first->useTestResolver();
  std::cout << "READY review-store-driver" << std::endl;
  std::string line;
  while (std::getline(std::cin, line)) {
    require(line.size() <= 64, "oversized review driver command");
    if (line == "QUIT") {
      for (auto& store : stores) store->close();
      return;
    }
    std::istringstream command(line);
    std::string operation, batch, extra;
    unsigned index = 2;
    require(static_cast<bool>(command >> operation >> index) && index < 2,
            "invalid review driver command");
    bool result = true;
    size_t size = 0;
    if (operation == "SEND") {
      require(static_cast<bool>(command >> batch), "missing review batch");
      const auto entries = relayEntries(batch);
      auto messages = fileMessages(entries);
      result = stores[index]->handleMessages(messages);
      require(messages->size() == entries.size(), "store changed batch size");
      for (size_t n = 0; n < entries.size(); ++n)
        require(*messages->at(n) == entries[n], "store changed input bytes");
      size = messages->size();
    } else if (operation == "COPY") {
      require(index == 1, "copy must replace second store");
      stores[1]->close();
      stores[1] = first->copy("second");
      require(!stores[1]->isOpen(), "network copy inherited live state");
    } else if (operation == "CHECK") {
      stores[index]->periodicCheck();
    } else if (operation == "FAILRESOLVE") {
      require(index == 0, "scripted resolver belongs to first store");
      first->failResolver();
    } else if (operation == "OPEN") {
      result = stores[index]->open();
      if (kind == "list" || kind == "default-list" || kind == "same-list")
        require(first->serverCount() <= 1, "reopen accumulated service-list servers");
      if (kind == "copy-error")
        require(stores[index]->getStatus() == (index == 0 ? "" : "Failed to connect"),
                "legacy network copy error policy changed");
    } else if (operation == "CLOSE") {
      stores[index]->close();
    } else throw std::runtime_error("unknown review driver operation");
    require(!(command >> extra), "extra review driver command fields");
    std::cout << "STATE " << operation << " " << index << " " << result << " "
              << stores[0]->isOpen() << " " << stores[1]->isOpen() << " "
              << fixture.handler->getCounter("scribe_overall:sent") << " " << size << std::endl;
  }
  throw std::runtime_error("review driver pipe closed before QUIT");
}

#endif // SCRIBE_TEST_STORE_REVIEW_CONTRACTS_H
