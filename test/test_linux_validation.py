#!/usr/bin/env python3
"""Reject unsafe validation inputs before creating output or running build tools."""

import contextlib
import importlib.util
import io
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "tools/validate_linux.py"
SPEC = importlib.util.spec_from_file_location("validate_linux", SCRIPT)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


@unittest.skipUnless(sys.platform == "linux" and platform.machine() == "x86_64",
                     "validation input regressions target the Linux x86_64 lane")
class LinuxValidationInputs(unittest.TestCase):
    def test_git_preflight_rejects_unusable_inputs_before_build(self):
        success = subprocess.CompletedProcess([], 0, "git version test\n", "")
        failure = subprocess.CompletedProcess([], 1, "", "unavailable")
        cases = (
            ([failure], "Git cannot use required", 1),
            ([success, failure], "required local upstream object is unavailable", 2),
            ([success, success, failure], ":src/file.cpp", 3),
        )
        for responses, diagnostic, calls in cases:
            with self.subTest(diagnostic=diagnostic), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "checkout"
                root.mkdir()
                output = Path(directory) / "new-output"
                env = {name: directory for name in VALIDATOR.PREFIXES}
                with mock.patch.dict(os.environ, env, clear=True), \
                     mock.patch.object(VALIDATOR, "SOURCE", root), \
                     mock.patch.object(sys, "argv", [str(SCRIPT), "--output", str(output)]), \
                     mock.patch.object(VALIDATOR.shutil, "which", return_value="existing-tool"), \
                     mock.patch.object(VALIDATOR.subprocess, "run", side_effect=responses) as run, \
                     mock.patch.object(VALIDATOR.subprocess, "check_output") as build_probe, \
                     contextlib.redirect_stderr(io.StringIO()) as errors:
                    with self.assertRaises(SystemExit) as exit_status:
                        VALIDATOR.main()
                self.assertEqual(exit_status.exception.code, 2)
                self.assertIn(diagnostic, errors.getvalue())
                self.assertFalse(output.exists())
                build_probe.assert_not_called()
                self.assertEqual(run.call_count, calls)
                for call in run.call_args_list:
                    self.assertEqual(call.args[0][:3],
                                     ["git", "--no-lazy-fetch", "--no-replace-objects"])
                    self.assertNotIn("fetch", call.args[0])
                self.assertEqual(run.call_args_list[0].args[0][-1], "--version")

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
