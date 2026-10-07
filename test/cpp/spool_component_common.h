// Minimal non-HDFS include boundary for the isolated StdFile component tests.
// Licensed under the Apache License, Version 2.0; see LICENSE.
// Both source versions use the same real Boost/filesystem and C++ file streams.
// Only diagnostics and unrelated Thrift/server declarations are omitted.
#ifndef SCRIBE_TEST_SPOOL_COMPONENT_COMMON_H
#define SCRIBE_TEST_SPOOL_COMPONENT_COMMON_H
#include <fstream>
#include <string>
#include <vector>
#include <limits.h>
#include <stdlib.h>
#include <unistd.h>
#include <boost/version.hpp>
#if __cplusplus < 201103L // only the pinned C++03 upstream file.h/file.cpp use the Boost pointer
#include <boost/shared_ptr.hpp>
#endif
#include <boost/filesystem/operations.hpp>
#include <boost/filesystem/convenience.hpp>
inline void LOG_OPER(const char*, ...) {}

#endif // SCRIBE_TEST_SPOOL_COMPONENT_COMMON_H
