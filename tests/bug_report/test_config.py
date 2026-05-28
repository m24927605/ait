from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.config import (
    BugReportPrefs,
    config_path,
    env_disabled,
    load_prefs,
    save_prefs,
    state_dir,
)


class XDGPathTests(unittest.TestCase):
    def test_config_path_default(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CONFIG_HOME"] = td
            try:
                p = config_path()
                self.assertEqual(p, Path(td) / "ait" / "config.json")
            finally:
                del os.environ["XDG_CONFIG_HOME"]

    def test_state_dir_default(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_STATE_HOME"] = td
            try:
                p = state_dir()
                self.assertEqual(p, Path(td) / "ait" / "bug_reports")
            finally:
                del os.environ["XDG_STATE_HOME"]


class PrefsRoundTripTests(unittest.TestCase):
    def test_load_missing_returns_unset_default(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CONFIG_HOME"] = td
            try:
                prefs = load_prefs()
                self.assertEqual(prefs.mode, "unset")
                self.assertTrue(prefs.include_tier2)
                self.assertFalse(prefs.include_tier3)
            finally:
                del os.environ["XDG_CONFIG_HOME"]

    def test_save_then_load_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CONFIG_HOME"] = td
            try:
                prefs = BugReportPrefs(
                    mode="always",
                    include_tier2=False,
                    include_tier3=True,
                )
                save_prefs(prefs)
                loaded = load_prefs()
                self.assertEqual(loaded.mode, "always")
                self.assertFalse(loaded.include_tier2)
                self.assertTrue(loaded.include_tier3)
            finally:
                del os.environ["XDG_CONFIG_HOME"]


class EnvDisableTests(unittest.TestCase):
    def test_env_never_disables(self):
        os.environ["AIT_BUG_REPORT"] = "never"
        try:
            self.assertTrue(env_disabled())
        finally:
            del os.environ["AIT_BUG_REPORT"]

    def test_no_env_means_not_disabled(self):
        os.environ.pop("AIT_BUG_REPORT", None)
        self.assertFalse(env_disabled())


if __name__ == "__main__":
    unittest.main()
