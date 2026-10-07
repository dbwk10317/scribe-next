"""Current-runtime check of the bounded TFileTransport reader in test/cpp/thriftfile_cross_reader.cpp."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ThriftFileCrossReaderTests(unittest.TestCase):
    def test_padded_native_events_read_exact_binary_payload_and_eof(self):
        if not os.environ.get("THRIFT_PREFIX") or not os.environ.get("TOOLS_PREFIX"):
            self.skipTest("cross-reader runtime check requires prepared Thrift/tools prefixes")
        thrift = Path(os.environ["THRIFT_PREFIX"])
        tools = Path(os.environ["TOOLS_PREFIX"])
        compiler = shutil.which("g++")
        if not compiler:
            self.skipTest("cross-reader runtime check requires g++")
        with tempfile.TemporaryDirectory(prefix="scribe-cross-reader-") as name:
            directory = Path(name)
            executable = directory / "reader"
            env = dict(os.environ)
            env["LD_LIBRARY_PATH"] = str(thrift / "lib") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
            subprocess.run([compiler, "-std=c++17", "-I" + str(thrift / "include"),
                            "-I" + str(tools / "include"),
                            ROOT / "test/cpp/thriftfile_cross_reader.cpp",
                            "-L" + str(thrift / "lib"), "-lthrift", "-pthread",
                            "-o", executable], env=env, check=True, capture_output=True, timeout=30)
            payloads = (b"A\0B\n\xff", b"ends\n")
            # Independent native uint32 event lengths and seven-byte chunk padding.
            data = (struct.pack("=I", 5) + payloads[0] + b"\0" * 7 +
                    struct.pack("=I", 5) + payloads[1])
            input_file, output = directory / "framed", directory / "payload"
            input_file.write_bytes(data)
            result = subprocess.run([executable, input_file, "16", output], env=env,
                                    check=True, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.stdout, "events=2 bytes=10\n")
            self.assertEqual(output.read_bytes(), b"".join(payloads))


if __name__ == "__main__":
    unittest.main()
