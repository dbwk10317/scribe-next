"""Single-threaded scripted downstream for the actual C++ NetworkStore driver.

Only Python stdlib, one retained 127.0.0.1:0 listener, and one owned child. The
peer encodes independent IDL/framed-binary expectations, not generated clients.
The shared LoopbackProcess supplies the existing bounded terminate/kill/reap path.
"""

import os
import select
import socket
import struct
import subprocess
import time

import loopback_rpc as tcp

MAX_REQUEST = 65536


class RelayWorkerProcess(tcp.LoopbackProcess):
    # C++ validates network destinations before initialize() and bounds each
    # child to 20 seconds, including a stuck native RPC or worker shutdown.
    mode = "relay-loopback-server"

BATCHES = {
    "binary": [(b"cat\0\xff", b"A\0B\n\xff\xc3\xa9"), (b"", b""), (b"tail", b"ends\n")],
    "abc": [(b"relay", b"A"), (b"relay", b"B"), (b"relay", b"C")],
    "4096": [(b"c" * 6000, b"x" * 4096)],
    "4097": [(b"first", b"x" * 2048), (b"second", b"y" * 2049)],
    "empty": [],
}


def receive_request(connection, deadline):
    """Bound both header and complete body, rejecting size before allocation."""
    def exact(size):
        chunks = []
        while size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("relay request deadline exceeded")
            connection.settimeout(remaining)
            chunk = connection.recv(size)
            if not chunk:
                raise AssertionError("peer received a truncated relay request")
            chunks.append(chunk)
            size -= len(chunk)
        return b"".join(chunks)
    header = exact(4)
    size = struct.unpack(">I", header)[0]
    if not 0 < size <= MAX_REQUEST:
        raise AssertionError(f"relay request exceeds fixture bound: {size}")
    return header + exact(size)


class RelayPeer(tcp.LoopbackProcess):
    def __init__(self, executable, environment, directory, pooled=False):
        super().__init__(executable, environment, directory, "")
        self.pooled = pooled
        self.listener = None
        self.accepted = []
        self.frames = []
        self.states = []
        self.deadline = None

    def remaining(self, limit=3):
        remaining = min(limit, self.deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("relay whole-process deadline exceeded")
        return remaining

    def read_line(self):
        result = b""
        while not result.endswith(b"\n"):
            if not select.select([self.process.stdout], [], [], self.remaining())[0]:
                raise AssertionError("relay driver output deadline exceeded\n" + self.diagnostics())
            byte = os.read(self.process.stdout.fileno(), 1)
            if not byte:
                raise AssertionError("relay driver exited before result\n" + self.diagnostics())
            result += byte
            if len(result) > 256:
                raise AssertionError("oversized relay driver record")
        return result.decode("ascii").strip()

    def start(self):
        self.deadline = time.monotonic() + 20
        try:
            self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sockets.append(self.listener)
            self.listener.bind(("127.0.0.1", 0))
            self.listener.listen(4)
            self.bound_address = self.listener.getsockname()
            if self.bound_address[0] != "127.0.0.1" or not self.bound_address[1]:
                raise AssertionError("scripted peer did not bind assigned IPv4 loopback")
            # The same socket remains open until cleanup; never reserve/release.
            self.config.write_text(
                f"remote_host=127.0.0.1\nremote_port={self.bound_address[1]}\n"
                f"timeout=500\nuse_conn_pool={'yes' if self.pooled else 'no'}\n")
            self.stderr = self.stderr_path.open("wb")
            self.process = subprocess.Popen(
                [str(self.executable), "relay-driver", str(self.config), str(self.directory)],
                cwd=self.directory, env=self.environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.stderr, bufsize=0,
            )
            if self.read_line() != "READY relay-driver":
                raise AssertionError("invalid relay driver readiness")
            return self
        except BaseException as error:
            try:
                detail = self.diagnostics()
            except Exception as diagnostic_error:
                detail = "stderr diagnostics unavailable: " + type(diagnostic_error).__name__
            finally:
                self.cleanup()
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise AssertionError(f"{error}\n{detail}") from error

    def command(self, value):
        encoded = (value + "\n").encode("ascii")
        if len(encoded) > 65 or b"\n" in encoded[:-1]:
            raise AssertionError("invalid relay script command")
        if not select.select([], [self.process.stdin], [], self.remaining())[1]:
            raise AssertionError("relay command deadline exceeded")
        if os.write(self.process.stdin.fileno(), encoded) != len(encoded):
            raise AssertionError("short relay command write")

    def state(self, operation, index, *, result, opened, sent, size=0):
        expected = (f"STATE {operation} {index} {int(result)} "
                    f"{int(opened[0])} {int(opened[1])} {sent} {size}")
        actual = self.read_line()
        self.states.append(actual)
        if actual != expected:
            raise AssertionError(f"relay result {actual!r} != {expected!r}\n{self.diagnostics()}")

    def accept(self):
        self.listener.settimeout(self.remaining())
        connection, address = self.listener.accept()
        self.sockets.append(connection)
        if address[0] != "127.0.0.1" or connection.getsockname() != self.bound_address:
            raise AssertionError("relay connection escaped assigned loopback peer")
        self.accepted.append(address)
        return connection

    def request(self, connection, batch):
        frame = receive_request(connection, time.monotonic() + self.remaining())
        expected = tcp.message(b"Log", 0, tcp.log_fields(BATCHES[batch]))
        if frame != expected:
            raise AssertionError(f"relay frame differs from exact non-versioned {batch} golden")
        self.frames.append(frame)
        return BATCHES[batch]

    def response(self, connection, code=0, *, strict=False):
        body = (struct.pack(">I", 0x80010002) + tcp.binary_string(b"Log") +
                struct.pack(">i", 0) + tcp.result_i32(code) if strict else
                tcp.reply(b"Log", 0, tcp.result_i32(code)))
        self.raw_response(connection, struct.pack(">I", len(body)) + body)

    def raw_response(self, connection, frame):
        connection.settimeout(self.remaining())
        connection.sendall(frame)

    def eof(self, connection):
        connection.settimeout(self.remaining())
        if connection.recv(1) != b"":
            raise AssertionError("relay sent unexpected bytes before closing connection")

    def no_pending_connections(self):
        if select.select([self.listener], [], [], 0)[0]:
            raise AssertionError("unexpected extra relay connection")

    def finish(self):
        self.command("QUIT")
        if self.read_line() != "PASS relay-driver":
            raise AssertionError("relay driver did not finish successfully")
        result = self.process.wait(timeout=self.remaining())
        if result != 0:
            raise AssertionError(f"relay driver exit={result}\n{self.diagnostics()}")
        self.no_pending_connections()

    def cleanup(self):
        try:
            super().cleanup()
        finally:
            if self.process is not None and self.process.stdin:
                self.process.stdin.close()

    def __exit__(self, error_type, error, traceback):
        try:
            if error_type is None:
                self.finish()
        finally:
            self.cleanup()
        return False
