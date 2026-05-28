from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.submitter import submit_or_defer


class SubmitOrDeferTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_defer_writes_to_pending_queue(self):
        with mock.patch("ait.bug_report.submitter.which", return_value=None):
            result = submit_or_defer(
                fingerprint="fp:aaaa1111",
                category="x",
                title="t",
                body="x" * 9000,  # exceeds URL_MAX so URL path fails too
                created_at="2026-05-28T10:00:00Z",
                browser_opener=lambda _u: False,
            )
        self.assertEqual(result.status, "deferred")
        # Pending file must exist
        path = Path(self._td.name) / "ait" / "bug_reports" / "pending" / "fp:aaaa1111.json"
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
