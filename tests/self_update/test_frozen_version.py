from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.cli_installation import package_version


class FrozenVersionTests(unittest.TestCase):
    def test_returns_pyproject_version_when_not_frozen(self):
        # Real path: package_version reads from pyproject.toml or importlib metadata.
        # In the dev environment, sys.frozen is not set, so this should return
        # the project's actual current version.
        v = package_version()
        # We can't pin a specific version string without coupling to releases.
        # But it MUST be a non-empty truthy string that looks like semver.
        self.assertIsInstance(v, str)
        self.assertTrue(v)
        # Either MAJOR.MINOR.PATCH or "unknown" — but here we expect a real version.
        self.assertNotEqual(v, "unknown",
                            "non-frozen path should not return 'unknown' "
                            "when the package is installed in editable mode")

    def test_returns_frozen_version_when_sys_frozen(self):
        # Simulate PyInstaller: sys.frozen = True + ait._frozen_version present.
        fake_mod = type(sys)("ait._frozen_version")
        fake_mod.__version__ = "9.9.9"
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.dict(sys.modules, {"ait._frozen_version": fake_mod}):
            self.assertEqual(package_version(), "9.9.9")

    def test_returns_unknown_when_frozen_but_module_missing(self):
        # Set sys.modules["ait._frozen_version"] = None to block both cached and
        # filesystem-level imports of the module (Python treats a None entry in
        # sys.modules as a "blocked" import and raises ImportError on access).
        # This simulates a PyInstaller bundle where _frozen_version was never
        # embedded, even though the file may exist in the development tree.
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.dict(sys.modules, {"ait._frozen_version": None}):
            self.assertEqual(package_version(), "unknown")


if __name__ == "__main__":
    unittest.main()
