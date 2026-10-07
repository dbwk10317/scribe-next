// scribe-next modification: adapt the Thrift 0.25 API boundary; preserve Scribe behavior.
// scribe-next modification: funnel the shutdown RPC thread and main into one exit; no behaviour change.
// scribe-next modification: std::shared_ptr/std::weak_ptr replace the internal Boost pointers; no behaviour change.
//  Copyright (c) 2007-2008 Facebook
//
//  Licensed under the Apache License, Version 2.0 (the "License");
//  you may not use this file except in compliance with the License.
//  You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.
//
// See accompanying file LICENSE or visit the Scribe site at:
// http://developers.facebook.com/scribe/
//
// @author Bobby Johnson
// @author James Wang
// @author Jason Sobel
// @author Avinash Lakshman
// @author Anthony Giardullo

#include "common.h"
#include "scribe_server.h"
#include <mutex>

using namespace apache::thrift;
using namespace apache::thrift::protocol;
using namespace apache::thrift::transport;
using namespace apache::thrift::server;
using namespace apache::thrift::concurrency;

using namespace scribe::thrift;
using namespace scribe::concurrency;

std::shared_ptr<TConfiguration> scribe::createThriftConfiguration() {
  if (!g_Handler->hasValidThriftLimits()) {
    throw std::runtime_error("Invalid Thrift wire limits; listener not started");
  }
  return std::make_shared<TConfiguration>(g_Handler->getThriftMaxMessageSize(),
                                         g_Handler->getThriftMaxFrameSize());
}

// TNonblockingServer owns a separate TMemoryBuffer, which otherwise keeps its
// default 100MiB budget even after configuring the accepted socket.
class ConfiguredInputTransportFactory : public TTransportFactory {
 public:
  explicit ConfiguredInputTransportFactory(std::shared_ptr<TConfiguration> config)
      : config_(config) {}
  std::shared_ptr<TTransport> getTransport(std::shared_ptr<TTransport> transport) override {
    transport->setConfiguration(config_);
    return transport;
  }
 private:
  std::shared_ptr<TConfiguration> config_;
};

/*
 * Network configuration and directory services
 */

bool scribe::network_config::getService(const std::string& serviceName,
                                        const std::string& options,
                                        server_vector_t& _return) {
  return false;
}

/*
 * Concurrency mechanisms
 */

std::shared_ptr<ReadWriteMutex> scribe::concurrency::createReadWriteMutex() {
  return std::shared_ptr<ReadWriteMutex>(new ReadWriteMutex());
}

/*
 * Time functions
 */

unsigned long scribe::clock::nowInMsec() {
  // There is a minor race condition between the 2 calls below,
  // but the chance is really small.

  // Get current time in timeval
  struct timeval tv;
  gettimeofday(&tv, NULL);

  // Get current time in sec
  time_t sec = time(NULL);

  return ((unsigned long)sec) * 1000 + (tv.tv_usec / 1000);
}

/*
 * Hash functions
 */

uint32_t scribe::integerhash::hash32(uint32_t key) {
  return key;
}

uint32_t scribe::strhash::hash32(const char *s) {
  // Use the djb2 hash (http://www.cse.yorku.ca/~oz/hash.html)
  if (s == NULL) {
    return 0;
  }
  uint32_t hash = 5381;
  int c;
  while ((c = *s++)) {
    hash = ((hash << 5) + hash) + c; // hash * 33 + c
  }
  return hash;
}

/*
 * Starting a scribe server.
 */
// note: this function uses global g_Handler.
std::shared_ptr<TNonblockingServer> scribe::createServer(
    std::shared_ptr<TNonblockingServerTransport> server_transport) {
  auto config = createThriftConfiguration();
  std::shared_ptr<TProcessor> processor(new scribeProcessor(g_Handler));
  /* This factory is for binary compatibility. */
  std::shared_ptr<TProtocolFactory> protocol_factory(
    new TBinaryProtocolFactory(0, 0, false, false)
  );
  std::shared_ptr<ThreadManager> thread_manager;

  if (g_Handler->numThriftServerThreads > 1) {
    // create a ThreadManager to process incoming calls
    thread_manager = ThreadManager::newSimpleThreadManager(
      g_Handler->numThriftServerThreads
    );

    std::shared_ptr<ThreadFactory> thread_factory(new ThreadFactory());
    thread_manager->threadFactory(thread_factory);
    thread_manager->start();
  }

  if (!server_transport) {
    server_transport.reset(new TNonblockingServerSocket(g_Handler->port));
  }
  std::shared_ptr<TNonblockingServer> server(new TNonblockingServer(
                                          processor,
                                          protocol_factory,
                                          server_transport,
                                          thread_manager
                                        ));
  server->setConfiguration(config);
  server->setInputTransportFactory(
      std::make_shared<ConfiguredInputTransportFactory>(config));
  g_Handler->setServer(server);

  LOG_OPER("Starting scribe server on port %lu", g_Handler->port);
  fflush(stderr);

  // throttle concurrent connections
  unsigned long mconn = g_Handler->getMaxConn();
  if (mconn > 0) {
    LOG_OPER("Throttle max_conn to %lu", mconn);
    server->setMaxConnections(mconn);
    server->setOverloadAction(T_OVERLOAD_CLOSE_ON_ACCEPT);
  }

  return server;
}

void scribe::startServer() {
  createServer()->serve();
  // this function never returns
}


/*
 * Stopping a scribe server.
 */
void scribe::stopServer() {
  // The shutdown RPC runs exit(0) on a Thrift worker thread while main() returns
  // from serve() and exits too; two exits ran the static destructors at once and
  // could crash (seen on the restarted receiver). One exit, the other caller waits.
  static std::once_flag once;
  std::call_once(once, [] { exit(0); });
}
