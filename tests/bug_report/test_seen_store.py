from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.seen_store import (
    SeenEntry,
    load_seen,
    record_seen,
    record_submitted,
    save_seen,
)


class SeenStoreTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_load_missing_returns_empty(self):
        self.assertEqual(load_seen(), {})

    def test_record_seen_increments_count(self):
        record_seen("fp:aaaa1111", category="db.operational", now="2026-05-28T10:00:00Z")
        record_seen("fp:aaaa1111", category="db.operational", now="2026-05-28T10:05:00Z")
        store = load_seen()
        self.assertEqual(store["fp:aaaa1111"].count, 2)
        self.assertEqual(store["fp:aaaa1111"].first_seen_at, "2026-05-28T10:00:00Z")
        self.assertEqual(store["fp:aaaa1111"].last_seen_at, "2026-05-28T10:05:00Z")

    def test_record_submitted_attaches_issue_url(self):
        record_seen("fp:bbbb2222", category="x", now="2026-05-28T10:00:00Z")
        record_submitted("fp:bbbb2222",
                        issue_url="https://github.com/m24927605/ait/issues/123",
                        method="gh",
                        now="2026-05-28T10:01:00Z")
        e = load_seen()["fp:bbbb2222"]
        self.assertEqual(e.submitted_issue_url,
                         "https://github.com/m24927605/ait/issues/123")
        self.assertEqual(e.submitted_method, "gh")

    def test_save_round_trip(self):
        record_seen("fp:cccc3333", category="c", now="2026-05-28T10:00:00Z")
        store = load_seen()
        save_seen(store)
        again = load_seen()
        self.assertEqual(again["fp:cccc3333"].count, 1)


if __name__ == "__main__":
    unittest.main()
