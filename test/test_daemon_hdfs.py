#!/usr/bin/env python3
"""Offline contracts for the isolated HDFS runner; no Hadoop processes launched."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import json
import subprocess
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import daemon_hdfs as h


class DistributedHdfsRunnerTests(unittest.TestCase):
    def test_hadoop_listener_inventory_rejects_wildcard_addresses(self):
        self.assertTrue(h.loopback_endpoint('tcp', '0100007F:4A38'))
        self.assertTrue(h.loopback_endpoint('tcp6', '00000000000000000000000001000000:4A38'))
        self.assertFalse(h.loopback_endpoint('tcp', '00000000:4A38'))
        self.assertFalse(h.loopback_endpoint('tcp6', '00000000000000000000000000000000:4A38'))

    def test_server_version_requires_exact_java17_major(self):
        self.assertTrue(h.java17('openjdk version "17.0.16" 2025-07-15'))
        self.assertTrue(h.java17('java version "17.0.16"'))
        for version in ('openjdk version "21.0.12"', 'openjdk version "170"', '', 'java version "1.7.0"'):
            self.assertFalse(h.java17(version))

    def test_hadoop_endpoints_and_private_storage_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = h.properties(root)
            for key in ('dfs.namenode.rpc-address', 'dfs.namenode.http-address',
                        'dfs.datanode.address', 'dfs.datanode.ipc.address', 'dfs.datanode.http.address'):
                self.assertTrue(values[key].startswith('127.0.0.1:'))
            self.assertEqual(values['dfs.replication'], '1')
            self.assertEqual(values['dfs.namenode.safemode.min.datanodes'], '1')
            self.assertNotIn('dfs.permissions.enabled', values)
            self.assertNotIn('dfs.namenode.datanode.registration.ip-hostname-check', values)
            for key in ('dfs.namenode.name.dir', 'dfs.datanode.data.dir'):
                self.assertTrue(values[key].startswith('file://' + str(root) + '/'))
            path = root / 'site.xml'
            h.xml(path, values)
            parsed = {p.findtext('name'): p.findtext('value') for p in ET.parse(path).findall('property')}
            self.assertEqual(parsed, values)

    def check_preflight_failure(self, java_version, ldd_output, expected):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hadoop, java, output = root / 'hadoop', root / 'java', root / 'output'
            for prefix, relative in ((hadoop, 'bin/hdfs'), (java, 'bin/java')):
                (prefix / 'bin').mkdir(parents=True)
                (prefix / relative).symlink_to(Path(sys.executable).resolve(strict=True))
            calls = []
            def fake_command(arguments, env, log, **kwargs):
                calls.append([str(x) for x in arguments])
                self.assertNotIn('HADOOP_WORKER_MODE', env)
                self.assertNotIn('HDFS_DFSADMIN_OPTS', env)
                self.assertNotIn('HADOOP_COMMON_HOME', env)
                for name in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
                    self.assertNotIn(name, env)
                payload = java_version if len(calls) == 1 else ldd_output
                Path(log).write_bytes(payload)
                return 0, payload
            arguments = ['daemon_hdfs.py', '--run-isolated-hdfs', '--hadoop', str(hadoop),
                         '--java-home', str(java), '--scribed', str(Path(sys.executable).resolve(strict=True)), '--output', str(output)]
            with mock.patch.dict(h.os.environ, {'HADOOP_WORKER_MODE': 'true', 'HDFS_DFSADMIN_OPTS': '-javaagent:bad', 'HADOOP_COMMON_HOME': '/wrong-sdk'}, clear=True), \
                 mock.patch.object(sys, 'argv', arguments), mock.patch.object(h.c, 'network_check'), \
                 mock.patch.object(h.c, 'port_free'), mock.patch.object(h, 'command', fake_command), \
                 mock.patch.object(h.os, 'listdir', return_value=['lo']), mock.patch.object(h, 'listeners', return_value=[]), \
                 mock.patch.object(h, 'foreground') as foreground:
                with self.assertRaisesRegex(ValueError, expected):
                    h.main()
                foreground.assert_not_called()
            result = json.loads((output / 'result.json').read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertIn(expected, result['error'])
            self.assertFalse(any('namenode' in call for call in calls))
            self.assertFalse((output / 'conf/core-site.xml').exists())

    def test_preflight_fixture_is_independent_of_hostile_java_environment(self):
        for name in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
            with self.subTest(variable=name), mock.patch.dict(h.os.environ, {name: '-javaagent:fixture-hostile'}):
                self.check_preflight_failure(b'openjdk version "21.0.12"\n', b'', 'requires JDK17')
                self.check_preflight_failure(b'openjdk version "17.0.16"\n', b'libjvm.so => not found\n',
                                            'native ABI/dependency preflight failed')
                self.assertEqual(h.os.environ[name], '-javaagent:fixture-hostile')

    def test_jdk21_preflight_stops_before_cluster_or_format(self):
        self.check_preflight_failure(b'openjdk version "21.0.12"\n', b'', 'requires JDK17')

    def test_missing_native_dependency_stops_before_cluster_or_format(self):
        self.check_preflight_failure(b'openjdk version "17.0.16"\n', b'libjvm.so => not found\n',
                                    'native ABI/dependency preflight failed')

    def test_exited_cli_still_cleans_its_owned_group(self):
        with tempfile.TemporaryDirectory() as directory:
            process = mock.Mock()
            process.wait.return_value = 0
            process.poll.return_value = 0
            with mock.patch.object(h.subprocess, 'Popen', return_value=process), \
                 mock.patch.object(h.c, 'cleanup_process') as cleanup:
                self.assertEqual(h.command([sys.executable, '-c', 'pass'], {}, Path(directory) / 'log'), (0, b''))
                cleanup.assert_called_once_with(process)

    def test_cli_timeout_cleans_group_before_propagating(self):
        with tempfile.TemporaryDirectory() as directory:
            process = mock.Mock()
            process.wait.side_effect = subprocess.TimeoutExpired(sys.executable, 1)
            with mock.patch.object(h.subprocess, 'Popen', return_value=process), \
                 mock.patch.object(h.c, 'cleanup_process') as cleanup:
                with self.assertRaises(subprocess.TimeoutExpired):
                    h.command([sys.executable, '-c', 'pass'], {}, Path(directory) / 'log', timeout=1)
                cleanup.assert_called_once_with(process)

    def test_readiness_retries_a_timed_out_owned_cli(self):
        process = mock.Mock()
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(h, 'command', side_effect=[subprocess.TimeoutExpired('hdfs', 10),
                 (0, b'Live datanodes (1):'), (0, b'Safe mode is OFF')]) as command, \
             mock.patch.object(h.time, 'sleep'):
            result = h.wait_ready(process, process, Path('/hdfs'), {}, Path(directory))
            self.assertEqual(result, {'attempts': 2, 'live_datanodes': 1, 'safemode': 'OFF'})
            self.assertEqual(command.call_count, 3)

    def test_public_source_payload_and_regular_marker_expectations(self):
        self.assertEqual(b''.join(value for category, value in h.FIRST), b'A\0B\n\xfftail')
        self.assertEqual(b''.join(value for category, value in h.SECOND), b'Z')
        self.assertEqual(h.NAMES, ['.fixture-seed', 'fixture_00000', 'fixture_current'])
        self.assertEqual(len(set(h.PORTS)), 6)


if __name__ == '__main__':
    unittest.main()
