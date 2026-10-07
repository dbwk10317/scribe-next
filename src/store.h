// scribe-next modification: C++17 cleanup; std::mutex status lock, override, deleted copies.
// scribe-next modification: std::shared_ptr/std::weak_ptr replace the internal Boost pointers; no behaviour change.
// scribe-next modification: the server context is injected (ScribeContext) instead of read from process globals; no behaviour change.
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
// @author Alex Moskalyuk
// @author Avinash Lakshman
// @author Anthony Giardullo
// @author Jan Oravec
// @author John Song

#ifndef SCRIBE_STORE_H
#define SCRIBE_STORE_H

#include "common.h" // includes std libs, thrift, and stl typedefs
#include <mutex>
#include "conf.h"
#include "file.h"
#include "conn_pool.h"
#include "store_queue.h"
#include "network_dynamic_config.h"

class StoreQueue;

/* defines used by the store class */
enum roll_period_t {
  ROLL_NEVER,
  ROLL_HOURLY,
  ROLL_DAILY,
  ROLL_OTHER
};


/*
 * Abstract class to define the interface for a store
 * and implement some basic functionality.
 */
class Store {
 public:
  // Creates an object of the appropriate subclass.
  static std::shared_ptr<Store>
    createStore(ScribeContext& context, StoreQueue* storeq,
                const std::string& type, const std::string& category,
                bool readable = false, bool multi_category = false);

  Store(ScribeContext& context, StoreQueue* storeq, const std::string& category,
        const std::string &type, bool multi_category = false);
  virtual ~Store();

  virtual std::shared_ptr<Store> copy(const std::string &category) = 0;
  virtual bool open() = 0;
  virtual bool isOpen() = 0;
  virtual void configure(pStoreConf configuration, pStoreConf parent);
  virtual void close() = 0;

  // Attempts to store messages and returns true if successful.
  // On failure, returns false and messages contains any un-processed messages
  virtual bool handleMessages(std::shared_ptr<logentry_vector_t> messages) = 0;
  virtual void periodicCheck() {}
  virtual void flush() = 0;

  virtual std::string getStatus();

  // following methods must be overidden to make a store readable
  virtual bool readOldest(/*out*/ std::shared_ptr<logentry_vector_t> messages,
                          struct tm* now);
  virtual void deleteOldest(struct tm* now);
  virtual bool replaceOldest(std::shared_ptr<logentry_vector_t> messages,
                             struct tm* now);
  virtual bool empty(struct tm* now);

  // don't need to override
  virtual const std::string& getType();

 protected:
  virtual void setStatus(const std::string& new_status);
  std::string status;
  std::string categoryHandled;
  bool multiCategory;             // Whether multiple categories are handled
  std::string storeType;

  // Don't ever take this lock for multiple stores at the same time
  std::mutex statusMutex;

  StoreQueue* storeQueue;
  ScribeContext& context;
  pStoreConf storeConf;
 private:
  // disallow copy, assignment, and empty construction
  Store(Store& rhs) = delete;
  Store& operator=(Store& rhs) = delete;
};

/*
 * Abstract class that serves as a base for file-based stores.
 * This class has logic for naming files and deciding when to rotate.
 */
class FileStoreBase : public Store {
 public:
  FileStoreBase(ScribeContext& context, StoreQueue* storeq,
                const std::string& category,
                const std::string &type, bool multi_category);
  ~FileStoreBase();

  virtual void copyCommon(const FileStoreBase *base);
  bool open() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void periodicCheck() override;

 protected:
  // We need to pass arguments to open when called internally.
  // The external open function just calls this with default args.
  virtual bool openInternal(bool incrementFilename, struct tm* current_time) = 0;
  virtual void rotateFile(time_t currentTime = 0);


  // appends information about the current file to a log file in the same
  // directory
  virtual void printStats();

  // Returns the number of bytes to pad to align to the specified block size
  unsigned long bytesToPad(unsigned long next_message_length,
                           unsigned long current_file_size,
                           unsigned long chunk_size);

  // A full filename includes an absolute path and a sequence number suffix.
  std::string makeBaseFilename(struct tm* creation_time);
  std::string makeFullFilename(int suffix, struct tm* creation_time,
                               bool use_full_path = true);
  std::string makeBaseSymlink();
  std::string makeFullSymlink();
  int  findOldestFile(const std::string& base_filename);
  int  findNewestFile(const std::string& base_filename);
  int  getFileSuffix(const std::string& filename,
                     const std::string& base_filename);
  void setHostNameSubDir();

  // Configuration
  std::string baseFilePath;
  std::string subDirectory;
  std::string filePath;
  std::string baseFileName;
  std::string baseSymlinkName;
  unsigned long maxSize;
  unsigned long maxWriteSize;
  roll_period_t rollPeriod;
  time_t rollPeriodLength;
  unsigned long rollHour;
  unsigned long rollMinute;
  std::string fsType;
  unsigned long chunkSize;
  bool writeMeta;
  bool writeCategory;
  bool createSymlink;
  bool writeStats;
  bool rotateOnReopen;

  // State
  unsigned long currentSize;
  time_t lastRollTime;         // either hour, day or time since epoch,
                               // depending on rollPeriod
  std::string currentFilename; // this isn't used to choose the next file name,
                               // we just need it for reporting
  unsigned long eventsWritten; // This is how many events this process has
                               // written to the currently open file. It is NOT
                               // necessarily the number of lines in the file

 private:
  // disallow copy, assignment, and empty construction
  FileStoreBase(FileStoreBase& rhs) = delete;
  FileStoreBase& operator=(FileStoreBase& rhs) = delete;
};

/*
 * This file-based store uses an instance of a FileInterface class that
 * handles the details of interfacing with the filesystem. (see file.h)
 */
class FileStore : public FileStoreBase {

 public:
  FileStore(ScribeContext& context, StoreQueue* storeq, const std::string& category,
            bool multi_category, bool is_buffer_file = false);
  ~FileStore();

  std::shared_ptr<Store> copy(const std::string &category) override;
  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override;
  bool isOpen() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void close() override;
  void flush() override;

  // Each read does its own open and close and gets the whole file.
  // This is separate from the write file, and not really a consistent
  // interface.
  bool readOldest(/*out*/ std::shared_ptr<logentry_vector_t> messages,
                  struct tm* now) override;
  virtual bool replaceOldest(std::shared_ptr<logentry_vector_t> messages,
                             struct tm* now) override;
  void deleteOldest(struct tm* now) override;
  bool empty(struct tm* now) override;

 protected:
  // Implement FileStoreBase virtual function
  bool openInternal(bool incrementFilename, struct tm* current_time) override;
  bool writeMessages(std::shared_ptr<logentry_vector_t> messages,
                     std::shared_ptr<FileInterface> write_file =
                     std::shared_ptr<FileInterface>());

  bool isBufferFile;
  bool addNewlines;

  // State
  std::shared_ptr<FileInterface> writeFile;

 private:
  // disallow copy, assignment, and empty construction
  FileStore(FileStore& rhs) = delete;
  FileStore& operator=(FileStore& rhs) = delete;
  long lostBytes_;
};

/*
 * This file-based store relies on thrift's TFileTransport to do the writing
 */
class ThriftFileStore : public FileStoreBase {
 public:
  ThriftFileStore(ScribeContext& context, StoreQueue* storeq,
                  const std::string& category,
                  bool multi_category);
  ~ThriftFileStore();

  std::shared_ptr<Store> copy(const std::string &category) override;
  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override;
  bool open() override;
  bool isOpen() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void close() override;
  void flush() override;
  bool createFileDirectory();

 protected:
  // Implement FileStoreBase virtual function
  bool openInternal(bool incrementFilename, struct tm* current_time) override;

  std::shared_ptr<apache::thrift::transport::TTransport> thriftFileTransport;

  unsigned long flushFrequencyMs;
  unsigned long msgBufferSize;
  unsigned long useSimpleFile;

 private:
  // disallow copy, assignment, and empty construction
  ThriftFileStore(ThriftFileStore& rhs) = delete;
  ThriftFileStore& operator=(ThriftFileStore& rhs) = delete;
};

/*
 * This store aggregates messages and sends them to another store
 * in larger groups. If it is unable to do this it saves them to
 * a secondary store, then reads them and sends them to the
 * primary store when it's back online.
 *
 * This actually involves two buffers. Messages are always buffered
 * briefly in memory, then they're buffered to a secondary store if
 * the primary store is down.
 */
class BufferStore : public Store {

 public:
  BufferStore(ScribeContext& context, StoreQueue* storeq,
              const std::string& category,
              bool multi_category);
  ~BufferStore();

  std::shared_ptr<Store> copy(const std::string &category) override;
  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override;
  bool open() override;
  bool isOpen() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void close() override;
  void flush() override;
  void periodicCheck() override;

  std::string getStatus() override;

 protected:
  // Store we're trying to get the messages to
  std::shared_ptr<Store> primaryStore;

  // Store to use as a buffer if the primary is unavailable.
  // The store must be of a type that supports reading.
  std::shared_ptr<Store> secondaryStore;

  // buffer state machine
  enum buffer_state_t {
    STREAMING,       // connected to primary and sending directly
    DISCONNECTED,    // disconnected and writing to secondary
    SENDING_BUFFER,  // connected to primary and sending data from secondary
  };

  // handles state pre and post conditions
  void changeState(buffer_state_t new_state);
  const char* stateAsString(buffer_state_t state);

  void setNewRetryInterval(bool);

  // configuration
  unsigned long bufferSendRate;   // number of buffer files
                                  // sent each periodicCheck
  time_t avgRetryInterval;        // in seconds, for retrying primary store open
  time_t retryIntervalRange;      // in seconds
  bool   replayBuffer;            // whether to send buffers from
                                  // secondary store to primary
  bool adaptiveBackoff;           // Adaptive backoff mode indicator
  unsigned long minRetryInterval; // The min the retryInterval can become
  unsigned long maxRetryInterval; // The max the retryInterval can become
  unsigned long maxRandomOffset;  // The max random offset added
                                  // to the retry interval


  // state
  time_t retryInterval;           // the current retry interval in seconds
  unsigned long numContSuccess;   // number of continuous successful sends
  buffer_state_t state;
  time_t lastOpenAttempt;

  bool flushStreaming;            // When flushStreaming is set to true,
                                  // incoming messages to a buffere store
                                  // that still has buffereed data in the
                                  // secondary store, i.e. buffer store in
                                  // SENDING_BUFFER phase, will be sent to the
                                  // primary store directly.  If false,
                                  // then in coming messages will first
                                  // be written to secondary store, and
                                  // later flushed out to the primary
                                  // store.

  double maxByPassRatio;          // During the buffer flushing phase, if
                                  // flushStreaming is enabled, the max
                                  // size of message queued before buffer
                                  // flushing yielding to sending current
                                  // incoming messages is calculated by
                                  // multiple max_queue_size with
                                  // buffer_bypass_max_ratio.

 private:
  // disallow copy, assignment, and empty construction
  BufferStore() = delete;
  BufferStore(BufferStore& rhs) = delete;
  BufferStore& operator=(BufferStore& rhs) = delete;
};

/*
 * This store sends messages to another scribe server.
 * This class is really just an adapter to the connection
 * pool of its server context.
 */
class NetworkStore : public Store {

 public:
  NetworkStore(ScribeContext& context, StoreQueue* storeq,
               const std::string& category,
               bool multi_category);
  ~NetworkStore();

  std::shared_ptr<Store> copy(const std::string &category) override;
  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override;
  bool open() override;
  bool isOpen() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void close() override;
  void flush() override;
  void periodicCheck() override;

 protected:
  static const long int DEFAULT_SOCKET_TIMEOUT_MS = 5000; // 5 sec timeout
  bool loadFromList(const std::string &list, unsigned long defaultPort,
                    server_vector_t& _return);

  // configuration
  bool useConnPool;
  bool serviceBased;
  bool listBased;
  long int timeout;
  std::string remoteHost;
  unsigned long remotePort; // long because it works with config code
  std::string serviceName;
  std::string serviceList;
  unsigned long serviceListDefaultPort;
  std::string serviceOptions;
  server_vector_t servers;
  unsigned long serviceCacheTimeout;
  time_t lastServiceCheck;
  // if true do not update status to reflect failure to connect
  bool ignoreNetworkError;
  NetworkDynamicConfigMod* configmod;

  // state
  bool opened;
  std::shared_ptr<scribeConn> unpooledConn; // null if useConnPool

 private:
  // disallow copy, assignment, and empty construction
  NetworkStore() = delete;
  NetworkStore(NetworkStore& rhs) = delete;
  NetworkStore& operator=(NetworkStore& rhs) = delete;
};

/*
 * This store separates messages into many groups based on a
 * hash function, and sends each group to a different store.
 */
class BucketStore : public Store {

 public:
  BucketStore(ScribeContext& context, StoreQueue* storeq,
              const std::string& category,
              bool multi_category);
  ~BucketStore();

  std::shared_ptr<Store> copy(const std::string &category) override;
  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override;
  bool open() override;
  bool isOpen() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void close() override;
  void flush() override;
  void periodicCheck() override;

  std::string getStatus() override;

 protected:
  enum bucketizer_type {
    context_log,
    random,      // randomly hash messages without using any key
    key_hash,    // use hashing to split keys into buckets
    key_modulo,  // use modulo to split keys into buckets
    key_range    // use bucketRange to compute modulo to split keys into buckets
  };

  bucketizer_type bucketType;
  char delimiter;
  bool removeKey;
  bool opened;
  unsigned long bucketRange;  // used to compute key_range bucketizing
  unsigned long numBuckets;
  std::vector<std::shared_ptr<Store> > buckets;

  unsigned long bucketize(const std::string& message);
  std::string getMessageWithoutKey(const std::string& message);

 private:
  // disallow copy, assignment, and emtpy construction
  BucketStore() = delete;
  BucketStore(BucketStore& rhs) = delete;
  BucketStore& operator=(BucketStore& rhs) = delete;
  void createBucketsFromBucket(pStoreConf configuration,
                               pStoreConf bucket_conf);
  void createBuckets(pStoreConf configuration);
};

/*
 * This store intentionally left blank.
 */
class NullStore : public Store {

 public:
  NullStore(ScribeContext& context, StoreQueue* storeq,
            const std::string& category,
            bool multi_category);
  virtual ~NullStore();

  std::shared_ptr<Store> copy(const std::string &category) override;
  bool open() override;
  bool isOpen() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void close() override;

  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override;
  void flush() override;

  // null stores are readable, but you never get anything
  virtual bool readOldest(std::shared_ptr<logentry_vector_t> messages,
                          struct tm* now) override;
  virtual bool replaceOldest(std::shared_ptr<logentry_vector_t> messages,
                             struct tm* now) override;
  virtual void deleteOldest(struct tm* now) override;
  virtual bool empty(struct tm* now) override;


 private:
  // disallow empty constructor, copy and assignment
  NullStore() = delete;
  NullStore(NullStore& rhs) = delete;
  NullStore& operator=(NullStore& rhs) = delete;
};

/*
 * This store relays messages to n other stores
 * @author Joel Seligstein
 */
class MultiStore : public Store {
 public:
  MultiStore(ScribeContext& context, StoreQueue* storeq,
             const std::string& category,
             bool multi_category);
  ~MultiStore();

  std::shared_ptr<Store> copy(const std::string &category) override;
  bool open() override;
  bool isOpen() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void close() override;

  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override;
  void periodicCheck() override;
  void flush() override;

  // read won't make sense since we don't know which store to read from
  bool readOldest(/*out*/ std::shared_ptr<logentry_vector_t> messages,
                  struct tm* now) override { return false; }
  void deleteOldest(struct tm* now) override {}
  bool empty(struct tm* now) override { return true; }

 protected:
  std::vector<std::shared_ptr<Store> > stores;
  enum report_success_value {
    SUCCESS_ANY = 1,
    SUCCESS_ALL
  };
  report_success_value report_success;

 private:
  // disallow copy, assignment, and empty construction
  MultiStore() = delete;
  MultiStore(MultiStore& rhs) = delete;
  MultiStore& operator=(MultiStore& rhs) = delete;
};


/*
 * This store will contain a separate store for every distinct
 * category it encounters.
 *
 */
class CategoryStore : public Store {
 public:
  CategoryStore(ScribeContext& context, StoreQueue* storeq,
                const std::string& category,
                bool multi_category);
  CategoryStore(ScribeContext& context, StoreQueue* storeq,
                const std::string& category,
                const std::string& name, bool multiCategory);
  ~CategoryStore();

  std::shared_ptr<Store> copy(const std::string &category) override;
  bool open() override;
  bool isOpen() override;
  void configure(pStoreConf configuration, pStoreConf parent) override;
  void close() override;

  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override;
  void periodicCheck() override;
  void flush() override;

 protected:
  void configureCommon(pStoreConf configuration, pStoreConf parent,
                       const std::string type);
  std::shared_ptr<Store> modelStore;
  std::map<std::string, std::shared_ptr<Store> > stores;

 private:
  CategoryStore() = delete;
  CategoryStore(CategoryStore& rhs) = delete;
  CategoryStore& operator=(CategoryStore& rhs) = delete;
};

/*
 * MultiFileStore is similar to FileStore except that it uses a separate file
 * for every category.  This is useful only if this store can handle mutliple
 * categories.
 */
class MultiFileStore : public CategoryStore {
 public:
  MultiFileStore(ScribeContext& context, StoreQueue* storeq,
                const std::string& category,
                bool multi_category);
  ~MultiFileStore();
  void configure(pStoreConf configuration, pStoreConf parent) override;

 private:
  MultiFileStore() = delete;
  MultiFileStore(MultiFileStore& rhs) = delete;
  MultiFileStore& operator=(MultiFileStore& rhs) = delete;
};

/*
 * ThriftMultiFileStore is similar to ThriftFileStore except that it uses a
 * separate thrift file for every category.  This is useful only if this store
 * can handle mutliple categories.
 */
class ThriftMultiFileStore : public CategoryStore {
 public:
  ThriftMultiFileStore(ScribeContext& context, StoreQueue* storeq,
                       const std::string& category,
                       bool multi_category);
  ~ThriftMultiFileStore();
  void configure(pStoreConf configuration, pStoreConf parent) override;


 private:
  ThriftMultiFileStore() = delete;
  ThriftMultiFileStore(ThriftMultiFileStore& rhs) = delete;
  ThriftMultiFileStore& operator=(ThriftMultiFileStore& rhs) = delete;
};
#endif // SCRIBE_STORE_H
