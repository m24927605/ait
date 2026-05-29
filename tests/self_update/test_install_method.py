from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import install_method


class InstallMethodTests(unittest.TestCase):
    def test_not_frozen_returns_pip(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertEqual(install_method(), "pip")

    def test_frozen_under_cellar_returns_brew(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable",
                               "/opt/homebrew/Cellar/ait/1.5.1/bin/ait"):
            self.assertEqual(install_method(), "brew")

    def test_frozen_elsewhere_returns_binary(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", "/usr/local/bin/ait"):
            self.assertEqual(install_method(), "binary")

    def test_frozen_in_home_local_bin_returns_binary(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable",
                               "/Users/me/.local/bin/ait"):
            self.assertEqual(install_method(), "binary")


if __name__ == "__main__":
    unittest.main()
