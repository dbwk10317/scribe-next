#!/usr/bin/env python3
"""Check the unported import against pinned Git objects; never fetch or execute it."""

import hashlib
from pathlib import Path
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "fcd294faffd1e88af1643a3a8c2359c41713f7c2"
TREE = "b4bf10438c6c3086a0e2dd78a6e4db659e49fbca"
IGNORE_APPENDIX = b"\n# scribe-next additions: "


def git(*args, input=None, ok=(0,)):
    result = subprocess.run(
        ["git", "--no-lazy-fetch", "--no-replace-objects", "-C", str(ROOT), *args],
        input=input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode not in ok:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )
    return result.stdout


def main():
    # Probe safety options without reading objects or permitting a lazy fetch.
    try:
        git("--version")
    except subprocess.CalledProcessError as error:
        print(
            "FAIL: local Git cannot use the required --no-lazy-fetch and "
            "--no-replace-objects options.", file=sys.stderr,
        )
        print(error.stderr.decode(errors="replace").strip(), file=sys.stderr)
        print(
            "Use a Git version that supports both options; upstream objects were not checked.",
            file=sys.stderr,
        )
        return 1

    try:
        tree = git("rev-parse", "--verify", COMMIT + "^{tree}").decode().strip()
        if tree != TREE:
            raise ValueError("upstream tree does not match the pinned tree")
        records = git("ls-tree", "-rz", COMMIT).split(b"\0")[:-1]
        original_ignore = git("show", COMMIT + ":.gitignore")
    except (subprocess.CalledProcessError, ValueError) as error:
        print(f"FAIL: cannot read pinned upstream: {error}", file=sys.stderr)
        print(
            f"Fetch it explicitly: git fetch https://github.com/facebookarchive/scribe.git "
            f"{COMMIT}:refs/remotes/upstream/baseline",
            file=sys.stderr,
        )
        return 1

    failures = []
    for record in records:
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, expected = metadata.decode().split()
        name = raw_path.decode()
        path = ROOT / name
        try:
            for parent in path.parents:
                if parent == ROOT:
                    break
                if not stat.S_ISDIR(parent.lstat().st_mode):
                    raise ValueError("parent is not a regular directory")
            file_mode = path.lstat().st_mode
            if kind != "blob" or mode not in ("100644", "100755"):
                raise ValueError("unsupported upstream entry")
            if not stat.S_ISREG(file_mode):
                raise ValueError("not a regular file")
            actual_mode = "100755" if file_mode & stat.S_IXUSR else "100644"
            if actual_mode != mode:
                raise ValueError(f"mode {actual_mode}, expected {mode}")
            data = path.read_bytes()
            if name == ".gitignore":
                # Only this file appends project rules to the unchanged upstream bytes.
                if not data.startswith(original_ignore + IGNORE_APPENDIX):
                    raise ValueError("upstream ignore rules or appendix marker changed")
                data = data[:len(original_ignore)]
            blob = b"blob " + str(len(data)).encode() + b"\0" + data
            if hashlib.sha1(blob).hexdigest() != expected:
                raise ValueError("content differs from upstream")
        except (OSError, ValueError) as error:
            failures.append(f"{name}: {error}")

    # An exact working-tree copy is insufficient if git add would omit a file.
    # Check both Linux and case-insensitive checkout behavior without staging.
    paths = b"\0".join(record.split(b"\t", 1)[1] for record in records) + b"\0"
    for ignorecase in ("false", "true"):
        try:
            ignored = git(
                "-c", f"core.ignorecase={ignorecase}",
                "-c", "core.excludesFile=/dev/null",
                "check-ignore", "--no-index", "-z", "--stdin",
                input=paths, ok=(0, 1),
            )
            for name in ignored.split(b"\0")[:-1]:
                failures.append(f"{name.decode()}: ignored with core.ignorecase={ignorecase}")
        except subprocess.CalledProcessError as error:
            failures.append(f"cannot check import visibility: {error}")

    if failures:
        print("FAIL:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"PASS: {len(records)} upstream paths match {COMMIT} (content and Git mode).")
    print(".gitignore preserves upstream bytes before the scribe-next appendix.")
    print("All upstream paths are visible to Git with core.ignorecase=false and true.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
