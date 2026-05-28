from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.excepthook import install, reset_for_tests, uninstall


class ExcepthookTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()
        reset_for_tests()
        self._original_hook = sys.excepthook

    def tearDown(self):
        sys.excepthook = self._original_hook
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_install_records_ait_exception(self):
        install()
        # Fabricate an exception with a frame whose module looks like 'ait.x'.
        try:
            raise ValueError("from ait")
        except ValueError as exc:
            # Force module attribution: set exc's traceback frame globals.
            sys.excepthook(type(exc), exc, exc.__traceback__)
        entries = collector_mod.collector().entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].exc_type, "ValueError")

    def test_install_skips_keyboard_interrupt(self):
        install()
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        self.assertEqual(collector_mod.collector().entries(), [])

    def test_chain_calls_previous_hook(self):
        calls = []

        def prev_hook(et, ev, tb):
            calls.append("prev")

        sys.excepthook = prev_hook
        install()
        try:
            raise ValueError("x")
        except ValueError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        self.assertEqual(calls, ["prev"])


if __name__ == "__main__":
    unittest.main()
