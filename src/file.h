// scribe-next modification: C++17 cleanup; override, deleted copies, loss helper, no behaviour change.
// scribe-next modification: owned read buffer via nothrow new; same nomem/loss accounting.
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
// @author Avinash Lakshman
// @author Jason Sobel

#ifndef SCRIBE_FILE_H
#define SCRIBE_FILE_H

#include "common.h"
#include <memory>

class FileInterface {
 public:
  FileInterface(const std::string& name, bool framed);
  virtual ~FileInterface();

  static std::shared_ptr<FileInterface> createFileInterface(const std::string& type,
                                                              const std::string& name,
                                                              bool framed = false);
  static std::vector<std::string> list(const std::string& path, const std::string& fsType);

  virtual bool openRead() = 0;
  virtual bool openWrite() = 0;
  virtual bool openTruncate() = 0;
  virtual bool isOpen() = 0;
  virtual void close() = 0;
  virtual bool write(const std::string& data) = 0;
  virtual void flush() = 0;
  virtual unsigned long fileSize() = 0;
  virtual long readNext(std::string& _return) = 0;
  virtual void deleteFile() = 0;
  virtual void listImpl(const std::string& path, std::vector<std::string>& _return) = 0;
  virtual std::string getFrame(unsigned data_size) {return std::string();};
  virtual bool createDirectory(std::string path) = 0;
  virtual bool createSymlink(std::string oldpath, std::string newpath) = 0;

 protected:
  bool framed;
  std::string filename;

  unsigned unserializeUInt(const char* buffer);
  void serializeUInt(unsigned data, char* buffer);
};

class StdFile : public FileInterface {
 public:
  StdFile(const std::string& name, bool framed);
  virtual ~StdFile();

  bool openRead() override;
  bool openWrite() override;
  bool openTruncate() override;
  bool isOpen() override;
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
  bool open(std::ios_base::openmode mode);
  long calcLoss();

  std::unique_ptr<char[]> inputBuffer;
  unsigned bufferSize;
  std::fstream file;

  // disallow copy, assignment, and empty construction
  StdFile() = delete;
  StdFile(StdFile& rhs) = delete;
  StdFile& operator=(StdFile& rhs) = delete;
};

#endif // !defined SCRIBE_FILE_H
