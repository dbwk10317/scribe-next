// Memory-only smoke fixture for the actual Scribe handler and generated RPC API.
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
  explicit TestHandler(const std::string& config) : scribeHandler(0, config) {}

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
  explicit HandlerFixture(const std::string& config)
      : handler(std::make_shared<TestHandler>(config)) {
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
  require(!output.fail(), "could not write temporary wire capture");
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

int main(int argc, char** argv) {
  try {
    require(argc == 4, "usage: fixture wire|handler config temporary-directory");
    if (std::string(argv[1]) == "wire") {
      testWire(argv[2], argv[3]);
    } else {
      require(std::string(argv[1]) == "handler", "unknown fixture mode");
      testHandler(argv[2]);
    }
    std::cout << "PASS " << argv[1] << std::endl;
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << std::endl;
    return 1;
  }
}
