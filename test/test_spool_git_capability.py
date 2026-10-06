#!/usr/bin/env python3
"""Keep unsupported Git options distinct from unavailable upstream objects."""
import os
import subprocess
import unittest
from unittest import mock

import test_ordinary_spool as spool


class SpoolGitCapabilityTests(unittest.TestCase):
    def test_unsupported_git_stops_before_object_access(self):
        result = subprocess.CompletedProcess([], 129, "", "unknown option: --no-lazy-fetch")
        with mock.patch.object(spool.subprocess, "run", return_value=result) as command:
            with self.assertRaisesRegex(RuntimeError, "safety options; upstream objects were not read"):
                spool.require_git_safety_options()
        command.assert_called_once_with(
            ["git", "--no-replace-objects", "--no-lazy-fetch", "--version"],
            cwd=spool.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        )

    def test_supported_probe_does_not_read_or_fetch_an_object(self):
        result = subprocess.CompletedProcess([], 0, "git version 2.52.0", "")
        with mock.patch.object(spool.subprocess, "run", return_value=result) as command:
            spool.require_git_safety_options()
        self.assertEqual(command.call_count, 1)
        self.assertEqual(command.call_args.args[0][-1], "--version")

    def test_setup_rejects_unsupported_git_before_creating_or_building_fixture(self):
        result = subprocess.CompletedProcess([], 129, "", "unknown option: --no-lazy-fetch")
        with mock.patch.dict(os.environ, {"TOOLS_PREFIX": "/tmp"}, clear=True), \
             mock.patch.object(spool.shutil, "which", return_value="/usr/bin/g++"), \
             mock.patch.object(spool.subprocess, "run", return_value=result) as command, \
             mock.patch.object(spool.tempfile, "TemporaryDirectory") as temporary:
            with self.assertRaisesRegex(RuntimeError, "upstream objects were not read"):
                spool.OrdinarySpoolTests.setUpClass()
            temporary.assert_not_called()
        self.assertEqual(command.call_count, 1)
        self.assertEqual(command.call_args.args[0][-1], "--version")

    def test_missing_object_keeps_its_source_diagnostic_after_supported_probe(self):
        supported = subprocess.CompletedProcess([], 0, "git version 2.52.0", "")
        missing = subprocess.CompletedProcess([], 128, b"", b"fatal: invalid object name")
        try:
            with mock.patch.dict(os.environ, {"TOOLS_PREFIX": "/tmp"}, clear=True), \
                 mock.patch.object(spool.shutil, "which", return_value="/usr/bin/g++"), \
                 mock.patch.object(spool.subprocess, "run", side_effect=[supported, missing]) as command:
                with self.assertRaisesRegex(AssertionError, "pinned public source is required locally; no fetch attempted"):
                    spool.OrdinarySpoolTests.setUpClass()
            self.assertEqual(command.call_count, 2)
            self.assertEqual(command.call_args_list[0].args[0][-1], "--version")
            self.assertEqual(command.call_args_list[1].args[0][1:4],
                             ["--no-replace-objects", "--no-lazy-fetch", "show"])
        finally:
            spool.OrdinarySpoolTests.doClassCleanups()


if __name__ == "__main__":
    unittest.main()

