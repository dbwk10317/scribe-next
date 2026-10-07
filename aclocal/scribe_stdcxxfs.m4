# scribe-next: the library a C++17 std::filesystem program needs, substituted as STDCXXFS_LIB.
# GCC 8 keeps std::filesystem in libstdc++fs; GCC 9 and later need nothing extra.
# The caller's CXXFLAGS and LIBS are restored after the check.
# Licensed under the Apache License, Version 2.0; see LICENSE.
AC_DEFUN([SCRIBE_STDCXXFS_LIB],
[
AC_LANG_PUSH([C++])
scribe_save_CXXFLAGS=$CXXFLAGS
scribe_save_LIBS=$LIBS
# src/Makefile.am also puts -std=c++17 (AM_CXXFLAGS) before the caller's CXXFLAGS.
CXXFLAGS="-std=c++17 $CXXFLAGS"
AC_MSG_CHECKING([for the library std::filesystem needs])
for STDCXXFS_LIB in '' -lstdc++fs; do
  LIBS="$scribe_save_LIBS $STDCXXFS_LIB"
  AC_LINK_IFELSE([AC_LANG_PROGRAM([[#include <filesystem>]],
                                  [[return std::filesystem::exists("/") ? 0 : 1;]])],
                 [scribe_stdcxxfs_linked=yes], [scribe_stdcxxfs_linked=no])
  test "$scribe_stdcxxfs_linked" = yes && break
done
CXXFLAGS=$scribe_save_CXXFLAGS
LIBS=$scribe_save_LIBS
AC_LANG_POP([C++])
AS_IF([test "$scribe_stdcxxfs_linked" = yes],
      [AC_MSG_RESULT([${STDCXXFS_LIB:-none needed}])],
      [AC_MSG_ERROR([cannot link a C++17 std::filesystem program, with or without -lstdc++fs])])
AC_SUBST([STDCXXFS_LIB])
])
