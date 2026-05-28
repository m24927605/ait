from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.safety import _safe, _log_internal_error


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_safe_returns_value_on_success(self):
        @_safe
        def f(x: int) -> int:
            return x + 1
        self.assertEqual(f(2), 3)

    def test_safe_swallows_exception_returning_none(self):
        @_safe
        def f():
            raise RuntimeError("boom")
        self.assertIsNone(f())

    def test_log_internal_error_writes_file(self):
        try:
            raise ValueError("hello")
        except ValueError as exc:
            _log_internal_error(exc)
        log = Path(self._td.name) / "ait" / "bug_reports" / "internal_errors.log"
        self.assertTrue(log.exists())
        content = log.read_text(encoding="utf-8")
        self.assertIn("ValueError", content)
        self.assertIn("hello", content)


if __name__ == "__main__":
    unittest.main()
