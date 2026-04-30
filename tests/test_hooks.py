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
            self.assertIn('>> "$REPO_ROOT/.ait/post-rewrite.last"', content)

    def test_install_post_rewrite_hook_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _git(repo_root, "init")

            first = install_post_rewrite_hook(repo_root)
            second = install_post_rewrite_hook(repo_root)

            self.assertEqual(first, second)
            content = first.read_text(encoding="utf-8")
            self.assertEqual(content.count("ait post-rewrite hook"), 2)

    def test_install_post_rewrite_hook_from_inside_worktree_resolves_common_dir(self) -> None:
        # Regression for dogfood-session-1 Bug A: calling the installer from
        # inside a git worktree (where `.git` is a file, not a directory)
        # previously crashed with NotADirectoryError on `.git/hooks/`.
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "main"
            repo_root.mkdir()
            _git(repo_root, "init")
            _git(repo_root, "config", "user.email", "test@example.com")
            _git(repo_root, "config", "user.name", "Test User")
            (repo_root / "seed.txt").write_text("seed\n", encoding="utf-8")
            _git(repo_root, "add", "seed.txt")
            _git(repo_root, "commit", "-m", "init")
            worktree_path = Path(tmp) / "worktree"
            _git(repo_root, "worktree", "add", "--detach", str(worktree_path), "HEAD")

            hook_path = install_post_rewrite_hook(worktree_path)

            self.assertTrue(hook_path.exists())
            self.assertTrue(hook_path.stat().st_mode & 0o111)
            # Hook must land in the common .git directory so it fires for
            # both the main repo and any worktree.
            self.assertEqual(
                hook_path.resolve(),
                (repo_root / ".git" / "hooks" / "post-rewrite").resolve(),
            )

    def test_install_post_rewrite_hook_respects_core_hooks_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _git(repo_root, "init")
            custom_hooks = repo_root / "custom-hooks"
            custom_hooks.mkdir()
            _git(repo_root, "config", "core.hooksPath", str(custom_hooks))

            hook_path = install_post_rewrite_hook(repo_root)

            self.assertEqual(hook_path.parent.resolve(), custom_hooks.resolve())

    def test_post_rewrite_hook_appends_not_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _git(repo_root, "init")
            _git(repo_root, "config", "user.email", "test@example.com")
            _git(repo_root, "config", "user.name", "Test User")
            install_post_rewrite_hook(repo_root)
            tracked = repo_root / "tracked.txt"
            tracked.write_text("v1\n", encoding="utf-8")
            _git(repo_root, "add", "tracked.txt")
            _git(repo_root, "commit", "-m", "tracked v1")

            for value in ("v2", "v3"):
                tracked.write_text(f"{value}\n", encoding="utf-8")
                _git(repo_root, "add", "tracked.txt")
                _git(repo_root, "commit", "--amend", "-m", f"tracked {value}")

            rewrite_path = repo_root / ".ait" / "post-rewrite.last"
            mappings = [
                line
                for line in rewrite_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual(2, len(mappings))
            for mapping in mappings:
                self.assertEqual(2, len(mapping.split()))


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
