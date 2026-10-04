#!/usr/bin/env python3
"""Exercise import failures in temporary checkouts, using local Git objects only."""

import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "verify_upstream_import", Path(__file__).with_name("verify_upstream_import.py")
)
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class ImportVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = tempfile.TemporaryDirectory(prefix="scribe-import-baseline-")
        cls.addClassCleanup(cls.baseline.cleanup)
        cls.baseline_root = Path(cls.baseline.name)
        cls.run_git(cls.baseline_root, "init", "--quiet")
        # A local fetch preserves the exact pinned objects; no URL is contacted.
        cls.run_git(
            cls.baseline_root, "fetch", "--quiet", "--no-tags",
            str(VERIFIER.ROOT), VERIFIER.COMMIT,
        )
        cls.run_git(cls.baseline_root, "checkout", "--quiet", "--detach", VERIFIER.COMMIT)
        cls.expected_paths = cls.run_git(cls.baseline_root, "ls-files", "-z")
        cls.expected_index = cls.index_entries(cls.baseline_root)

    @staticmethod
    def run_git(root, *args, input=None):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], input=input, stderr=subprocess.PIPE
        )

    @classmethod
    def index_entries(cls, root):
        return {
            path: metadata.split()
            for metadata, path in (
                record.split(b"\t", 1)
                for record in cls.run_git(root, "ls-files", "--stage", "-z").split(b"\0")[:-1]
            )
        }

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="scribe-import-test-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "checkout"
        shutil.copytree(self.baseline_root, self.root)
        self.ignore = self.root / ".gitignore"
        self.upstream_ignore = self.ignore.read_bytes()
        self.ignore.write_bytes(
            self.upstream_ignore + VERIFIER.IGNORE_APPENDIX
            + b"test additions\n!/test/resultChecker/makefile\n"
        )
        patch = mock.patch.object(VERIFIER, "ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def verify(self, status, message):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            actual = VERIFIER.main()
        self.assertEqual(actual, status, output.getvalue() + errors.getvalue())
        self.assertIn(message, output.getvalue() + errors.getvalue())

    def test_pristine_import_passes(self):
        self.verify(0, "PASS: 105 upstream paths match")

    def test_changed_content_fails(self):
        with (self.root / "src/conf.cpp").open("ab") as source:
            source.write(b"\n// mutation\n")
        self.verify(1, "src/conf.cpp: content differs from upstream")

    def test_missing_source_fails(self):
        (self.root / "if/bucketupdater.thrift").unlink()
        self.verify(1, "if/bucketupdater.thrift:")

    def test_removed_executable_bit_fails(self):
        (self.root / "bootstrap.sh").chmod(0o644)
        self.verify(1, "bootstrap.sh: mode 100644, expected 100755")

    def test_removed_owner_execute_bit_fails_with_other_execute_bits(self):
        (self.root / "bootstrap.sh").chmod(0o655)
        self.verify(1, "bootstrap.sh: mode 100644, expected 100755")

    def test_added_executable_bit_fails(self):
        (self.root / "LICENSE").chmod(0o755)
        self.verify(1, "LICENSE: mode 100755, expected 100644")

    def test_git_mode_uses_owner_execute_bit(self):
        (self.root / "LICENSE").chmod(0o645)
        self.verify(0, "PASS: 105 upstream paths match")

    def test_file_symlink_fails_even_with_identical_bytes(self):
        source = self.root / "README"
        source.rename(self.root / "README-copy")
        source.symlink_to("README-copy")
        self.verify(1, "README: not a regular file")

    def test_parent_symlink_fails_even_with_identical_bytes(self):
        source = self.root / "if"
        source.rename(self.root / "if-copy")
        source.symlink_to("if-copy", target_is_directory=True)
        self.verify(1, "if/scribe.thrift: parent is not a regular directory")

    def test_upstream_ignore_edit_fails(self):
        self.ignore.write_bytes(self.ignore.read_bytes().replace(b"Makefile\n", b"makefile\n", 1))
        self.verify(1, ".gitignore: upstream ignore rules or appendix marker changed")

    def test_missing_appendix_marker_fails(self):
        self.ignore.write_bytes(self.upstream_ignore)
        self.verify(1, ".gitignore: upstream ignore rules or appendix marker changed")

    def test_project_only_appendix_is_allowed(self):
        with self.ignore.open("ab") as rules:
            rules.write(b"/build/\n")
        self.verify(0, "PASS: 105 upstream paths match")

    def test_missing_makefile_exception_fails_on_case_insensitive_git(self):
        self.ignore.write_bytes(
            self.ignore.read_bytes().replace(b"!/test/resultChecker/makefile\n", b"")
        )
        self.verify(1, "test/resultChecker/makefile: ignored with core.ignorecase=true")

    def test_new_rule_hiding_upstream_source_fails(self):
        with self.ignore.open("ab") as rules:
            rules.write(b"/src/conf.cpp\n")
        self.verify(1, "src/conf.cpp: ignored with core.ignorecase=false")

    def test_all_upstream_paths_can_be_staged_in_both_git_modes(self):
        for ignorecase in ("false", "true"):
            with self.subTest(ignorecase=ignorecase):
                self.run_git(self.root, "rm", "--quiet", "--cached", "-r", ".")
                self.run_git(
                    self.root, "-c", f"core.ignorecase={ignorecase}",
                    "-c", "core.excludesFile=/dev/null", "add", "--all",
                )
                self.assertEqual(self.run_git(self.root, "ls-files", "-z"), self.expected_paths)
                actual = self.index_entries(self.root)
                for path, expected in self.expected_index.items():
                    self.assertEqual(actual[path][0], expected[0], path)
                    self.assertEqual(actual[path][2], b"0", path)
                    if path != b".gitignore":
                        self.assertEqual(actual[path][1], expected[1], path)
                self.assertEqual(
                    self.run_git(self.root, "show", ":.gitignore"), self.ignore.read_bytes()
                )

    def test_missing_pinned_object_fails(self):
        with mock.patch.object(VERIFIER, "COMMIT", "0" * 40):
            self.verify(1, "cannot read pinned upstream")

    def test_wrong_tree_fails(self):
        with mock.patch.object(VERIFIER, "TREE", "0" * 40):
            self.verify(1, "upstream tree does not match the pinned tree")

    def test_git_replacements_cannot_change_the_baseline(self):
        original = self.run_git(self.root, "rev-parse", VERIFIER.COMMIT + ":.gitignore").decode().strip()
        replacement = self.run_git(self.root, "hash-object", "-w", "--stdin", input=b"replacement\n").decode().strip()
        self.run_git(self.root, "replace", original, replacement)
        self.verify(0, "PASS: 105 upstream paths match")


if __name__ == "__main__":
    unittest.main()
