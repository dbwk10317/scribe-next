#!/usr/bin/env python3
"""Compile actual ConnPool methods with deterministic transport-free connection stubs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ConnPoolConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("THRIFT_PREFIX", "FB303_PREFIX", "SCRIBE_BUILD", "TOOLS_PREFIX")
        if any(not os.environ.get(name) for name in names):
            raise unittest.SkipTest("requires prepared matching Thrift/fb303/build/tools")
        thrift, fb303, build, tools = (Path(os.environ[name]) for name in names)
        includes = [ROOT / "src", build, thrift / "include", thrift / "include/thrift",
                    fb303 / "include/thrift", fb303 / "include/thrift/fb303", tools / "include"]
        libs = [thrift / "lib", fb303 / "lib", tools / "lib",
                *sorted((tools / "lib").glob("*-linux-gnu"))]
        cls.env = dict(os.environ)
        cls.env["LD_LIBRARY_PATH"] = os.pathsep.join(map(str, libs))
        temporary = tempfile.TemporaryDirectory(prefix="scribe-pool-concurrency-")
        cls.addClassCleanup(temporary.cleanup)
        work = Path(temporary.name)
        # The exact production pool methods are exercised; every scribeConn method
        # (constructors, refcounts, lock/unlock and I/O) is a fixture stub.
        source = (ROOT / "src/conn_pool.cpp").read_text()
        boundary = "scribeConn::scribeConn("
        if boundary not in source:
            raise AssertionError("conn_pool.cpp no longer has the scribeConn boundary")
        (work / "pool.cpp").write_text(source.split(boundary, 1)[0])
        cls.probe = work / "probe"
        command = ["g++", "-std=c++17", "-O0", "-g", "-pthread",
                   *("-I" + str(path) for path in includes), work / "pool.cpp",
                   ROOT / "test/cpp/conn_pool_concurrency.cpp",
                   *("-L" + str(path) for path in libs), "-lthrift", "-lfb303",
                   "-o", cls.probe]
        compiled = subprocess.run(list(map(str, command)), env=cls.env, capture_output=True,
                                  text=True, timeout=60)
        if compiled.returncode:
            raise AssertionError(compiled.stdout + compiled.stderr)

    def run_probe(self, mode, expected):
        run = subprocess.run([self.probe, mode], env=self.env, capture_output=True,
                             text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn(expected, run.stdout)

    def test_send_reopen_identity_refcounts_and_exception_unlock(self):
        for mode, expected in (("concurrent", "checks_passed=1"), ("exception", "PASS exception")):
            with self.subTest(mode=mode):
                self.run_probe(mode, expected)

    def test_open_of_another_key_does_not_wait_for_a_stalled_send(self):
        # openCommon must not wait for a connection lock while holding the map lock.
        self.run_probe("liveness", "other_open_fast=1 checks_passed=1")

if __name__ == "__main__":
    unittest.main()
