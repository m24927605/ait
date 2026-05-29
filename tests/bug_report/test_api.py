from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.api import report_internal_error


class ApiTests(unittest.TestCase):
    def setUp(self):
        # tests/conftest.py sets AIT_BUG_REPORT=never globally to stop
        # subprocess tests polluting ~/.local/state/ait/. This test
        # class needs the pipeline alive to assert on it — opt back in.
        _orig = os.environ.pop("AIT_BUG_REPORT", None)
        self.addCleanup(
            lambda: os.environ.__setitem__("AIT_BUG_REPORT", _orig)
            if _orig is not None
            else os.environ.pop("AIT_BUG_REPORT", None)
        )
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_report_internal_error_appends_to_collector(self):
        try:
            raise ValueError("boom")
        except ValueError as exc:
            report_internal_error(category="db.operational", exc=exc)
        entries = collector_mod.collector().entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].category, "db.operational")

    def test_never_raises(self):
        report_internal_error(category="x", exc=None)  # type: ignore[arg-type]
        # No assertion needed — failure to swallow would raise.


if __name__ == "__main__":
    unittest.main()
