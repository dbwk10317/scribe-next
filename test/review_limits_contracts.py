"""Explicit finite wire limits on actual production-factory loopback transports.

The 256MiB boundary uses a streamed single Log and a null destination, bounding
client memory. The separate 20MiB spool replay checks real destination bytes.
No production CLI listener or company/old-runtime equivalence is asserted.
"""

from pathlib import Path
import socket
import struct
import subprocess
import tempfile

import loopback_rpc as tcp


class ReviewLimitsContracts:
    @staticmethod
    def limit_null_config(frame=None, message=None):
        settings = "port=1463\nnum_thrift_server_threads=1\nmax_queue_size=1073741824\n"
        if frame is not None:
            settings += f"thrift_max_frame_size={frame}\n"
        if message is not None:
            settings += f"thrift_max_message_size={message}\n"
        return settings + "<store>\ncategory=accepted\ntype=null\ntarget_write_size=1\n</store>\n"

    @staticmethod
    def send_sized_log(connection, size, sequence, category=b"accepted"):
        payload_size = size - 36 - len(category)
        if payload_size < 0:
            raise AssertionError("fixture Log size is too small")
        prefix = (tcp.binary_string(b"Log") + b"\x01" + struct.pack(">i", sequence) +
                  b"\x0f\x00\x01\x0c" + struct.pack(">i", 1) +
                  b"\x0b\x00\x01" + tcp.binary_string(category) +
                  b"\x0b\x00\x02" + struct.pack(">i", payload_size))
        if len(prefix) + payload_size + 2 != size:
            raise AssertionError("independent serialized-size accounting mismatch")
        connection.settimeout(30)
        connection.sendall(struct.pack(">I", size) + prefix)
        chunk = b"x" * min(payload_size, 1024 * 1024)
        remaining = payload_size
        while remaining:
            amount = min(remaining, len(chunk))
            connection.sendall(chunk[:amount])
            remaining -= amount
        connection.sendall(b"\0\0")
        return tcp.receive_frame(connection, timeout=30)

    def limit_header_rejected(self, server, size):
        connection = server.connect()
        connection.sendall(struct.pack(">I", size))
        connection.settimeout(3)
        try:
            self.assertEqual(connection.recv(1), b"")
        except ConnectionResetError:
            pass
        self.assertIsNone(server.process.poll(), server.diagnostics())
        healthy = server.connect()
        self.assertEqual(self.tcp_call(healthy, b"getName", 700),
                         tcp.reply(b"getName", 700, tcp.result_string(b"Scribe")))

    def test_wire_limit_defaults_explicit_overrides_and_every_transport_layer(self):
        for frame, message in ((None, None), (128, 1024), (1024, 128),
                               (1, 1), (2147483647, 2147483647)):
            with self.subTest(frame=frame, message=message):
                config = self.limit_null_config(frame, message)
                config += f"expected_frame={frame or 268435456}\nexpected_message={message or 268435456}\n"
                self.run_fixture("limits-valid", config)

    def test_wire_limit_invalid_config_refuses_server_construction(self):
        for key in ("thrift_max_frame_size", "thrift_max_message_size"):
            for value in ("0", "-1", "+1", "", "garbage", "128suffix", "0x80",
                          "2147483648", "18446744073709551616"):
                with self.subTest(key=key, value=value):
                    self.run_fixture("limits-invalid", self.limit_null_config() + f"{key}={value}\n")

    def test_wire_frame_and_message_f_minus_one_f_f_plus_one_repeated_frames(self):
        for frame, message in ((128, 1024), (1024, 128)):
            with self.subTest(frame=frame, message=message), self.loopback_process(
                    config=self.limit_null_config(frame, message)) as server:
                connection = server.connect()
                for sequence, size in enumerate((127, 128, 44, 128), 701):
                    self.assertEqual(self.send_sized_log(connection, size, sequence),
                                     tcp.reply(b"Log", sequence, tcp.result_i32(0)))
                self.limit_header_rejected(server, 129)

    def test_wire_default_256mib_boundary_and_input_memory_above_100mib(self):
        with self.loopback_process(config=self.limit_null_config()) as server:
            connection = server.connect()
            for sequence, size in enumerate((268435455, 268435456), 711):
                self.assertEqual(self.send_sized_log(connection, size, sequence),
                                 tcp.reply(b"Log", sequence, tcp.result_i32(0)))
            self.limit_header_rejected(server, 268435457)
            self.assertEqual(self.tcp_call(connection, b"getCounter", 713,
                                          tcp.string_argument(b"accepted:received good")),
                             tcp.reply(b"getCounter", 713, tcp.result_i64(2)))

    def test_wire_category_overhead_counts_toward_request_not_payload_size(self):
        with self.loopback_process(config=self.limit_null_config(128, 1024)) as server:
            connection = server.connect()
            self.assertEqual(self.send_sized_log(connection, 128, 721, b"c" * 88),
                             tcp.reply(b"Log", 721, tcp.result_i32(0)))
            self.limit_header_rejected(server, 129)

    def test_wire_limits_reload_retains_startup_policy(self):
        config = self.limit_null_config(128, 1024)
        for frame, message in ((64, 64), (None, None), (128, None), (None, 1024),
                               ("0", 1024), (128, "garbage")):
            with self.subTest(frame=frame, message=message), self.loopback_process(config=config) as server:
                connection = server.connect()
                server.config.write_text(self.limit_null_config(frame, message))
                connection.sendall(tcp.message(b"reinitialize", 730, oneway=True))
                self.assertEqual(self.send_sized_log(connection, 128, 731),
                                 tcp.reply(b"Log", 731, tcp.result_i32(0)))
                self.limit_header_rejected(server, 129)
            if frame != "0" and message != "garbage":
                self.assertIn("wire-limit changes require restart", server.diagnostics())

    def test_wire_relay_outgoing_limit_and_incoming_reply_limit(self):
        for frame, message, category, payload, reply_size, expected, count in (
                (128, 1024, 4, 87, 24, 0, 1), (128, 1024, 4, 88, 24, 0, 1),
                (128, 1024, 4, 89, None, 1, 1), (1024, 128, 4, 89, None, 1, 1),
                (128, 1024, 88, 4, 24, 0, 1), (128, 1024, 89, 4, None, 1, 1),
                (128, 1024, 4, 0, 129, -1, 1), (1024, 128, 4, 0, 129, -1, 1),
                (20, 1024, 0, 0, None, 1, 0), (21, 1024, 0, 0, 20, 0, 0),
                (22, 1024, 0, 0, 20, 0, 0), (1024, 20, 0, 0, None, 1, 0),
                (1024, 21, 0, 0, 20, 0, 0), (1024, 22, 0, 0, 20, 0, 0),
                (128, 1024, 4, 68, 20, 0, 2), (128, 1024, 4, 69, 20, 0, 2),
                (128, 1024, 4, 70, None, 1, 2), (1024, 128, 4, 68, 20, 0, 2),
                (1024, 128, 4, 69, 20, 0, 2), (1024, 128, 4, 70, None, 1, 2)):
            with self.subTest(frame=frame, message=message, category=category,
                              payload=payload, reply=reply_size, count=count):
                directory = Path(tempfile.mkdtemp(prefix="limit-relay-", dir=self.temporary))
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                    listener.bind(("127.0.0.1", 0))
                    listener.listen(1)
                    listener.settimeout(5)
                    config = directory / "scribe.conf"
                    config.write_text(self.limit_null_config(frame, message) +
                                      f"remote_port={listener.getsockname()[1]}\n"
                                      f"category_size={category}\npayload_size={payload}\nentry_count={count}\n")
                    process = subprocess.Popen([str(self.fixture), "limit-relay", str(config), str(directory)],
                                               cwd=directory, env=self.env, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, text=True)
                    try:
                        connection, address = listener.accept()
                        with connection:
                            connection.settimeout(5)
                            if reply_size is None:
                                self.assertEqual(connection.recv(1), b"")
                            else:
                                header = bytearray()
                                while len(header) < 4:
                                    data = connection.recv(4 - len(header))
                                    self.assertTrue(data, "relay closed before frame header")
                                    header.extend(data)
                                size = struct.unpack(">I", header)[0]
                                body = bytearray()
                                while len(body) < size:
                                    data = connection.recv(size - len(body))
                                    self.assertTrue(data, "truncated relay Log")
                                    body.extend(data)
                                expected_wire = tcp.message(b"Log", 0, tcp.log_fields(
                                    [(b"c" * category, b"x" * (payload if i == 0 else 0))
                                     for i in range(count)]))
                                self.assertEqual(bytes(header + body), expected_wire)
                                if expected == 0:
                                    response = tcp.reply(b"Log", 0, tcp.result_i32(0))
                                    connection.sendall(struct.pack(">I", len(response)) + response)
                                else:
                                    connection.sendall(struct.pack(">I", reply_size))
                                    self.assertEqual(connection.recv(1), b"")
                        output, errors = process.communicate(timeout=5)
                        self.assertEqual(process.returncode, 0, errors)
                        self.assertIn(f"RESULT {expected} {count if expected == 0 else 0} {count}", output)
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=2)
                        for pipe in (process.stdout, process.stderr):
                            pipe.close()

    def test_wire_20mib_oldest_spool_replays_without_split_or_byte_change(self):
        downstream_config = self.loopback_config().replace("category=accepted", "category=fallback")
        payload = (b"A\0B\n\xff" * ((20 * 1024 * 1024) // 5 + 1))[:20 * 1024 * 1024]
        with self.loopback_process(config=downstream_config) as downstream:
            config = self.file_config(max_write_size=100000000) + (
                f"remote_host=127.0.0.1\nremote_port={downstream.port}\ntimeout=500\nuse_conn_pool=yes\n")
            directory = self.run_fixture("limit-spool-relay", config, {
                "data/fixture_00000": self.file_frame(payload)})
            self.assertEqual(list((directory / "data").iterdir()), [])
            connection = downstream.connect()
            self.assertEqual(self.tcp_call(connection, b"getCounter", 740,
                                          tcp.string_argument(b"fallback:received good")),
                             tcp.reply(b"getCounter", 740, tcp.result_i64(1)))
        self.assertEqual((downstream.directory / "data/received_00000").read_bytes(), payload)

    def test_wire_mapping_client_reply_frame_and_message_boundaries(self):
        for frame, message in ((128, 1024), (1024, 128)):
            for reply_size in (127, 128, 129):
                with self.subTest(frame=frame, message=message, reply_size=reply_size):
                    directory = Path(tempfile.mkdtemp(prefix="limit-mapping-", dir=self.temporary))
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                        listener.bind(("127.0.0.1", 0))
                        listener.listen(1)
                        listener.settimeout(5)
                        config = directory / "scribe.conf"
                        config.write_text(self.limit_null_config(frame, message) +
                                          f"remote_port={listener.getsockname()[1]}\n")
                        process = subprocess.Popen(
                            [str(self.fixture), "limit-mapping", str(config), str(directory)],
                            cwd=directory, env=self.env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
                        try:
                            connection, address = listener.accept()
                            with connection:
                                request = tcp.receive_frame(connection, timeout=5)
                                self.assertEqual(request, tcp.message(
                                    b"getMapping", 0, tcp.string_argument(b"limitmapping"))[4:])
                                if reply_size == 129:
                                    connection.sendall(struct.pack(">I", reply_size))
                                else:
                                    host = b"x" * (reply_size - 48)
                                    fields = (b"\x0d\x00\x00\x08\x0c" + struct.pack(">i", 1) +
                                              struct.pack(">i", 42) + b"\x0b\x00\x02" +
                                              tcp.binary_string(host) + b"\x08\x00\x03" +
                                              struct.pack(">i", 124) + b"\0\0")
                                    response = tcp.reply(b"getMapping", 0, fields)
                                    self.assertEqual(len(response), reply_size)
                                    connection.sendall(struct.pack(">I", reply_size) + response)
                                connection.settimeout(5)
                                self.assertEqual(connection.recv(1), b"")
                            output, errors = process.communicate(timeout=5)
                            self.assertEqual(process.returncode, 0, errors)
                            expected = (f"MAPPING 1 {reply_size - 48} 124" if reply_size <= 128 else
                                        "MAPPING 0 4 19")
                            self.assertIn(expected, output)
                        finally:
                            if process.poll() is None:
                                process.kill()
                                process.wait(timeout=2)
                            for pipe in (process.stdout, process.stderr):
                                pipe.close()

    def test_wire_downstream_smaller_policy_retains_20mib_spool_for_retry(self):
        config = "thrift_max_frame_size=128\nthrift_max_message_size=1024\n" + self.loopback_config()
        payload = b"x" * (20 * 1024 * 1024)
        original = self.file_frame(payload)
        with self.loopback_process(config=config) as downstream:
            config = self.file_config() + (
                f"remote_host=127.0.0.1\nremote_port={downstream.port}\ntimeout=500\n"
                "use_conn_pool=yes\nexpected_rejected=1\n")
            directory = self.run_fixture("limit-spool-relay", config, {
                "data/fixture_00000": original})
            self.assertEqual((directory / "data/fixture_00000").read_bytes(), original)
            connection = downstream.connect()
            self.assertEqual(self.tcp_call(connection, b"getCounter", 750,
                                          tcp.string_argument(b"accepted:received good")),
                             tcp.reply(b"getCounter", 750, tcp.result_i64(0)))
