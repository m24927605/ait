from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.pending_queue import (
    PendingReport,
    clear_pending,
    enqueue,
    list_pending,
    load_pending,
    prune_old,
    remove,
)


class PendingQueueTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_enqueue_then_load(self):
        report = PendingReport(
            fingerprint="fp:aaaa1111",
            title="t",
            body="b",
            category="x",
            created_at="2026-05-28T10:00:00Z",
        )
        enqueue(report)
        loaded = load_pending("fp:aaaa1111")
        self.assertEqual(loaded.title, "t")
        self.assertEqual(loaded.body, "b")

    def test_list_empty(self):
        self.assertEqual(list_pending(), [])

    def test_list_returns_all_fingerprints(self):
        for fp in ("fp:aaaa1111", "fp:bbbb2222"):
            enqueue(PendingReport(
                fingerprint=fp, title="t", body="b",
                category="c", created_at="2026-05-28T10:00:00Z",
            ))
        self.assertEqual(set(list_pending()), {"fp:aaaa1111", "fp:bbbb2222"})

    def test_remove(self):
        enqueue(PendingReport(
            fingerprint="fp:aaaa1111", title="t", body="b",
            category="c", created_at="2026-05-28T10:00:00Z",
        ))
        remove("fp:aaaa1111")
        self.assertEqual(list_pending(), [])

    def test_prune_old_drops_files_over_30_days(self):
        old = (dt.datetime(2026, 5, 28, tzinfo=dt.timezone.utc)
               - dt.timedelta(days=31)).isoformat().replace("+00:00", "Z")
        enqueue(PendingReport(
            fingerprint="fp:oldold01", title="t", body="b",
            category="c", created_at=old,
        ))
        enqueue(PendingReport(
            fingerprint="fp:new1111", title="t", body="b",
            category="c", created_at="2026-05-28T10:00:00Z",
        ))
        prune_old(now=dt.datetime(2026, 5, 28, tzinfo=dt.timezone.utc))
        remaining = set(list_pending())
        self.assertEqual(remaining, {"fp:new1111"})


if __name__ == "__main__":
    unittest.main()
