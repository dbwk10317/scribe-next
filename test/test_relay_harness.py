"""Dependency-free negatives for the new scripted relay peer's safety bounds."""

from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest import mock

import relay_peer as relay


class RelayHarnessTests(unittest.TestCase):
    def test_oversized_request_is_rejected_before_body_read(self):
        connection = mock.Mock()
        connection.recv.return_value = struct.pack(">I", relay.MAX_REQUEST + 1)
        with self.assertRaisesRegex(AssertionError, "exceeds fixture bound"):
            relay.receive_request(connection, time.monotonic() + 3)
        connection.recv.assert_called_once_with(4)

    def test_startup_diagnostic_failure_still_closes_peer_and_reaps_child(self):
        with tempfile.TemporaryDirectory(prefix="scribe-relay-helper-") as root:
            peer = relay.RelayPeer("unused-test-fixture", {}, Path(root))
            listener = mock.Mock()
            listener.getsockname.return_value = ("127.0.0.1", 32001)
            process = mock.Mock()
            process.poll.return_value = None
            process.wait.return_value = -15
            with mock.patch.object(relay.socket, "socket", return_value=listener), \
                    mock.patch.object(relay.subprocess, "Popen", return_value=process), \
                    mock.patch.object(peer, "read_line", side_effect=OSError("controlled startup failure")), \
                    mock.patch.object(peer, "diagnostics", side_effect=OSError("unreadable stderr")):
                with self.assertRaisesRegex(AssertionError, "controlled startup failure"):
                    peer.start()
            listener.bind.assert_called_once_with(("127.0.0.1", 0))
            listener.close.assert_called_once_with()
            process.terminate.assert_called_once_with()
            process.wait.assert_called_once_with(timeout=2)
            process.kill.assert_not_called()
            process.stdout.close.assert_called_once_with()
            process.stdin.close.assert_called_once_with()
            self.assertIsNone(peer.stderr)


if __name__ == "__main__":
    unittest.main()
