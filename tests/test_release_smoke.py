from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReleaseSmokeTests(unittest.TestCase):
    def test_package_versions_match(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "release-smoke" / "check_package_metadata.py")],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("release metadata ok", result.stdout)

    def test_wheel_smoke_script_runs_fresh_repo(self) -> None:
        if importlib.util.find_spec("build") is None:
            self.skipTest("Python build package is not installed")
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp) / "dist"
            build = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "--outdir",
                    str(dist_dir),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, build.returncode, build.stderr)

            smoke = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "release-smoke" / "wheel_smoke.py"),
                    "--dist-dir",
                    str(dist_dir),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=180,
            )

        self.assertEqual(0, smoke.returncode, smoke.stderr)
        self.assertIn("release wheel smoke ok", smoke.stdout)


if __name__ == "__main__":
    unittest.main()
