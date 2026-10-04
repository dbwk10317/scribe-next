#!/usr/bin/env python3
"""Compile and exercise the real POSIX mutex compatibility boundary.

This instrumentation lane is Linux-only; Apple ld lacks GNU --wrap.
No Thrift installation or Scribe process is needed. The fixture is compiled in
a temporary directory, with and without NDEBUG; each behavioral case runs in its
own bounded process. GNU linker's pthread wrappers observe contention without
replacing the real lock operations or relying on sleeps to observe a held lock.
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MutexCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not sys.platform.startswith("linux"):
            raise unittest.SkipTest("Linux GNU --wrap mutex fixture unrun on " + sys.platform)
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest("real mutex compatibility tests unrun; missing g++")
        temporary = tempfile.TemporaryDirectory(prefix="scribe-mutex-compat-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.executables = {}
        for mode, flags in (("assertions", []), ("ndebug", ["-DNDEBUG"])):
            executable = cls.root / ("mutex-compat-" + mode)
            result = subprocess.run(
                [compiler, "-std=c++17", "-pthread", "-Wall", "-Wextra", *flags,
                 "-I", str(ROOT / "src"),
                 str(ROOT / "test/mutex_compat_fixture.cpp"),
                 "-Wl,--wrap=pthread_rwlock_rdlock",
                 "-Wl,--wrap=pthread_rwlock_wrlock",
                 "-o", str(executable)],
                cwd=cls.root, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"mutex fixture compilation failed ({mode}):\n" + result.stdout
                )
            cls.executables[mode] = executable

    def run_case(self, case):
        for mode, executable in self.executables.items():
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [str(executable), case], cwd=self.root, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stdout, case + ": OK\n")

    def test_default_guard_allows_concurrent_readers(self):
        self.run_case("concurrent-readers")

    def test_explicit_write_guard_excludes_reader_and_writer_until_release(self):
        self.run_case("exclusive-writer")

    def test_recursive_read_locks_require_matching_releases(self):
        self.run_case("recursive-readers")

    def test_exception_unwinding_releases_read_and_write_guards(self):
        self.run_case("exception-release")

    def test_manual_read_release_write_release_is_not_atomic_upgrade(self):
        self.run_case("manual-transition")

    def test_mutex_and_guard_are_noncopyable(self):
        self.run_case("noncopyable")


if __name__ == "__main__":
    unittest.main()
