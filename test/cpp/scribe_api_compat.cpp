// Socket-free contract fixture for actual Scribe config, handler, and RPC APIs.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "common.h"
#include "scribe_server.h"

using apache::thrift::protocol::TBinaryProtocol;
using apache::thrift::protocol::TProtocol;
using apache::thrift::transport::TFramedTransport;
using apache::thrift::transport::TMemoryBuffer;
using scribe::thrift::LogEntry;
using scribe::thrift::ResultCode;
using scribe::thrift::scribeClient;
using scribe::thrift::scribeProcessor;

static void require(bool value, const char* message) {
  if (!value) {
    throw std::runtime_error(message);
  }
}

class TestHandler : public scribeHandler {
 public:
  explicit TestHandler(const std::string& config, unsigned long port = 0)
      : scribeHandler(port, config) {}

  ResultCode Log(const std::vector<LogEntry>& messages) override {
    received = messages;
    return scribeHandler::Log(messages);
  }

  // There is only one caller of the handler in this fixture. This joins actual
  // store workers, but never calls shutdown(), stopServer(), exit(), or serve().
  void stopForTest() { stopStores(); }

  std::vector<LogEntry> received;
};

struct HandlerFixture {
  explicit HandlerFixture(const std::string& config, unsigned long port = 0)
      : handler(std::make_shared<TestHandler>(config, port)) {
    // Actual stores use the existing global handler for their counters.
    g_Handler = handler;
  }
  ~HandlerFixture() {
    handler->stopForTest();
    g_Handler.reset();
  }
  std::shared_ptr<TestHandler> handler;
};

static std::shared_ptr<TProtocol> protocol(
    const std::shared_ptr<TMemoryBuffer>& memory) {
  auto framed = std::make_shared<TFramedTransport>(memory);
  // Match the explicit false/false binary settings in the server, relay, and
  // mapping paths. This fixture dispatches in memory; it does not run those sockets.
  return std::make_shared<TBinaryProtocol>(framed, 0, 0, false, false);
}

struct MemoryRpc {
  explicit MemoryRpc(const std::shared_ptr<TestHandler>& handler)
      : request(std::make_shared<TMemoryBuffer>()),
        response(std::make_shared<TMemoryBuffer>()),
        client(protocol(response), protocol(request)), processor(handler) {}

  void process() {
    require(processor.process(protocol(request), protocol(response), nullptr),
            "processor did not handle the memory request");
  }

  std::shared_ptr<TMemoryBuffer> request;
  std::shared_ptr<TMemoryBuffer> response;
  scribeClient client;
  scribeProcessor processor;
};

static LogEntry entry(const std::string& category, const std::string& message) {
  LogEntry result;
  result.category = category;
  result.message = message;
  return result;
}

static void save(const std::string& path, const std::string& bytes) {
  std::ofstream output(path.c_str(), std::ios::binary);
  output.write(bytes.data(), bytes.size());
  output.close();
  require(!output.fail(), "could not write temporary fixture file");
}

static void testWire(const std::string& config, const std::string& directory) {
  HandlerFixture fixture(config);
  auto handler = fixture.handler;
  handler->initialize();
  require(handler->getStatus() == facebook::fb303::ALIVE, "null config not alive");
  const std::vector<LogEntry> messages = {
    entry("accepted", std::string("A\0B\n\xff\xc3\xa9", 7)),
    entry(std::string("unknown\0\xff", 9), std::string("\0\n", 2)),
    entry("", "blank-category-payload")
  };
  MemoryRpc rpc(handler);
  rpc.client.send_Log(messages);
  save(directory + "/request.bin", rpc.request->getBufferAsString());
  rpc.process();
  save(directory + "/response.bin", rpc.response->getBufferAsString());
  require(rpc.client.recv_Log() == scribe::thrift::OK, "Log ACK changed");
  require(handler->received == messages, "processor changed category/message bytes");
  require(handler->getCounter("accepted:received good") == 1, "accepted counter");
  require(handler->getCounter(std::string("unknown\0\xff", 9) + ":received bad") == 1,
          "unknown binary category counter");
  require(handler->getCounter("scribe_overall:received blank category") == 1,
          "blank category counter");
  // OK was already received above. Only now wait for the null-store worker.
  handler->stopForTest();
  require(handler->getCounter("accepted:ignored") == 1, "null-store discard counter");
}

static void testHandler(const std::string& config) {
  HandlerFixture fixture(config);
  auto handler = fixture.handler;
  require(handler->getStatus() == facebook::fb303::STARTING, "initial status");
  std::string text;
  handler->getStatusDetails(text);
  require(text == "initial state", "initial status details");
  handler->initialize();
  {
    MemoryRpc rpc(handler);
    rpc.client.send_getName();
    rpc.process();
    rpc.client.recv_getName(text);
    require(text == "Scribe", "inherited fb303 getName");
  }
  {
    MemoryRpc rpc(handler);
    rpc.client.send_getVersion();
    rpc.process();
    rpc.client.recv_getVersion(text);
    require(text == "2.2", "handler getVersion");
  }
  {
    MemoryRpc rpc(handler);
    rpc.client.send_getStatus();
    rpc.process();
    require(rpc.client.recv_getStatus() == facebook::fb303::ALIVE, "RPC status");
  }
  {
    MemoryRpc rpc(handler);
    rpc.client.send_getStatusDetails();
    rpc.process();
    rpc.client.recv_getStatusDetails(text);
    require(text.empty(), "initialized status details");
  }
  {
    MemoryRpc rpc(handler);
    rpc.client.send_Log({});
    rpc.process();
    require(rpc.client.recv_Log() == scribe::thrift::OK, "empty batch ACK");
  }
  const std::vector<LogEntry> messages = {
    entry("accepted", "one"), entry("accepted", "two"),
    entry("unknown", "discard"), entry("", "discard")
  };
  {
    MemoryRpc rpc(handler);
    rpc.client.send_Log(messages);
    rpc.process();
    require(rpc.client.recv_Log() == scribe::thrift::OK, "mixed batch ACK");
  }
  {
    MemoryRpc rpc(handler);
    rpc.client.send_getCounter("accepted:received good");
    rpc.process();
    require(rpc.client.recv_getCounter() == 2, "inherited getCounter");
  }
  {
    MemoryRpc rpc(handler);
    rpc.client.send_getCounters();
    rpc.process();
    std::map<std::string, int64_t> counters;
    rpc.client.recv_getCounters(counters);
    require(counters.at("scribe_overall:received good") == 2, "overall good counter");
    require(counters.at("unknown:received bad") == 1, "unknown counter");
    require(counters.at("scribe_overall:received bad") == 1, "overall bad counter");
    require(counters.at("scribe_overall:received blank category") == 1, "blank counter");
  }
  {
    MemoryRpc rpc(handler);
    rpc.client.send_reinitialize();
    rpc.process();
    require(rpc.response->available_read() == 0, "oneway reinitialize wrote a reply");
  }
  require(handler->getStatus() == facebook::fb303::ALIVE, "reinitialize status");
  require(handler->getCounter("accepted:ignored") == 2, "reinitialize did not drain workers");
  require(handler->Log({entry("accepted", "after reinitialize")}) == scribe::thrift::OK,
          "reinitialized worker did not accept a message");
  handler->stopForTest();
  require(handler->getStatus() == facebook::fb303::STOPPING, "stopStores status");
  require(handler->getCounter("accepted:ignored") == 3, "stopStores did not drain workers");
  require(handler->Log({entry("accepted", "after stop")}) == scribe::thrift::TRY_LATER,
          "STOPPING must reject Log");
  require(handler->getCounter("accepted:received good") == 3, "rejected message counted good");
}

// These are deliberately permissive legacy contracts, not a strict config
// validator. Expected values are literal observations of the pinned parser.
static void requireString(const StoreConf& conf, const std::string& key,
                          const std::string& expected) {
  std::string actual("untouched");
  require(conf.getString(key, actual), ("missing config key: " + key).c_str());
  require(actual == expected, ("unexpected config value: " + key).c_str());
}

static pStoreConf requireStore(StoreConf& conf, const std::string& name) {
  pStoreConf result;
  require(conf.getStore(name, result), ("missing config store: " + name).c_str());
  return result;
}

static void testConfigValues(const std::string& filename) {
  StoreConf conf;
  conf.parseConfig(filename);
  requireString(conf, "text", "alpha=beta");
  requireString(conf, "quoted", "\"before");
  requireString(conf, "duplicate", "last");
  requireString(conf, "empty", "");
  requireString(conf, "", "empty key");
  // The parser trims only space and tab, not CR. No newline normalization.
  requireString(conf, "carriage", "value\r");
  long integer = 71;
  unsigned long unsignedInteger = 72;
  unsigned long long largeInteger = 73;
  float real = 74;
  std::string text("untouched");
  require(!conf.getInt("missing", integer) && integer == 71, "missing int changed output");
  require(!conf.getUnsigned("missing", unsignedInteger) && unsignedInteger == 72,
          "missing unsigned changed output");
  require(!conf.getUnsignedLongLong("missing", largeInteger) && largeInteger == 73,
          "missing unsigned long long changed output");
  require(!conf.getFloat("missing", real) && real == 74, "missing float changed output");
  require(!conf.getString("missing", text) && text == "untouched",
          "missing string changed output");
  require(conf.getInt("hex", integer) && integer == 42, "base-0 hex int");
  require(conf.getInt("octal", integer) && integer == 8, "base-0 octal int");
  require(conf.getInt("signed", integer) && integer == -17, "signed numeric prefix");
  require(conf.getInt("garbage", integer) && integer == 0, "garbage int exists and is zero");
  require(conf.getInt("empty", integer) && integer == 0, "empty int exists and is zero");
  require(conf.getUnsigned("hex", unsignedInteger) && unsignedInteger == 42,
          "base-0 hex unsigned");
  require(conf.getUnsigned("octal", unsignedInteger) && unsignedInteger == 8,
          "base-0 octal unsigned");
  require(conf.getUnsignedLongLong("hex", largeInteger) && largeInteger == 0,
          "unsigned long long is decimal, not base-0");
  require(conf.getUnsignedLongLong("octal", largeInteger) && largeInteger == 10,
          "unsigned long long decimal leading zero");
  require(conf.getUnsignedLongLong("large", largeInteger) && largeInteger == 4294967301ULL,
          "unsigned long long numeric prefix");
  require(conf.getFloat("real", real) && real == 1.25f, "float numeric prefix");
  require(conf.getFloat("garbage", real) && real == 0, "garbage float exists and is zero");
  conf.setString("text", "replacement");
  conf.setUnsigned("written_unsigned", 42);
  conf.setUnsignedLongLong("written_large", 4294967301ULL);
  requireString(conf, "text", "replacement");
  requireString(conf, "written_unsigned", "42");
  requireString(conf, "written_large", "4294967301");
}

static void testConfigHierarchy(const std::string& filename, const std::string& directory) {
  StoreConf conf;
  conf.parseConfig(filename);
  pStoreConf first = requireStore(conf, "store0");
  pStoreConf nested = requireStore(*first, "inner");
  requireString(*nested, "value", "nested");
  pStoreConf untouched = nested;
  require(!conf.getStore("missing", untouched) && untouched == nested,
          "missing store changed output");
  std::vector<pStoreConf> stores(1, nested);
  conf.getAllStores(stores);
  require(stores.size() == 13 && stores.front() == nested,
          "getAllStores must append without clearing existing entries");
  const char* expected[] = {"0", "1", "10", "11", "2", "3", "4", "5", "6", "7", "8", "9"};
  for (size_t i = 0; i < 12; ++i) {
    requireString(*stores[i + 1], "id", expected[i]);
  }
  std::ostringstream printed;
  printed << conf;
  save(directory + "/parsed.conf", printed.str());
}

static void testConfigInheritance(const std::string& filename) {
  HandlerFixture fixture(filename);
  fixture.handler->initialize();
  require(fixture.handler->getStatus() == facebook::fb303::ALIVE, "inheritance handler config");
  // Store::configure supplies parents explicitly. Parsing by itself does not.
  pStoreConf root(new StoreConf);
  root->parseConfig(filename);
  root->setString("file::ancestor", "local-root-typed");
  pStoreConf parent = requireStore(*root, "store0");
  pStoreConf child = requireStore(*parent, "leaf");
  requireString(*child, "nearest", "global-nearest");
  parent->setParent(root);
  child->setParent(parent);
  requireString(*child, "direct", "leaf-direct");
  requireString(*child, "self", "leaf-typed");
  requireString(*child, "nearest", "parent-typed");
  requireString(*child, "ancestor", "local-root-typed");
  requireString(*child, "empty", "");
  requireString(*child, "global_only", "global-value");
  std::string text("unchanged");
  require(!child->getString("unqualified", text) && text == "unchanged",
          "ordinary parent keys must not be inherited");
  require(!child->getString("category", text) && text == "unchanged",
          "category must not be inherited");
  require(!child->getString("categories", text) && text == "unchanged",
          "categories must not be inherited");
  StoreConf noType;
  noType.setParent(parent);
  require(!noType.getString("type", text) && text == "unchanged", "type must not be inherited");
  require(!noType.getString("ancestor", text) && text == "unchanged",
          "untyped stores must not inherit typed parameters");
  StoreConf detached;
  detached.setString("type", "file");
  requireString(detached, "global_only", "global-value");
  StoreConf otherType;
  otherType.setString("type", "buffer");
  otherType.setParent(parent);
  requireString(otherType, "nearest", "buffer-parent");
  pStoreConf absent = child;
  require(!child->getStore("leaf", absent) && absent == child,
          "nested stores must not be inherited");
  // Break the explicit test tree's parent/child shared ownership cycles.
  child->setParent(pStoreConf());
  parent->setParent(pStoreConf());
}

static void testConfigMalformed(const std::string& filename, const std::string& directory) {
  StoreConf conf;
  conf.parseConfig(filename);
  requireString(conf, "key", "last");
  requireString(conf, "after_bad_open", "retained");
  requireString(*requireStore(conf, "duplicate"), "id", "new");
  requireString(*requireStore(conf, "unclosed"), "inside", "accepted at EOF");
  std::ostringstream printed;
  printed << conf;
  save(directory + "/parsed.conf", printed.str());
  // parseConfig merges into a reused object; it does not clear existing keys.
  save(directory + "/second.conf", "key=updated\n");
  conf.parseConfig(directory + "/second.conf");
  requireString(conf, "key", "updated");
  requireString(conf, "after_bad_open", "retained");
  requireString(*requireStore(conf, "duplicate"), "id", "new");
  StoreConf stopped;
  save(directory + "/early-close.conf", "before=kept\n</arbitrary>\nafter=ignored\n");
  stopped.parseConfig(directory + "/early-close.conf");
  requireString(stopped, "before", "kept");
  std::string value("untouched");
  require(!stopped.getString("after", value) && value == "untouched",
          "top-level closing tag must end parsing");
  const std::string missing = directory + "/does-not-exist.conf";
  bool threw = false;
  try {
    stopped.parseConfig(missing);
  } catch (const std::runtime_error& error) {
    threw = true;
    require(std::string(error.what()) == "Failed to open config file <" + missing + ">",
            "missing-file exception text");
  }
  require(threw, "missing config file must throw");
}

static void testHandlerDefaults(const std::string& filename, bool overrides) {
  // Exercise the handler input to CLI precedence without entering main/serve.
  HandlerFixture fixture(filename, 2600);
  auto handler = fixture.handler;
  require(handler->port == 2600, "constructor port");
  require(handler->numThriftServerThreads == 3, "default server threads");
  require(handler->getMaxQueueSize() == 5000000ULL, "default max queue bytes");
  require(handler->getMaxConn() == 0, "default max connections");
  handler->initialize();
  require(handler->getStatus() == facebook::fb303::ALIVE, "handler config not alive");
  require(handler->port == (overrides ? 48879UL : 2600UL), "config/constructor port precedence");
  require(handler->numThriftServerThreads == (overrides ? 7U : 3U), "configured server threads");
  require(handler->getMaxQueueSize() == (overrides ? 4294967301ULL : 5000000ULL),
          "configured queue bytes");
  require(handler->getMaxConn() == (overrides ? 17UL : 0UL), "configured max connections");
}

static void testHandlerInvalid(const std::string& filename) {
  HandlerFixture fixture(filename);
  auto handler = fixture.handler;
  handler->initialize();
  require(handler->getStatus() == facebook::fb303::WARNING, "invalid config must warn");
  std::string details;
  handler->getStatusDetails(details);
  require(details == "No stores configured successfully", "legacy final error details");
  require(handler->Log({entry("accepted", "discard")}) == scribe::thrift::OK,
          "WARNING without stores still ACKs discarded messages");
  require(handler->getCounter("accepted:received bad") == 1, "invalid config discard counter");
  require(handler->getCounter("accepted:received good") == 0, "invalid config accepted message");
}

static void testRouting(const std::string& filename) {
  HandlerFixture fixture(filename);
  auto handler = fixture.handler;
  handler->initialize();
  require(handler->getStatus() == facebook::fb303::ALIVE, "routing config not alive");
  require(handler->Log({entry("ab.exact", "exact"), entry("abc.input", "prefix"),
                        entry("ab.other", "prefix"), entry("unmatched", "default"),
                        entry("", "blank")}) == scribe::thrift::OK, "routing ACK");
  handler->stopForTest();
  require(handler->getCounter("ab.exact:ignored") == 1, "exact must win over prefix");
  require(handler->getCounter("ab:ignored") == 4, "shorter sorted prefix and two-store fan-out");
  require(handler->getCounter("abc:ignored") == 0, "prefix matching is not longest-prefix");
  require(handler->getCounter("default:ignored") == 1, "fallback default store");
  require(handler->getCounter("scribe_overall:ignored") == 6, "fan-out discard total");
  require(handler->getCounter("scribe_overall:received good") == 4,
          "fan-out must count one good per message, not per destination");
  require(handler->getCounter("scribe_overall:received bad") == 0, "default route rejected message");
  require(handler->getCounter("scribe_overall:received blank category") == 1,
          "blank category must not enter default route");
}

#include "filestore_contracts.h"

int main(int argc, char** argv) {
  try {
    require(argc == 4, "usage: fixture mode config temporary-directory");
    if (std::string(argv[1]) == "wire") {
      testWire(argv[2], argv[3]);
    } else if (std::string(argv[1]) == "handler") {
      testHandler(argv[2]);
    } else if (std::string(argv[1]) == "config-values") {
      testConfigValues(argv[2]);
    } else if (std::string(argv[1]) == "config-hierarchy") {
      testConfigHierarchy(argv[2], argv[3]);
    } else if (std::string(argv[1]) == "config-inheritance") {
      testConfigInheritance(argv[2]);
    } else if (std::string(argv[1]) == "config-malformed") {
      testConfigMalformed(argv[2], argv[3]);
    } else if (std::string(argv[1]) == "config-defaults") {
      testHandlerDefaults(argv[2], false);
    } else if (std::string(argv[1]) == "config-overrides") {
      testHandlerDefaults(argv[2], true);
    } else if (std::string(argv[1]) == "config-invalid") {
      testHandlerInvalid(argv[2]);
    } else if (std::string(argv[1]) == "routing") {
      testRouting(argv[2]);
    } else if (dispatchFileStore(argv[1], argv[2], argv[3])) {
      // Actual filesystem contract mode completed.
    } else {
      throw std::runtime_error("unknown fixture mode");
    }
    std::cout << "PASS " << argv[1] << std::endl;
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << std::endl;
    return 1;
  }
}
