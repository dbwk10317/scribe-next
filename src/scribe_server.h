// scribe-next modification: adapt the Thrift 0.25 API boundary; preserve Scribe behavior.
// scribe-next modification: C++17 cleanup; override and deleted copies, no behaviour change.
// scribe-next modification: std::shared_ptr/std::weak_ptr replace the internal Boost pointers; no behaviour change.
// scribe-next modification: the server context is injected (ScribeContext) instead of read from process globals; no behaviour change.
//  Copyright (c) 2007-2009 Facebook
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

#ifndef SCRIBE_SERVER_H
#define SCRIBE_SERVER_H

#include "store.h"
#include "store_queue.h"
#include "context.h"

typedef std::vector<std::shared_ptr<StoreQueue> > store_list_t;
typedef std::map<std::string, std::shared_ptr<store_list_t> > category_map_t;

class scribeHandler : virtual public scribe::thrift::scribeIf,
                              public facebook::fb303::FacebookBase,
                              public ScribeContext {

 public:
  scribeHandler(unsigned long int port, const std::string& conf_file);
  ~scribeHandler();

  void shutdown() override;
  void initialize();
  void reinitialize() override;

  scribe::thrift::ResultCode Log(const std::vector<scribe::thrift::LogEntry>& messages) override;

  void getVersion(std::string& _return) override {_return = scribeversion;}
  facebook::fb303::fb_status getStatus() override;
  void getStatusDetails(std::string& _return) override;
  void setStatus(facebook::fb303::fb_status new_status);
  void setStatusDetails(const std::string& new_status_details);

  unsigned long int port; // it's long because that's all I implemented in the conf class

  // number of threads processing new Thrift connections
  size_t numThriftServerThreads;


  inline unsigned long long getMaxQueueSize() override {
    return maxQueueSize;
  }

  inline const StoreConf& getConfig() const {
    return config;
  }

  void incCounter(std::string category, std::string counter) override;
  void incCounter(std::string category, std::string counter, long amount) override;
  void incCounter(std::string counter) override;
  void incCounter(std::string counter, long amount) override;

  inline void setServer(
      std::shared_ptr<apache::thrift::server::TNonblockingServer> & server) {
    this->server = server;
  }
  unsigned long getMaxConn() {
    return maxConn;
  }
  int getThriftMaxFrameSize() const override { return thriftMaxFrameSize; }
  int getThriftMaxMessageSize() const override { return thriftMaxMessageSize; }
  bool hasValidThriftLimits() const override { return thriftLimitsValid; }
  ConnPool& getConnPool() override { return connPool; }
  facebook::fb303::FacebookBase* getFacebookBase() override { return this; }
 private:
  std::shared_ptr<apache::thrift::server::TNonblockingServer> server;
  // Declared before the store maps so it outlives their network stores.
  ConnPool connPool;

  unsigned long checkPeriod; // periodic check interval for all contained stores

  // This map has an entry for each configured category.
  // Each of these entries is a map of type->StoreQueue.
  // The StoreQueue contains a store, which could contain additional stores.
  category_map_t categories;
  category_map_t category_prefixes;

  // the default stores
  store_list_t defaultStores;

  std::string configFilename;
  facebook::fb303::fb_status status;
  std::string statusDetails;
  apache::thrift::concurrency::Mutex statusLock;
  apache::thrift::concurrency::Mutex throttleLock;
  time_t lastMsgTime;
  unsigned long numMsgLastSecond;
  unsigned long maxMsgPerSecond;
  unsigned long maxConn;
  unsigned long long maxQueueSize;
  int thriftMaxFrameSize;
  int thriftMaxMessageSize;
  bool thriftLimitsValid;
  StoreConf config;
  bool newThreadPerCategory;

  /* mutex to syncronize access to scribeHandler.
   * A single mutex is fine since it only needs to be locked in write mode
   * during start/stop/reinitialize or when we need to create a new category.
   */
  std::shared_ptr<scribe::concurrency::ReadWriteMutex>
    scribeHandlerLock;

  // disallow empty construction, copy, and assignment
  scribeHandler() = delete;
  scribeHandler(const scribeHandler& rhs) = delete;
  const scribeHandler& operator=(const scribeHandler& rhs) = delete;

 protected:
  bool throttleDeny(int num_messages); // returns true if overloaded
  void deleteCategoryMap(category_map_t& cats);
  const char* statusAsString(facebook::fb303::fb_status new_status);
  bool createCategoryFromModel(const std::string &category,
                               const std::shared_ptr<StoreQueue> &model);
  std::shared_ptr<StoreQueue>
    configureStoreCategory(pStoreConf store_conf,
                           const std::string &category,
                           const std::shared_ptr<StoreQueue> &model,
                           bool category_list=false);
  bool configureStore(pStoreConf store_conf, int* num_stores);
  void stopStores();
  bool throttleRequest(const std::vector<scribe::thrift::LogEntry>&  messages);
  std::shared_ptr<store_list_t>
    createNewCategory(const std::string& category);
  void addMessage(const scribe::thrift::LogEntry& entry,
                  const std::shared_ptr<store_list_t>& store_list);
};
#endif // SCRIBE_SERVER_H
// scribe-next modification: serialize the per-second throttle state independently of handler read access.
