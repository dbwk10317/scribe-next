#!/usr/bin/env python3
"""Opt-in real Scribe API/config contracts, without a daemon, sockets, or service.

Set THRIFT_PREFIX, FB303_PREFIX, SCRIBE_BUILD, and TOOLS_PREFIX to a prepared
Thrift 0.25.0/fb303 build and its compiler/Boost/libevent environment. SCRIBE_BUILD
is a configured in-source build copy of the current checkout. Reused objects
must have matching sources, generated code, and non-stale compiler dependencies.
Only temporary fixture files are created; no dependency download/build occurs.

This is a single-version golden and config/handler fixture, not old/new differential,
socket-server coverage, full old/new file/spool compatibility, or a durability guarantee.
FileStore cases use real temporary files and controlled primary replay outcomes.
"""

import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
OBJECTS = (
    "store", "store_queue", "conf", "file", "conn_pool",
    "network_dynamic_config", "dynamic_bucket_updater", "env_default",
)
GENERATED = ("scribe", "scribe_types", "BucketStoreMapping", "bucketupdater_types")


def checked(command, cwd, env=None, timeout=120):
    result = subprocess.run(
        [str(argument) for argument in command], cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout,
    )
    if result.returncode:
        raise AssertionError(f"command failed: {shlex.join(map(str, command))}\n{result.stdout}")
    return result.stdout


def make_value(makefile, name):
    match = re.search(rf"^{re.escape(name)} = (.*)$", makefile, re.M)
    if not match:
        raise AssertionError(f"missing configured Makefile variable: {name}")
    return match.group(1)


def check_fresh_object(build, name):
    """Use the compiler's dependency list rather than only the .cpp timestamp."""
    source = build / "src"
    obj = source / (name + ".o")
    depfile = source / ".deps" / (name + ".Po")
    logical_line = depfile.read_text().replace("\\\n", " ").splitlines()[0]
    dependencies = shlex.split(logical_line.split(":", 1)[1])
    if not dependencies:
        raise AssertionError(f"no compiler dependencies recorded for {obj}")
    for dependency in dependencies:
        path = source / dependency
        if path.stat().st_mtime_ns > obj.stat().st_mtime_ns:
            raise AssertionError(f"stale build object {obj}; rebuild after changing {path}")


class ScribeApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("THRIFT_PREFIX", "FB303_PREFIX", "SCRIBE_BUILD", "TOOLS_PREFIX")
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise unittest.SkipTest("actual Scribe API tests unrun; set " + ", ".join(missing))
        thrift, fb303, cls.build, tools = (Path(os.environ[name]).resolve() for name in names)
        temporary = tempfile.TemporaryDirectory(prefix="scribe-api-compat-")
        cls.addClassCleanup(temporary.cleanup)
        cls.temporary = Path(temporary.name)
        makefile = (cls.build / "src/Makefile").read_text()
        for name, prefix in (("thrift_home", thrift), ("fb303_home", fb303)):
            if Path(make_value(makefile, name)).resolve() != prefix:
                raise AssertionError(f"{name} does not match the configured Scribe build")
        if make_value(makefile, "ENV_SOURCES") != "env_default.cpp":
            raise AssertionError("this fixture supports the public env_default build lane only")
        # Source-copy equality prevents accidentally testing an earlier checkout.
        for directory, patterns in (("src", ("*.cpp", "*.h", "Makefile.am")),
                                    ("if", ("*.thrift",))):
            for pattern in patterns:
                for source in (ROOT / directory).glob(pattern):
                    copy = cls.build / directory / source.name
                    if source.read_bytes() != copy.read_bytes():
                        raise AssertionError(f"build source differs from current checkout: {source}")

        libdirs = [thrift / "lib", fb303 / "lib", tools / "lib"]
        libdirs += sorted((tools / "lib").glob("*-linux-gnu"))
        cls.env = dict(os.environ)
        cls.env["LD_LIBRARY_PATH"] = os.pathsep.join(map(str, libdirs))
        if os.environ.get("LD_LIBRARY_PATH"):
            cls.env["LD_LIBRARY_PATH"] += os.pathsep + os.environ["LD_LIBRARY_PATH"]
        compiler = thrift / "bin/thrift"
        if checked([compiler, "--version"], ROOT, cls.env).strip() != "Thrift version 0.25.0":
            raise AssertionError("this integration lane requires Thrift 0.25.0")
        generated = cls.temporary / "generated"
        generated.mkdir()
        for name in ("scribe", "bucketupdater"):
            checked([compiler, "-I", fb303 / "share", "--gen", "cpp:pure_enums",
                     "-out", generated, ROOT / "if" / (name + ".thrift")], ROOT, cls.env)
        for name in GENERATED:
            for suffix in (".cpp", ".h"):
                if (generated / (name + suffix)).read_bytes() != (
                    cls.build / "src/gen-cpp" / (name + suffix)
                ).read_bytes():
                    raise AssertionError(f"stale or modified generated source: {name}{suffix}")
        for name in (*OBJECTS, *GENERATED, "scribe_server"):
            check_fresh_object(cls.build, name)
        for archive, members in (("libscribe.a", GENERATED[:2]),
                                 ("libdynamicbucketupdater.a", GENERATED[2:])):
            path = cls.build / "src" / archive
            if any((cls.build / "src" / (name + ".o")).stat().st_mtime_ns
                   > path.stat().st_mtime_ns for name in members):
                raise AssertionError(f"stale generated RPC library: {path}")
        cls.scribed = cls.build / "src/scribed"
        if any(path.stat().st_mtime_ns > cls.scribed.stat().st_mtime_ns
               for path in (cls.build / "src").glob("*.o")):
            raise AssertionError("scribed is older than its objects; relink before testing")

        includes = [ROOT / "src", cls.build, thrift / "include", thrift / "include/thrift",
                    fb303 / "include/thrift", fb303 / "include/thrift/fb303", tools / "include"]
        cxx = shlex.split(make_value(makefile, "CXX"))
        flags = ["-std=c++17", "-O0", "-g", "-pthread", *(f"-I{path}" for path in includes)]
        server_object = cls.temporary / "scribe_server_test.o"
        checked([*cxx, *flags, "-Dmain=scribe_cli_main", "-c", ROOT / "src/scribe_server.cpp",
                 "-o", server_object], ROOT, cls.env)
        cls.fixture = cls.temporary / "scribe-api-fixture"
        checked([*cxx, *flags, ROOT / "test/cpp/scribe_api_compat.cpp", server_object,
                 *(cls.build / "src" / (name + ".o") for name in OBJECTS),
                 cls.build / "src/libscribe.a", cls.build / "src/libdynamicbucketupdater.a",
                 *(f"-L{path}" for path in libdirs), "-lfb303", "-lthrift", "-lthriftnb",
                 "-levent", "-lboost_filesystem", "-lboost_system", "-o", cls.fixture], ROOT, cls.env)

    def run_fixture(self, mode, config_text=None, input_files=None):
        directory = Path(tempfile.mkdtemp(prefix=mode + "-", dir=self.temporary))
        config = directory / "scribe.conf"
        # A port is required by initialize(); no socket/server is constructed.
        if config_text is None:
            config_text = "port=1463\n<store>\ncategory=accepted\ntype=null\n</store>\n"
        config_text = config_text.replace("@DIRECTORY@", str(directory))
        config.write_bytes(config_text.encode("utf-8"))
        for relative, contents in (input_files or {}).items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        output = checked([self.fixture, mode, config, directory], directory, self.env, timeout=20)
        self.assertIn("PASS " + mode, output)
        return directory

    @staticmethod
    def file_config(**values):
        # All writes/deletes stay inside a new fixture directory. No production
        # spool path, network service or time-based rotation is used.
        defaults = {"file_path": "@DIRECTORY@/data", "base_filename": "fixture",
                    "rotate_period": "never", "create_symlink": "yes",
                    "fs_type": "std", "test_framed": 1, "test_multi": 0,
                    "write_category": "no", "add_newlines": 0,
                    "max_size": 0, "max_write_size": 7}
        defaults.update(values)
        return ("port=1463\n<store>\ncategory=accepted\ntype=null\n</store>\n" +
                "".join(f"{key}={value}\n" for key, value in defaults.items()))

    @staticmethod
    def file_frame(payload):
        return struct.pack("<I", len(payload)) + payload

    @staticmethod
    def file_entries(entries):
        return "".join(category.hex() + ":" + payload.hex() + "\n"
                       for category, payload in entries).encode("ascii")

    def test_filestore_plain_category_newline_bytes_and_relative_symlink(self):
        entries = ((b"cat\x00\xff", b"A\x00B\n\xff"), (b"", b""), (b"tail", b"ends\n"))
        for category in (False, True):
            for newline in (False, True):
                with self.subTest(category=category, newline=newline):
                    directory = self.run_fixture("filestore-write", self.file_config(
                        test_framed=0, write_category="yes" if category else "no",
                        add_newlines=int(newline)))
                    expected = b"".join((cat + b"\n" if category else b"") + payload +
                                        (b"\n" if newline else b"") for cat, payload in entries)
                    self.assertEqual((directory / "data/fixture_00000").read_bytes(), expected)
                    link = directory / "data/fixture_current"
                    self.assertTrue(link.is_symlink())
                    self.assertEqual(os.readlink(link), "fixture_00000")
                    self.assertEqual(sorted(p.name for p in link.parent.iterdir()),
                                     ["fixture_00000", "fixture_current"])

    def test_filestore_buffer_category_newline_frames_and_actual_replay(self):
        entries = ((b"cat\x00\xff", b"A\x00B\n\xff"), (b"", b""), (b"tail", b"ends\n"))
        for category in (False, True):
            for newline in (False, True):
                with self.subTest(category=category, newline=newline):
                    directory = self.run_fixture("filestore-write", self.file_config(
                        write_category="yes" if category else "no", add_newlines=int(newline)))
                    expected = b"".join((self.file_frame(cat + b"\n") if category else b"") +
                                        self.file_frame(payload + (b"\n" if newline else b""))
                                        for cat, payload in entries)
                    self.assertEqual((directory / "data/fixture_00000").read_bytes(), expected)
                    replay = entries if newline else entries[:1]  # zero frame stops actual replay
                    self.assertEqual((directory / "read.txt").read_bytes(), self.file_entries(
                        ((cat if category else b"fallback", payload + (b"\n" if newline else b""))
                         for cat, payload in replay)))
                    self.assertEqual([p.name for p in (directory / "data").iterdir()], ["fixture_00000"])

    def test_filestore_multi_buffer_forces_category_and_disables_chunks_rotation(self):
        directory = self.run_fixture("filestore-write", self.file_config(
            test_multi=1, write_category="no", add_newlines=1,
            chunk_size=8, rotate_period="hourly"))
        entries = ((b"cat\x00\xff", b"A\x00B\n\xff"), (b"", b""), (b"tail", b"ends\n"))
        expected = b"".join(self.file_frame(cat + b"\n") + self.file_frame(payload + b"\n")
                            for cat, payload in entries)
        self.assertEqual((directory / "data/fixture_00000").read_bytes(), expected)
        self.assertEqual((directory / "read.txt").read_bytes(), self.file_entries(
            ((cat, payload + b"\n") for cat, payload in entries)))
        self.assertEqual([p.name for p in (directory / "data").iterdir()], ["fixture_00000"])

    def test_filestore_close_reopen_appends_without_new_suffix(self):
        directory = self.run_fixture("filestore-reopen", self.file_config())
        self.assertEqual((directory / "data/fixture_00000").read_bytes(),
                         self.file_frame(b"A\x00B") * 2)
        self.assertEqual((directory / "read.txt").read_bytes(),
                         self.file_entries([(b"fallback", b"A\x00B")] * 2))
        self.assertEqual([p.name for p in (directory / "data").iterdir()], ["fixture_00000"])

    def test_filestore_read_appends_and_uses_fallback_category(self):
        directory = self.run_fixture("filestore-read-delete", self.file_config(test_append=1), {
            "data/fixture_00000": self.file_frame(b"one\x00\xff") + self.file_frame(b"two\n")})
        self.assertEqual((directory / "read-0.txt").read_bytes(), self.file_entries([
            (b"sentinel", b"keep"), (b"fallback", b"one\x00\xff"), (b"fallback", b"two\n")]))
        self.assertEqual((directory / "states.txt").read_text(), "before-0=0\nafter-0=0\nempty-0=1\n")
        self.assertEqual(list((directory / "data").iterdir()), [])

    def test_filestore_category_reader_strips_last_byte_without_validating_newline(self):
        directory = self.run_fixture("filestore-read-delete", self.file_config(write_category="yes"), {
            "data/fixture_00000": b"".join(self.file_frame(x) for x in
                (b"cat\x00\xff\n", b"first\n", b"bad!", b"second", b"\n", b"third"))})
        self.assertEqual((directory / "read-0.txt").read_bytes(), self.file_entries([
            (b"cat\x00\xff", b"first\n"), (b"bad", b"second"), (b"", b"third")]))

    def test_filestore_zero_partial_header_orphan_category_are_uncounted_on_delete(self):
        cases = ((False, self.file_frame(b"") + self.file_frame(b"hidden")),
                 (False, b"\x05\x00\x00"),
                 (True, self.file_frame(b"orphan\n")),
                 (True, self.file_frame(b"orphan\n") + b"\x05\x00"),
                 (True, self.file_frame(b"empty\n") + self.file_frame(b"") +
                  self.file_frame(b"later\n") + self.file_frame(b"hidden")))
        for category, content in cases:
            with self.subTest(category=category, content=content):
                directory = self.run_fixture("filestore-read-delete", self.file_config(
                    write_category="yes" if category else "no"), {"data/fixture_00000": content})
                self.assertEqual((directory / "read-0.txt").read_bytes(), b"")
                self.assertEqual((directory / "states.txt").read_text(), "before-0=0\nafter-0=0\nempty-0=1\n")
                self.assertEqual(list((directory / "data").iterdir()), [])

    def test_filestore_truncated_payload_loss_at_delete_then_clean_read_adds_no_loss(self):
        content = self.file_frame(b"abc") + struct.pack("<I", 5) + b"xy"
        self.assertEqual(len(content), 13)
        directory = self.run_fixture("filestore-read-delete", self.file_config(test_cycles=2), {
            "data/fixture_00000": content, "data/fixture_00001": self.file_frame(b"later")})
        self.assertEqual((directory / "read-0.txt").read_bytes(), self.file_entries([(b"fallback", b"abc")]))
        self.assertEqual((directory / "read-1.txt").read_bytes(), self.file_entries([(b"fallback", b"later")]))
        self.assertEqual((directory / "states.txt").read_text(),
                         "before-0=0\nafter-0=13\nempty-0=0\nbefore-1=13\nafter-1=13\nempty-1=1\n")

    def test_filestore_oldest_numeric_order_and_unrelated_files_survive(self):
        directory = self.run_fixture("filestore-read-delete", self.file_config(test_cycles=2), {
            "data/fixture_00010": self.file_frame(b"ten"),
            "data/fixture_00002": self.file_frame(b"two"), "data/unrelated_00001": b"keep"})
        self.assertEqual((directory / "read-0.txt").read_bytes(), self.file_entries([(b"fallback", b"two")]))
        self.assertEqual((directory / "read-1.txt").read_bytes(), self.file_entries([(b"fallback", b"ten")]))
        self.assertEqual((directory / "data/unrelated_00001").read_bytes(), b"keep")
        self.assertEqual([p.name for p in (directory / "data").iterdir()], ["unrelated_00001"])

    def test_filestore_replace_existing_overwrites_oldest_and_keeps_newest(self):
        # Approved app-flag correction enables the existing replacement path.
        original = self.file_frame(b"original")
        directory = self.run_fixture("filestore-replace", self.file_config(), {
            "data/fixture_00000": original, "data/fixture_00001": self.file_frame(b"newest")})
        self.assertEqual((directory / "states.txt").read_text(), "replace=1\nopen=1\n")
        self.assertEqual((directory / "data/fixture_00000").read_bytes(), self.file_frame(b"remaining"))
        self.assertEqual((directory / "data/fixture_00001").read_bytes(), self.file_frame(b"newest"))

    def test_filestore_missing_oldest_preserves_output_and_replace_returns_false(self):
        directory = self.run_fixture("filestore-read-delete", self.file_config(test_append=1))
        self.assertEqual((directory / "read-0.txt").read_bytes(), self.file_entries([(b"sentinel", b"keep")]))
        self.assertEqual((directory / "states.txt").read_text(), "before-0=0\nafter-0=0\nempty-0=1\n")
        directory = self.run_fixture("filestore-replace", self.file_config())
        self.assertEqual((directory / "states.txt").read_text(), "replace=0\nopen=0\n")
        self.assertFalse((directory / "data").exists())

    def test_filestore_delete_active_writer_leaves_unlinked_inode_until_close(self):
        directory = self.run_fixture("filestore-delete-open", self.file_config(), {
            "data/fixture_00000": self.file_frame(b"old")})
        self.assertEqual((directory / "states.txt").read_text(),
                         "open-after-delete=1\nwrite-after-delete=1\n")
        self.assertEqual(list((directory / "data").iterdir()), [])

    def test_filestore_buffer_successful_replay_deletes_and_transitions_streaming(self):
        directory = self.run_fixture("filestore-buffer-replay", self.file_config(), {
            "data/fixture_00000": self.file_frame(b"one") + self.file_frame(b"two")})
        self.assertEqual((directory / "received.txt").read_bytes(),
                         self.file_entries([(b"fallback", b"one"), (b"fallback", b"two")]))
        self.assertEqual((directory / "accepted.txt").read_bytes(),
                         self.file_entries([(b"fallback", b"one"), (b"fallback", b"two")]))
        self.assertEqual((directory / "states.txt").read_text(),
                         "lost=0\nbytes-lost=0\nretries=0\ndisconnected=0\nstreaming=1\nempty=1\n")
        self.assertEqual(list((directory / "data").iterdir()), [])

    def test_filestore_buffer_partial_replay_retains_two_unhandled_messages(self):
        directory = self.run_fixture("filestore-buffer-replay", self.file_config(test_partial=1), {
            "data/fixture_00000": b"".join(self.file_frame(x) for x in (b"one", b"two", b"three"))})
        self.assertEqual((directory / "received.txt").read_bytes(), self.file_entries(
            [(b"fallback", x) for x in (b"one", b"two", b"three")]))
        self.assertEqual((directory / "accepted.txt").read_bytes(),
                         self.file_entries([(b"fallback", b"one")]))
        self.assertEqual((directory / "states.txt").read_text(),
                         "lost=0\nbytes-lost=0\nretries=1\ndisconnected=1\nstreaming=0\nempty=0\n")
        expected = self.file_frame(b"two") + self.file_frame(b"three")
        self.assertEqual((directory / "remaining.bin").read_bytes(), expected)
        self.assertEqual((directory / "data/fixture_00000").read_bytes(), expected)

    def test_filestore_partial_then_success_replays_only_retained_messages(self):
        directory = self.run_fixture("filestore-buffer-replay", self.file_config(
            test_partial=1, test_resume=1), {"data/fixture_00000": b"".join(
                self.file_frame(x) for x in (b"one", b"two", b"three"))})
        self.assertEqual((directory / "remaining.bin").read_bytes(),
                         self.file_frame(b"two") + self.file_frame(b"three"))
        self.assertEqual((directory / "received-again.txt").read_bytes(),
                         self.file_entries([(b"fallback", b"two"), (b"fallback", b"three")]))
        self.assertEqual((directory / "accepted-again.txt").read_bytes(), self.file_entries(
            [(b"fallback", x) for x in (b"one", b"two", b"three")]))
        self.assertEqual((directory / "states-again.txt").read_text(),
                         "lost=0\nbytes-lost=0\nretries=1\ndisconnected=0\nstreaming=1\nempty=1\n")
        self.assertEqual(list((directory / "data").iterdir()), [])

    def test_filestore_partial_rewrite_preserves_categories_and_reapplies_add_newlines(self):
        # Input already has the LF added by an earlier write. Existing writer
        # semantics append another LF on replacement; do not silently normalize.
        entries = ((b"one\x00\xff", b"one\n"), (b"two", b"two\n"), (b"", b"three\n"))
        directory = self.run_fixture("filestore-buffer-replay", self.file_config(
            test_partial=1, test_resume=1, write_category="yes", add_newlines=1), {
            "data/fixture_00000": b"".join(self.file_frame(cat + b"\n") +
                                          self.file_frame(payload) for cat, payload in entries)})
        expected = b"".join(self.file_frame(cat + b"\n") + self.file_frame(payload + b"\n")
                            for cat, payload in entries[1:])
        self.assertEqual((directory / "remaining.bin").read_bytes(), expected)
        remaining = [(cat, payload + b"\n") for cat, payload in entries[1:]]
        self.assertEqual((directory / "received-again.txt").read_bytes(), self.file_entries(remaining))
        self.assertEqual((directory / "accepted-again.txt").read_bytes(),
                         self.file_entries([entries[0]] + remaining))
        self.assertEqual((directory / "states-again.txt").read_text(),
                         "lost=0\nbytes-lost=0\nretries=1\ndisconnected=0\nstreaming=1\nempty=1\n")
        self.assertEqual(list((directory / "data").iterdir()), [])

    def test_framed_non_strict_binary_golden_and_payload_bytes(self):
        directory = self.run_fixture("wire")
        # Independently assemble the IDL's wire structure, without Thrift APIs.
        def string(value):
            return struct.pack(">I", len(value)) + value

        entries = ((b"accepted", b"A\x00B\n\xff\xc3\xa9"),
                   (b"unknown\x00\xff", b"\x00\n"), (b"", b"blank-category-payload"))
        # Non-versioned message: name, T_CALL=1, sequence=0; field list=15/id=1.
        body = string(b"Log") + b"\x01" + struct.pack(">i", 0)
        body += b"\x0f\x00\x01\x0c" + struct.pack(">I", len(entries))
        for category, message in entries:
            body += b"\x0b\x00\x01" + string(category)
            body += b"\x0b\x00\x02" + string(message) + b"\x00"
        body += b"\x00"
        self.assertEqual((directory / "request.bin").read_bytes(), struct.pack(">I", len(body)) + body)
        # T_REPLY=2, success field T_I32=8/id=0, ResultCode.OK=0, T_STOP=0.
        body = string(b"Log") + b"\x02" + struct.pack(">i", 0) + b"\x08\x00\x00"
        body += struct.pack(">i", 0) + b"\x00"
        self.assertEqual((directory / "response.bin").read_bytes(), struct.pack(">I", len(body)) + body)

    def test_actual_null_ack_counters_fb303_and_worker_reinitialize(self):
        self.run_fixture("handler")

    def test_config_values_conversions_and_missing_getters(self):
        self.run_fixture("config-values", (
            " \t# full-line comment\n"
            " \ttext \t= alpha=beta \t # inline comment\n"
            'quoted="before#after"\n'
            "duplicate=first\nduplicate=last\nempty=\n=empty key\n"
            "carriage=value\r\nhex=0x2a\noctal=010\nsigned=-17tail\n"
            "garbage=nonsense\nlarge=4294967301suffix\nreal=1.25suffix\n"
        ))

    def test_config_nested_stores_sorted_enumeration_and_serialization(self):
        config = "z=last\na=first\n"
        for i in range(12):
            config += f"<store>\nid={i}\n"
            if i == 0:
                config += "<inner>\nvalue=nested\n</inner>\n"
            config += "</store>\n"
        directory = self.run_fixture("config-hierarchy", config)
        expected = "a=first\nz=last\n"
        for i in (0, 1, 10, 11, 2, 3, 4, 5, 6, 7, 8, 9):
            expected += f"<store{i}>\n  id={i}\n"
            if i == 0:
                expected += "  <inner>\n    value=nested\n  </inner>\n"
            expected += f"</store{i}>\n"
        self.assertEqual((directory / "parsed.conf").read_bytes(), expected.encode())

    def test_config_explicit_parent_typed_inheritance_and_global_fallback(self):
        self.run_fixture("config-inheritance", (
            "port=1463\nfile::nearest=global-nearest\n"
            "file::ancestor=root-typed\nfile::global_only=global-value\n"
            "<store>\ncategory=accepted\ncategories=another\ntype=null\n"
            "unqualified=not-inherited\nfile::nearest=parent-typed\n"
            "file::direct=parent-typed\nfile::self=parent-self\nfile::empty=parent-nonempty\n"
            "file::category=must-not-inherit\nfile::categories=must-not-inherit\n"
            "buffer::nearest=buffer-parent\n"
            "<leaf>\ntype=file\ndirect=leaf-direct\nfile::self=leaf-typed\nempty=\n"
            "</leaf>\n</store>\n"
        ))

    def test_config_malformed_input_is_permissive_and_missing_file_throws(self):
        directory = self.run_fixture("config-malformed", (
            "not-an-assignment\n<bad-open\nafter_bad_open=retained\n"
            "key=first\nkey=last\n"
            "<duplicate>\nid=old\n</different-name>\n"
            "<duplicate>ignored trailing text\nid=new\n</duplicate>\n"
            "<unclosed>\ninside=accepted at EOF\n"
        ))
        self.assertEqual((directory / "parsed.conf").read_text(), (
            "after_bad_open=retained\nkey=last\n"
            "<duplicate>\n  id=new\n</duplicate>\n"
            "<unclosed>\n  inside=accepted at EOF\n</unclosed>\n"
        ))

    def test_handler_defaults_and_constructor_port_without_config_port(self):
        self.run_fixture("config-defaults", "<store>\ncategory=accepted\ntype=null\n</store>\n")

    def test_handler_config_overrides_constructor_port_and_limits(self):
        self.run_fixture("config-overrides", (
            "port=0xBEEF\nnum_thrift_server_threads=07\nmax_conn=17suffix\n"
            "max_queue_size=4294967301suffix\n"
            "<store>\ncategory=accepted\ntype=null\n</store>\n"
        ))

    def test_handler_invalid_config_warns_but_acks_unrouted_messages(self):
        for settings in ("", "port=0\n", "port=1463\nnum_thrift_server_threads=0\n",
                         "port=1463\nnum_thrift_server_threads=garbage\n"):
            with self.subTest(settings=settings):
                self.run_fixture("config-invalid", settings +
                                 "<store>\ncategory=accepted\ntype=null\n</store>\n")

    def test_routing_exact_sorted_prefix_default_and_fanout(self):
        config = "port=1463\nnew_thread_per_category=no\n"
        # Longer prefix appears first in the file; sorted map chooses ab*.
        for category in ("abc*", "ab*", "ab.exact", "default", "ab*"):
            config += f"<store>\ncategory={category}\ntype=null\n</store>\n"
        self.run_fixture("routing", config)

    def test_actual_scribed_help_without_starting_service(self):
        output = checked([self.scribed, "--help"], self.temporary, self.env, timeout=10)
        self.assertIn("Usage:", output)
        self.assertIn("[-p port] [-c config_file]", output)
        # Upstream calls setrlimit before getopt. Its process-local warning is
        # permitted here and must not be described as a daemon/runtime failure.
        self.assertNotIn("scribe server exiting", output)


if __name__ == "__main__":
    unittest.main()
