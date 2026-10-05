#!/usr/bin/env python3
"""Validate the existing Linux build lane in a new, isolated output directory.

Uses caller-prepared dependencies only. Never installs dependencies or starts a
daemon. The installation prefix is logical: every installed file uses DESTDIR.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import stat
import subprocess
import sys


SOURCE = Path(__file__).resolve().parents[1]
PREFIXES = ("THRIFT_PREFIX", "FB303_PREFIX", "TOOLS_PREFIX", "THRIFT_PYTHON_SOURCE")


def file_record(path, root):
    return {"path": str(path.relative_to(root)), "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": format(stat.S_IMODE(path.stat().st_mode), "04o")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new directory outside the checkout")
    parser.add_argument("--shared-rpc",action="store_true",help="validate original --disable-static RPC .so mode; default remains static")
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error("output already exists; choose a new directory")
    output = output.resolve()
    if output.is_relative_to(SOURCE) or not output.parent.is_dir():
        parser.error("output must have an existing parent and be outside the checkout")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("this validated lane is Linux x86_64 only")
    env = dict(os.environ)
    for name in ("PYTHON_SETUPUTIL_ARGS", "DIST_EXTRA_CONFIG", "MAKEFLAGS", "MFLAGS",
                 "GNUMAKEFLAGS", "MAKEOVERRIDES"):
        if env.get(name):
            parser.error("unsupported install/make override for this staged validation lane: " + name)
    if any((SOURCE / "lib/py" / name).exists() for name in ("setup.cfg", "pyproject.toml")):
        parser.error("custom Python setup config is outside this validated default lane")
    missing = [name for name in PREFIXES if not env.get(name) or not Path(env[name]).is_dir()]
    if missing:
        parser.error("provide existing directories for " + ", ".join(missing))
    for tool in ("git", "make", "autoreconf") + (("readelf",) if args.shared_rpc else ()):
        if not shutil.which(tool):
            parser.error("missing existing tool: " + tool)
    thrift, fb303, tools, python_source = (Path(env[n]).resolve() for n in PREFIXES)
    if not (thrift / "bin/thrift").is_file():
        parser.error("missing prepared compiler: " + str(thrift / "bin/thrift"))
    version = subprocess.check_output([thrift / "bin/thrift", "--version"], text=True).strip()
    if version != "Thrift version 0.25.0":
        parser.error("compiler/runtime lane requires Thrift 0.25.0")
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=SOURCE,
    ).split(b"\0")
    paths = [Path(os.fsdecode(p)) for p in paths if p]
    for relative in paths:
        path = SOURCE / relative
        if (not path.is_file() or path.is_symlink() or path.resolve() != path
                or path.stat().st_mode & 0o6000):
            parser.error("source export requires regular non-symlink files: " + str(relative))
    records = [file_record(SOURCE / relative, SOURCE) for relative in paths]
    output.mkdir(mode=0o700)
    build, stage, logs = (output / name for name in ("build", "stage", "logs"))
    build.mkdir(); logs.mkdir()
    (output / "home").mkdir(mode=0o700)
    env["HOME"] = str(output / "home")
    env["PYTHON_SETUPUTIL_ARGS"] = "--record="
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for relative in paths:
        target = build / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / relative, target)
    multiarch = tools / "lib/x86_64-linux-gnu"
    libraries = (multiarch, thrift / "lib", fb303 / "lib")
    env["PATH"] = str(thrift / "bin") + os.pathsep + env.get("PATH", "")
    env.setdefault("PYTHON", sys.executable)
    env.setdefault("CPPFLAGS", f"-I{tools}/include -I{tools}/include/x86_64-linux-gnu")
    env.setdefault("CXXFLAGS", "-O2 -std=c++17 -D_GLIBCXX_USE_DEPRECATED=0")
    env.setdefault("LDFLAGS", " ".join(f"-L{p} -Wl,-rpath,{p}" for p in libraries))
    env.update(SCRIBE_BUILD=str(build), THRIFT_PREFIX=str(thrift), FB303_PREFIX=str(fb303),
               TOOLS_PREFIX=str(tools), THRIFT_PYTHON_SOURCE=str(python_source))
    inherited_loader=env.get("LD_LIBRARY_PATH","")
    result = {"status": "running", "rpc_library_mode":"shared" if args.shared_rpc else "static", "source_head": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip(),
        "platform": platform.platform(), "thrift_version": version,
        "source_files": records, "steps": [],
        "inputs": {n: env.get(n) for n in (*PREFIXES, "CC", "CXX", "CFLAGS", "CXXFLAGS",
                                               "CPPFLAGS", "LDFLAGS", "PYTHON", "PY_PREFIX",
                                               "PATH", "LD_LIBRARY_PATH", "PYTHON_SETUPUTIL_ARGS", "HOME")}}

    def run(name, command, cwd=build):
        command = list(map(str, command))
        with (logs / (name + ".log")).open("w") as log:
            completed = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        result["steps"].append({"name": name, "command": command, "cwd": str(cwd),
                                "exit_code": completed.returncode})
        if completed.returncode:
            raise RuntimeError(name + " failed; see " + str(logs / (name + ".log")))

    try:
        run("configure", ["sh", "./bootstrap.sh", "--prefix=/opt/scribe",
                          "--with-thriftpath=" + str(thrift), "--with-fb303path=" + str(fb303),
                          "--with-boost=" + str(tools), "--with-boost-system=boost_system",
                          "--with-boost-filesystem=boost_filesystem",
                          *(["--disable-static"] if args.shared_rpc else [])])
        makefile = (build / "src/Makefile").read_text()
        configured = dict(line.split(" = ", 1) for line in makefile.splitlines() if " = " in line)
        result["configured"] = {n: configured[n] for n in ("CC", "CXX", "CFLAGS", "CXXFLAGS",
                                                         "CPPFLAGS", "LDFLAGS", "PYTHON", "PY_PREFIX", "LTYPE")}
        if configured["LTYPE"] != (".so" if args.shared_rpc else ".a"):
            raise RuntimeError("configured RPC mode differs from selected lane")
        if args.shared_rpc:
            env["LD_LIBRARY_PATH"]=str(build / "src")+(os.pathsep+inherited_loader if inherited_loader else "")
            result["build_loader_path"]=env["LD_LIBRARY_PATH"]
        run("compiler-version", [*shlex.split(configured["CXX"]), "--version"])
        run("python-version", [*shlex.split(configured["PYTHON"]), "--version"])
        run("clean", ["make", "clean"])
        run("build", ["make", "-j2"])
        if args.shared_rpc:
            run("shared-elf",["readelf","-W","-d",build / "src/scribed",
                              build / "src/libscribe.so",build / "src/libdynamicbucketupdater.so"])
            elf=(logs / "shared-elf.log").read_text()
            sections=[part.partition("\n")[2] for part in elf.split("\nFile: ")
                      if part.partition("\n")[0]==str(build / "src/scribed")]
            if len(sections)!=1 or any("Shared library: ["+name+"]" not in sections[0]
                                       for name in ("libscribe.so","libdynamicbucketupdater.so")):
                raise RuntimeError("shared scribed lacks expected RPC DT_NEEDED entries")
        # Existing discovery/runner, with machine-readable counts and explicit skip rejection.
        run("tests", [sys.executable, "-B", "-c", """
import json, pathlib, sys, unittest
suite = unittest.defaultTestLoader.discover(sys.argv[1], pattern='test_*.py')
r = unittest.TextTestRunner(verbosity=2).run(suite)
pathlib.Path(sys.argv[2]).write_text(json.dumps({'run': r.testsRun, 'failures': len(r.failures),
    'errors': len(r.errors), 'skipped': len(r.skipped)}, indent=2) + '\\n')
sys.exit(0 if r.wasSuccessful() and not r.skipped and r.testsRun >= 150 else 1)
""", SOURCE / "test", output / "test-results.json"], cwd=SOURCE)
        run("install", ["make", "install", "DESTDIR=" + str(stage)])
        if args.shared_rpc:
            env["LD_LIBRARY_PATH"]=os.pathsep.join(map(str,(stage / "opt/scribe/lib",*libraries)))
            for name in ("libscribe.so","libdynamicbucketupdater.so"):
                installed=stage / "opt/scribe/lib" / name
                if installed.is_symlink() or not installed.is_file() or installed.read_bytes()!=(build / "src" / name).read_bytes():
                    raise RuntimeError("staged RPC library differs from built file: "+name)
            env["LD_DEBUG"]="libs"
            result["installed_loader_path"]=env["LD_LIBRARY_PATH"]
        run("installed-help", [stage / "opt/scribe/bin/scribed", "--help"],cwd=stage)
        if args.shared_rpc:
            loader=(logs / "installed-help.log").read_text()
            if any("calling init: "+str(stage / "opt/scribe/lib" / name) not in loader for name in ("libscribe.so","libdynamicbucketupdater.so")):
                raise RuntimeError("staged help did not load the staged RPC libraries")
        if records != [file_record(SOURCE / relative, SOURCE) for relative in paths]:
            raise RuntimeError("source changed during validation; result cannot identify one source snapshot")
        if any(p.is_symlink() for p in stage.rglob("*")):
            raise RuntimeError("unexpected staged symlink; manifest must not follow files outside DESTDIR")
        result["installed_files"] = [file_record(p, stage) for p in sorted(stage.rglob("*")) if p.is_file()]
        result["generated_files"] = [file_record(p, build) for p in sorted((build / "src").glob("gen-*/**/*"))
                                     if p.is_file() and p.suffix in (".cpp", ".h", ".py", ".php", ".java")]
        result["dependency_files"] = []
        for root, patterns in ((thrift, ("bin/thrift", "lib/libthrift*")),
                               (fb303, ("lib/libfb303*",)),
                               (tools, ("lib/x86_64-linux-gnu/libboost_system*",
                                        "lib/x86_64-linux-gnu/libboost_filesystem*",
                                        "lib/x86_64-linux-gnu/libevent*"))):
            for pattern in patterns:
                for p in sorted(root.glob(pattern)):
                    if p.is_file():
                        result["dependency_files"].append({"prefix": str(root), "resolved_path": str(p.resolve()),
                                                           **file_record(p, root)})
        result["status"] = "passed"
    except (OSError, RuntimeError) as error:
        result["status"] = "failed"; result["error"] = str(error)
    finally:
        (output / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"] + ": " + str(output / "validation.json"))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
