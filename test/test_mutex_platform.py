"""Explicit unsupported-platform classification without hiding Linux failures."""

import subprocess
import unittest
from unittest import mock

import test_mutex_compat as mutex_tests


class MutexPlatformTests(unittest.TestCase):
    def test_non_linux_wrapper_fixture_is_an_explicit_non_run(self):
        fixture = type("UnsupportedFixture", (mutex_tests.MutexCompatibilityTests,), {})
        with mock.patch.object(mutex_tests.sys, "platform", "darwin"), \
                mock.patch.object(mutex_tests.shutil, "which") as compiler:
            with self.assertRaisesRegex(unittest.SkipTest, "Linux GNU --wrap.*darwin"):
                fixture.setUpClass()
            compiler.assert_not_called()

    def test_linux_compile_errors_remain_errors_and_keep_real_wrap_flags(self):
        fixture = type("FailingLinuxFixture", (mutex_tests.MutexCompatibilityTests,), {})
        failure = subprocess.CompletedProcess([], 1, "controlled compile failure")
        try:
            with mock.patch.object(mutex_tests.sys, "platform", "linux"), \
                    mock.patch.object(mutex_tests.shutil, "which", return_value="g++"), \
                    mock.patch.object(mutex_tests.subprocess, "run", return_value=failure) as run:
                with self.assertRaisesRegex(RuntimeError, "mutex fixture compilation failed"):
                    fixture.setUpClass()
                command = run.call_args.args[0]
                self.assertIn("-Wl,--wrap=pthread_rwlock_rdlock", command)
                self.assertIn("-Wl,--wrap=pthread_rwlock_wrlock", command)
        finally:
            fixture.doClassCleanups()


if __name__ == "__main__":
    unittest.main()
