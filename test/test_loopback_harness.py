"""Dependency-free negative tests for subprocess cleanup and client reply bounds."""

from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

import loopback_rpc as tcp


class LoopbackHarnessTests(unittest.TestCase):
    def test_startup_diagnostics_failure_still_terminates_and_reaps_owned_child(self):
        with tempfile.TemporaryDirectory(prefix="scribe-loopback-helper-") as root:
            driver = tcp.LoopbackProcess("unused-test-fixture", {}, Path(root), "port=1463\n")
            process = mock.Mock()
            process.poll.return_value = None
            process.wait.return_value = -15
            with mock.patch.object(tcp.subprocess, "Popen", return_value=process), \
                    mock.patch.object(tcp.select, "select", side_effect=OSError("controlled startup failure")), \
                    mock.patch.object(driver, "diagnostics", side_effect=OSError("unreadable stderr")):
                with self.assertRaisesRegex(AssertionError, "controlled startup failure"):
                    driver.start()
            process.terminate.assert_called_once_with()
            process.wait.assert_called_once_with(timeout=2)
            process.kill.assert_not_called()
            process.stdout.close.assert_called_once_with()
            self.assertIsNone(driver.stderr)

    def test_cleanup_timeout_escalates_only_owned_child_and_waits_after_kill(self):
        with tempfile.TemporaryDirectory(prefix="scribe-loopback-helper-") as root:
            driver = tcp.LoopbackProcess("unused-test-fixture", {}, Path(root), "port=1463\n")
            process = mock.Mock()
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired("owned-child", 2), -9]
            driver.process = process
            driver.cleanup()
            process.terminate.assert_called_once_with()
            process.kill.assert_called_once_with()
            self.assertEqual(process.wait.call_args_list, [mock.call(timeout=2), mock.call(timeout=2)])
            process.stdout.close.assert_called_once_with()

    def test_client_rejects_oversized_reply_before_reading_body(self):
        connection = mock.Mock()
        connection.recv.return_value = struct.pack(">I", tcp.MAX_REPLY + 1)
        with self.assertRaisesRegex(AssertionError, "beyond-fixture-limit"):
            tcp.receive_frame(connection)
        connection.recv.assert_called_once_with(4)


if __name__ == "__main__":
    unittest.main()
