#!/usr/bin/env python3
"""Opt-in compiler check for the pinned Thrift C++ build lane.

Set THRIFT_PREFIX and FB303_PREFIX to the prepared workspace dependencies.
This generates temporary files only; it does not build or run Scribe.
"""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ThriftGenerationTests(unittest.TestCase):
    def test_library_sources_match_actual_generator_output(self):
        thrift_prefix = os.environ.get("THRIFT_PREFIX")
        fb303_prefix = os.environ.get("FB303_PREFIX")
        if not thrift_prefix or not fb303_prefix:
            self.skipTest("set THRIFT_PREFIX and FB303_PREFIX for actual IDL generation")
        compiler = Path(thrift_prefix) / "bin/thrift"
        version = subprocess.check_output(
            [str(compiler), "--version"], text=True, timeout=30
        ).strip()
        self.assertEqual(version, "Thrift version 0.25.0")
        makefile = (ROOT / "src/Makefile.am").read_text()
        with tempfile.TemporaryDirectory(prefix="scribe-idl-generation-") as directory:
            for name, targets in (
                ("scribe", ("libscribe_a", "libscribe_so")),
                ("bucketupdater", ("libdynamicbucketupdater_a", "libdynamicbucketupdater_so")),
            ):
                output = Path(directory) / name / "gen-cpp"
                output.mkdir(parents=True)
                subprocess.run(
                    [str(compiler), "-I", str(Path(fb303_prefix) / "share"),
                     "--gen", "cpp:pure_enums", "-out", str(output),
                     str(ROOT / "if" / (name + ".thrift"))],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                )
                generated = {
                    "gen-cpp/" + path.name for path in output.glob("*.cpp")
                    if not path.name.endswith("_server.skeleton.cpp")
                }
                for target in targets:
                    with self.subTest(target=target):
                        match = re.search(rf"^{target}_SOURCES\s*=\s*(.+)$", makefile, re.M)
                        self.assertIsNotNone(match, target)
                        self.assertEqual(set(match.group(1).split()), generated)


if __name__ == "__main__":
    unittest.main()
