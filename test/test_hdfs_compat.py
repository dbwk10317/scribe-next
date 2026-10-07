#!/usr/bin/env python3
"""Exercise both official libhdfs delete API shapes without a Hadoop install."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def filesystem_libs(compiler, directory):
    """Same choice as configure: GCC 8 needs -lstdc++fs for std::filesystem, GCC 9 and later do not."""
    source = Path(directory) / "filesystem-probe.cpp"
    source.write_text('#include <filesystem>\nint main() { return std::filesystem::exists("/") ? 0 : 1; }\n')
    linked = subprocess.run([str(compiler), "-std=c++17", str(source), "-o", str(source.with_suffix(""))],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    return [] if linked.returncode == 0 else ["-lstdc++fs"]


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


class HdfsLinkLifetimeTests(unittest.TestCase):
    def test_temporary_link_releases_object_and_native_handles(self):
        prefix = os.environ.get("TOOLS_PREFIX")
        compiler = shutil.which("g++")
        if not prefix or not compiler:
            self.skipTest("actual HdfsFile component unrun; set TOOLS_PREFIX and provide g++")
        tools = Path(prefix).resolve()
        libraries = [tools / "lib", *sorted((tools / "lib").glob("*-linux-gnu"))]
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = os.pathsep.join(map(str, libraries))
        env["ASAN_OPTIONS"] = "halt_on_error=1:alloc_dealloc_mismatch=1:detect_leaks=1"
        env["LSAN_OPTIONS"] = "exitcode=23"
        env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        with tempfile.TemporaryDirectory(prefix="scribe-hdfs-lifetime-") as directory:
            work = Path(directory)
            for name in ("file.cpp", "file.h", "HdfsFile.cpp", "HdfsFile.h", "compat_hdfs.h"):
                shutil.copyfile(ROOT / "src" / name, work / name)
            shutil.copyfile(ROOT / "test/cpp/spool_component_common.h", work / "common.h")
            fs_libs = filesystem_libs(compiler, work)
            for sanitized in (False, True):
                binary = work / ("sanitized" if sanitized else "ordinary")
                flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if sanitized else []
                command = [compiler, "-std=c++17", "-O1", "-g", "-DUSE_SCRIBE_HDFS", *flags,
                           "-I", str(work), "-I", str(ROOT / "test/fixtures/hdfs_mock"),
                           "-I", str(tools / "include"), str(work / "file.cpp"),
                           str(work / "HdfsFile.cpp"), str(ROOT / "test/cpp/hdfs_link_lifetime.cpp"),
                           *("-L" + str(path) for path in libraries), *fs_libs,
                           "-o", str(binary)]
                compiled = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT, timeout=90)
                self.assertEqual(compiled.returncode, 0, compiled.stdout)
                for mode in ("success", "existing", "open-failure", "short-write"):
                    with self.subTest(sanitized=sanitized, mode=mode):
                        executed = subprocess.run([binary, mode], env=env, text=True,
                                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
                        self.assertEqual(executed.returncode, 0, executed.stdout)
                        self.assertIn("PASS " + mode, executed.stdout)


if __name__ == "__main__":
    unittest.main()
