#!/usr/bin/env python3
"""Opt-in real Scribe API smoke tests, without a daemon, sockets, or service.

Set THRIFT_PREFIX, FB303_PREFIX, SCRIBE_BUILD, and TOOLS_PREFIX to a prepared
Thrift 0.25.0/fb303 build and its compiler/Boost/libevent environment. SCRIBE_BUILD
is a configured in-source build copy of the current checkout. Reused objects
must have matching sources, generated code, and non-stale compiler dependencies.
Only temporary fixture files are created; no dependency download/build occurs.

This is a single-version golden and handler smoke, not old/new differential,
socket-server coverage, file/spool compatibility, or a durability guarantee.
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

    def run_fixture(self, mode):
        directory = self.temporary / mode
        directory.mkdir()
        config = directory / "scribe.conf"
        # A port is required by initialize(); no socket/server is constructed.
        config.write_text("port=1463\n<store>\ncategory=accepted\ntype=null\n</store>\n")
        output = checked([self.fixture, mode, config, directory], directory, self.env, timeout=20)
        self.assertIn("PASS " + mode, output)
        return directory

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

    def test_actual_scribed_help_without_starting_service(self):
        output = checked([self.scribed, "--help"], self.temporary, self.env, timeout=10)
        self.assertIn("Usage:", output)
        self.assertIn("[-p port] [-c config_file]", output)
        # Upstream calls setrlimit before getopt. Its process-local warning is
        # permitted here and must not be described as a daemon/runtime failure.
        self.assertNotIn("scribe server exiting", output)


if __name__ == "__main__":
    unittest.main()
