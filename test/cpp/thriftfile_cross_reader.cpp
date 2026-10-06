// Test-only bounded cross-version reader; compile against the selected Thrift runtime.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include <stdint.h> // Global fixed-width types required by the Thrift 0.9 headers.
#include <thrift/transport/TFileTransport.h>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <unistd.h>

int main(int argc, char** argv) {
  alarm(10);
  if (argc != 4) return 2;
  char* end = NULL;
  const unsigned long chunk = std::strtoul(argv[2], &end, 10);
  if (!*argv[2] || *end || chunk < 4 || chunk > 1024) return 2;
  try {
    apache::thrift::transport::TFileTransport reader(argv[1], true);
    reader.setChunkSize(chunk);
    reader.setReadTimeout(apache::thrift::transport::TFileTransport::NO_TAIL_READ_TIMEOUT);
    std::string payload;
    unsigned events = 0;
    unsigned char bytes[128];
    unsigned count;
    while ((count = reader.read(bytes, sizeof(bytes)))) {
      if (++events > 8 || payload.size() + count > 256) return 3;
      payload.append(reinterpret_cast<const char*>(bytes), count);
    }
    if (reader.peek()) return 3;
    std::ofstream output(argv[3], std::ios::out | std::ios::binary | std::ios::trunc);
    output.write(payload.data(), payload.size());
    output.close();
    if (!output) return 4;
    std::cout << "events=" << events << " bytes=" << payload.size() << "\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << "\n";
    return 1;
  }
}
