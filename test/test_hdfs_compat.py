#!/usr/bin/env python3
"""Exercise both official libhdfs delete API shapes without a Hadoop install."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HdfsDeleteCompatibilityTests(unittest.TestCase):
    def check_api(self, modern):
        compiler = shutil.which("g++")
        if compiler is None:
            self.skipTest("libhdfs API probe unrun; missing g++")
        extra = ", int recursive" if modern else ""
        recursive_check = "assert(recursive == 1);" if modern else ""
        source = '''#include <cassert>
#include "compat_hdfs.h"
struct FileSystem {}; using hdfsFS = FileSystem*;
static hdfsFS expected; static const char* expected_path; static int calls, result;
extern "C" int hdfsDelete(hdfsFS fs, const char* path%s) {
  assert(fs == expected && path == expected_path); %s ++calls; return result;
}
int main() {
  FileSystem fs; const char path[] = "original/path";
  expected = &fs; expected_path = path;
  for (int value : {0, -1}) {
    result = value; calls = 0;
    scribe::hdfsDeleteCompat(&hdfsDelete, expected, expected_path);
    assert(calls == 1);
  }
}
''' % (extra, recursive_check)
        source = '#include <initializer_list>\n' + source
        with tempfile.TemporaryDirectory(prefix="scribe-hdfs-api-") as directory:
            path = Path(directory)
            (path / "probe.cpp").write_text(source)
            compiled = subprocess.run(
                [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                 str(path / "probe.cpp"), "-o", str(path / "probe")],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout)
            executed = subprocess.run([str(path / "probe")], text=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stdout)

    def test_historical_two_argument_api(self):
        self.check_api(False)

    def test_modern_three_argument_api_preserves_recursive_delete(self):
        self.check_api(True)


if __name__ == "__main__":
    unittest.main()
