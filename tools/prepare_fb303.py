#!/usr/bin/env python3
"""Copy fixed fb303 0.25.0 source and apply the project counter-lock patch.

This prepares source only. It never modifies the supplied source or installs
anything. Use the existing fb303 configure/make lane on the separate copy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "ac791badf8210c68694153fb507202b0ea4ef7baf0d5303b4d91f12ceabddcae"
HEADER = "64c024914c2156c77cca43b3939a70cf447f4eb10be4be263eb0294b29b9a49b"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(strict=True), args.output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        parser.error("output must be absent with an existing parent")
    if output.resolve().is_relative_to(source):
        parser.error("output must be outside the supplied source")
    for path, expected in ((source / "cpp/FacebookBase.cpp", BASE),
                           (source / "cpp/FacebookBase.h", HEADER)):
        if not path.is_file() or digest(path) != expected:
            parser.error("source does not match fixed fb303 0.25.0: " + str(path))
    patch = ROOT / "dependencies/fb303-0.25.0-counter-lock.patch"
    shutil.copytree(source, output, ignore=shutil.ignore_patterns(
        ".deps", ".libs", "*.o", "*.a", "*.so", "Makefile", "config.log",
        "config.status", "autom4te.cache"))
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=output, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=output, check=True)
    manifest = {"version": "0.25.0", "patch": patch.name,
                "patch_sha256": digest(patch), "base_cpp_sha256": BASE,
                "header_sha256": HEADER,
                "patched_cpp_sha256": digest(output / "cpp/FacebookBase.cpp")}
    (output / "scribe-next-fb303-safety.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
