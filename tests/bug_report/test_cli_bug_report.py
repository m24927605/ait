from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.cli.bug_report import run_list, run_clear, run_show
from ait.bug_report.pending_queue import PendingReport, enqueue


class CliBugReportTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def _enq(self, fp):
        enqueue(PendingReport(
            fingerprint=fp, title="t", body="b",
            category="c", created_at="2026-05-28T10:00:00Z",
        ))

    def test_list_empty(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = run_list()
        self.assertEqual(rc, 0)
        self.assertIn("no pending", buf.getvalue().lower())

    def test_list_with_entries(self):
        self._enq("fp:aaaa1111")
        self._enq("fp:bbbb2222")
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            run_list()
        out = buf.getvalue()
        self.assertIn("fp:aaaa1111", out)
        self.assertIn("fp:bbbb2222", out)

    def test_show_prints_body(self):
        self._enq("fp:aaaa1111")
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = run_show("fp:aaaa1111")
        self.assertEqual(rc, 0)
        self.assertIn("Title: t", buf.getvalue())
        self.assertIn("b", buf.getvalue())

    def test_clear_all(self):
        self._enq("fp:aaaa1111")
        self._enq("fp:bbbb2222")
        rc = run_clear(all_flag=True, fingerprint=None)
        self.assertEqual(rc, 0)
        from ait.bug_report.pending_queue import list_pending
        self.assertEqual(list_pending(), [])


if __name__ == "__main__":
    unittest.main()
