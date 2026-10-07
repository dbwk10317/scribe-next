// Test-only actual FileStore/BufferStore contracts; no production API changes.
// Licensed under the Apache License, Version 2.0; see LICENSE.
// Included after the common fixture helpers in scribe_api_compat.cpp.
#ifndef SCRIBE_TEST_FILESTORE_CONTRACTS_H
#define SCRIBE_TEST_FILESTORE_CONTRACTS_H

static std::shared_ptr<logentry_vector_t> fileMessages(
    const std::vector<LogEntry>& entries) {
  std::shared_ptr<logentry_vector_t> result(new logentry_vector_t);
  for (const auto& value : entries) {
    result->push_back(logentry_ptr_t(new LogEntry(value)));
  }
  return result;
}

static std::string hexBytes(const std::string& bytes) {
  static const char digits[] = "0123456789abcdef";
  std::string result;
  for (unsigned char byte : bytes) {
    result += digits[byte >> 4];
    result += digits[byte & 15];
  }
  return result;
}

static void saveEntries(const std::string& path,
                        std::shared_ptr<logentry_vector_t> messages) {
  std::string text;
  for (const auto& value : *messages) {
    text += hexBytes(value->category) + ":" + hexBytes(value->message) + "\n";
  }
  save(path, text);
}

struct FileStoreFixture {
  explicit FileStoreFixture(const std::string& filename)
      : handlerFixture(filename), configuration(new StoreConf) {
    // Only the existing null-store worker is initialized; stop/join it before
    // file tests. The real handler remains alive for config/counter operations.
    handlerFixture.handler->initialize();
    handlerFixture.handler->stopForTest();
    configuration->parseConfig(filename);
    unsigned long framed = 1, multi = 0;
    configuration->getUnsigned("test_framed", framed);
    configuration->getUnsigned("test_multi", multi);
    store.reset(new FileStore(*handlerFixture.handler, nullptr, "fallback", multi != 0, framed != 0));
    store->configure(configuration, pStoreConf());
    now = {};
    now.tm_year = 126;
    now.tm_mon = 9;
    now.tm_mday = 4;
    // All fixtures use rotate_period=never (buffers enforce this too), so no
    // production clock/scheduler modification or sleep is needed.
  }
  ~FileStoreFixture() { store->close(); }
  HandlerFixture handlerFixture;
  pStoreConf configuration;
  std::shared_ptr<FileStore> store;
  struct tm now;
};

static void testFileStoreWrite(const std::string& config,
                               const std::string& directory) {
  FileStoreFixture fixture(config);
  const auto messages = fileMessages({
      entry(std::string("cat\0\xff", 5), std::string("A\0B\n\xff", 5)),
      entry("", ""), entry("tail", "ends\n")});
  require(fixture.store->handleMessages(messages), "FileStore write failed");
  require(messages->size() == 3, "successful write changed input batch");
  fixture.store->flush();
  fixture.store->close();
  unsigned long framed = 1;
  fixture.configuration->getUnsigned("test_framed", framed);
  if (framed) {
    auto read = fileMessages({});
    require(fixture.store->readOldest(read, &fixture.now), "read after write failed");
    saveEntries(directory + "/read.txt", read);
  }
}

static void testFileStoreReopen(const std::string& config,
                                const std::string& directory) {
  FileStoreFixture fixture(config);
  for (int pass = 0; pass < 2; ++pass) {
    auto messages = fileMessages({entry("source", std::string("A\0B", 3))});
    require(fixture.store->handleMessages(messages), "append after close failed");
    fixture.store->flush();
    fixture.store->close();
  }
  auto read = fileMessages({});
  require(fixture.store->readOldest(read, &fixture.now), "append replay failed");
  saveEntries(directory + "/read.txt", read);
}

static void testFileStoreReadDelete(const std::string& config,
                                    const std::string& directory) {
  FileStoreFixture fixture(config);
  unsigned long cycles = 1, append = 0;
  fixture.configuration->getUnsigned("test_cycles", cycles);
  fixture.configuration->getUnsigned("test_append", append);
  require(cycles <= 4, "unbounded fixture cycles");
  std::ostringstream states;
  for (unsigned long index = 0; index < cycles; ++index) {
    auto messages = fileMessages(append ? std::vector<LogEntry>{entry("sentinel", "keep")}
                                       : std::vector<LogEntry>{});
    require(fixture.store->readOldest(messages, &fixture.now), "readOldest failed");
    saveEntries(directory + "/read-" + std::to_string(index) + ".txt", messages);
    states << "before-" << index << "="
           << fixture.handlerFixture.handler->getCounter("fallback:bytes lost") << "\n";
    fixture.store->deleteOldest(&fixture.now);
    states << "after-" << index << "="
           << fixture.handlerFixture.handler->getCounter("fallback:bytes lost") << "\n";
    states << "empty-" << index << "=" << fixture.store->empty(&fixture.now) << "\n";
  }
  save(directory + "/states.txt", states.str());
}

static void testFileStoreReplace(const std::string& config,
                                 const std::string& directory) {
  FileStoreFixture fixture(config);
  auto messages = fileMessages({entry("unhandled", "remaining")});
  const bool result = fixture.store->replaceOldest(messages, &fixture.now);
  save(directory + "/states.txt", std::string("replace=") + (result ? "1" : "0") +
       "\nopen=" + (fixture.store->isOpen() ? "1" : "0") + "\n");
  require(messages->size() == 1 && messages->at(0)->message == "remaining",
          "replace mutated caller batch");
  fixture.store->close();
}

static void testFileStoreDeleteOpen(const std::string& config,
                                    const std::string& directory) {
  FileStoreFixture fixture(config);
  require(fixture.store->open(), "open writer before delete failed");
  fixture.store->deleteOldest(&fixture.now);
  const bool stillOpen = fixture.store->isOpen();
  auto later = fileMessages({entry("source", "after-unlink")});
  const bool accepted = fixture.store->handleMessages(later);
  fixture.store->flush();
  fixture.store->close();
  save(directory + "/states.txt", std::string("open-after-delete=") +
       (stillOpen ? "1" : "0") + "\nwrite-after-delete=" +
       (accepted ? "1" : "0") + "\n");
}

// Controlled primary only: the secondary is a real FileStore and periodicCheck,
// delete/replace/state transitions/counters are unchanged production methods.
class ReplayPrimary : public Store {
 public:
  ReplayPrimary(ScribeContext& context, bool partial)
      : Store(context, nullptr, "fallback", "test-primary", false), partial_(partial) {}
  std::shared_ptr<Store> copy(const std::string&) override {
    throw std::runtime_error("unused primary copy");
  }
  bool open() override { return true; }
  bool isOpen() override { return true; }
  void close() override {}
  void flush() override {}
  bool handleMessages(std::shared_ptr<logentry_vector_t> messages) override {
    received = *messages;
    if (partial_) {
      require(messages->size() == 3, "partial replay fixture expected three entries");
      accepted.push_back(messages->front());
      messages->erase(messages->begin());
      return false;
    }
    accepted.insert(accepted.end(), messages->begin(), messages->end());
    return true;
  }
  void acceptAllNext() { partial_ = false; }
  logentry_vector_t received;
  logentry_vector_t accepted;
 private:
  bool partial_;
};

class ReplayBuffer : public BufferStore {
 public:
  ReplayBuffer(ScribeContext& context, std::shared_ptr<Store> primary,
               std::shared_ptr<Store> secondary)
      : BufferStore(context, nullptr, "fallback", false) {
    primaryStore = primary;
    secondaryStore = secondary;
    // Begin at an explicit already-connected replay boundary, without a socket,
    // timer wait, or claim to cover connection/retry scheduling.
    retryIntervalRange = 1;
    changeState(SENDING_BUFFER);
    require(secondaryStore->isOpen(), "replay state must have an open secondary");
  }
  void reconnectForTest() { changeState(SENDING_BUFFER); }
  bool disconnected() const { return state == DISCONNECTED; }
  bool streaming() const { return state == STREAMING; }
};

static void testBufferReplay(const std::string& config,
                             const std::string& directory) {
  FileStoreFixture fixture(config);
  unsigned long partial = 0;
  fixture.configuration->getUnsigned("test_partial", partial);
  ScribeContext& context = *fixture.handlerFixture.handler;
  std::shared_ptr<ReplayPrimary> primary(new ReplayPrimary(context, partial != 0));
  ReplayBuffer buffer(context, primary, fixture.store);
  auto record = [&](const std::string& suffix) {
    saveEntries(directory + "/received" + suffix + ".txt",
                std::shared_ptr<logentry_vector_t>(new logentry_vector_t(primary->received)));
    saveEntries(directory + "/accepted" + suffix + ".txt",
                std::shared_ptr<logentry_vector_t>(new logentry_vector_t(primary->accepted)));
    std::ostringstream states;
    states << "lost=" << fixture.handlerFixture.handler->getCounter("fallback:lost") << "\n"
           << "bytes-lost=" << fixture.handlerFixture.handler->getCounter("fallback:bytes lost") << "\n"
           << "retries=" << fixture.handlerFixture.handler->getCounter("fallback:retries") << "\n"
           << "disconnected=" << buffer.disconnected() << "\n"
           << "streaming=" << buffer.streaming() << "\n"
           << "empty=" << fixture.store->empty(&fixture.now) << "\n";
    save(directory + "/states" + suffix + ".txt", states.str());
  };
  buffer.periodicCheck();
  record("");
  fixture.store->flush();
  std::ifstream remaining((directory + "/data/fixture_00000").c_str(), std::ios::binary);
  if (remaining) {
    const std::string bytes((std::istreambuf_iterator<char>(remaining)),
                            std::istreambuf_iterator<char>());
    save(directory + "/remaining.bin", bytes);
  }
  remaining.close();
  unsigned long resume = 0;
  fixture.configuration->getUnsigned("test_resume", resume);
  if (resume) {
    primary->acceptAllNext();
    buffer.reconnectForTest();  // Explicit readiness, not a retry timing test.
    buffer.periodicCheck();
    record("-again");
  }
  buffer.close();
}

static bool dispatchFileStore(const std::string& mode, const std::string& config,
                              const std::string& directory) {
  if (mode == "filestore-write") testFileStoreWrite(config, directory);
  else if (mode == "filestore-reopen") testFileStoreReopen(config, directory);
  else if (mode == "filestore-read-delete") testFileStoreReadDelete(config, directory);
  else if (mode == "filestore-replace") testFileStoreReplace(config, directory);
  else if (mode == "filestore-delete-open") testFileStoreDeleteOpen(config, directory);
  else if (mode == "filestore-buffer-replay") testBufferReplay(config, directory);
  else return false;
  return true;
}
#endif
