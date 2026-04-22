from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.hooks import install_post_rewrite_hook


class HookTests(unittest.TestCase):
    def test_install_post_rewrite_hook_creates_executable_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _git(repo_root, "init")

            hook_path = install_post_rewrite_hook(repo_root)

            self.assertTrue(hook_path.exists())
            self.assertTrue(hook_path.stat().st_mode & 0o111)
            content = hook_path.read_text(encoding="utf-8")
            self.assertIn("ait post-rewrite hook", content)

    def test_install_post_rewrite_hook_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _git(repo_root, "init")

            first = install_post_rewrite_hook(repo_root)
            second = install_post_rewrite_hook(repo_root)

            self.assertEqual(first, second)
            content = first.read_text(encoding="utf-8")
            self.assertEqual(content.count("ait post-rewrite hook"), 2)


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


if __name__ == "__main__":
    unittest.main()
