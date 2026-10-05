// Regression contracts for the previously excluded store defects.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_TEST_STORE_REVIEW_CONTRACTS_H
#define SCRIBE_TEST_STORE_REVIEW_CONTRACTS_H

#include <condition_variable>
#include <future>

// Block the resolver itself, so progress proves lock independence without a
// latency benchmark or a production daemon. The normal routing tests below
// separately check resolved destinations and failed-refresh static fallback.
struct BlockingCopyResolver {
  static std::mutex mutex;
  static std::condition_variable changed;
  static bool released;
  static unsigned calls;
  static bool valid(const std::string&, const StoreConf*) { return true; }
  static bool resolve(const std::string& category, const StoreConf*,
                      std::string&, uint32_t&) {
    if (category != "new-category") return false;
    std::unique_lock<std::mutex> lock(mutex);
    ++calls;
    changed.notify_all();
    // The fixture's process alarm bounds failures; only explicit release can
    // satisfy the blocker, even if a test thread is heavily descheduled.
    changed.wait(lock, [] { return released; });
    return false;
  }
};
std::mutex BlockingCopyResolver::mutex;
std::condition_variable BlockingCopyResolver::changed;
bool BlockingCopyResolver::released = false;
unsigned BlockingCopyResolver::calls = 0;

static void testDynamicCopyLocking(const std::string& filename) {
  auto* module = getNetworkDynamicConfigMod("thrift_bucket");
  require(module != nullptr, "missing dynamic module");
  const auto original = *module;
  struct Restore {
    NetworkDynamicConfigMod* module;
    NetworkDynamicConfigMod original;
    ~Restore() { *module = original; }
  } restore{module, original};
  module->isConfigValidFunc = BlockingCopyResolver::valid;
  module->getHostFunc = BlockingCopyResolver::resolve;
  HandlerFixture fixture(filename);
  fixture.handler->initialize();
  require(fixture.handler->getStatus() == facebook::fb303::ALIVE,
          "locking config not alive");
  auto created = std::async(std::launch::async, [&] {
    return fixture.handler->scribeHandler::Log({entry("new-category", "payload")});
  });
  bool entered;
  {
    std::unique_lock<std::mutex> lock(BlockingCopyResolver::mutex);
    entered = BlockingCopyResolver::changed.wait_for(lock, std::chrono::seconds(2),
        [] { return BlockingCopyResolver::calls != 0; });
  }
  auto existing = std::async(std::launch::async, [&] {
    return fixture.handler->scribeHandler::Log({entry("accepted", "unrelated")});
  });
  const bool createReady = created.wait_for(std::chrono::milliseconds(500)) ==
      std::future_status::ready;
  const bool existingReady = existing.wait_for(std::chrono::milliseconds(500)) ==
      std::future_status::ready;
  std::cout << "LOCKING resolver_entered=" << entered
            << " new_log_ready=" << createReady
            << " existing_log_ready=" << existingReady << std::endl;
  {
    std::lock_guard<std::mutex> lock(BlockingCopyResolver::mutex);
    BlockingCopyResolver::released = true;
  }
  BlockingCopyResolver::changed.notify_all();
  const auto createResult = created.get();
  const auto existingResult = existing.get();
  require(entered, "copied store never resolved in worker");
  require(createReady, "new category Log waited for blocked resolver");
  require(existingReady, "unrelated category Log blocked behind resolver");
  require(createResult == scribe::thrift::OK && existingResult == scribe::thrift::OK,
          "locking regression changed queue acceptance");
}

class ReviewNetworkStore : public NetworkStore {
 public:
  explicit ReviewNetworkStore(const std::string& category)
      : NetworkStore(nullptr, category, true) {}
  unsigned long defaultPort() const { return serviceListDefaultPort; }
  size_t serverCount() const { return servers.size(); }
  void useTestResolver() { configmod = &resolver; }
  static unsigned resolverCalls;
  void failResolver() {
    storeConf->setUnsigned("test_next_port", 0);
    storeConf->setUnsigned("test_copy_port", 0);
  }
 private:
  // Only the resolver result is scripted. Connection/pool open, send, close,
  // copy and periodicCheck below are the real production implementation.
  static bool getHost(const std::string& category, const StoreConf* config,
                      std::string& host, uint32_t& port) {
    ++resolverCalls;
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
unsigned ReviewNetworkStore::resolverCalls = 0;

static void testDynamicCopyInitialResolution(const std::string& filename) {
  HandlerFixture fixture(filename);
  pStoreConf config(new StoreConf);
  config->setString("remote_host", "127.0.0.1");
  config->setUnsigned("remote_port", 0); // Failed fallback never opens a socket.
  ReviewNetworkStore source("first");
  source.configure(config, pStoreConf());
  source.useTestResolver();
  for (bool checkBeforeOpen : {false, true}) {
    ReviewNetworkStore::resolverCalls = 0;
    auto copy = source.copy("second");
    require(ReviewNetworkStore::resolverCalls == 0, "copy called resolver inline");
    if (checkBeforeOpen) copy->periodicCheck();
    require(!copy->open(), "invalid fallback unexpectedly opened");
    require(ReviewNetworkStore::resolverCalls == 1,
            "initial resolution was omitted or repeated after periodic check");
    require(!copy->open(), "invalid fallback unexpectedly reopened");
    require(ReviewNetworkStore::resolverCalls == 1,
            "failed initial resolution repeated on reopen");
    copy->periodicCheck();
    require(ReviewNetworkStore::resolverCalls == 2, "ongoing refresh was lost");
  }
}

static void testStoreReviewDefaults(const std::string& filename) {
  HandlerFixture fixture(filename);
  // Deterministically expose a missing scalar initializer, including with
  // allocators/stack layouts that would otherwise happen to contain zero.
  alignas(ReviewNetworkStore) unsigned char storage[sizeof(ReviewNetworkStore)];
  memset(storage, 0xa5, sizeof(storage));
  auto* store = new (storage) ReviewNetworkStore("first");
  const auto port = store->defaultPort();
  store->~ReviewNetworkStore();
  require(port == 0, "unconfigured service-list port must be zero");
}

static void testStoreReviewBucket(const std::string& filename) {
  HandlerFixture fixture(filename);
  pStoreConf config(new StoreConf);
  config->parseConfig(filename);
  BucketStore bucket(nullptr, "model", false);
  bucket.configure(config, pStoreConf());
  std::string expected;
  config->getString("test_error", expected);
  if (!expected.empty()) {
    require(!bucket.open(), "invalid bucket configuration opened");
    require(bucket.getStatus() == expected, "bucket configuration error changed");
    return;
  }
  require(bucket.open(), "valid bucket configuration failed");
  // Model is already open; its clone must retain policy and use new files.
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
  boost::shared_ptr<ReviewNetworkStore> first(new ReviewNetworkStore("first"));
  boost::shared_ptr<Store> stores[] = {first, boost::shared_ptr<Store>(new ReviewNetworkStore("second"))};
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
        require(stores[index]->getStatus().empty(), "copy lost ignore_network_error");
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
