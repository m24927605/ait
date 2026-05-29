from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import compare_versions


class CompareVersionsTests(unittest.TestCase):
    def test_equal(self):
        self.assertEqual(compare_versions("1.5.0", "1.5.0"), 0)
        self.assertEqual(compare_versions("v1.5.0", "1.5.0"), 0)
        self.assertEqual(compare_versions("1.5.0", "v1.5.0"), 0)

    def test_older(self):
        self.assertEqual(compare_versions("1.5.0", "1.5.1"), -1)
        self.assertEqual(compare_versions("1.4.3", "1.5.0"), -1)
        self.assertEqual(compare_versions("0.9.9", "1.0.0"), -1)

    def test_newer(self):
        self.assertEqual(compare_versions("1.5.1", "1.5.0"), 1)
        self.assertEqual(compare_versions("2.0.0", "1.9.9"), 1)

    def test_malformed_raises(self):
        with self.assertRaises(ValueError):
            compare_versions("notaversion", "1.5.0")


if __name__ == "__main__":
    unittest.main()
