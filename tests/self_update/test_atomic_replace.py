from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import atomic_replace


class AtomicReplaceTests(unittest.TestCase):
    def test_replaces_existing_file_with_new_content(self):
        with tempfile.TemporaryDirectory() as td_str:
            td = Path(td_str)
            target = td / "ait"
            target.write_text("old binary", encoding="utf-8")
            atomic_replace(target, b"new binary")
            self.assertEqual(target.read_bytes(), b"new binary")

    def test_creates_file_when_missing(self):
        with tempfile.TemporaryDirectory() as td_str:
            td = Path(td_str)
            target = td / "ait"
            atomic_replace(target, b"new binary")
            self.assertEqual(target.read_bytes(), b"new binary")

    def test_failure_cleans_up_tmp_and_preserves_target(self):
        with tempfile.TemporaryDirectory() as td_str:
            td = Path(td_str)
            target = td / "ait"
            target.write_text("old binary", encoding="utf-8")
            with mock.patch("os.replace", side_effect=PermissionError("no")):
                with self.assertRaises(PermissionError):
                    atomic_replace(target, b"new binary")
            # Target unchanged
            self.assertEqual(target.read_text(encoding="utf-8"), "old binary")
            # No leftover .ait.new.* in the directory
            leftovers = [p.name for p in td.iterdir() if p.name.startswith(".ait.new")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
