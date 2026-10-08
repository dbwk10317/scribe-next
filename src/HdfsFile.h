// scribe-next modification: return an empty string from the unavailable HDFS stub.
// scribe-next modification: C++17 cleanup; override, deleted copies, stub tidy-up; unused HdfsLock class, inputBuffer_/bufferSize_ members and the undefined init() declaration removed.
// Copyright (c) 2009- Facebook
// Distributed under the Scribe Software License
//
// See accompanying file LICENSE or visit the Scribe site at:
// http://developers.facebook.com/scribe/
//
#ifndef HDFS_FILE_H
#define HDFS_FILE_H

#ifdef USE_SCRIBE_HDFS
#include "hdfs.h"

class HdfsFile : public FileInterface {
 public:
  explicit HdfsFile(const std::string& name);
  virtual ~HdfsFile();

  bool openRead() override;  // open for reading file
  bool openWrite() override; // open for appending to file
  bool openTruncate() override; // truncate and open for write
  bool isOpen() override;    // is file open?
  void close() override;
  bool write(const std::string& data) override;
  void flush() override;
  unsigned long fileSize() override;
  long readNext(std::string& _return) override;
  void deleteFile() override;
  void listImpl(const std::string& path, std::vector<std::string>& _return) override;
  std::string getFrame(unsigned data_size) override;
  bool createDirectory(std::string path) override;
  bool createSymlink(std::string oldpath, std::string newpath) override;

 private:
  hdfsFS fileSys;
  hdfsFile hfile;
  hdfsFS connectToPath(const char* uri);

  // disallow copy, assignment, and empty construction
  HdfsFile() = delete;
  HdfsFile(HdfsFile& rhs) = delete;
  HdfsFile& operator=(HdfsFile& rhs) = delete;
};

#else

class HdfsFile : public FileInterface {
 public:
  explicit HdfsFile(const std::string& name) : FileInterface(name, false) {
    LOG_OPER("[hdfs] ERROR: HDFS is not supported.  file: %s", name.c_str());
    LOG_OPER("[hdfs] If you want HDFS Support, please recompile scribe with HDFS support");
  }
  static void init() {};
  bool openRead() override { return false; };  // open for reading file
  bool openWrite() override { return false; }; // open for appending to file
  bool openTruncate() override { return false; } // open for write and truncate
  bool isOpen() override { return false; };    // is file open?
  void close() override {};
  bool write(const std::string& data) override { return false; };
  void flush() override {};
  unsigned long fileSize() override { return 0; };
  long readNext(std::string& _return) override { return 0; };
  void deleteFile() override {};
  void listImpl(const std::string& path, std::vector<std::string>& _return) override {};
  std::string getFrame(unsigned data_size) override { return std::string(); };
  bool createDirectory(std::string path) override { return false; };
  bool createSymlink(std::string oldpath, std::string newpath) override { return false; };
};
#endif // USE_SCRIBE_HDFS

#endif // HDFS_FILE_H
