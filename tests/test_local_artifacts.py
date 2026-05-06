from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.local_artifacts import (
    ArtifactRecommendation,
    decide_artifact,
    reconcile_local_artifacts,
    scan_local_artifacts,
)


class LocalArtifactTests(unittest.TestCase):
    def test_scan_finds_ignored_and_untracked_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / ".gitignore").write_text(".env.local\n", encoding="utf-8")
            _git(repo_root, "add", ".gitignore")
            _git(repo_root, "commit", "-m", "ignore env")
            (repo_root / ".env.local").write_text("FEATURE=true\n", encoding="utf-8")
            (repo_root / "scratch.txt").write_text("note\n", encoding="utf-8")

            artifacts = scan_local_artifacts(repo_root)

            self.assertEqual(
                [".env.local", "scratch.txt"],
                [artifact.path for artifact in artifacts],
            )
            self.assertEqual("ignored", artifacts[0].git_status)
            self.assertEqual("untracked", artifacts[1].git_status)

    def test_reconcile_copies_safe_editor_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "worktree"
            dest = Path(tmp) / "dest"
            worktree.mkdir()
            dest.mkdir()
            _init_git_repo(worktree)
            (worktree / ".gitignore").write_text(".vscode/\n", encoding="utf-8")
            _git(worktree, "add", ".gitignore")
            _git(worktree, "commit", "-m", "ignore vscode")
            (worktree / ".vscode").mkdir()
            (worktree / ".vscode" / "settings.json").write_text('{"python.testing.pytestEnabled": true}\n', encoding="utf-8")

            report = reconcile_local_artifacts(worktree, dest)

            self.assertTrue(report.cleanup_allowed)
            self.assertEqual([".vscode/settings.json"], [decision.path for decision in report.copied])
            self.assertEqual(
                '{"python.testing.pytestEnabled": true}\n',
                (dest / ".vscode" / "settings.json").read_text(encoding="utf-8"),
            )

    def test_reconcile_leaves_env_file_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "worktree"
            dest = Path(tmp) / "dest"
            worktree.mkdir()
            dest.mkdir()
            _init_git_repo(worktree)
            (worktree / ".gitignore").write_text(".env.local\n", encoding="utf-8")
            _git(worktree, "add", ".gitignore")
            _git(worktree, "commit", "-m", "ignore env")
            (worktree / ".env.local").write_text("API_URL=http://localhost\n", encoding="utf-8")

            report = reconcile_local_artifacts(worktree, dest)

            self.assertFalse(report.cleanup_allowed)
            self.assertEqual([".env.local"], [decision.path for decision in report.pending])
            self.assertFalse((dest / ".env.local").exists())

    def test_reconcile_skips_generated_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "worktree"
            dest = Path(tmp) / "dest"
            worktree.mkdir()
            dest.mkdir()
            _init_git_repo(worktree)
            (worktree / ".gitignore").write_text(".venv/\nnode_modules/\n", encoding="utf-8")
            _git(worktree, "add", ".gitignore")
            _git(worktree, "commit", "-m", "ignore generated")
            (worktree / ".venv").mkdir()
            (worktree / ".venv" / "pyvenv.cfg").write_text("home = /tmp\n", encoding="utf-8")
            (worktree / "node_modules").mkdir()
            (worktree / "node_modules" / "pkg.js").write_text("module.exports = {}\n", encoding="utf-8")

            report = reconcile_local_artifacts(worktree, dest)

            self.assertTrue(report.cleanup_allowed)
            self.assertEqual([".venv", "node_modules"], [decision.path for decision in report.skipped])
            self.assertFalse((dest / ".venv").exists())
            self.assertFalse((dest / "node_modules").exists())

    def test_reconcile_does_not_overwrite_conflicting_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "worktree"
            dest = Path(tmp) / "dest"
            worktree.mkdir()
            dest.mkdir()
            _init_git_repo(worktree)
            (worktree / ".gitignore").write_text(".vscode/\n", encoding="utf-8")
            _git(worktree, "add", ".gitignore")
            _git(worktree, "commit", "-m", "ignore vscode")
            (worktree / ".vscode").mkdir()
            (worktree / ".vscode" / "settings.json").write_text('{"from":"worktree"}\n', encoding="utf-8")
            (dest / ".vscode").mkdir()
            (dest / ".vscode" / "settings.json").write_text('{"from":"dest"}\n', encoding="utf-8")

            report = reconcile_local_artifacts(worktree, dest)

            self.assertFalse(report.cleanup_allowed)
            self.assertEqual([".vscode/settings.json"], [decision.path for decision in report.pending])
            self.assertEqual('{"from":"dest"}\n', (dest / ".vscode" / "settings.json").read_text(encoding="utf-8"))

    def test_guardrail_overrides_recommendation_for_secret_like_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "worktree"
            dest = Path(tmp) / "dest"
            worktree.mkdir()
            dest.mkdir()
            _init_git_repo(worktree)
            (worktree / ".gitignore").write_text(".env.local\n", encoding="utf-8")
            _git(worktree, "add", ".gitignore")
            _git(worktree, "commit", "-m", "ignore env")
            (worktree / ".env.local").write_text("TOKEN=secret\n", encoding="utf-8")
            artifact = scan_local_artifacts(worktree)[0]

            decision = decide_artifact(
                artifact,
                worktree,
                dest,
                recommender=lambda metadata: ArtifactRecommendation("copy", "recommended"),
            )

            self.assertEqual("pending", decision.action)
            self.assertIn("secret", decision.reason)


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
