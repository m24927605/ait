from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.config import load_prefs
from ait.cli.config import run_bug_report_config


class ConfigCmdTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_CONFIG_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_set_mode_always(self):
        rc = run_bug_report_config(args=["always"])
        self.assertEqual(rc, 0)
        self.assertEqual(load_prefs().mode, "always")

    def test_invalid_mode_returns_error(self):
        rc = run_bug_report_config(args=["bogus"])
        self.assertNotEqual(rc, 0)

    def test_show_when_no_args(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = run_bug_report_config(args=[])
        self.assertEqual(rc, 0)
        self.assertIn("mode:", buf.getvalue().lower())

    def test_tier_toggle(self):
        run_bug_report_config(args=["tier3", "on"])
        self.assertTrue(load_prefs().include_tier3)
        run_bug_report_config(args=["tier3", "off"])
        self.assertFalse(load_prefs().include_tier3)


if __name__ == "__main__":
    unittest.main()
