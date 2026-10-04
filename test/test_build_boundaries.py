#!/usr/bin/env python3
"""scribe-next build-boundary regressions; never build or run Scribe.

The shell tests use stub tools and the actual flag-selection shell fragment.
They do not demonstrate Autotools expansion or compiler compatibility. Real
Autotools tests run only when their tools exist, and report an explicit skip
otherwise. Every generated file is confined to a temporary directory.
"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUTOTOOLS = ("autoreconf", "autoconf", "automake", "aclocal", "m4")


def run(command, root, env=None):
    return subprocess.run(
        command, cwd=root, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=120,
    )


def macro_body(name):
    source = (ROOT / "acinclude.m4").read_text()
    return source.split(f"AC_DEFUN([{name}],\n[\n", 1)[1].split("\n])", 1)[0]


def automake_initialization():
    return re.search(
        r"^AM_INIT_AUTOMAKE\([^\n]+", (ROOT / "configure.ac").read_text(), re.M,
    ).group()


class BootstrapShellTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="scribe-bootstrap-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        shutil.copy2(ROOT / "bootstrap.sh", self.root / "bootstrap.sh")
        for name, path, status in (
            ("autoreconf", self.bin / "autoreconf", "AUTORECONF_STATUS"),
            ("configure", self.root / "configure", "CONFIGURE_STATUS"),
        ):
            path.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\0' \"$@\" > '{name}.args'\n"
                f'exit "${{{status}:-0}}"\n'
            )
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin))
        self.env.pop("AUTORECONF_STATUS", None)
        self.env.pop("CONFIGURE_STATUS", None)

    def arguments(self, tool):
        return (self.root / f"{tool}.args").read_bytes().split(b"\0")[:-1]

    def test_no_arguments_preserves_existing_options(self):
        result = run(["/bin/sh", "./bootstrap.sh"], self.root, self.env)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            self.arguments("autoreconf"), [b"--force", b"--verbose", b"--install"],
        )
        self.assertEqual(self.arguments("configure"), [b"--config-cache"])

    def test_preserves_spaces_empty_arguments_and_globs(self):
        (self.root / "one.marker").touch()
        (self.root / "two.marker").touch()
        arguments = ["--prefix=/tmp/scribe prefix", "CXXFLAGS=-O2 -std=c++17", "", "*.marker"]
        result = run(["/bin/sh", "./bootstrap.sh", *arguments], self.root, self.env)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            self.arguments("configure"),
            [b"--config-cache", *(argument.encode() for argument in arguments)],
        )

    def test_autoreconf_failure_stops_before_stale_configure(self):
        self.env["AUTORECONF_STATUS"] = "23"
        result = run(["/bin/sh", "./bootstrap.sh"], self.root, self.env)
        self.assertFalse((self.root / "configure.args").exists(), result.stdout)
        self.assertEqual(result.returncode, 23, result.stdout)

    def test_missing_autoreconf_stops_before_stale_configure(self):
        (self.bin / "autoreconf").unlink()
        result = run(["/bin/sh", "./bootstrap.sh"], self.root, self.env)
        self.assertFalse((self.root / "configure.args").exists(), result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_configure_failure_is_returned(self):
        self.env["CONFIGURE_STATUS"] = "29"
        result = run(["/bin/sh", "./bootstrap.sh"], self.root, self.env)
        self.assertEqual(result.returncode, 29, result.stdout)


class ConfigureShellTests(unittest.TestCase):
    def test_automake_is_initialized_once_with_original_options(self):
        sources = (ROOT / "configure.ac").read_text() + (ROOT / "acinclude.m4").read_text()
        self.assertEqual(len(re.findall(r"^AM_INIT_AUTOMAKE\(", sources, re.M)), 1)
        for option in ("foreign", "-Wall", "1.9.5", "no-define"):
            self.assertIn(option, automake_initialization())

    def test_caller_flag_state_is_captured_before_compiler_defaults(self):
        initialize = macro_body("FB_INITIALIZE")
        for variable, compiler in (("cflags", "CC"), ("cxxflags", "CXX")):
            self.assertLess(
                initialize.index(f"fb_user_{variable}_set="),
                initialize.index(f"AC_PROG_{compiler}"),
            )

    def test_flag_selection_shell_matrix(self):
        initialize = macro_body("FB_INITIALIZE")
        snapshots = "\n".join(re.findall(
            r"^fb_user_(?:c|cxx)flags_set=.*$", initialize, re.M,
        ))
        selection = macro_body("FB_ENABLE_DEFAULT_OPT_BUILD")
        selection = selection[selection.index('if test "$ENABLED_OPT"'):]
        selection = selection.split("AC_MSG_RESULT", 1)[0]
        # This models compiler-added defaults only; it is not an Autoconf run.
        script = snapshots + '\n: "${CFLAGS=-g -O2}" "${CXXFLAGS=-g -O2}"\n'
        script += selection + '\nprintf "%s\\n%s\\n" "$CFLAGS" "$CXXFLAGS"\n'
        for mode, default in (("yes", "-Wall -O3"), ("no", "-Wall -g")):
            for cflags in (None, "", "-O0 -g3"):
                for cxxflags in (None, "", "-O2 -std=c++17"):
                    with self.subTest(mode=mode, cflags=cflags, cxxflags=cxxflags):
                        env = dict(os.environ, ENABLED_OPT=mode)
                        for name, value in (("CFLAGS", cflags), ("CXXFLAGS", cxxflags)):
                            env.pop(name, None)
                            if value is not None:
                                env[name] = value
                        result = run(["/bin/sh", "-c", script], ROOT, env)
                        self.assertEqual(result.returncode, 0, result.stdout)
                        self.assertEqual(result.stdout.splitlines(), [
                            default if cflags is None else cflags,
                            default if cxxflags is None else cxxflags,
                        ])


class AutotoolsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [tool for tool in AUTOTOOLS if shutil.which(tool) is None]
        if missing:
            raise unittest.SkipTest("real Autotools integration unrun; missing " + ", ".join(missing))

    def test_actual_project_autoreconf_and_configure_help(self):
        with tempfile.TemporaryDirectory(prefix="scribe-autoreconf-test-") as temporary:
            root = Path(temporary) / "source"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            result = run(["autoreconf", "--force", "--verbose", "--install"], root)
            self.assertEqual(result.returncode, 0, result.stdout)
            result = run(["./configure", "--help"], root)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("--disable-opt", result.stdout)

    def test_real_configure_flag_matrix_in_minimal_fixture(self):
        missing = [tool for tool in ("cc", "c++", "make") if shutil.which(tool) is None]
        if missing:
            self.skipTest("real compiler/configure flag check unrun; missing " + ", ".join(missing))
        with tempfile.TemporaryDirectory(prefix="scribe-configure-flags-") as temporary:
            root = Path(temporary)
            shutil.copy2(ROOT / "acinclude.m4", root / "acinclude.m4")
            (root / "configure.ac").write_text(
                "AC_INIT([scribe-build-boundary-test], [1])\n"
                + automake_initialization() + "\n"
                "FB_INITIALIZE\n"
                "FB_ENABLE_DEFAULT_OPT_BUILD\n"
                "AC_CONFIG_FILES([Makefile flags.mk])\n"
                "AC_OUTPUT\n"
            )
            (root / "Makefile.am").write_text("EXTRA_DIST = flags.mk.in\n")
            (root / "flags.mk.in").write_text("CFLAGS=@CFLAGS@\nCXXFLAGS=@CXXFLAGS@\n")
            result = run(["autoreconf", "--force", "--install"], root)
            self.assertEqual(result.returncode, 0, result.stdout)
            for mode, default in (([], "-Wall -O3"), (["--disable-opt"], "-Wall -g")):
                for cflags in (None, "", "-O0 -g3"):
                    for cxxflags in (None, "", "-O2 -std=c++17"):
                        with self.subTest(mode=mode, cflags=cflags, cxxflags=cxxflags):
                            env = dict(os.environ)
                            for name, value in (("CFLAGS", cflags), ("CXXFLAGS", cxxflags)):
                                env.pop(name, None)
                                if value is not None:
                                    env[name] = value
                            result = run(["./configure", *mode], root, env)
                            self.assertEqual(result.returncode, 0, result.stdout)
                            self.assertEqual((root / "flags.mk").read_text(),
                                f"CFLAGS={default if cflags is None else cflags}\n"
                                f"CXXFLAGS={default if cxxflags is None else cxxflags}\n")


if __name__ == "__main__":
    unittest.main()
