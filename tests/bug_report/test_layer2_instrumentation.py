from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.api import report_internal_error


class Layer2Tests(unittest.TestCase):
    """Smoke test that the helper is callable from each module's context.

    Real-call-site coverage relies on each module's existing tests still
    passing post-instrumentation; this case checks the contract.
    """

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_each_layer2_category_records(self):
        categories = [
            "daemon.protocol.transport",
            "daemon.protocol.main",
            "db.operational",
            "events.txn_rollback",
            "memory.note_write",
            "hooks.install",
            "reconcile.post_rewrite",
            "verifier.crash",
        ]
        for cat in categories:
            # Reset between iterations: the collector fingerprints by
            # (exc_type, frames), so the same RuntimeError raised from the same
            # function would otherwise collapse to one entry.
            collector_mod.reset_for_tests()
            try:
                raise RuntimeError(f"simulated {cat}")
            except RuntimeError as exc:
                report_internal_error(category=cat, exc=exc)
            entries = collector_mod.collector().entries()
            cats = {e.category for e in entries}
            self.assertIn(cat, cats, f"category {cat!r} not recorded")


if __name__ == "__main__":
    unittest.main()
