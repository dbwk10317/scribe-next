// scribe-next modification: adapt the Thrift 0.25 API boundary; preserve Scribe behavior.
// scribe-next modification: C++17 cleanup; std::mutex pool guards keep lock points, dead null checks removed.
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


#include "common.h"
#include "scribe_server.h"
#include "conn_pool.h"

using std::string;
using std::ostringstream;
using std::map;
using boost::shared_ptr;
using namespace apache::thrift;
using namespace apache::thrift::protocol;
using namespace apache::thrift::transport;
using namespace apache::thrift::server;
using namespace scribe::thrift;


ConnPool::ConnPool() {
}

ConnPool::~ConnPool() {
}

string ConnPool::makeKey(const string& hostname, unsigned long port) {
  string key(hostname);
  key += ":";

  ostringstream oss;
  oss << port;
  key += oss.str();
  return key;
}

bool ConnPool::open(const string& hostname, unsigned long port, int timeout) {
        return openCommon(makeKey(hostname, port),
                    boost::shared_ptr<scribeConn>(new scribeConn(hostname, port, timeout)));
}

bool ConnPool::open(const string &service, const server_vector_t &servers, int timeout) {
        return openCommon(service,
                    boost::shared_ptr<scribeConn>(new scribeConn(service, servers, timeout)));
}

void ConnPool::close(const string& hostname, unsigned long port) {
  closeCommon(makeKey(hostname, port));
}

void ConnPool::close(const string &service) {
  closeCommon(service);
}

int ConnPool::send(const string& hostname, unsigned long port,
                    boost::shared_ptr<logentry_vector_t> messages) {
  return sendCommon(makeKey(hostname, port), messages);
}

int ConnPool::send(const string &service,
                    boost::shared_ptr<logentry_vector_t> messages) {
  return sendCommon(service, messages);
}

// Keep one connection locked through status inspection or a send, including exceptions.
namespace {
class ConnectionGuard {
 public:
  explicit ConnectionGuard(scribeConn& connection) : connection(connection) { connection.lock(); }
  ~ConnectionGuard() { connection.unlock(); }
  ConnectionGuard(const ConnectionGuard&) = delete;
  ConnectionGuard& operator=(const ConnectionGuard&) = delete;
 private:
  scribeConn& connection;
};
}

bool ConnPool::openCommon(const string &key, boost::shared_ptr<scribeConn> conn) {

  // note on locking:
  // The mapMutex locks all reads and writes to the connMap.
  // The locks on each connection serialize writes and deletion.
  // The lock on a connection doesn't protect its refcount, as refcounts
  // are only accessed under the mapMutex.
  // mapMutex MUST be held before attempting to lock particular connection

  // Declared before the guard so a replaced connection is still destroyed
  // after mapMutex is released, as with the former unlock-then-return.
  boost::shared_ptr<scribeConn> old_conn;
  std::lock_guard<std::mutex> map_lock(mapMutex);
  conn_map_t::iterator iter = connMap.find(key);
  if (iter != connMap.end()) {
    old_conn = (*iter).second;
    ConnectionGuard connection_guard(*old_conn);
    if (old_conn->isOpen()) {
      old_conn->addRef();
      return true;
    }
    if (conn->open()) {
      LOG_OPER("CONN_POOL: switching to a new connection <%s>", key.c_str());
      conn->setRef(old_conn->getRef());
      conn->addRef();
      // old connection will be magically deleted by shared_ptr
      connMap[key] = conn;
      return true;
    }
    return false;
  }
  // don't need to lock the conn yet, because no one know about
  // it until we release the mapMutex
  if (conn->open()) {
    // ref count starts at one, so don't addRef here
    connMap[key] = conn;
    return true;
  }
  // conn object that failed to open is deleted
  return false;
}

void ConnPool::closeCommon(const string &key) {
  std::lock_guard<std::mutex> map_lock(mapMutex);
  conn_map_t::iterator iter = connMap.find(key);
  if (iter != connMap.end()) {
    (*iter).second->releaseRef();
    if ((*iter).second->getRef() <= 0) {
      (*iter).second->lock();
      (*iter).second->close();
      (*iter).second->unlock();
      connMap.erase(iter);
    }
  } else {
    // This can be bad. If one client double closes then other cleints are screwed
    LOG_OPER("LOGIC ERROR: attempting to close connection <%s> that connPool has no entry for", key.c_str());
  }
}

int ConnPool::sendCommon(const string &key,
                          boost::shared_ptr<logentry_vector_t> messages) {
  std::unique_lock<std::mutex> map_lock(mapMutex);
  conn_map_t::iterator iter = connMap.find(key);
  if (iter != connMap.end()) {
    boost::shared_ptr<scribeConn> connection = iter->second;
    ConnectionGuard connection_guard(*connection);
    map_lock.unlock();
    return connection->send(messages);
  } else {
    LOG_OPER("send failed. No connection pool entry for <%s>", key.c_str());
    return (CONN_FATAL);
  }
}

scribeConn::scribeConn(const string& hostname, unsigned long port, int timeout_)
  : refCount(1),
  serviceBased(false),
  remoteHost(hostname),
  remotePort(port),
  timeout(timeout_) {
  pthread_mutex_init(&mutex, NULL);
}

scribeConn::scribeConn(const string& service, const server_vector_t &servers, int timeout_)
  : refCount(1),
  serviceBased(true),
  serviceName(service),
  serverList(servers),
  timeout(timeout_) {
  pthread_mutex_init(&mutex, NULL);
}

scribeConn::~scribeConn() {
  pthread_mutex_destroy(&mutex);
}

void scribeConn::addRef() {
  ++refCount;
}

void scribeConn::releaseRef() {
  --refCount;
}

unsigned scribeConn::getRef() {
  return refCount;
}

void scribeConn::setRef(unsigned r) {
  refCount = r;
}

void scribeConn::lock() {
  pthread_mutex_lock(&mutex);
}

void scribeConn::unlock() {
  pthread_mutex_unlock(&mutex);
}

bool scribeConn::isOpen() {
  return framedTransport->isOpen();
}

bool scribeConn::open() {
  try {

    socket = serviceBased ?
      std::shared_ptr<TSocket>(new TSocketPool(serverList)) :
      std::shared_ptr<TSocket>(new TSocket(remoteHost, remotePort));

    socket->setConnTimeout(timeout);
    socket->setRecvTimeout(timeout);
    socket->setSendTimeout(timeout);
    /*
     * We don't want to send resets to close the connection. Among
     * other badness it also reduces data reliability. On getting a
     * rest, the receiving socket will throw any data the receving
     * process has not yet read.
     *
     * echo 5 > /proc/sys/net/ipv4/tcp_fin_timeout to set the TIME_WAIT
     * timeout on a system.
     * sysctl -a | grep tcp
     */
    socket->setLinger(0, 0);

    auto config = scribe::createThriftConfiguration();
    socket->setConfiguration(config);
    framedTransport = std::shared_ptr<TFramedTransport>(new TFramedTransport(socket, config));
    protocol = std::shared_ptr<TBinaryProtocol>(new TBinaryProtocol(framedTransport));
    protocol->setStrict(false, false);
    resendClient = std::shared_ptr<scribeClient>(new scribeClient(protocol));

    framedTransport->open();
    if (serviceBased) {
      remoteHost = socket->getPeerHost();
    }
  } catch (const TTransportException& ttx) {
    LOG_OPER("failed to open connection to remote scribe server %s thrift error <%s>",
             connectionString().c_str(), ttx.what());
    return false;
  } catch (const std::exception& stx) {
    LOG_OPER("failed to open connection to remote scribe server %s std error <%s>",
             connectionString().c_str(), stx.what());
    return false;
  }
  LOG_OPER("Opened connection to remote scribe server %s",
           connectionString().c_str());
  return true;
}

void scribeConn::close() {
  try {
    framedTransport->close();
  } catch (const TTransportException& ttx) {
    LOG_OPER("error <%s> while closing connection to remote scribe server %s",
             ttx.what(), connectionString().c_str());
  }
}

int
scribeConn::send(boost::shared_ptr<logentry_vector_t> messages) {
  // Non-strict binary Log payload: 21-byte envelope, then 15 bytes plus the
  // category/message bytes per entry. The outer four-byte frame is excluded.
  // TFramedTransport::flush itself only limits writes to 2GB. Reject locally
  // without splitting or discarding a retained batch that exceeds our policy.
  const uint64_t limit = (std::min)(g_Handler->getThriftMaxFrameSize(),
                                   g_Handler->getThriftMaxMessageSize());
  uint64_t wire_size = 21;
  for (const auto& message : *messages) {
    wire_size += 15 + message->category.size() + message->message.size();
    if (wire_size > limit) {
      LOG_OPER("Relay Log exceeds configured wire limit <%llu> bytes",
               static_cast<unsigned long long>(limit));
      return CONN_TRANSIENT;
    }
  }
  if (wire_size > limit) {
    LOG_OPER("Relay Log exceeds configured wire limit <%llu> bytes",
             static_cast<unsigned long long>(limit));
    return CONN_TRANSIENT;
  }
  bool fatal;
  int size = messages->size();
  if (!isOpen()) {
    if (!open()) {
      return (CONN_FATAL);
    }
  }

  // Copy the vector of pointers to a vector of objects
  // This is because thrift doesn't support vectors of pointers,
  // but we need to use them internally to avoid even more copies.
  std::vector<LogEntry> msgs;
  msgs.reserve(size);
  for (logentry_vector_t::iterator iter = messages->begin();
       iter != messages->end();
       ++iter) {
    msgs.push_back(**iter);
  }
  ResultCode result = TRY_LATER;
  try {
    result = resendClient->Log(msgs);

    if (result == OK) {
      g_Handler->incCounter("sent", size);
      LOG_OPER("Successfully sent <%d> messages to remote scribe server %s",
          size, connectionString().c_str());
      return (CONN_OK);
    }
    fatal = false;
    LOG_OPER("Failed to send <%d> messages, remote scribe server %s "
        "returned error code <%d>", size, connectionString().c_str(),
        (int) result);
  } catch (const TTransportException& ttx) {
    fatal = true;
    LOG_OPER("Failed to send <%d> messages to remote scribe server %s "
        "error <%s>", size, connectionString().c_str(), ttx.what());
  } catch (...) {
    fatal = true;
    LOG_OPER("Unknown exception sending <%d> messages to remote scribe "
        "server %s", size, connectionString().c_str());
  }
  /*
   * If this is a serviceBased connection then close it. We might
   * be lucky and get another service when we reopen this connection.
   * If the IP:port of the remote is fixed then no point closing this
   * connection ... we are going to get the same connection back.
   */
  if (serviceBased || fatal) {
    close();
    return (CONN_FATAL);
  }
  return (CONN_TRANSIENT);
}

std::string scribeConn::connectionString() {
        if (serviceBased) {
                return "<" + remoteHost + " Service: " + serviceName + ">";
        } else {
                char port[10];
                snprintf(port, 10, "%lu", remotePort);
                return "<" + remoteHost + ":" + string(port) + ">";
        }
}
