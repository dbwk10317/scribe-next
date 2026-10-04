"""Bounded stdlib client/process helpers for the test-constructed loopback server.

No installed Python Thrift, production daemon, external bind, or network service.
Wire values below come from the IDL/TBinaryProtocol layout, not generated clients.
"""

import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import time

MAX_REPLY = 262144


def binary_string(value):
    return struct.pack(">i", len(value)) + value


def message(name, sequence, fields=b"\0", *, strict=False, oneway=False):
    kind = 4 if oneway else 1
    header = (struct.pack(">I", 0x80010000 | kind) + binary_string(name) if strict else
              binary_string(name) + bytes([kind]))
    body = header + struct.pack(">i", sequence) + fields
    return struct.pack(">I", len(body)) + body


def log_fields(entries):
    body = b"\x0f\x00\x01\x0c" + struct.pack(">i", len(entries))
    for category, payload in entries:
        body += b"\x0b\x00\x01" + binary_string(category)
        body += b"\x0b\x00\x02" + binary_string(payload) + b"\0"
    return body + b"\0"


def string_argument(value):
    return b"\x0b\x00\x01" + binary_string(value) + b"\0"


def reply(name, sequence, fields, kind=2):
    return binary_string(name) + bytes([kind]) + struct.pack(">i", sequence) + fields


def result_i32(value):
    return b"\x08\x00\x00" + struct.pack(">i", value) + b"\0"


def result_i64(value):
    return b"\x0a\x00\x00" + struct.pack(">q", value) + b"\0"


def result_string(value):
    return b"\x0b\x00\x00" + binary_string(value) + b"\0"


class Cursor:
    """Only the bounded fields needed for counter-map/application-error replies."""
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, count):
        if count < 0 or count > len(self.data) - self.offset:
            raise AssertionError("truncated or invalid reply field")
        value = self.data[self.offset:self.offset + count]
        self.offset += count
        return value

    def number(self, pattern):
        return struct.unpack(pattern, self.take(struct.calcsize(pattern)))[0]

    def string(self):
        return self.take(self.number(">i"))

    def finish(self):
        if self.offset != len(self.data):
            raise AssertionError("unexpected trailing reply bytes")


def counter_map(body, name, sequence):
    c = Cursor(body)
    if (c.string(), c.number(">B"), c.number(">i"), c.take(5)) != (
            name, 2, sequence, b"\x0d\x00\x00\x0b\x0a"):
        raise AssertionError("unexpected getCounters reply shape")
    count = c.number(">i")
    if not 0 <= count <= 10000:
        raise AssertionError("unbounded map count")
    values = {}
    for unused in range(count):
        key, value = c.string(), c.number(">q")
        if key in values:
            raise AssertionError("duplicate counter key")
        values[key] = value
    if c.take(1) != b"\0":
        raise AssertionError("missing map result STOP")
    c.finish()
    return values


def application_error(body, name, sequence):
    c = Cursor(body)
    if (c.string(), c.number(">B"), c.number(">i"), c.take(3)) != (
            name, 3, sequence, b"\x0b\x00\x01"):
        raise AssertionError("unexpected application exception shape")
    text = c.string()
    if c.take(3) != b"\x08\x00\x02":
        raise AssertionError("missing application exception code")
    code = c.number(">i")
    if c.take(1) != b"\0":
        raise AssertionError("missing application exception STOP")
    c.finish()
    return text, code


def receive_frame(sock, timeout=3):
    deadline = time.monotonic() + timeout
    def exact(count):
        chunks = []
        while count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("bounded RPC deadline exceeded")
            sock.settimeout(remaining)
            chunk = sock.recv(count)
            if not chunk:
                raise AssertionError("connection closed before complete reply")
            chunks.append(chunk)
            count -= len(chunk)
        return b"".join(chunks)
    size = struct.unpack(">I", exact(4))[0]
    if not 0 < size <= MAX_REPLY:
        raise AssertionError(f"invalid/beyond-fixture-limit reply length: {size}")
    return exact(size)


class LoopbackProcess:
    mode = "loopback-server"

    def __init__(self, executable, environment, directory, configuration):
        self.directory = Path(directory)
        self.config = self.directory / "scribe.conf"
        self.config.write_text(configuration.replace("@DIRECTORY@", str(self.directory)))
        self.stderr_path = self.directory / "server.stderr"
        self.stderr = None
        self.process = None
        self.sockets = []
        self.executable, self.environment = executable, environment

    def diagnostics(self):
        if self.stderr:
            self.stderr.flush()
        return self.stderr_path.read_bytes()[-65536:].decode(errors="replace") if self.stderr_path.exists() else ""

    def start(self):
        try:
            self.stderr = self.stderr_path.open("wb")
            self.process = subprocess.Popen(
                [str(self.executable), self.mode, str(self.config), str(self.directory)],
                cwd=self.directory, env=self.environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=self.stderr, bufsize=0,
            )
            deadline = time.monotonic() + 10
            ready = b""
            while not ready.endswith(b"\n"):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                    raise AssertionError("loopback startup timeout")
                byte = os.read(self.process.stdout.fileno(), 1)
                if not byte:
                    raise AssertionError("child exited before loopback readiness")
                ready += byte
                if len(ready) > 128:
                    raise AssertionError("invalid readiness record")
            fields = ready.decode("ascii").strip().split()
            if len(fields) != 3 or fields[:2] != ["READY", "127.0.0.1"]:
                raise AssertionError(f"invalid loopback readiness: {ready!r}")
            self.port = int(fields[2])
            if not 0 < self.port <= 65535:
                raise AssertionError("invalid assigned loopback port")
            return self
        except BaseException as error:
            try:
                detail = self.diagnostics()
            except Exception as diagnostic_error:
                detail = "stderr diagnostics unavailable: " + type(diagnostic_error).__name__
            finally:
                self.cleanup()  # Diagnostic failures must never bypass child reaping.
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise AssertionError(f"{error}\n{detail}") from error

    def connect(self):
        connection = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        if connection.getpeername() != ("127.0.0.1", self.port):
            connection.close()
            raise AssertionError("connection peer is not assigned loopback address")
        self.sockets.append(connection)
        return connection

    def shutdown(self):
        if self.process.poll() is not None:
            raise AssertionError("server exited before shutdown\n" + self.diagnostics())
        connection = self.connect()
        connection.sendall(message(b"shutdown", 9000, oneway=True))
        try:
            result = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired as error:
            raise AssertionError("shutdown deadline exceeded\n" + self.diagnostics()) from error
        if result != 0:
            raise AssertionError(f"shutdown exit={result}\n" + self.diagnostics())

    def cleanup(self):
        for connection in self.sockets:
            connection.close()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()  # Only this owned PID, never name/global kill.
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            if self.process.stdout:
                self.process.stdout.close()
        if self.stderr:
            self.stderr.close()
            self.stderr = None

    def __enter__(self):
        return self.start()

    def __exit__(self, error_type, error, traceback):
        try:
            if error_type is None:
                self.shutdown()
        finally:
            self.cleanup()
        return False
