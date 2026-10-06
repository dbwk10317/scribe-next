// Actual HdfsFile source with scripted C calls: no JVM, filesystem or network.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "file.h"
#include "HdfsFile.h"
#include <cassert>
#include <iostream>

static char fsHandle, fileHandle;
static int connections, files, connects, disconnects, opens, closes, writes, flags;
static bool failOpen, failWrite, existing;
static std::string bytes;
extern "C" hdfsFS hdfsConnectNewInstance(const char* host, tPort port) {
  assert(std::string(host) == "default" && port == 0);
  ++connections; ++connects; return &fsHandle;
}
extern "C" int hdfsDisconnect(hdfsFS fs) {
  assert(fs == &fsHandle && connections > 0);
  --connections; ++disconnects; return 0;
}
extern "C" hdfsFile hdfsOpenFile(hdfsFS fs, const char* path, int value, int, short, tSize) {
  assert(fs == &fsHandle && std::string(path) == "new/path");
  ++opens; flags = value;
  if (failOpen) return nullptr;
  ++files; return &fileHandle;
}
extern "C" int hdfsCloseFile(hdfsFS fs, hdfsFile file) {
  assert(fs == &fsHandle && file == &fileHandle && files == 1);
  --files; ++closes; return 0;
}
extern "C" tSize hdfsWrite(hdfsFS fs, hdfsFile file, const void* data, tSize size) {
  assert(fs == &fsHandle && file == &fileHandle);
  ++writes; bytes.assign(static_cast<const char*>(data), size);
  return failWrite ? size - 1 : size;
}
extern "C" int hdfsFlush(hdfsFS, hdfsFile) { return 0; }
extern "C" int hdfsExists(hdfsFS, const char*) { return existing ? 0 : -1; }
extern "C" hdfsFileInfo* hdfsGetPathInfo(hdfsFS, const char*) { return nullptr; }
extern "C" void hdfsFreeFileInfo(hdfsFileInfo*, int) {}
extern "C" hdfsFileInfo* hdfsListDirectory(hdfsFS, const char*, int*) { return nullptr; }
extern "C" int hdfsDelete(hdfsFS, const char*, int) { return 0; }

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const std::string mode(argv[1]);
  failOpen = mode == "open-failure";
  failWrite = mode == "short-write";
  existing = mode == "existing";
  const std::string original("old/path\0\n\xff", 11);
  {
    HdfsFile parent("parent");
    const bool result = parent.createSymlink(original, "new/path");
    assert(result == (!failOpen && !failWrite));
    if (connections != 1 || files != 0) {
      std::cerr << "temporary HDFS resources remain: " << connections << ":" << files << std::endl;
      return 4;
    }
    assert(opens == 1 && closes == (failOpen ? 0 : 1));
    assert(writes == (failOpen ? 0 : 1));
    if (!failOpen) assert(bytes == original);
    assert(flags == (O_WRONLY | (existing ? O_APPEND : 0)));
  }
  assert(connects == 2 && disconnects == 2 && connections == 0 && files == 0);
  std::cout << "PASS " << mode << std::endl;
}
