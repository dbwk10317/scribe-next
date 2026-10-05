#!/usr/bin/env python3
"""Offline first-batch replay and fake-process safety; never starts a daemon."""

import binascii
import copy
import errno
import importlib.util
import io
import json
from pathlib import Path
import socket
import signal
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("daemon_differential", ROOT / "tools/daemon_differential.py")
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)
FIXTURES = ROOT / "test/fixtures/first_daemon_differential"


class DaemonDifferentialOfflineTests(unittest.TestCase):
    def report(self):
        return json.loads((FIXTURES / "expected.json").read_text())

    def test_verified_wire_and_report_replay(self):
        report = self.report()
        for record in report["records"]:
            name = "%02d-%s" % (record["sequence"], record["method"])
            self.assertEqual((FIXTURES / (name + ".request.bin")).read_bytes(),
                             binascii.unhexlify(record["request_hex"]))
            if not record["oneway"]:
                wire = (FIXTURES / (name + ".reply.bin")).read_bytes()
                self.assertEqual(wire, binascii.unhexlify(record["reply_hex"]))
                self.assertEqual(client.parse_reply(wire[4:], record["method"].encode(), record["sequence"]),
                                 record["value"])
        result = client.compare_lanes(report, copy.deepcopy(report))
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(result["checks"].values()))

    def test_missing_or_corrupted_evidence_cannot_pass(self):
        old = self.report()
        for mutate in (lambda r: r["records"].pop(),
                       lambda r: r["records"][0].update(reply_hex="00000000"),
                       lambda r: r["records"][0].update(value="wrong"),
                       lambda r: r["records"][8].update(reply_hex="00000000"),
                       lambda r: r.update(files=[])):
            changed = copy.deepcopy(old)
            mutate(changed)
            with self.assertRaises(ValueError):
                client.compare_lanes(old, changed)

    def test_isolation_failure_never_launches_a_process(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            args = ["harness", "--run-isolated-daemons", "--targets", "never-read.json", "--output", str(output)]
            for uid,euid,interfaces in ((1000,1000,["lo"]), (65534,0,["lo"]), (65534,65534,["lo","eth0"])):
                with patch.object(sys, "argv", args), patch.object(client.os, "getuid", return_value=uid), \
                        patch.object(client.os, "geteuid", return_value=euid), \
                        patch.object(client.os, "listdir", return_value=interfaces), patch.object(client.subprocess, "Popen") as launch:
                    with self.assertRaises(ValueError):
                        client.main()
                    launch.assert_not_called()
                    self.assertFalse(output.exists())

    def test_port_occupancy_or_permission_error_is_not_free(self):
        conn = Mock()
        with patch.object(client.socket, "create_connection", return_value=conn):
            with self.assertRaises(ValueError):
                client.port_free()
            conn.close.assert_called_once()
        with patch.object(client.socket, "create_connection", side_effect=socket.error(errno.EACCES, "denied")):
            with self.assertRaises(socket.error):
                client.port_free()
        with patch.object(client.socket, "create_connection", side_effect=socket.error(errno.ECONNREFUSED, "refused")):
            client.port_free()

    def test_protocol_failure_closes_files_and_reaps_only_owned_child(self):
        process = Mock(pid=42, returncode=None)
        process.poll.side_effect = lambda: process.returncode
        process.wait.side_effect = lambda: process.returncode
        conn = Mock()
        conn.getpeername.return_value = ("127.0.0.1", client.PORT)
        conn.recv.return_value = struct.pack(">I", client.MAX_REPLY + 1)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(client, "ROOT", directory), \
                patch.object(client, "TARGETS", {"old": {"command": ["/unused/fake-daemon"]}}), \
                patch.object(client, "network_check"), patch.object(client, "port_free"), \
                patch.object(client, "connection_owner", return_value="123"), \
                patch.object(client, "group_exists", side_effect=[True,False,False,False]), \
                patch.object(client.os, "killpg", side_effect=lambda pid,sig: setattr(process,"returncode",-15)) as kill, \
                patch.object(client.os, "getuid", return_value=65534), \
                patch.object(client.os, "listdir", return_value=["lo"]), \
                patch.object(client.subprocess, "Popen", return_value=process) as launch, \
                patch.object(client.socket, "create_connection", return_value=conn):
            with self.assertRaisesRegex(ValueError, "unbounded reply frame"):
                client.run_lane("old")
            kill.assert_called_once_with(42,signal.SIGTERM)
            process.wait.assert_called_once()
            conn.close.assert_called_once()
            for name in ("stdin", "stdout", "stderr"):
                self.assertTrue(launch.call_args.kwargs[name].closed)
            report = json.loads((Path(directory) / "evidence/old/result.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["cleanup_exit"], -15)

    def test_owned_session_kill_fallback_also_covers_descendants(self):
        process = Mock(pid=42)
        process.wait.return_value = -9
        alive = [True]
        def signal_group(pid,sig):
            if sig==signal.SIGKILL: alive[0]=False
        with patch.object(client,"group_exists",side_effect=lambda pid: alive[0]), \
                patch.object(client.os,"killpg",side_effect=signal_group) as kill, \
                patch.object(client.time,"time",side_effect=[0,3]):
            self.assertEqual(client.cleanup_process(process),-9)
        self.assertEqual(kill.call_args_list,[unittest.mock.call(42,signal.SIGTERM),unittest.mock.call(42,signal.SIGKILL)])
        process.wait.assert_called_once()

    def test_connected_socket_must_be_owned_by_target_pid(self):
        conn = Mock()
        conn.getpeername.return_value = ("127.0.0.1",client.PORT)
        conn.getsockname.return_value = ("127.0.0.1",40000)
        local = "0100007F:%04X" % client.PORT
        remote = "0100007F:%04X" % 40000
        tcp = "header\n0: %s %s 01 0 0 0 65534 0 123\n" % (local,remote)
        def table(path):
            return io.StringIO(tcp if str(path).endswith("/tcp") else "header\n")
        with patch.object(client.os,"listdir",return_value=["3"]), \
                patch.object(client.os,"readlink",return_value="socket:[123]"), \
                patch("builtins.open",side_effect=table):
            self.assertEqual(client.connection_owner(42,conn),"123")
        with patch.object(client.os,"listdir",return_value=["3"]), \
                patch.object(client.os,"readlink",return_value="socket:[999]"), \
                patch("builtins.open",side_effect=table), \
                patch.object(client.time,"time",side_effect=[0,4]):
            with self.assertRaisesRegex(ValueError,"ownership"):
                client.connection_owner(42,conn)
        conn.sendall.assert_not_called()

    def test_three_store_case_has_explicit_routing_bytes_and_ignore_counts(self):
        entries,delta,unused=client.case_data('stores')
        self.assertEqual([c for c,p in entries],
                         [b'discard']*3+[b'fanout']*3+[b'catA',b'catB',b'catA',b'',b'unknown'])
        self.assertEqual(delta['scribe_overall:received good'],9)
        self.assertEqual((delta['discard:ignored'],delta['fanout:ignored'],delta['scribe_overall:ignored']),
                         (3,3,6))
        files,links=client.expected_outputs('stores')
        self.assertEqual({f['path']:f['hex'] for f in files},
                         {'left/left_00000':'4100420aff7461696c','right/right_00000':'4100420aff7461696c',
                          'category/catA/catA_00000':'4100420aff','category/catB/catB_00000':'7461696c'})
        self.assertEqual(len(links),4)
        fields=client.log_fields(entries)
        self.assertEqual(struct.unpack('>i',fields[4:8])[0],11)

    def test_synthetic_store_report_checks_all_fanout_outputs_and_case_identity(self):
        # Synthetic expectations only: first real store-case execution belongs to the server.
        report=self.report();report['case']='stores'
        entries,delta,unused=client.case_data('stores')
        report['counter_delta']=delta
        report['files'],report['symlinks']=client.expected_outputs('stores')
        report['records'][6]['request_hex']=client.hexbytes(client.framed(b'Log',7,client.log_fields(entries)))
        fields=b'\x0d\x00\x00\x0b\x0a'+struct.pack('>i',len(delta))
        for key,value in sorted(delta.items()):
            fields+=client.string(key.encode())+struct.pack('>q',value)
        fields+=b'\0'
        body=client.string(b'getCounters')+b'\x02'+struct.pack('>i',8)+fields
        report['records'][7].update(reply_hex=client.hexbytes(struct.pack('>I',len(body))+body),value=delta)
        self.assertEqual(client.compare_lanes(report,copy.deepcopy(report),'stores')['status'],'passed')
        with self.assertRaisesRegex(ValueError,'case mismatch'):
            client.compare_lanes(report,copy.deepcopy(report),'file')
        broken=copy.deepcopy(report);broken['files'].pop()
        with self.assertRaisesRegex(ValueError,'output file'):
            client.compare_lanes(broken,copy.deepcopy(broken),'stores')


if __name__ == "__main__":
    unittest.main()
