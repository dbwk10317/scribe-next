"""Real fixed-host relay contracts, mixed into the source-checked API fixture.

Fault/retry outcomes use direct NetworkStore calls, never worker retry timing.
Only the final healthy test uses two actual handler/StoreQueue worker processes.
"""

from pathlib import Path
import socket
import struct
import subprocess
import tempfile

import loopback_rpc as tcp
import relay_peer as relay


class RelayContracts:
    def relay_peer(self, pooled=False):
        directory = Path(tempfile.mkdtemp(prefix="relay-", dir=self.temporary))
        return relay.RelayPeer(self.fixture, self.env, directory, pooled)

    def relay_request(self, peer, batch, connection=None, index=0):
        peer.command(f"SEND {index} {batch}")
        if connection is None:
            connection = peer.accept()
        peer.request(connection, batch)
        return connection

    def test_relay_binary_bytes_ok_and_empty_batch_sent_count(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.relay_peer(pooled) as peer:
                connection = self.relay_request(peer, "binary")
                peer.response(connection)
                peer.state("SEND", 0, result=True, opened=(True, False), sent=3, size=3)
                self.relay_request(peer, "empty", connection)
                peer.response(connection, strict=True)
                peer.state("SEND", 0, result=True, opened=(True, False), sent=3)
                self.assertEqual(len(peer.accepted), 1)
                self.assertEqual(len(peer.frames), 2)

    def test_relay_try_later_retains_fixed_connection_for_explicit_retry(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.relay_peer(pooled) as peer:
                connection = self.relay_request(peer, "abc")
                peer.response(connection, 1)
                peer.state("SEND", 0, result=False, opened=(True, False), sent=0, size=3)
                self.relay_request(peer, "abc", connection)
                peer.response(connection)
                peer.state("SEND", 0, result=True, opened=(True, False), sent=3, size=3)
                self.assertEqual(peer.frames[0], peer.frames[1])
                self.assertEqual(len(peer.accepted), 1)

    def test_relay_response_loss_then_retry_records_six_but_counts_three_sent(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled), self.relay_peer(pooled) as peer:
                ledger = []
                connection = self.relay_request(peer, "abc")
                ledger.extend(relay.BATCHES["abc"])
                connection.close()  # Peer records all three, then loses the response.
                peer.state("SEND", 0, result=False, opened=(False, False), sent=0, size=3)
                connection = self.relay_request(peer, "abc")
                ledger.extend(relay.BATCHES["abc"])
                peer.response(connection)
                peer.state("SEND", 0, result=True, opened=(True, False), sent=3, size=3)
                self.assertEqual(ledger, relay.BATCHES["abc"] * 2)
                self.assertEqual(len(ledger), 6)
                self.assertEqual(len(peer.accepted), 2)

    def test_relay_simulated_downstream_prefix_then_retry_has_aabc_ledger(self):
        # This is a scripted downstream application policy, not a reproduction
        # of actual Scribe STOPPING/partial acceptance. The IDL reply is one enum.
        with self.relay_peer() as peer:
            connection = self.relay_request(peer, "abc")
            ledger = relay.BATCHES["abc"][:1]
            peer.response(connection, 1)
            peer.state("SEND", 0, result=False, opened=(True, False), sent=0, size=3)
            self.relay_request(peer, "abc", connection)
            ledger.extend(relay.BATCHES["abc"])
            peer.response(connection)
            peer.state("SEND", 0, result=True, opened=(True, False), sent=3, size=3)
            self.assertEqual(b"".join(payload for category, payload in ledger), b"AABC")
            self.assertEqual(len(peer.accepted), 1)

    def test_relay_bounded_response_faults_close_then_healthy_reconnect(self):
        for pooled in (False, True):
            for fault in ("silent", "truncated", "oversized", "application-exception"):
                with self.subTest(pooled=pooled, fault=fault), self.relay_peer(pooled) as peer:
                    connection = self.relay_request(peer, "abc")
                    if fault == "truncated":
                        peer.raw_response(connection, struct.pack(">I", 32) + b"\0\0")
                        connection.shutdown(socket.SHUT_WR)
                    elif fault == "oversized":
                        # Header only; Thrift rejects before allocating this body.
                        peer.raw_response(connection, struct.pack(">I", 0x7fffffff))
                    elif fault == "application-exception":
                        fields = (b"\x0b\x00\x01" + tcp.binary_string(b"scripted failure") +
                                  b"\x08\x00\x02" + struct.pack(">i", 6) + b"\0")
                        body = tcp.reply(b"Log", 0, fields, kind=3)
                        peer.raw_response(connection, struct.pack(">I", len(body)) + body)
                    # For silent, do not sleep or close the peer. Only the actual
                    # configured 500ms receive timeout can finish this first call.
                    peer.state("SEND", 0, result=False, opened=(False, False), sent=0, size=3)
                    peer.eof(connection)
                    healthy = self.relay_request(peer, "abc")
                    peer.response(healthy)
                    peer.state("SEND", 0, result=True, opened=(True, False), sent=3, size=3)
                    self.assertEqual(len(peer.accepted), 2)

    def test_relay_pool_two_stores_repeated_open_close_and_final_reopen(self):
        with self.relay_peer(pooled=True) as peer:
            peer.command("OPEN 0")
            connection = peer.accept()
            peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
            peer.command("OPEN 0")
            peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
            peer.command("OPEN 1")
            peer.state("OPEN", 1, result=True, opened=(True, True), sent=0)
            peer.no_pending_connections()
            self.relay_request(peer, "binary", connection)
            peer.response(connection)
            peer.state("SEND", 0, result=True, opened=(True, True), sent=3, size=3)
            for unused in range(2):
                peer.command("CLOSE 0")
                peer.state("CLOSE", 0, result=True, opened=(False, True), sent=3)
            self.relay_request(peer, "abc", connection, index=1)
            peer.response(connection)
            peer.state("SEND", 1, result=True, opened=(False, True), sent=6, size=3)
            peer.command("CLOSE 1")
            peer.state("CLOSE", 1, result=True, opened=(False, False), sent=6)
            peer.eof(connection)
            peer.command("OPEN 1")
            reopened = peer.accept()
            peer.state("OPEN", 1, result=True, opened=(False, True), sent=6)
            self.relay_request(peer, "abc", reopened, index=1)
            peer.response(reopened)
            peer.state("SEND", 1, result=True, opened=(False, True), sent=9, size=3)
            peer.command("CLOSE 1")
            peer.state("CLOSE", 1, result=True, opened=(False, False), sent=9)
            peer.eof(reopened)
            self.assertEqual(len(peer.accepted), 2)

    def test_relay_dummy_message_byte_threshold_and_rejection_suppresses_payload(self):
        for pooled in (False, True):
            with self.subTest(pooled=pooled, case="boundary"), self.relay_peer(pooled) as peer:
                connection = self.relay_request(peer, "4096")
                peer.response(connection)
                peer.state("SEND", 0, result=True, opened=(True, False), sent=1, size=1)
                peer.command("SEND 0 4097")
                peer.request(connection, "empty")
                peer.response(connection)
                peer.request(connection, "4097")
                peer.response(connection)
                # The successful empty probe adds zero, not one, to sent.
                peer.state("SEND", 0, result=True, opened=(True, False), sent=3, size=2)
                self.assertEqual(len(peer.frames), 3)
            with self.subTest(pooled=pooled, case="rejected-dummy"), self.relay_peer(pooled) as peer:
                peer.command("SEND 0 4097")
                connection = peer.accept()
                peer.request(connection, "empty")
                peer.response(connection, 1)
                peer.state("SEND", 0, result=False, opened=(True, False), sent=0, size=2)
                # The next exact request proves there was no hidden full-payload
                # send after the rejected dummy; no short negative-time window.
                self.relay_request(peer, "binary", connection)
                peer.response(connection)
                peer.state("SEND", 0, result=True, opened=(True, False), sent=3, size=3)
                self.assertEqual(len(peer.frames), 2)
                self.assertEqual(len(peer.accepted), 1)

    def test_relay_peer_failure_closes_listener_and_reaps_owned_child(self):
        peer = self.relay_peer()
        with self.assertRaisesRegex(RuntimeError, "controlled peer failure"):
            with peer:
                peer.command("OPEN 0")
                peer.accept()
                peer.state("OPEN", 0, result=True, opened=(True, False), sent=0)
                raise RuntimeError("controlled peer failure")
        self.assertIsNotNone(peer.process.returncode)
        self.assertEqual(peer.process.wait(timeout=1), peer.process.returncode)
        self.assertTrue(peer.process.stdin.closed)
        self.assertTrue(peer.process.stdout.closed)
        self.assertTrue(all(connection.fileno() == -1 for connection in peer.sockets))

    def test_relay_fixture_rejects_external_or_unbounded_destinations_before_open(self):
        base = "remote_host=127.0.0.1\nremote_port=1\ntimeout=500\n"
        invalid = [base.replace("127.0.0.1", "192.0.2.1"),
                   base.replace("remote_port=1", "remote_port=0"),
                   base.replace("remote_port=1", "remote_port=65536"),
                   base.replace("timeout=500", "timeout=0")]
        invalid += [base + key + "=forbidden\n" for key in
                    ("smc_service", "service_list", "dynamic_config_type")]
        cases = [("relay-driver", config) for config in invalid]
        cases += [("relay-loopback-server", "port=1463\nnetwork::" + key +
                   "=forbidden\n<store>\ntype=network\ncategory=accepted\n" + base + "</store>\n")
                  for key in ("smc_service", "service_list", "dynamic_config_type")]
        for mode, config in cases:
            with self.subTest(mode=mode, config=config):
                directory = Path(tempfile.mkdtemp(prefix="relay-invalid-", dir=self.temporary))
                filename = directory / "scribe.conf"
                filename.write_text(config)
                result = subprocess.run(
                    [str(self.fixture), mode, str(filename), str(directory)],
                    cwd=directory, env=self.env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, text=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertNotIn("READY", result.stdout)
                self.assertIn("relay fixture", result.stderr)

    def test_relay_real_upstream_worker_to_downstream_worker_file_bytes(self):
        def server(config):
            directory = Path(tempfile.mkdtemp(prefix="relay-worker-", dir=self.temporary))
            return relay.RelayWorkerProcess(self.fixture, self.env, directory, config)

        downstream = server(self.loopback_config())
        with downstream:
            config = ("port=1463\nnum_thrift_server_threads=3\n"
                      "<store>\ncategory=accepted\ntype=network\n"
                      f"remote_host=127.0.0.1\nremote_port={downstream.port}\n"
                      "timeout=500\nuse_conn_pool=yes\ntarget_write_size=1000000\n"
                      "max_write_interval=3600\n</store>\n")
            upstream = server(config)
            payloads = [b"A\0B\n\xff\xc3\xa9", b"", b"tail\n"]
            with upstream:
                connection = upstream.connect()
                entries = [(b"accepted", payload) for payload in payloads]
                self.assertEqual(self.tcp_call(connection, b"Log", 81, tcp.log_fields(entries)),
                                 tcp.reply(b"Log", 81, tcp.result_i32(0)))
                self.assertEqual(self.tcp_call(connection, b"getCounter", 82,
                                              tcp.string_argument(b"accepted:received good")),
                                 tcp.reply(b"getCounter", 82, tcp.result_i64(3)))
            # Normal shutdown joins the healthy upstream network worker. Only
            # now assert downstream acceptance, then drain its FileStore worker.
            connection = downstream.connect()
            self.assertEqual(self.tcp_call(connection, b"getCounter", 83,
                                          tcp.string_argument(b"accepted:received good")),
                             tcp.reply(b"getCounter", 83, tcp.result_i64(3)))
        self.assertEqual((downstream.directory / "data/received_00000").read_bytes(),
                         b"".join(payloads))
        self.assertEqual(upstream.process.returncode, 0)
        self.assertEqual(downstream.process.returncode, 0)
