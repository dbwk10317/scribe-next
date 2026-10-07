#!/usr/bin/env python3
"""Bounded ordinary-spool component differential and sanitizer regression.

The legacy file.cpp/file.h/HdfsFile.h are read byte-for-byte from the pinned
public Git object and built as C++03 with installed Boost. The current component
is built as C++17. Both use the same minimal include-only common header; neither
is a legacy Scribe daemon, old Thrift runtime, enabled-HDFS or thriftfile transport test.
Set TOOLS_PREFIX to the approved Boost development prefix. No downloads occur.
"""

import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "fcd294faffd1e88af1643a3a8c2359c41713f7c2"
SOURCES = ("file.cpp", "file.h", "HdfsFile.h")


def run(command, *, cwd, env=None, timeout=60, check=True):
    result = subprocess.run(
        [str(part) for part in command], cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout,
    )
    if check and result.returncode:
        raise AssertionError(f"command failed ({result.returncode}): {command}\n{result.stdout}\n{result.stderr}")
    return result


def require_git_safety_options():
    result = subprocess.run(
        ["git", "--no-replace-objects", "--no-lazy-fetch", "--version"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Git cannot use required --no-lazy-fetch/--no-replace-objects safety options; "
                           "upstream objects were not read and no fetch was attempted: " + result.stderr.strip())


class OrdinarySpoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prefix = os.environ.get("TOOLS_PREFIX")
        if not prefix:
            raise unittest.SkipTest("ordinary spool component tests unrun; set TOOLS_PREFIX")
        compiler = shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("ordinary spool component tests unrun; missing g++")
        require_git_safety_options()
        cls.tools = Path(prefix).resolve()
        temporary = tempfile.TemporaryDirectory(prefix="scribe-spool-contract-")
        cls.addClassCleanup(temporary.cleanup)
        cls.work = Path(temporary.name)
        cls.env = dict(os.environ)
        libdirs = [cls.tools / "lib", *sorted((cls.tools / "lib").glob("*-linux-gnu"))]
        cls.env["LD_LIBRARY_PATH"] = os.pathsep.join(map(str, libdirs))
        if os.environ.get("LD_LIBRARY_PATH"):
            cls.env["LD_LIBRARY_PATH"] += os.pathsep + os.environ["LD_LIBRARY_PATH"]
        # Do not inherit options that could hide the allocation mismatch.
        # LeakSanitizer cannot run under this cloud executor's ptrace boundary.
        # This suite covers ASan allocation/bounds plus UBSan, not leak checking.
        cls.env["ASAN_OPTIONS"] = "halt_on_error=1:alloc_dealloc_mismatch=1:detect_leaks=0"
        cls.env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        cls.executables = {}
        for version, standard in (("legacy", "c++03"), ("current", "c++17")):
            directory = cls.work / version
            directory.mkdir()
            for name in SOURCES:
                if version == "legacy":
                    result = subprocess.run(
                        ["git", "--no-replace-objects", "--no-lazy-fetch", "show", f"{UPSTREAM}:src/{name}"],
                        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                    )
                    if result.returncode:
                        raise AssertionError("pinned public source is required locally; no fetch attempted: "
                                             + result.stderr.decode(errors="replace"))
                    data = result.stdout
                else:
                    data = (ROOT / "src" / name).read_bytes()
                (directory / name).write_bytes(data)
            shutil.copyfile(ROOT / "test/cpp/spool_component_common.h", directory / "common.h")
            for sanitizer in (False, True):
                executable = directory / ("spool-sanitized" if sanitizer else "spool")
                flags = ["-O1", "-g", "-fno-omit-frame-pointer"]
                if sanitizer:
                    flags += ["-fsanitize=address,undefined"]
                run([compiler, "-std=" + standard, *flags,
                     "-I", directory, "-I", cls.tools / "include",
                     directory / "file.cpp", ROOT / "test/cpp/spool_component.cpp",
                     *("-L" + str(path) for path in libdirs), "-lboost_filesystem",
                     "-o", executable], cwd=directory, env=cls.env, timeout=90)
                cls.executables[version, sanitizer] = executable

    def directory(self):
        directory = self.work / self._testMethodName
        directory.mkdir()
        return directory

    def read(self, version, path, count, *, sanitizer=False, destruct=None, check=True):
        if destruct is None:
            destruct = version == "current"
        mode = "read" if destruct else "read-without-destruction"
        return run([self.executables[version, sanitizer], mode, path, count],
                   cwd=path.parent, env=self.env, timeout=15, check=check)

    def check_read(self, path, expected):
        serialized = "".join(f"{length}:{payload.hex()}\n" for length, payload in expected)
        for version in ("legacy", "current"):
            with self.subTest(version=version):
                self.assertEqual(self.read(version, path, len(expected)).stdout, serialized)
        # Current source must also destroy the buffer under both sanitizers.
        self.assertEqual(self.read("current", path, len(expected), sanitizer=True).stdout, serialized)

    def test_length_header_is_four_byte_little_endian(self):
        for length in (0, 1, 255, 256, 65536, 0x01020304, 0xFFFFFFFF):
            for version in ("legacy", "current"):
                with self.subTest(length=length, version=version):
                    result = run([self.executables[version, False], "frame", length],
                                 cwd=self.work, env=self.env)
                    self.assertEqual(result.stdout, struct.pack("<I", length).hex() + ":\n")

    def test_non_hdfs_stub_frame_is_empty_and_remains_unavailable(self):
        for sanitizer in (False, True):
            for length in (0, 1, 0xFFFFFFFF):
                with self.subTest(sanitizer=sanitizer, length=length):
                    result = run([self.executables["current", sanitizer], "non-hdfs-frame", length],
                                 cwd=self.work, env=self.env)
                    self.assertEqual(result.stdout, ":0:0\n")

    def test_legacy_and_current_writes_cross_read_and_match_independent_bytes(self):
        directory = self.directory()
        payloads = [b"category\x00\xff\n", b"payload\x00\n\xff\xc3\xa9", b"last"]
        inputs = []
        for index, payload in enumerate(payloads):
            path = directory / f"payload{index}"
            path.write_bytes(payload)
            inputs.append(path)
        expected = b"".join(struct.pack("<I", len(payload)) + payload for payload in payloads)
        for writer in ("legacy", "current"):
            with self.subTest(writer=writer):
                path = directory / (writer + ".spool")
                run([self.executables[writer, False], "write", path, *inputs],
                    cwd=directory, env=self.env)
                self.assertEqual(path.read_bytes(), expected)
                self.check_read(path, [(len(payload), payload) for payload in payloads]
                                + [(0, payloads[-1])])

    def test_raw_legacy_truncate_still_fails_while_fixed_current_truncates(self):
        # The approved loss fix intentionally differs from pinned upstream.
        directory = self.directory()
        for version in ("legacy", "current"):
            with self.subTest(version=version):
                path = directory / (version + ".spool")
                path.write_bytes(b"ORIGINAL\x00\xff")
                result = run([self.executables[version, False], "truncate", path],
                             cwd=directory, env=self.env)
                self.assertEqual(result.stdout, "0:0\n" if version == "legacy" else "1:1\n")
                self.assertEqual(path.read_bytes(), b"ORIGINAL\x00\xff" if version == "legacy" else b"")

    def test_fixed_direct_truncate_can_create_a_missing_file_legacy_cannot(self):
        # FileStore separately checks findOldestFile; this is the lower-level
        # out|trunc effect, documented rather than hidden as compatibility.
        directory = self.directory()
        for version in ("legacy", "current"):
            with self.subTest(version=version):
                path = directory / (version + ".missing")
                result = run([self.executables[version, False], "truncate", path],
                             cwd=directory, env=self.env)
                self.assertEqual(result.stdout, "0:0\n" if version == "legacy" else "1:1\n")
                self.assertEqual(path.exists(), version == "current")
                if version == "current":
                    self.assertEqual(path.read_bytes(), b"")

    def test_truncate_open_failure_is_still_reported_for_a_directory(self):
        directory = self.directory()
        sentinel = directory / "keep"
        sentinel.write_bytes(b"untouched")
        for version in ("legacy", "current"):
            with self.subTest(version=version):
                result = run([self.executables[version, False], "truncate", directory],
                             cwd=directory, env=self.env)
                self.assertEqual(result.stdout, "0:0\n")
                self.assertEqual(sentinel.read_bytes(), b"untouched")

    def test_open_write_appends_complete_frames(self):
        directory = self.directory()
        payload = directory / "payload"
        payload.write_bytes(b"A\x00B")
        for version in ("legacy", "current"):
            with self.subTest(version=version):
                path = directory / (version + ".spool")
                for unused in range(2):
                    run([self.executables[version, False], "write", path, payload],
                        cwd=directory, env=self.env)
                self.assertEqual(path.read_bytes(), (b"\x03\x00\x00\x00A\x00B") * 2)
                self.check_read(path, [(3, b"A\x00B"), (3, b"A\x00B"), (0, b"A\x00B")])

    def test_empty_and_truncated_headers_preserve_output_and_return_zero(self):
        directory = self.directory()
        for size in range(4):
            with self.subTest(header_bytes=size):
                path = directory / str(size)
                path.write_bytes(b"\x05\x00\x00"[:size])
                self.check_read(path, [(0, b"sentinel")])

    def test_zero_frame_stops_a_normal_replay_but_an_explicit_next_call_can_continue(self):
        path = self.directory() / "zero"
        path.write_bytes(struct.pack("<I", 0) + struct.pack("<I", 3) + b"abc")
        self.check_read(path, [(0, b"sentinel"), (3, b"abc"), (0, b"abc")])

    def test_truncated_payload_retains_prior_output_and_reports_legacy_loss(self):
        directory = self.directory()
        for prefix, expected in ((b"", [(-6, b"sentinel")]),
                                 (b"\x03\x00\x00\x00abc", [(3, b"abc"), (-13, b"abc")])):
            with self.subTest(valid_prefix=bool(prefix)):
                path = directory / ("prefix" if prefix else "only")
                path.write_bytes(prefix + struct.pack("<I", 5) + b"xy")
                self.check_read(path, expected)

    def test_int_max_length_rejection_can_report_zero_or_remaining_tail(self):
        directory = self.directory()
        for tail in (b"", b"xyz"):
            with self.subTest(tail=tail):
                path = directory / str(len(tail))
                path.write_bytes(struct.pack("<I", 0x7FFFFFFF) + tail)
                self.check_read(path, [(-len(tail), b"sentinel")])

    def test_buffer_growth_and_large_buffer_release_preserve_payload(self):
        directory = self.directory()
        # Exercise the 64KiB allocation boundary and >1MiB release path without
        # requesting unbounded allocations from a corrupt length field.
        for size in (65535, 65536, 65537, 1048577):
            with self.subTest(size=size):
                payload = (b"\x00\xffA\n" * ((size + 3) // 4))[:size]
                path = directory / str(size)
                path.write_bytes(struct.pack("<I", size) + payload)
                self.check_read(path, [(size, payload), (0, payload)])

    def test_allocation_mismatch_is_reproduced_then_fixed_without_suppression(self):
        path = self.directory() / "small"
        path.write_bytes(b"\x03\x00\x00\x00abc")
        legacy = self.read("legacy", path, 1, sanitizer=True, destruct=True, check=False)
        self.assertNotEqual(legacy.returncode, 0)
        self.assertIn("AddressSanitizer: alloc-dealloc-mismatch", legacy.stderr)
        self.assertIn("StdFile::~StdFile", legacy.stderr)
        self.assertEqual(legacy.stdout, "3:616263\n")
        current = self.read("current", path, 1, sanitizer=True)
        self.assertEqual(current.stdout, legacy.stdout)
        self.assertNotIn("Sanitizer", current.stderr)


if __name__ == "__main__":
    unittest.main()
