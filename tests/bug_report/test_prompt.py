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
from ait.bug_report.config import BugReportPrefs
from ait.bug_report.prompt import interactive_flush


def _make_exc():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc


class PromptTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_non_tty_writes_to_pending(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None,
                 now="2026-05-28T10:00:00Z")
        out = io.StringIO()
        # is_tty False on both streams
        interactive_flush(
            input_provider=lambda _p: "",
            is_tty=False,
            stdout=out,
            stderr=out,
            now="2026-05-28T10:00:00Z",
        )
        text = out.getvalue()
        self.assertIn("pending", text.lower())

    def test_tty_no_keypress_to_n(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None,
                 now="2026-05-28T10:00:00Z")
        out = io.StringIO()
        interactive_flush(
            input_provider=lambda _p: "n",
            is_tty=True,
            stdout=out,
            stderr=out,
            now="2026-05-28T10:00:00Z",
        )
        # No submission happened — verify pending NOT written either
        # because the user explicitly declined this run.
        from ait.bug_report.pending_queue import list_pending
        self.assertEqual(list_pending(), [])


    def test_collect_tier3_env_vars(self):
        from ait.bug_report.prompt import _collect_tier3
        os.environ["AIT_FOO_TEST"] = "value"
        try:
            envs = _collect_tier3(BugReportPrefs(include_tier3=True))
            self.assertIn("AIT_FOO_TEST", envs)
        finally:
            del os.environ["AIT_FOO_TEST"]

    def test_collect_tier3_respects_opt_out(self):
        from ait.bug_report.prompt import _collect_tier3
        envs = _collect_tier3(BugReportPrefs(include_tier3=False))
        self.assertEqual(envs, {})

    def test_collect_tier2_handles_missing_cwd(self):
        # Simulate a torn-down tmp dir: os.getcwd raises FileNotFoundError.
        import unittest.mock as mock
        with mock.patch("pathlib.Path.cwd",
                        side_effect=FileNotFoundError("dir gone")):
            from ait.bug_report.prompt import _collect_tier2
            # MUST NOT raise; should return a BuildInput slice with empty fields.
            result = _collect_tier2(BugReportPrefs(include_tier2=True))
            self.assertEqual(result.get("install_nonce", ""), "")


if __name__ == "__main__":
    unittest.main()
