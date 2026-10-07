#!/usr/bin/env python3
"""Compile actual ConnPool methods with deterministic transport-free connection stubs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ConnPoolConcurrencyTests(unittest.TestCase):
    def test_send_reopen_identity_refcounts_and_exception_unlock(self):
        names = ("THRIFT_PREFIX", "FB303_PREFIX", "SCRIBE_BUILD", "TOOLS_PREFIX")
        if any(not os.environ.get(name) for name in names):
            self.skipTest("requires prepared matching Thrift/fb303/build/tools")
        thrift, fb303, build, tools = (Path(os.environ[name]) for name in names)
        includes = [ROOT / "src", build, thrift / "include", thrift / "include/thrift",
                    fb303 / "include/thrift", fb303 / "include/thrift/fb303", tools / "include"]
        libs = [thrift / "lib", fb303 / "lib", tools / "lib",
                *sorted((tools / "lib").glob("*-linux-gnu"))]
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = os.pathsep.join(map(str, libs))
        with tempfile.TemporaryDirectory(prefix="scribe-pool-concurrency-") as directory:
            work = Path(directory)
            # The exact production pool methods are exercised; every scribeConn method
            # (constructors, refcounts, lock/unlock and I/O) is a fixture stub.
            source = (ROOT / "src/conn_pool.cpp").read_text()
            boundary = "scribeConn::scribeConn("
            self.assertIn(boundary, source)
            (work / "pool.cpp").write_text(source.split(boundary, 1)[0])
            command = ["g++", "-std=c++17", "-O0", "-g", "-pthread",
                       *("-I" + str(path) for path in includes), work / "pool.cpp",
                       ROOT / "test/cpp/conn_pool_concurrency.cpp",
                       *("-L" + str(path) for path in libs), "-lthrift", "-lfb303",
                       "-o", work / "probe"]
            compiled = subprocess.run(list(map(str, command)), env=env, capture_output=True,
                                      text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            for mode in ("concurrent", "exception"):
                with self.subTest(mode=mode):
                    run = subprocess.run([work / "probe", mode], env=env, capture_output=True,
                                         text=True, timeout=10)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    self.assertIn("checks_passed=1" if mode=="concurrent" else
                                  "PASS exception", run.stdout)

if __name__ == "__main__":
    unittest.main()
