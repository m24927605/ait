from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "release-smoke"))

from binary_smoke import smoke, SmokeFailure


class BinarySmokeTests(unittest.TestCase):
    def test_smoke_returns_zero_when_all_checks_pass(self):
        # Mock subprocess.run to return success for the three expected calls.
        def fake_run(cmd, **kwargs):
            r = mock.Mock()
            r.returncode = 0
            r.stdout = "ait 1.5.0\n"
            # When the binary "init" command is called, create .ait so the
            # filesystem check in smoke() can find it.
            if len(cmd) >= 2 and cmd[-1] == "init" and "cwd" in kwargs:
                Path(kwargs["cwd"]).mkdir(parents=True, exist_ok=True)
                (Path(kwargs["cwd"]) / ".ait").mkdir(exist_ok=True)
            return r
        with mock.patch("binary_smoke.subprocess.run", side_effect=fake_run):
            rc = smoke(Path("/fake/ait"))
        self.assertEqual(rc, 0)

    def test_smoke_raises_when_version_check_fails(self):
        def fake_run(cmd, **kwargs):
            r = mock.Mock()
            r.returncode = 1
            r.stderr = "could not import ait.X.Y"
            r.stdout = ""
            return r
        with mock.patch("binary_smoke.subprocess.run", side_effect=fake_run):
            with self.assertRaises(SmokeFailure):
                smoke(Path("/fake/ait"))


if __name__ == "__main__":
    unittest.main()
