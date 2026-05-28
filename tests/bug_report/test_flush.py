from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.config import BugReportPrefs, save_prefs
from ait.bug_report.flush import decide_prompt, FlushDecision
from ait.bug_report.seen_store import record_seen, record_submitted


def _make_exc():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc


class DecidePromptTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def _now(self, d=0):
        base = dt.datetime(2026, 5, 28, tzinfo=dt.timezone.utc)
        return (base + dt.timedelta(days=d)).isoformat().replace("+00:00", "Z")

    def test_unseen_fp_should_prompt(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None, now=self._now())
        d = decide_prompt(now=self._now())
        self.assertEqual(d.action, "prompt")
        self.assertEqual(len(d.to_prompt), 1)

    def test_seen_recently_not_submitted_silent(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None, now=self._now())
        fp = c.entries()[0].fingerprint
        record_seen(fp, category="x", now=self._now(-1))
        d = decide_prompt(now=self._now())
        self.assertEqual(d.action, "silent")

    def test_seen_over_7d_ago_reprompt(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None, now=self._now())
        fp = c.entries()[0].fingerprint
        record_seen(fp, category="x", now=self._now(-10))
        d = decide_prompt(now=self._now())
        self.assertEqual(d.action, "prompt")

    def test_already_submitted_open_silent(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None, now=self._now())
        fp = c.entries()[0].fingerprint
        record_seen(fp, category="x", now=self._now())
        record_submitted(fp, issue_url="https://x/123",
                         method="gh", now=self._now())
        d = decide_prompt(now=self._now())
        self.assertEqual(d.action, "silent")


if __name__ == "__main__":
    unittest.main()
