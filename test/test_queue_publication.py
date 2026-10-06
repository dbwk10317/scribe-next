#!/usr/bin/env python3
"""Actual StoreQueue methods with a barrier-controlled store dependency stub."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class QueuePublicationTests(unittest.TestCase):
    def test_status_waits_for_worker_configuration_publication(self):
        self.run_component("queue_publication.cpp", "early_status=0 status=")

    def test_concurrent_byte_size_and_configured_target_snapshots(self):
        self.run_component("queue_snapshots.cpp", "snapshot_bounds=1 final_bytes=0")

    def run_component(self, source, expected):
        tools = os.environ.get("TOOLS_PREFIX")
        if not tools:
            self.skipTest("requires prepared Boost headers")
        with tempfile.TemporaryDirectory(prefix="scribe-queue-publication-") as directory:
            work = Path(directory)
            for name in ("store_queue.cpp", "store_queue.h"):
                shutil.copyfile(ROOT / "src" / name, work / name)
            shutil.copyfile(ROOT / "test/cpp/queue_component_common.h", work / "common.h")
            (work / "scribe_server.h").write_text('#include "store_queue.h"\n')
            command = ["g++", "-std=c++17", "-O0", "-g", "-pthread", "-I", str(work),
                       "-I", str(Path(tools) / "include"), str(work / "store_queue.cpp"),
                       str(ROOT / "test/cpp" / source),
                       *(["-Wl,--wrap=pthread_mutex_lock"] if source=="queue_publication.cpp" else []),
                       "-o", str(work / "probe")]
            compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout+compile_result.stderr)
            run = subprocess.run([work / "probe"], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            self.assertIn(expected, run.stdout)
