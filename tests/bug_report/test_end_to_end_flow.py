from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.api import flush_at_exit, report_internal_error
from ait.bug_report.config import BugReportPrefs, save_prefs
from ait.bug_report.pending_queue import list_pending


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        # Clean up env vars, but only if we set them (AIT_BUG_REPORT may be
        # cleaned up individually in tests that set it).
        os.environ.pop("XDG_STATE_HOME", None)
        os.environ.pop("XDG_CONFIG_HOME", None)
        os.environ.pop("AIT_BUG_REPORT", None)
        self._td.cleanup()

    def test_env_never_disables_pipeline(self):
        os.environ["AIT_BUG_REPORT"] = "never"
        try:
            raise ValueError("x")
        except ValueError as exc:
            report_internal_error(category="x", exc=exc)
        self.assertEqual(collector_mod.collector().entries(), [])

    def test_mode_never_disables_pipeline(self):
        save_prefs(BugReportPrefs(mode="never"))
        try:
            raise ValueError("x")
        except ValueError as exc:
            report_internal_error(category="x", exc=exc)
        self.assertEqual(collector_mod.collector().entries(), [])

    def test_non_tty_flush_writes_pending(self):
        save_prefs(BugReportPrefs(mode="ask"))
        try:
            raise ValueError("integration boom")
        except ValueError as exc:
            report_internal_error(category="db.operational", exc=exc)
        with mock.patch("sys.stdin") as si, mock.patch("sys.stdout") as so:
            si.isatty.return_value = False
            so.isatty.return_value = False
            flush_at_exit()
        self.assertEqual(len(list_pending()), 1)

    def test_self_safety_internal_failure_does_not_break(self):
        # Force a failure inside the submitter (build_issue). Patch the name
        # as referenced in ait.bug_report.prompt (where it is imported from
        # builder), not the original module, so the mock is actually used.
        # flush_at_exit is wrapped with @_safe and must NOT raise even if
        # build_issue is broken.
        with mock.patch("ait.bug_report.prompt.build_issue",
                        side_effect=RuntimeError("synthetic")):
            try:
                raise ValueError("x")
            except ValueError as exc:
                report_internal_error(category="x", exc=exc)
            # flush_at_exit must NOT raise even though build_issue is broken.
            flush_at_exit()
        # No assertion needed: the test passes iff no exception escaped.


if __name__ == "__main__":
    unittest.main()
