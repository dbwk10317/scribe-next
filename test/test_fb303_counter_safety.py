"""Real prepared fb303 counter contracts and bounded allocation failures."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Fb303CounterSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("THRIFT_PREFIX", "FB303_PREFIX", "TOOLS_PREFIX")
        if any(not os.environ.get(name) for name in names):
            raise unittest.SkipTest("provide prepared " + ", ".join(names))
        thrift, fb303, tools = (Path(os.environ[n]) for n in names)
        temporary = tempfile.TemporaryDirectory(prefix="fb303-counter-safety-")
        cls.addClassCleanup(temporary.cleanup)
        cls.binary = Path(temporary.name) / "fixture"
        includes = (thrift / "include", thrift / "include/thrift", fb303 / "include/thrift/fb303",
                    tools / "include")
        command = [*shlex.split(os.environ.get("CXX", "g++")), "-std=c++17", "-O0", "-g", "-pthread",
                   *("-I" + str(p) for p in includes), str(ROOT / "test/cpp/fb303_counter_safety.cpp"),
                   str(fb303 / "lib/libfb303.a"), "-L" + str(thrift / "lib"), "-lthrift",
                   "-Wl,--wrap=_Znwm", "-o", str(cls.binary)]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
        cls.env = dict(os.environ)
        cls.env["LD_LIBRARY_PATH"] = str(thrift / "lib") + os.pathsep + cls.env.get("LD_LIBRARY_PATH", "")

    def run_case(self, mode):
        result = subprocess.run([self.binary, mode], env=self.env, capture_output=True,
                                text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(mode + ": PASS", result.stdout)

    def test_increment_allocation_exception_releases_counter_lock(self):
        self.run_case("increment")

    def test_set_allocation_exception_releases_counter_lock(self):
        self.run_case("set")

    def test_snapshot_allocation_exception_releases_counter_lock(self):
        self.run_case("snapshot")

    def test_normal_counter_returns_signed_values_snapshot_and_concurrent_updates(self):
        self.run_case("normal")
