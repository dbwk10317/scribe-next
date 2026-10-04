// Test-only direct NetworkStore/ConnPool/scribeConn contract driver.
// Licensed under the Apache License, Version 2.0; see LICENSE.
// No production entry point, retry scheduler, or source semantics are changed.
#ifndef SCRIBE_TEST_RELAY_CONTRACTS_H
#define SCRIBE_TEST_RELAY_CONTRACTS_H

static std::vector<LogEntry> relayEntries(const std::string& name) {
  if (name == "binary") {
    return {entry(std::string("cat\0\xff", 5), std::string("A\0B\n\xff\xc3\xa9", 7)),
            entry("", ""), entry("tail", "ends\n")};
  }
  if (name == "abc") {
    return {entry("relay", "A"), entry("relay", "B"), entry("relay", "C")};
  }
  if (name == "4096") {
    // Category bytes do not contribute to the production dummy threshold.
    return {entry(std::string(6000, 'c'), std::string(4096, 'x'))};
  }
  if (name == "4097") {
    return {entry("first", std::string(2048, 'x')),
            entry("second", std::string(2049, 'y'))};
  }
  require(name == "empty", "unknown relay batch");
  return {};
}

static void requireRelayDestination(const pStoreConf& configuration) {
  std::string value;
  require(configuration->getString("remote_host", value) && value == "127.0.0.1",
          "relay fixture requires remote_host=127.0.0.1");
  unsigned long port = 0;
  require(configuration->getUnsigned("remote_port", port) && port > 0 && port <= 65535,
          "relay fixture requires an assigned loopback port");
  long timeout = 0;
  require(configuration->getInt("timeout", timeout) && timeout == 500,
          "relay fixture requires a 500ms socket timeout");
  for (const auto* key : {"smc_service", "service_list", "dynamic_config_type"}) {
    require(!configuration->getString(key, value),
            "relay fixture prohibits service/list/dynamic destinations");
  }
}

static void runRelayDriver(const std::string& filename) {
  // Typed StoreConf lookups may consult g_Handler even before initialize().
  HandlerFixture fixture(filename);
  pStoreConf configuration(new StoreConf);
  configuration->parseConfig(filename);
  requireRelayDestination(configuration);
  // This handler is only a real counter owner; initialize/worker/server are not
  // called here. Worker integration is separately exercised over loopback RPC.
  NetworkStore first(nullptr, "first", true), second(nullptr, "second", true);
  NetworkStore* stores[] = {&first, &second};
  for (auto* store : stores) store->configure(configuration, pStoreConf());
  std::cout << "READY relay-driver" << std::endl;

  // The Python owner supplies a small bounded script and owns process deadlines.
  // Each SEND is exactly one direct call; retries are never worker-timing based.
  std::string line;
  while (std::getline(std::cin, line)) {
    require(line.size() <= 64, "oversized relay driver command");
    if (line == "QUIT") {
      for (auto* store : stores) store->close();
      return;
    }
    std::istringstream command(line);
    std::string operation, batch, extra;
    unsigned index = 2;
    require(static_cast<bool>(command >> operation >> index) && index < 2,
            "invalid relay driver command");
    bool result = true;
    size_t size = 0;
    if (operation == "SEND") {
      require(static_cast<bool>(command >> batch), "missing relay batch");
      const auto entries = relayEntries(batch);
      auto messages = fileMessages(entries);
      result = stores[index]->handleMessages(messages);
      require(messages->size() == entries.size(), "relay changed batch length");
      for (size_t n = 0; n < entries.size(); ++n) {
        require(*messages->at(n) == entries[n], "relay changed input bytes");
      }
      size = messages->size();
    } else if (operation == "OPEN") {
      result = stores[index]->open();
    } else if (operation == "CLOSE") {
      stores[index]->close();
    } else {
      throw std::runtime_error("unknown relay driver operation");
    }
    require(!(command >> extra), "extra relay driver command fields");
    std::cout << "STATE " << operation << " " << index << " " << result << " "
              << first.isOpen() << " " << second.isOpen() << " "
              << fixture.handler->getCounter("scribe_overall:sent") << " "
              << size << std::endl;
    require(std::cout.good(), "could not publish relay result");
  }
  throw std::runtime_error("relay driver command pipe closed before QUIT");
}

static void runRelayLoopbackServer(const std::string& filename,
                                   const std::string& directory) {
  {
    HandlerFixture validation(filename);
    StoreConf configuration;
    configuration.parseConfig(filename);
    std::vector<pStoreConf> stores;
    configuration.getAllStores(stores);
    require(stores.size() == 1, "relay worker fixture requires exactly one store");
    std::string type;
    require(stores[0]->getString("type", type), "relay worker fixture requires store type");
    if (type == "network") {
      // initialize() later installs the root config in g_Handler. Do not let a
      // global inherited service/list/dynamic key bypass this pre-open guard.
      for (const auto* key : {"smc_service", "service_list", "dynamic_config_type"}) {
        std::string value;
        require(!configuration.getString(std::string("network::") + key, value),
                "relay fixture prohibits inherited service/list/dynamic destinations");
      }
      requireRelayDestination(stores[0]);
    }
    else require(type == "file", "relay worker fixture requires network or file store");
  }
  runLoopbackServer(filename, directory);
}

#endif // SCRIBE_TEST_RELAY_CONTRACTS_H
