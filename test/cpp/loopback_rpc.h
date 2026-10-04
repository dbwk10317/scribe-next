// Test-only loopback RPC fixture; no production server construction changes.
// Licensed under the Apache License, Version 2.0; see LICENSE.
// Included after the common fixture helpers in scribe_api_compat.cpp.
#ifndef SCRIBE_TEST_LOOPBACK_RPC_H
#define SCRIBE_TEST_LOOPBACK_RPC_H

#include <netinet/in.h>
#include <sys/socket.h>

class LoopbackReady : public apache::thrift::server::TServerEventHandler {
 public:
  explicit LoopbackReady(const std::shared_ptr<
      apache::thrift::transport::TNonblockingServerSocket>& transport)
      : transport_(transport) {}

  void preServe() override {
    // Thrift calls preServe after listen(). getPort() is the requested zero;
    // check the actual socket rather than selecting/releasing a port in advance.
    sockaddr_storage address = {};
    socklen_t length = sizeof(address);
    require(getsockname(transport_->getSocketFD(),
                        reinterpret_cast<sockaddr*>(&address), &length) == 0,
            "loopback getsockname failed");
    require(address.ss_family == AF_INET && length == sizeof(sockaddr_in),
            "loopback listener is not IPv4");
    const auto* ipv4 = reinterpret_cast<const sockaddr_in*>(&address);
    require(ntohl(ipv4->sin_addr.s_addr) == INADDR_LOOPBACK,
            "loopback listener is not bound to 127.0.0.1");
    const unsigned port = ntohs(ipv4->sin_port);
    require(port != 0 && port == static_cast<unsigned>(transport_->getListenPort()),
            "loopback listener has an invalid or inconsistent assigned port");
    std::cout << "READY 127.0.0.1 " << port << std::endl;
    require(std::cout.good(), "could not publish loopback readiness");
  }

 private:
  std::shared_ptr<apache::thrift::transport::TNonblockingServerSocket> transport_;
};

static void runLoopbackServer(const std::string& config,
                              const std::string& directory) {
  using apache::thrift::concurrency::ThreadFactory;
  using apache::thrift::concurrency::ThreadManager;
  using apache::thrift::protocol::TBinaryProtocolFactory;
  using apache::thrift::server::TNonblockingServer;
  using apache::thrift::transport::TNonblockingServerSocket;

  struct stat info;
  require(stat(directory.c_str(), &info) == 0 && S_ISDIR(info.st_mode),
          "loopback temporary directory does not exist");

  // Use the unmodified handler, including its real oneway shutdown RPC. The
  // owning Python parent enforces deadlines and kills/reaps this child on error.
  auto handler = std::make_shared<scribeHandler>(0, config);
  g_Handler = handler;
  handler->initialize();
  if (handler->getStatus() != facebook::fb303::ALIVE) {
    std::string details;
    handler->getStatusDetails(details);
    throw std::runtime_error("loopback handler initialization failed: " + details);
  }

  auto processor = std::make_shared<scribeProcessor>(handler);
  auto protocolFactory = std::make_shared<TBinaryProtocolFactory>(0, 0, false, false);
  std::shared_ptr<ThreadManager> threadManager;
  // Match both current startServer branches without calling the production
  // entry point, whose transport does not explicitly restrict the bind address.
  if (handler->numThriftServerThreads > 1) {
    threadManager = ThreadManager::newSimpleThreadManager(handler->numThriftServerThreads);
    auto threadFactory = std::make_shared<ThreadFactory>();
    threadManager->threadFactory(threadFactory);
    threadManager->start();
  }

  // initialize() requires a positive config port, but this test-only native
  // transport always binds an OS-assigned ephemeral port on IPv4 loopback.
  auto transport = std::make_shared<TNonblockingServerSocket>("127.0.0.1", 0);
  auto server = std::make_shared<TNonblockingServer>(
      processor, protocolFactory, transport, threadManager);
  handler->setServer(server);
  const unsigned long maxConnections = handler->getMaxConn();
  if (maxConnections > 0) {
    server->setMaxConnections(maxConnections);
    server->setOverloadAction(apache::thrift::server::T_OVERLOAD_CLOSE_ON_ACCEPT);
  }
  server->setServerEventHandler(std::make_shared<LoopbackReady>(transport));
  server->serve();
}

#endif // SCRIBE_TEST_LOOPBACK_RPC_H
