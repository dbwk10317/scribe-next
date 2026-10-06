// Regression contracts for the previously excluded store defects.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_TEST_STORE_REVIEW_CONTRACTS_H
#define SCRIBE_TEST_STORE_REVIEW_CONTRACTS_H

extern ConnPool g_connPool;

class ReviewNetworkStore : public NetworkStore {
 public:
  explicit ReviewNetworkStore(const std::string& category)
      : NetworkStore(nullptr, category, true) {}
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
  static bool getHost(const std::string& category, const StoreConf* config,
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
  unsigned firstListOpens = 0;
  bool retainedSourceReference = false;
  std::cout << "READY review-store-driver" << std::endl;
  std::string line;
  while (std::getline(std::cin, line)) {
    require(line.size() <= 64, "oversized review driver command");
    if (line == "QUIT") {
      for (auto& store : stores) store->close();
      // Test cleanup only: legacy endpoint-before-close leaves the old pool
      // reference alive. Release it after all observable results are checked.
      if (retainedSourceReference) g_connPool.close("127.0.0.1", firstPort);
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
      const bool wasOpen = stores[index]->isOpen();
      stores[index]->periodicCheck();
      std::string pooled;
      config->getString("use_conn_pool", pooled);
      if (index == 0 && wasOpen && !stores[index]->isOpen() && pooled == "yes")
        retainedSourceReference = true;
    } else if (operation == "FAILRESOLVE") {
      require(index == 0, "scripted resolver belongs to first store");
      first->failResolver();
    } else if (operation == "OPEN") {
      result = stores[index]->open();
      if (index == 0 && (kind == "list" || kind == "default-list" || kind == "same-list"))
        require(first->serverCount() == ++firstListOpens, "legacy service-list accumulation changed");
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
