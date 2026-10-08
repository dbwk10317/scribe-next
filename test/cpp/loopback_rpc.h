// Loopback transport fixture using the production server construction path.
// Licensed under the Apache License, Version 2.0; see LICENSE.
// Included after the common fixture helpers in scribe_api_compat.cpp.
#ifndef SCRIBE_TEST_LOOPBACK_RPC_H
#define SCRIBE_TEST_LOOPBACK_RPC_H

#include <netinet/in.h>
#include <sys/socket.h>

class LoopbackReady : public apache::thrift::server::TServerEventHandler {
 public:
  LoopbackReady(const std::shared_ptr<
                    apache::thrift::transport::TNonblockingServerSocket>& transport,
                const std::shared_ptr<TServerEventHandler>& production)
      : transport_(transport), production_(production) {}

  void preServe() override {
    production_->preServe();  // publishes the server to the handler as main() does
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
  std::shared_ptr<TServerEventHandler> production_;
};

static void runLoopbackServer(const std::string& config,
                              const std::string& directory) {
  using apache::thrift::transport::TNonblockingServerSocket;

  struct stat info;
  require(stat(directory.c_str(), &info) == 0 && S_ISDIR(info.st_mode),
          "loopback temporary directory does not exist");

  // Use the unmodified handler, including its real oneway shutdown RPC. The
  // owning Python parent enforces deadlines and kills/reaps this child on error.
  auto handler = std::make_shared<scribeHandler>(0, config);
  g_Handler = handler;  // scribe::createServer() wires it like main() does
  handler->initialize();
  if (handler->getStatus() != facebook::fb303::ALIVE) {
    std::string details;
    handler->getStatusDetails(details);
    throw std::runtime_error("loopback handler initialization failed: " + details);
  }

  // initialize() requires a positive config port, but this test-only native
  // transport always binds an OS-assigned ephemeral port on IPv4 loopback.
  auto transport = std::make_shared<TNonblockingServerSocket>("127.0.0.1", 0);
  // Exercise the same processor/protocol/thread/max_conn construction as the
  // real startServer entry point; only the listener transport is supplied here.
  auto server = scribe::createServer(transport);
  require(static_cast<bool>(server->getThreadManager()) ==
              (handler->numThriftServerThreads > 1),
          "production factory selected the wrong thread manager branch");
  if (handler->getMaxConn() > 0) {
    require(server->getMaxConnections() == handler->getMaxConn() &&
                server->getOverloadAction() ==
                    apache::thrift::server::T_OVERLOAD_CLOSE_ON_ACCEPT,
            "production factory did not apply max_conn");
  }
  server->setServerEventHandler(
      std::make_shared<LoopbackReady>(transport, server->getEventHandler()));
  server->serve();
}

#endif // SCRIBE_TEST_LOOPBACK_RPC_H
