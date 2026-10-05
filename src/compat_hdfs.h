// Preserve the legacy libhdfs delete(Path) recursive behavior across C API arities.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_COMPAT_HDFS_H
#define SCRIBE_COMPAT_HDFS_H

namespace scribe {
template <class FileSystem>
inline void hdfsDeleteCompat(int (*remove)(FileSystem, const char*),
                             FileSystem fs, const char* path) {
  (void)remove(fs, path);
}

template <class FileSystem>
inline void hdfsDeleteCompat(int (*remove)(FileSystem, const char*, int),
                             FileSystem fs, const char* path) {
  (void)remove(fs, path, 1);
}
} // namespace scribe
#endif
