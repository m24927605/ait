from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.collector import Collector, CollectedEntry
from ait.bug_report.fingerprint import Frame


def _make_exc():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc


class CollectorTests(unittest.TestCase):
    def test_starts_empty(self):
        c = Collector()
        self.assertEqual(c.entries(), [])

    def test_record_one(self):
        c = Collector()
        c.record(category="db.operational", exc=_make_exc(),
                 context=None, now="2026-05-28T10:00:00Z")
        self.assertEqual(len(c.entries()), 1)
        e = c.entries()[0]
        self.assertEqual(e.category, "db.operational")
        self.assertEqual(e.exc_type, "ValueError")
        self.assertEqual(e.exc_message, "boom")

    def test_same_fp_merges_count(self):
        c = Collector()
        for _ in range(3):
            c.record(category="x", exc=_make_exc(),
                     context=None, now="2026-05-28T10:00:00Z")
        entries = c.entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].count, 3)

    def test_capacity_20(self):
        c = Collector(max_entries=20)

        # Build 21 entries with distinct fingerprints by faking unique
        # tracebacks. We construct a synthetic exception per iteration whose
        # __traceback__ frames carry a unique function name. Since real frames
        # require real call sites, the simplest reliable mechanism is to use
        # exec() to define and call 21 differently-named functions.
        excs = []
        for i in range(21):
            ns: dict = {}
            exec(
                f"def make_{i}():\n"
                f"    raise ValueError('boom-{i}')\n",
                ns,
            )
            try:
                ns[f"make_{i}"]()
            except ValueError as exc:
                excs.append(exc)

        for i, exc in enumerate(excs):
            c.record(category=f"cat-{i}", exc=exc,
                     context=None, now="2026-05-28T10:00:00Z")

        self.assertEqual(len(c.entries()), 20)
        # The oldest (first inserted) entry must have been evicted.
        first_fp_fns = {f.function for e in c.entries() for f in e.frames}
        self.assertNotIn("make_0", first_fp_fns)
        self.assertIn("make_20", first_fp_fns)
        self.assertTrue(c.truncated)


if __name__ == "__main__":
    unittest.main()
