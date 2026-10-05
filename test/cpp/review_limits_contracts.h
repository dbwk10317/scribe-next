// Explicit finite Thrift wire-policy contracts. Apache License 2.0; see LICENSE.
#ifndef SCRIBE_TEST_REVIEW_LIMITS_CONTRACTS_H
#define SCRIBE_TEST_REVIEW_LIMITS_CONTRACTS_H

#include "conn_pool.h"
#include "dynamic_bucket_updater.h"

static void testThriftLimits(const std::string& filename, bool invalid) {
  HandlerFixture fixture(filename);
  auto handler = fixture.handler;
  handler->initialize();
  if (invalid) {
    require(handler->getStatus() == facebook::fb303::WARNING &&
                !handler->hasValidThriftLimits(), "invalid limits accepted");
    try {
      scribe::createServer(std::make_shared<
          apache::thrift::transport::TNonblockingServerSocket>("127.0.0.1", 0));
    } catch (const std::runtime_error&) {
      return;
    }
    throw std::runtime_error("invalid limits constructed server");
  }
  require(handler->getStatus() == facebook::fb303::ALIVE, "valid limits rejected");
  unsigned long frame = scribe::DEFAULT_THRIFT_MAX_SIZE;
  unsigned long message = scribe::DEFAULT_THRIFT_MAX_SIZE;
  handler->getConfig().getUnsigned("expected_frame", frame);
  handler->getConfig().getUnsigned("expected_message", message);
  require(handler->getThriftMaxFrameSize() == static_cast<int>(frame) &&
              handler->getThriftMaxMessageSize() == static_cast<int>(message),
          "handler effective limits mismatch");
  auto server = scribe::createServer(std::make_shared<
      apache::thrift::transport::TNonblockingServerSocket>("127.0.0.1", 0));
  auto configuration = server->getConfiguration();
  require(server->getMaxFrameSize() == frame &&
              configuration->getMaxMessageSize() == static_cast<int>(message),
          "production server limits mismatch");
  auto memory = std::make_shared<TMemoryBuffer>();
  require(server->getInputTransportFactory()->getTransport(memory) == memory,
          "input policy unexpectedly wrapped memory transport");
  require(memory->getConfiguration() == configuration,
          "separate input memory retained default configuration");
  const auto client = scribe::createThriftConfiguration();
  require(client->getMaxFrameSize() == static_cast<int>(frame) &&
              client->getMaxMessageSize() == static_cast<int>(message),
          "RPC client limits differ from server");
}

class LimitConnection : public scribeConn {
 public:
  LimitConnection(unsigned long port) : scribeConn("127.0.0.1", port, 500) {}
  void checkPolicy() {
    require(socket->getConfiguration()->getMaxFrameSize() ==
                g_Handler->getThriftMaxFrameSize() &&
                framedTransport->getMaxFrameSize() ==
                    static_cast<uint32_t>(g_Handler->getThriftMaxFrameSize()) &&
                framedTransport->getConfiguration()->getMaxMessageSize() ==
                    g_Handler->getThriftMaxMessageSize(), "relay layer policy mismatch");
  }
};

static void runLimitRelay(const std::string& filename) {
  HandlerFixture fixture(filename);
  auto handler = fixture.handler;
  handler->initialize();
  require(handler->getStatus() == facebook::fb303::ALIVE, "limit relay config");
  unsigned long port = 0, category_size = 0, payload_size = 0;
  require(handler->getConfig().getUnsigned("remote_port", port) && port > 0 && port <= 65535,
          "limit relay requires assigned loopback port");
  handler->getConfig().getUnsigned("category_size", category_size);
  handler->getConfig().getUnsigned("payload_size", payload_size);
  require(category_size + payload_size <= 21 * 1024 * 1024,
          "limit relay fixture payload bound");
  auto messages = fileMessages({entry(std::string(category_size, 'c'),
                                     std::string(payload_size, 'x'))});
  LimitConnection connection(port);
  require(connection.open(), "limit relay connection failed");
  connection.checkPolicy();
  const int result = connection.send(messages);
  require(messages->size() == 1 && messages->at(0)->category == std::string(category_size, 'c') &&
              messages->at(0)->message == std::string(payload_size, 'x'),
          "limit relay changed retained bytes");
  std::cout << "RESULT " << result << " " << handler->getCounter("scribe_overall:sent")
            << " " << messages->size() << std::endl;
  connection.close();
}

static void runLimitSpoolRelay(const std::string& filename) {
  FileStoreFixture fixture(filename);
  requireRelayDestination(fixture.configuration);
  boost::shared_ptr<NetworkStore> primary(new NetworkStore(nullptr, "fallback", true));
  primary->configure(fixture.configuration, pStoreConf());
  require(primary->open(), "spool relay primary open");
  ReplayBuffer buffer(primary, fixture.store);
  buffer.periodicCheck();
  unsigned long rejected = 0;
  fixture.configuration->getUnsigned("expected_rejected", rejected);
  if (rejected) {
    require(buffer.disconnected() && !fixture.store->empty(&fixture.now),
            "rejected spool batch was removed or marked streaming");
    require(fixture.handlerFixture.handler->getCounter("fallback:lost") == 0 &&
                fixture.handlerFixture.handler->getCounter("fallback:bytes lost") == 0 &&
                fixture.handlerFixture.handler->getCounter("scribe_overall:sent") == 0,
            "rejected spool counters changed");
    buffer.close();
    return;
  }
  buffer.periodicCheck();  // Exhaustion is detected on the next normal check.
  require(buffer.streaming() && fixture.store->empty(&fixture.now),
          "20MiB spool did not finish replay");
  require(fixture.handlerFixture.handler->getCounter("fallback:lost") == 0 &&
              fixture.handlerFixture.handler->getCounter("fallback:bytes lost") == 0 &&
              fixture.handlerFixture.handler->getCounter("scribe_overall:sent") == 1,
          "spool relay loss/sent counters");
  buffer.close();
}

static void runLimitMapping(const std::string& filename) {
  HandlerFixture fixture(filename);
  auto handler = fixture.handler;
  handler->initialize();
  require(handler->getStatus() == facebook::fb303::ALIVE, "limit mapping config");
  unsigned long remote_port = 0;
  require(handler->getConfig().getUnsigned("remote_port", remote_port) &&
              remote_port > 0 && remote_port <= 65535,
          "limit mapping requires assigned loopback port");
  std::string host = "keep";
  uint32_t port = 19;
  // Invoke only the RPC mapping client. No NetworkStore dynamic destination,
  // service discovery, bucket fallback/configure/copy/routing path is used.
  const bool result = DynamicBucketUpdater::getHost(handler.get(), "limitmapping",
      60, 42, host, port, "127.0.0.1", static_cast<uint32_t>(remote_port), 500, 500, 500);
  std::cout << "MAPPING " << result << " " << host.size() << " " << port << std::endl;
}

#endif
