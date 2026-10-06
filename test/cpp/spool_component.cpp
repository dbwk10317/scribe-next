// Bounded command-line fixture for actual legacy/current StdFile source.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "file.h"
#include "HdfsFile.h"
#include <iostream>
#include <iomanip>
#include <iterator>
#include <sstream>

static std::string hex(const std::string& bytes) {
  std::ostringstream result;
  result << std::hex << std::setfill('0');
  for (std::string::const_iterator it = bytes.begin(); it != bytes.end(); ++it) {
    result << std::setw(2) << static_cast<unsigned>(static_cast<unsigned char>(*it));
  }
  return result.str();
}

int main(int argc, char** argv) {
  if (argc < 3) return 2;
  const std::string mode(argv[1]);
  if (mode == "non-hdfs-frame") {
    HdfsFile unsupported("unused");
    std::cout << hex(unsupported.getFrame(static_cast<unsigned>(strtoul(argv[2], NULL, 10))))
              << ":" << unsupported.openWrite() << ":" << unsupported.isOpen() << std::endl;
    return 0;
  }
  if (mode == "frame") {
    StdFile framed("unused", true);
    StdFile unframed("unused", false);
    const unsigned length = static_cast<unsigned>(strtoul(argv[2], NULL, 10));
    std::cout << hex(framed.getFrame(length)) << ":"
              << hex(unframed.getFrame(length)) << std::endl;
    return 0;
  }
  if (mode == "truncate") {
    StdFile output(argv[2], true);
    std::cout << output.openTruncate() << ":" << output.isOpen() << std::endl;
    output.close();
    return 0;
  }
  if (mode == "write") {
    StdFile output(argv[2], true);
    if (!output.openWrite()) return 3;
    for (int index = 3; index < argc; ++index) {
      std::ifstream input(argv[index], std::ios::binary);
      if (!input) return 4;
      const std::string payload((std::istreambuf_iterator<char>(input)),
                                std::istreambuf_iterator<char>());
      if (!output.write(output.getFrame(payload.size())) || !output.write(payload)) return 5;
    }
    output.flush();
    output.close();
    return 0;
  }
  if (mode == "read" || mode == "read-without-destruction") {
    if (argc != 4) return 2;
    const int count = atoi(argv[3]);
    if (count < 1 || count > 10) return 2;
    StdFile input(argv[2], true);
    if (!input.openRead()) return 3;
    std::string payload("sentinel");
    for (int index = 0; index < count; ++index) {
      const long length = input.readNext(payload);
      std::cout << length << ":" << hex(payload) << std::endl;
    }
    input.close();
    if (mode == "read-without-destruction") {
      // The raw legacy destructor has independently tested malloc/delete[] UB.
      // Close the file and flush results before process exit, isolating format
      // comparison from that defect. Never use this mode for the fixed reader.
      std::cout.flush();
      _exit(0);
    }
    return 0;
  }
  return 2;
}
