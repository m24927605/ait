from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.fingerprint import Frame, fingerprint


class FingerprintTests(unittest.TestCase):
    def test_returns_fp_prefixed_8_hex(self):
        fp = fingerprint("ValueError", [Frame("foo.py", "bar")])
        self.assertTrue(fp.startswith("fp:"))
        self.assertEqual(len(fp), 11)  # 'fp:' + 8 hex
        int(fp[3:], 16)  # must be valid hex

    def test_same_input_same_output(self):
        frames = [Frame("foo.py", "bar"), Frame("baz.py", "qux")]
        self.assertEqual(
            fingerprint("ValueError", frames),
            fingerprint("ValueError", frames),
        )

    def test_different_exc_type_different_fp(self):
        frames = [Frame("foo.py", "bar")]
        self.assertNotEqual(
            fingerprint("ValueError", frames),
            fingerprint("TypeError", frames),
        )

    def test_line_numbers_ignored(self):
        a = [Frame("foo.py", "bar")]
        b = [Frame("foo.py", "bar")]
        self.assertEqual(fingerprint("E", a), fingerprint("E", b))

    def test_basename_extracted(self):
        a = [Frame("/long/abs/path/foo.py", "bar")]
        b = [Frame("foo.py", "bar")]
        self.assertEqual(fingerprint("E", a), fingerprint("E", b))

    def test_only_top_3_frames(self):
        a = [Frame(f"f{i}.py", "g") for i in range(5)]
        b = a[:3]
        self.assertEqual(fingerprint("E", a), fingerprint("E", b))

    def test_fewer_than_3_frames_ok(self):
        fp = fingerprint("E", [Frame("a.py", "b")])
        self.assertTrue(fp.startswith("fp:"))

    def test_empty_frames_ok(self):
        fp = fingerprint("E", [])
        self.assertTrue(fp.startswith("fp:"))


if __name__ == "__main__":
    unittest.main()
