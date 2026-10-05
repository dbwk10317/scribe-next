#!/usr/bin/env python3
"""Reject unsafe validation inputs before creating output or running build tools."""

import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/validate_linux.py"


@unittest.skipUnless(sys.platform == "linux" and platform.machine() == "x86_64",
                     "validation input regressions target the Linux x86_64 lane")
class LinuxValidationInputs(unittest.TestCase):
    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            marker = output / "keep"
            marker.write_bytes(b"existing user data")
            result = subprocess.run([sys.executable, "-B", SCRIPT, "--output", output],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output already exists", result.stdout)
            self.assertEqual(marker.read_bytes(), b"existing user data")

    def test_missing_dependencies_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            env = dict(os.environ)
            for name in ("THRIFT_PREFIX", "FB303_PREFIX", "TOOLS_PREFIX", "THRIFT_PYTHON_SOURCE",
                         "PYTHON_SETUPUTIL_ARGS", "DIST_EXTRA_CONFIG", "MAKEFLAGS", "MFLAGS",
                         "GNUMAKEFLAGS", "MAKEOVERRIDES"):
                env.pop(name, None)
            result = subprocess.run([sys.executable, "-B", SCRIPT, "--output", output], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("provide existing directories", result.stdout)
            self.assertFalse(output.exists())

    def test_external_install_record_override_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            record = Path(directory) / "outside-record.txt"
            for name in ("PYTHON_SETUPUTIL_ARGS", "DIST_EXTRA_CONFIG", "MAKEFLAGS"):
                env = dict(os.environ)
                for override in ("PYTHON_SETUPUTIL_ARGS", "DIST_EXTRA_CONFIG", "MAKEFLAGS", "MFLAGS",
                                 "GNUMAKEFLAGS", "MAKEOVERRIDES"):
                    env.pop(override, None)
                env[name] = "--record=" + str(record)
                result = subprocess.run([sys.executable, "-B", SCRIPT, "--output", output], env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsupported install/make override", result.stdout)
                self.assertIn(name, result.stdout)
                self.assertFalse(output.exists())
                self.assertFalse(record.exists())


if __name__ == "__main__":
    unittest.main()
