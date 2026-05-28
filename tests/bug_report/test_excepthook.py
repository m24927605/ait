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
        # Fabricate an exception whose __module__ looks like 'ait.x'.
        class _AitError(Exception):
            pass
        _AitError.__module__ = "ait.internal"
        try:
            raise _AitError("from ait")
        except _AitError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        entries = collector_mod.collector().entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].exc_type, "_AitError")

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


    def test_third_party_exception_not_recorded(self):
        install()
        # Simulate an exception from a non-ait module.
        class _Foreign(Exception):
            pass
        _Foreign.__module__ = "urllib.error"
        try:
            raise _Foreign("from third party")
        except _Foreign as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        self.assertEqual(collector_mod.collector().entries(), [])


if __name__ == "__main__":
    unittest.main()
