// Test-only ThriftFileStore characterization using the actual Thrift transports.
// Licensed under the Apache License, Version 2.0; see LICENSE.
// Include after filestore_contracts.h and its existing common fixture helpers.
#ifndef SCRIBE_TEST_THRIFTFILE_CONTRACTS_H
#define SCRIBE_TEST_THRIFTFILE_CONTRACTS_H

#include <thrift/transport/TFileTransport.h>
#include <thrift/transport/TSimpleFileTransport.h>

class ThriftFileProbe : public ThriftFileStore {
 public:
  explicit ThriftFileProbe(ScribeContext& context)
      : ThriftFileStore(context, nullptr, "fallback", false) {}

  // Form protected member pointers in the derived scope and apply them to the
  // real base object returned by copy(). No layout cast or production hook.
  static std::string snapshot(ThriftFileStore& store) {
    auto* transport = (store.*(&ThriftFileProbe::thriftFileTransport)).get();
    auto* file = dynamic_cast<apache::thrift::transport::TFileTransport*>(transport);
    auto* simple = dynamic_cast<apache::thrift::transport::TSimpleFileTransport*>(transport);
    require(!transport || file || simple, "unexpected thriftfile transport");
    std::ostringstream result;
    result << "open=" << store.isOpen() << "\n"
           << "kind=" << (file ? "tfile" : simple ? "simple" : "closed") << "\n"
           << "use_simple_file=" << store.*(&ThriftFileProbe::useSimpleFile) << "\n"
           << "flush_frequency_ms=" << store.*(&ThriftFileProbe::flushFrequencyMs) << "\n"
           << "msg_buffer_size=" << store.*(&ThriftFileProbe::msgBufferSize) << "\n"
           << "current_size=" << store.*(&ThriftFileProbe::currentSize) << "\n"
           << "events_written=" << store.*(&ThriftFileProbe::eventsWritten) << "\n"
           << "filename=" << store.*(&ThriftFileProbe::currentFilename) << "\n";
    if (file) {
      result << "transport_chunk_size=" << file->getChunkSize() << "\n"
             << "transport_flush_max_us=" << file->getFlushMaxUs() << "\n"
             << "transport_event_buffer_size=" << file->getEventBufferSize() << "\n";
    }
    return result.str();
  }

  static std::string filename(ThriftFileStore& store) {
    return store.*(&ThriftFileProbe::currentFilename);
  }

  static bool simpleTransport(ThriftFileStore& store) {
    return dynamic_cast<apache::thrift::transport::TSimpleFileTransport*>(
        (store.*(&ThriftFileProbe::thriftFileTransport)).get()) != nullptr;
  }
};

struct ThriftFileFixture {
  explicit ThriftFileFixture(const std::string& filename)
      : handler(filename), config(new StoreConf), store(*handler.handler) {
    // Direct store calls need only the existing handler's counters, no workers
    // or sockets. All configuration paths are owned temporary fixture files.
    config->parseConfig(filename);
    store.configure(config, pStoreConf());
  }
  ~ThriftFileFixture() { store.close(); }
  HandlerFixture handler;
  pStoreConf config;
  ThriftFileProbe store;
};

static std::vector<LogEntry> thriftFileEntries() {
  return {entry(std::string("cat\0\xff", 5), std::string("A\0B\n\xff", 5)),
          entry("", ""), entry("tail", "ends\n")};
}

static void writeThriftFile(Store& store, const std::vector<LogEntry>& entries) {
  auto messages = fileMessages(entries);
  require(store.handleMessages(messages), "ThriftFileStore rejected small batch");
  require(messages->size() == entries.size(), "successful thriftfile write changed batch size");
  for (size_t index = 0; index < entries.size(); ++index)
    require(*messages->at(index) == entries[index], "thriftfile changed caller bytes");
  store.flush(); // Production no-op: readback happens only after normal close.
}

static void readThriftFile(const std::string& path, bool simple, unsigned long chunk,
                           const std::string& output) {
  std::string all;
  auto entries = fileMessages({});
  uint8_t bytes[128];
  unsigned reads = 0;
  if (simple) {
    apache::thrift::transport::TSimpleFileTransport reader(path, true, false);
    while (const auto count = reader.read(bytes, sizeof(bytes))) {
      require(++reads <= 8 && all.size() + count <= 256, "unbounded simple readback");
      all.append(reinterpret_cast<const char*>(bytes), count);
    }
  } else {
    apache::thrift::transport::TFileTransport reader(path, true);
    if (chunk) reader.setChunkSize(chunk);
    reader.setReadTimeout(apache::thrift::transport::TFileTransport::NO_TAIL_READ_TIMEOUT);
    while (const auto count = reader.read(bytes, sizeof(bytes))) {
      require(++reads <= 8 && all.size() + count <= 256, "unbounded event readback");
      const std::string message(reinterpret_cast<const char*>(bytes), count);
      all += message;
      entries->push_back(logentry_ptr_t(new LogEntry(entry("", message))));
    }
    require(!reader.peek(), "TFileTransport readback did not reach non-tailing EOF");
    saveEntries(output + "-events.txt", entries);
  }
  save(output + ".bin", all);
}

static void testThriftFileWrite(const std::string& filename,
                                const std::string& directory, bool chunkLimit) {
  ThriftFileFixture fixture(filename);
  require(!fixture.store.isOpen(), "configured thriftfile unexpectedly open");
  require(fixture.store.open(), "thriftfile open failed");
  save(directory + "/opened.txt", ThriftFileProbe::snapshot(fixture.store));
  writeThriftFile(fixture.store, chunkLimit ? std::vector<LogEntry>{entry("cat", "too-long!")}
                                         : thriftFileEntries());
  const auto path = ThriftFileProbe::filename(fixture.store);
  save(directory + "/written.txt", ThriftFileProbe::snapshot(fixture.store));
  fixture.store.close(); // Destroys/joins TFileTransport before any reader opens.
  require(!fixture.store.isOpen(), "thriftfile close left transport open");
  save(directory + "/closed.txt", ThriftFileProbe::snapshot(fixture.store));
  unsigned long simple = 0, chunk = 0;
  fixture.config->getUnsigned("use_simple_file", simple);
  fixture.config->getUnsigned("chunk_size", chunk);
  readThriftFile(path, simple != 0, chunk, directory + "/readback");
}

static void testThriftFileSettings(const std::string& filename,
                                   const std::string& directory) {
  ThriftFileFixture fixture(filename);
  save(directory + "/configured.txt", ThriftFileProbe::snapshot(fixture.store));
  auto copied = fixture.store.copy("copied");
  auto* copy = dynamic_cast<ThriftFileStore*>(copied.get());
  require(copy && !copy->isOpen(), "copy inherited live transport");
  save(directory + "/copy-configured.txt", ThriftFileProbe::snapshot(*copy));
  require(fixture.store.open() && copy->open(), "configured/copied thriftfile open failed");
  save(directory + "/opened.txt", ThriftFileProbe::snapshot(fixture.store));
  save(directory + "/copy-opened.txt", ThriftFileProbe::snapshot(*copy));
  fixture.store.close();
  copy->close();
  require(!fixture.store.isOpen() && !copy->isOpen(), "settings close failed");
}

static void testThriftFileCopy(const std::string& filename,
                               const std::string& directory) {
  ThriftFileFixture fixture(filename);
  writeThriftFile(fixture.store, thriftFileEntries());
  save(directory + "/written.txt", ThriftFileProbe::snapshot(fixture.store));
  const auto sourcePath = ThriftFileProbe::filename(fixture.store);
  auto copied = fixture.store.copy("copied"); // Clone an already-open model.
  auto* copy = dynamic_cast<ThriftFileStore*>(copied.get());
  require(copy && !copy->isOpen(), "copy inherited live transport");
  save(directory + "/copy-configured.txt", ThriftFileProbe::snapshot(*copy));
  writeThriftFile(*copy, thriftFileEntries());
  save(directory + "/copy-written.txt", ThriftFileProbe::snapshot(*copy));
  const auto copyPath = ThriftFileProbe::filename(*copy);
  require(sourcePath != copyPath, "copy reused source file");
  const bool copySimple = ThriftFileProbe::simpleTransport(*copy);
  copy->close();
  require(fixture.store.isOpen(), "closing copy closed source transport");
  fixture.store.close();
  require(!fixture.store.isOpen() && !copy->isOpen(), "copy close failed");
  unsigned long simple = 0, chunk = 0;
  fixture.config->getUnsigned("use_simple_file", simple);
  fixture.config->getUnsigned("chunk_size", chunk);
  readThriftFile(sourcePath, simple != 0, chunk, directory + "/source-readback");
  // Use the actual writer's mode so the before/after regression fails on bytes
  // or copied settings rather than reading a file with the wrong transport.
  readThriftFile(copyPath, copySimple, chunk, directory + "/copy-readback");
}

static void testThriftFileReopen(const std::string& filename,
                                 const std::string& directory) {
  ThriftFileFixture fixture(filename);
  unsigned long simple = 0, chunk = 0;
  fixture.config->getUnsigned("use_simple_file", simple);
  fixture.config->getUnsigned("chunk_size", chunk);
  for (unsigned pass = 0; pass < 2; ++pass) {
    require(fixture.store.open(), "thriftfile reopen failed");
    writeThriftFile(fixture.store, {entry("ignored", std::string("A\0B", 3))});
    save(directory + "/pass-" + std::to_string(pass) + ".txt",
         ThriftFileProbe::snapshot(fixture.store));
    const auto path = ThriftFileProbe::filename(fixture.store);
    fixture.store.close();
    require(!fixture.store.isOpen(), "reopen close failed");
    readThriftFile(path, simple != 0, chunk, directory + "/readback-" + std::to_string(pass));
  }
}

static bool dispatchThriftFile(const std::string& mode, const std::string& filename,
                               const std::string& directory) {
  if (mode.compare(0, 11, "thriftfile-") != 0) return false;
  alarm(10); // Bounded child lifetime, including asynchronous writer close/join.
  if (mode == "thriftfile-write") testThriftFileWrite(filename, directory, false);
  else if (mode == "thriftfile-chunk-limit") testThriftFileWrite(filename, directory, true);
  else if (mode == "thriftfile-settings") testThriftFileSettings(filename, directory);
  else if (mode == "thriftfile-copy") testThriftFileCopy(filename, directory);
  else if (mode == "thriftfile-reopen") testThriftFileReopen(filename, directory);
  else throw std::runtime_error("unknown thriftfile mode");
  alarm(0);
  return true;
}

#endif // SCRIBE_TEST_THRIFTFILE_CONTRACTS_H
