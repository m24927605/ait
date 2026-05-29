from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import refuse_with_message


class RefuseTests(unittest.TestCase):
    def test_pip_refusal_mentions_pip_install_upgrade(self):
        buf = io.StringIO()
        rc = refuse_with_message("pip", stdout=buf)
        self.assertEqual(rc, 1)
        self.assertIn("pip install --upgrade ait-vcs", buf.getvalue())

    def test_brew_refusal_mentions_brew_upgrade(self):
        buf = io.StringIO()
        rc = refuse_with_message("brew", stdout=buf)
        self.assertEqual(rc, 1)
        self.assertIn("brew upgrade ait", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
