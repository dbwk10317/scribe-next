// Minimal scripted C API for the HdfsFile lifetime component test, not JNI/libhdfs.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_TEST_HDFS_MOCK_H
#define SCRIBE_TEST_HDFS_MOCK_H
#include <stdint.h>
#include <cstring>
#include <fcntl.h>
#include <pthread.h>
extern "C" {
typedef void* hdfsFS;
typedef void* hdfsFile;
typedef int32_t tSize;
typedef int16_t tPort;
typedef int64_t tOffset;
struct hdfsFileInfo { tOffset mSize; char* mName; };
hdfsFS hdfsConnectNewInstance(const char*, tPort);
int hdfsDisconnect(hdfsFS);
hdfsFile hdfsOpenFile(hdfsFS, const char*, int, int, short, tSize);
int hdfsCloseFile(hdfsFS, hdfsFile);
tSize hdfsWrite(hdfsFS, hdfsFile, const void*, tSize);
int hdfsFlush(hdfsFS, hdfsFile);
int hdfsExists(hdfsFS, const char*);
hdfsFileInfo* hdfsGetPathInfo(hdfsFS, const char*);
void hdfsFreeFileInfo(hdfsFileInfo*, int);
hdfsFileInfo* hdfsListDirectory(hdfsFS, const char*, int*);
int hdfsDelete(hdfsFS, const char*, int);
}
#endif
