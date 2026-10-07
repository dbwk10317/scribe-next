#!/usr/bin/env python3
"""Opt-in staged Python package provenance and pure-Python wire smoke.

Uses an already configured SCRIBE_BUILD and installed setuptools. No downloads,
system installation, daemon, or old/company runtime equivalence are implied.
THRIFT_PYTHON_SOURCE points to the matching Thrift 0.25.0 lib/py/src tree.

It modifies the SCRIBE_BUILD tree: it plants a newer stale
lib/py/build/lib/scribe/ttypes.py and deletes src/gen-py/scribe/scribe.py and
__init__.py, then runs make all/install/install-exec-hook in lib/py, which
regenerate src/gen-py/scribe, rebuild lib/py/build and write
lib/py/installed_files.txt, then make uninstall, which consumes that record.
Only the install/uninstall targets go to a temporary DESTDIR.
"""

import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


def installed_package(stage, install_lib):
    """Validate the install command's exact scheme; never choose a glob fallback."""
    stage = stage.resolve()
    library = Path(install_lib)
    if not library.is_absolute() or not library.resolve().is_relative_to(stage):
        raise AssertionError("install_lib is outside DESTDIR: " + str(library))
    expected = library / "scribe"
    candidates = [p for p in stage.rglob("scribe") if p.is_dir()]
    if candidates != [expected] or not (expected / "__init__.py").is_file():
        raise AssertionError("expected only " + str(expected) + "; found " + str(candidates))
    if any(p.is_symlink() for p in stage.rglob("*")):
        raise AssertionError("symlink in installed package path: " + str(expected))
    return expected


class PythonPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("SCRIBE_BUILD", "THRIFT_PREFIX", "FB303_PREFIX")
        if any(not os.environ.get(name) for name in names):
            raise unittest.SkipTest("set " + ", ".join(names) + " for staged packaging")
        cls.build, cls.thrift, cls.fb303 = (Path(os.environ[n]).resolve() for n in names)
        makefile = (cls.build / "lib/py/Makefile").read_text()
        values = dict(line.split(" = ", 1) for line in makefile.splitlines() if " = " in line)
        cls.python = shlex.split(values["PYTHON"])
        cls.prefix = values["PY_PREFIX"]
        cls.install_args = shlex.split(values.get("PYTHON_SETUPUTIL_ARGS",
                                                os.environ.get("PYTHON_SETUPUTIL_ARGS", "")))
        for name in ("lib/py/setup.py", "lib/py/Makefile.am", "src/Makefile.am", "if/scribe.thrift"):
            if (ROOT / name).read_bytes() != (cls.build / name).read_bytes():
                raise AssertionError("build source differs: " + name)
        temporary = tempfile.TemporaryDirectory(prefix="scribe-python-package-")
        cls.addClassCleanup(temporary.cleanup)
        cls.temporary = Path(temporary.name)
        cls.stage = cls.temporary / "stage"
        # A newer cache from the legacy package must never win over current IDL output.
        cache = cls.build / "lib/py/build/lib/scribe/ttypes.py"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("raise AssertionError('stale legacy build cache')\n")
        os.utime(cache, (time.time() + 3600, time.time() + 3600))
        # Missing sibling outputs must also be regenerated without a C++ rebuild.
        (cls.build / "src/gen-py/scribe/scribe.py").unlink(missing_ok=True)
        library = cls.install_library(cls.stage)
        cls.run_command(["make", "-C", cls.build / "lib/py", "all", "install",
                         "DESTDIR=" + str(cls.stage)])
        cls.package = installed_package(cls.stage, library)

    @classmethod
    def install_library(cls, stage):
        # Ask the selected interpreter/backend to finalize the same install options.
        output = cls.run_command([*cls.python, "-B", "-c", """
import json, sys
from setuptools import Distribution
d = Distribution({'name': 'scribe', 'version': '2.0', 'packages': ['scribe']})
d.parse_config_files()
d.script_args = ['install', '--root=' + sys.argv[1], '--prefix=' + sys.argv[2], *sys.argv[3:]]
d.parse_command_line()
c = d.get_command_obj('install'); c.ensure_finalized()
print(json.dumps({'install_lib': c.install_lib}))
""", stage, cls.prefix, *cls.install_args], cwd=cls.build / "lib/py")
        library = json.loads(output.splitlines()[-1])["install_lib"]
        library = Path(library)
        if not library.is_absolute() or not library.resolve().is_relative_to(stage.resolve()):
            raise AssertionError("install_lib is outside DESTDIR: " + str(library))
        return library

    @classmethod
    def run_command(cls, command, env=None, cwd=None):
        result = subprocess.run(list(map(str, command)), cwd=cwd or cls.temporary,
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=120)
        if result.returncode:
            raise AssertionError(result.stdout)
        return result.stdout

    def test_installed_sources_match_current_generated_idl(self):
        expected = self.temporary / "expected"
        expected.mkdir()
        self.run_command([self.thrift / "bin/thrift", "-I", self.fb303 / "share",
                          "--gen", "py", "-out", expected, ROOT / "if/scribe.thrift"])
        generated = {p.name: p.read_bytes() for p in (expected / "scribe").glob("*.py")}
        installed = {p.name: p.read_bytes() for p in self.package.glob("*.py")}
        self.assertEqual(installed, generated)
        self.assertFalse((self.package.parent / "bucketupdater").exists())
        metadata = list(self.package.parent.glob("scribe-2.0*.egg-info/PKG-INFO"))
        self.assertEqual(len(metadata), 1)
        self.assertIn("Name: scribe\n", metadata[0].read_text())
        self.assertIn("Version: 2.0\n", metadata[0].read_text())
        # Both layouts must validate only against the build PYTHON's own scheme:
        # the pythonX.Y directory its setuptools chose for the real install above.
        scheme = self.package.parent.resolve().relative_to(self.stage.resolve()).parent
        for layout in ("site-packages", "dist-packages"):
            stage = self.temporary / ("scheme-" + layout)
            library = stage / scheme / layout
            package = library / "scribe"
            with self.assertRaises(AssertionError):
                installed_package(stage, library)
            package.mkdir(parents=True)
            (package / "__init__.py").touch()
            self.assertEqual(installed_package(stage, library), package)
            other = stage / "unexpected/scribe"
            other.mkdir(parents=True)
            with self.assertRaises(AssertionError):
                installed_package(stage, library)
            with self.assertRaises(AssertionError):
                installed_package(stage, self.temporary / "outside")
            other.rmdir()
            outside = self.temporary / "outside-file"
            outside.touch()
            (package / "__init__.py").unlink()
            (package / "__init__.py").symlink_to(outside)
            with self.assertRaises(AssertionError):
                installed_package(stage, library)
            (package / "__init__.py").unlink()
            (package / "__init__.py").touch()
            actual = library / "actual-package"
            package.rename(actual)
            package.symlink_to(actual, target_is_directory=True)
            with self.assertRaises(AssertionError):
                installed_package(stage, library)

        original = type(self).install_args
        try:
            type(self).install_args = [*original, "--root=" + str(self.temporary / "outside-root")]
            with self.assertRaises(AssertionError):
                self.install_library(self.temporary / "guarded-stage")
        finally:
            type(self).install_args = original

    def test_install_hook_repairs_missing_output_and_newer_legacy_cache(self):
        cache = self.build / "lib/py/build/lib/scribe/ttypes.py"
        cache.write_text("raise AssertionError('stale legacy build cache')\n")
        os.utime(cache, (time.time() + 3600, time.time() + 3600))
        (self.build / "src/gen-py/scribe/__init__.py").unlink()
        stage = self.temporary / "install-only"
        library = self.install_library(stage)
        self.run_command(["make", "-C", self.build / "lib/py", "install-exec-hook",
                          "DESTDIR=" + str(stage)])
        package = installed_package(stage, library)
        for name in ("__init__.py", "constants.py", "scribe.py", "ttypes.py"):
            self.assertEqual((package / name).read_bytes(),
                             (self.build / "src/gen-py/scribe" / name).read_bytes())
        self.assertNotIn(b"stale legacy build cache", (package / "ttypes.py").read_bytes())
        # The uninstall hook must remove exactly the recorded files and the directories they
        # emptied, under the same DESTDIR, and consume installed_files.txt.
        record = self.build / "lib/py/installed_files.txt"
        self.assertTrue(record.is_file())
        self.run_command(["make", "-C", self.build / "lib/py", "uninstall",
                          "DESTDIR=" + str(stage)])
        self.assertFalse(record.exists())
        self.assertFalse(package.exists())
        self.assertEqual(list(stage.rglob("*.py")), [])
        self.assertEqual(list(stage.rglob("*.egg-info")), [])

    def test_installed_client_import_and_binary_wire(self):
        source = os.environ.get("THRIFT_PYTHON_SOURCE")
        if not source:
            self.skipTest("set THRIFT_PYTHON_SOURCE for matching source-runtime smoke")
        runtime = self.temporary / "runtime"
        runtime.mkdir()
        shutil.copytree(source, runtime / "thrift")
        self.run_command([self.thrift / "bin/thrift", "--gen", "py", "-out", runtime,
                          self.fb303 / "share/fb303/if/fb303.thrift"])
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(self.package.parent), str(runtime))),
                   PYTHONDONTWRITEBYTECODE="1")
        output = self.run_command([*self.python, "-B", "-c", """
from scribe.ttypes import LogEntry, ResultCode
from scribe.scribe import Client, Iface, Log_args, Log_result
from fb303.FacebookService import Iface as BaseIface
from thrift.protocol import TBinaryProtocol
from thrift.transport import TTransport
assert issubclass(Iface, BaseIface)
assert (ResultCode.OK, ResultCode.TRY_LATER) == (0, 1)
memory = TTransport.TMemoryBuffer()
protocol = TBinaryProtocol.TBinaryProtocol(memory, strictRead=False, strictWrite=False)
entry = LogEntry(category='c\\0é', message='m\\n\\0')
Client(protocol).send_Log([entry])
wire = memory.getvalue()
assert wire.hex() == '000000034c6f6701000000000f00010c000000010b0001000000046300c3a90b0002000000036d0a000000'
reader = TBinaryProtocol.TBinaryProtocol(TTransport.TMemoryBuffer(wire), strictRead=False)
assert reader.readMessageBegin() == ('Log', 1, 0)
args = Log_args(); args.read(reader); reader.readMessageEnd()
assert args.messages == [entry]
reply = TTransport.TMemoryBuffer()
Log_result(success=ResultCode.TRY_LATER).write(TBinaryProtocol.TBinaryProtocol(reply))
assert reply.getvalue().hex() == '0800000000000100'
print('installed Python client import, inherited fb303, Log bytes and result PASS')
"""], env)
        self.assertIn("PASS", output)


if __name__ == "__main__":
    unittest.main()
