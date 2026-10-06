"""Bounded actual ThriftFileStore bytes/readback; single-version characterization.

Each child has a ten-second C++ alarm and the shared owner has a subprocess
timeout. Readback is after normal close/join, not a crash/fsync guarantee.
Copy preserves upstream default framed mode even when its source is raw.
Empty/over-chunk drops retain their observed behavior. No old runtime is exercised.
"""

import os
from pathlib import Path
import struct


class ThriftFileContracts:
    @staticmethod
    def thriftfile_config(**values):
        defaults = {"file_path": "@DIRECTORY@/data", "base_filename": "fixture",
                    "rotate_period": "never", "create_symlink": "yes",
                    "fs_type": "std", "max_size": 0}
        defaults.update(values)
        return ("port=1463\n<store>\ncategory=accepted\ntype=null\n</store>\n" +
                "".join(f"{key}={value}\n" for key, value in defaults.items()))

    @staticmethod
    def thriftfile_state(directory, name):
        return dict(line.split("=", 1) for line in (directory / name).read_text().splitlines())

    @staticmethod
    def thriftfile_frame(payload):
        # TFileTransport memcpy()s the native uint32_t length, unlike the
        # ordinary spool's specified little-endian frame. This lane is Linux.
        return struct.pack("=I", len(payload)) + payload

    def thriftfile_bytes(self, payloads, chunk=0):
        result = b""
        for payload in payloads:
            frame = self.thriftfile_frame(payload)
            if chunk and len(result) % chunk + len(frame) > chunk:
                result += b"\0" * (chunk - len(result) % chunk)
            result += frame
        return result

    def assert_thriftfile_readback(self, directory, name, payloads, simple=False):
        self.assertEqual((directory / (name + ".bin")).read_bytes(), b"".join(payloads))
        if not simple:
            self.assertEqual((directory / (name + "-events.txt")).read_bytes(),
                             self.file_entries((b"", payload) for payload in payloads))

    def test_thriftfile_defaults_and_unopened_copy_transport_settings(self):
        directory = self.run_fixture("thriftfile-settings", self.thriftfile_config())
        for name in ("configured.txt", "copy-configured.txt"):
            state = self.thriftfile_state(directory, name)
            self.assertEqual({key: state[key] for key in ("open", "kind", "use_simple_file",
                             "flush_frequency_ms", "msg_buffer_size")},
                             dict(open="0", kind="closed", use_simple_file="0",
                                  flush_frequency_ms="0", msg_buffer_size="0"))
        for name in ("opened.txt", "copy-opened.txt"):
            state = self.thriftfile_state(directory, name)
            self.assertEqual(state["kind"], "tfile")
            self.assertEqual(state["transport_chunk_size"], "16777216")
            self.assertEqual(state["transport_flush_max_us"], "3000000")
            self.assertEqual(state["transport_event_buffer_size"], "10000")

    def test_thriftfile_configured_and_copied_transport_settings(self):
        directory = self.run_fixture("thriftfile-settings", self.thriftfile_config(
            chunk_size=16, flush_frequency_ms=7, msg_buffer_size=3))
        for name in ("opened.txt", "copy-opened.txt"):
            state = self.thriftfile_state(directory, name)
            self.assertEqual(state["kind"], "tfile")
            self.assertEqual(state["transport_chunk_size"], "16")
            self.assertEqual(state["transport_flush_max_us"], "7000")
            self.assertEqual(state["transport_event_buffer_size"], "3")

    def test_thriftfile_default_event_bytes_ignore_category_and_drop_empty(self):
        payloads = (b"A\0B\n\xff", b"ends\n")
        directory = self.run_fixture("thriftfile-write", self.thriftfile_config(
            write_category="yes", add_newlines=1))
        self.assertEqual((directory / "data/fixture_00000").read_bytes(),
                         self.thriftfile_bytes(payloads))
        self.assert_thriftfile_readback(directory, "readback", payloads)
        written = self.thriftfile_state(directory, "written.txt")
        self.assertEqual((written["events_written"], written["current_size"]), ("3", "10"))
        self.assertEqual(self.thriftfile_state(directory, "closed.txt")["kind"], "closed")
        self.assertEqual(os.readlink(directory / "data/fixture_current"), "fixture_00000")

    def test_thriftfile_simple_raw_bytes_ignore_event_settings_and_category(self):
        payloads = (b"A\0B\n\xff", b"ends\n")
        for value in (1, 2):
            with self.subTest(use_simple_file=value):
                directory = self.run_fixture("thriftfile-write", self.thriftfile_config(
                    use_simple_file=value, chunk_size=8, flush_frequency_ms=7,
                    msg_buffer_size=3, write_category="yes", add_newlines=1))
                self.assertEqual((directory / "data/fixture_00000").read_bytes(), b"".join(payloads))
                self.assert_thriftfile_readback(directory, "readback", payloads, simple=True)
                opened = self.thriftfile_state(directory, "opened.txt")
                self.assertEqual(opened["kind"], "simple")
                self.assertNotIn("transport_chunk_size", opened)

    def test_thriftfile_chunk_padding_and_actual_event_reader(self):
        payloads = (b"A\0B\n\xff", b"ends\n")
        directory = self.run_fixture("thriftfile-write", self.thriftfile_config(
            chunk_size=16, flush_frequency_ms=7, msg_buffer_size=3))
        self.assertEqual((directory / "data/fixture_00000").read_bytes(),
                         self.thriftfile_frame(payloads[0]) + b"\0" * 7 +
                         self.thriftfile_frame(payloads[1]))
        self.assert_thriftfile_readback(directory, "readback", payloads)

    def test_thriftfile_reopen_always_increments_suffix_without_appending(self):
        for simple in (0, 1):
            for rotate in ("no", "yes"):
                with self.subTest(simple=simple, rotate_on_reopen=rotate):
                    directory = self.run_fixture("thriftfile-reopen", self.thriftfile_config(
                        use_simple_file=simple, rotate_on_reopen=rotate), {
                            "data/fixture_00000": b"untouched-0",
                            "data/fixture_00007": b"untouched-7"})
                    self.assertEqual((directory / "data/fixture_00000").read_bytes(), b"untouched-0")
                    self.assertEqual((directory / "data/fixture_00007").read_bytes(), b"untouched-7")
                    for pass_number, suffix in enumerate((8, 9)):
                        expected = b"A\0B" if simple else self.thriftfile_frame(b"A\0B")
                        self.assertEqual((directory / f"data/fixture_{suffix:05d}").read_bytes(), expected)
                        state = self.thriftfile_state(directory, f"pass-{pass_number}.txt")
                        self.assertEqual(Path(state["filename"]).name, f"fixture_{suffix:05d}")
                        self.assert_thriftfile_readback(directory, f"readback-{pass_number}",
                                                       (b"A\0B",), simple=bool(simple))
                    self.assertEqual(os.readlink(directory / "data/fixture_current"), "fixture_00009")
                    self.assertEqual(sorted(path.name for path in (directory / "data").iterdir()),
                                     ["fixture_00000", "fixture_00007", "fixture_00008",
                                      "fixture_00009", "fixture_current"])

    def test_thriftfile_open_model_copy_retains_chunk_settings_and_uses_new_path(self):
        payloads = (b"A\0B\n\xff", b"ends\n")
        directory = self.run_fixture("thriftfile-copy", self.thriftfile_config(
            sub_directory="nested", base_symlink_name="active", chunk_size=16,
            flush_frequency_ms=7, msg_buffer_size=3))
        expected = self.thriftfile_bytes(payloads, chunk=16)
        self.assertEqual((directory / "data/nested/fixture_00000").read_bytes(), expected)
        self.assertEqual((directory / "data/copied/nested/copied_00000").read_bytes(), expected)
        self.assertEqual(os.readlink(directory / "data/nested/active_current"), "fixture_00000")
        self.assertEqual(os.readlink(directory / "data/copied/nested/active_current"), "copied_00000")
        self.assertEqual(self.thriftfile_state(directory, "copy-configured.txt")["open"], "0")
        copied = self.thriftfile_state(directory, "copy-written.txt")
        self.assertEqual((copied["transport_chunk_size"], copied["transport_flush_max_us"],
                          copied["transport_event_buffer_size"]), ("16", "7000", "3"))
        self.assert_thriftfile_readback(directory, "source-readback", payloads)
        self.assert_thriftfile_readback(directory, "copy-readback", payloads)

    def test_thriftfile_simple_source_copy_preserves_legacy_framed_reader_contract(self):
        payloads = (b"A\0B\n\xff", b"ends\n")
        for value in (1, 2):
            with self.subTest(use_simple_file=value):
                directory = self.run_fixture("thriftfile-copy", self.thriftfile_config(
                    use_simple_file=value, sub_directory="nested", base_symlink_name="active",
                    chunk_size=16, flush_frequency_ms=7, msg_buffer_size=3))
                self.assertEqual((directory / "data/copied/nested/copied_00000").read_bytes(),
                                 self.thriftfile_bytes(payloads, chunk=16))
                self.assertEqual((directory / "data/nested/fixture_00000").read_bytes(),
                                 b"".join(payloads))
                configured = self.thriftfile_state(directory, "copy-configured.txt")
                self.assertEqual((configured["open"], configured["kind"], configured["filename"],
                                  configured["current_size"], configured["events_written"]),
                                 ("0", "closed", "", "0", "0"))
                source = self.thriftfile_state(directory, "written.txt")
                copied = self.thriftfile_state(directory, "copy-written.txt")
                self.assertEqual((source["kind"], source["use_simple_file"]),
                                 ("simple", str(value)))
                self.assertNotIn("transport_chunk_size", source)
                self.assertEqual((copied["kind"], copied["use_simple_file"],
                                  copied["transport_chunk_size"], copied["flush_frequency_ms"],
                                  copied["msg_buffer_size"]), ("tfile", "0", "16", "7", "3"))
                self.assertEqual(os.readlink(directory / "data/nested/active_current"),
                                 "fixture_00000")
                self.assertEqual(os.readlink(directory / "data/copied/nested/active_current"),
                                 "copied_00000")
                self.assert_thriftfile_readback(directory, "source-readback", payloads, simple=True)
                self.assert_thriftfile_readback(directory, "copy-readback", payloads)

    def test_thriftfile_simple_copy_keeps_existing_framed_files_and_uses_next_suffix(self):
        payloads = (b"A\0B\n\xff", b"ends\n")
        legacy = self.thriftfile_frame(b"legacy\0\n\xff")
        for value in (1, 2):
            with self.subTest(use_simple_file=value):
                directory = self.run_fixture("thriftfile-copy", self.thriftfile_config(
                    use_simple_file=value, chunk_size=16, flush_frequency_ms=7, msg_buffer_size=3),
                    {"data/copied/copied_00000": legacy, "data/copied/copied_00007": legacy})
                self.assertEqual((directory / "data/copied/copied_00008").read_bytes(),
                                 self.thriftfile_bytes(payloads, chunk=16))
                for suffix in (0, 7):
                    self.assertEqual((directory / f"data/copied/copied_{suffix:05d}").read_bytes(),
                                     legacy)
                self.assertEqual(Path(self.thriftfile_state(directory, "copy-written.txt")
                                      ["filename"]).name, "copied_00008")
                self.assertEqual(os.readlink(directory / "data/copied/copied_current"),
                                 "copied_00008")
                self.assertEqual(sorted(path.name for path in (directory / "data/copied").iterdir()),
                                 ["copied_00000", "copied_00007", "copied_00008", "copied_current"])
                self.assert_thriftfile_readback(directory, "copy-readback", payloads)

    def test_thriftfile_known_over_chunk_event_is_accepted_but_not_written(self):
        directory = self.run_fixture("thriftfile-chunk-limit", self.thriftfile_config(
            chunk_size=8, flush_frequency_ms=7, msg_buffer_size=3))
        self.assertEqual((directory / "data/fixture_00000").read_bytes(), b"")
        written = self.thriftfile_state(directory, "written.txt")
        self.assertEqual((written["events_written"], written["current_size"]), ("1", "9"))
        self.assert_thriftfile_readback(directory, "readback", ())
