from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "release-smoke"))

from render_brew_formula import parse_checksums, render_formula


SAMPLE_CHECKSUMS = """\
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  ait-v1.5.1-macos-arm64
bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  ait-v1.5.1-macos-x86_64
cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc  ait-v1.5.1-linux-x86_64
dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd  ait-v1.5.1-linux-arm64
"""


class RenderBrewFormulaTests(unittest.TestCase):
    def test_parse_checksums_returns_dict_keyed_by_target(self):
        out = parse_checksums(SAMPLE_CHECKSUMS, version="v1.5.1")
        self.assertEqual(out["macos-arm64"], "a" * 64)
        self.assertEqual(out["macos-x86_64"], "b" * 64)
        self.assertEqual(out["linux-x86_64"], "c" * 64)
        self.assertEqual(out["linux-arm64"], "d" * 64)

    def test_render_formula_includes_version_and_all_four_shas(self):
        sums = parse_checksums(SAMPLE_CHECKSUMS, version="v1.5.1")
        formula = render_formula(version="v1.5.1", checksums=sums)
        self.assertIn('version "1.5.1"', formula)
        self.assertIn("a" * 64, formula)
        self.assertIn("b" * 64, formula)
        self.assertIn("c" * 64, formula)
        self.assertIn("d" * 64, formula)
        # Structure sanity
        self.assertIn("class Ait < Formula", formula)
        self.assertIn("on_macos do", formula)
        self.assertIn("on_linux do", formula)

    def test_parse_checksums_raises_when_target_missing(self):
        bad = "aa  ait-v1.5.1-macos-arm64\n"  # only one entry
        with self.assertRaises(ValueError):
            parse_checksums(bad, version="v1.5.1")


if __name__ == "__main__":
    unittest.main()
