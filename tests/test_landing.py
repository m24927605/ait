from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import create_attempt, create_commit_for_attempt, create_intent
from ait.landing import apply_attempt
from ait.recovery import recover_attempt
from ait.workspace_lease import read_workspace_lease


class LandingTests(unittest.TestCase):
    def test_apply_latest_lands_clean_current_branch_and_cleans_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Clean apply", "clean.py", "value = 1\n")
            _commit_ait_gitignore_if_needed(repo_root)

            result = apply_attempt(repo_root, attempt_selector="latest")

            self.assertEqual(attempt_id, result.attempt_id)
            self.assertEqual("applied", result.status)
            self.assertTrue((repo_root / "clean.py").exists())
            self.assertFalse(workspace.exists())
            self.assertTrue(result.worktree_cleaned)
            self.assertIsNone(read_workspace_lease(workspace))
            self.assertEqual("", _git_stdout(repo_root, "status", "--short"))

    def test_apply_to_non_current_branch_does_not_touch_dirty_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Branch apply", "branch.py", "value = 1\n")
            (repo_root / "README.md").write_text("local edit\n", encoding="utf-8")

            result = apply_attempt(repo_root, attempt_selector=attempt_id, target_ref="feature/apply")

            self.assertEqual("applied", result.status)
            self.assertEqual("feature/apply", result.branch)
            self.assertEqual("main", _git_stdout(repo_root, "branch", "--show-current"))
            self.assertEqual("local edit\n", (repo_root / "README.md").read_text(encoding="utf-8"))
            self.assertEqual(
                result.commit_oid,
                _git_stdout(repo_root, "rev-parse", "--verify", "refs/heads/feature/apply"),
            )
            self.assertFalse(workspace.exists())

    def test_dirty_current_checkout_applies_unrelated_patch_without_stashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Dirty safe", "agent.txt", "agent\n")
            (repo_root / "README.md").write_text("local edit\n", encoding="utf-8")

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("applied", result.status)
            self.assertEqual("patch_apply_clean_overlap", result.landing_plan.kind)
            self.assertEqual("local edit\n", (repo_root / "README.md").read_text(encoding="utf-8"))
            self.assertEqual("agent\n", (repo_root / "agent.txt").read_text(encoding="utf-8"))
            self.assertFalse(workspace.exists())
            self.assertTrue(result.worktree_cleaned)
            self.assertIsNotNone(result.patch_artifact_ref)
            self.assertIsNotNone(result.result_artifact_ref)
            self.assertTrue(Path(result.patch_artifact_ref or "").exists())
            self.assertTrue(Path(result.result_artifact_ref or "").exists())
            status = _git_stdout(repo_root, "status", "--short")
            self.assertIn("M README.md", status)
            self.assertIn("?? agent.txt", status)

    def test_dirty_current_checkout_holds_on_overlapping_tracked_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Overlap", "README.md", "attempt edit\n")
            (repo_root / "README.md").write_text("local edit\n", encoding="utf-8")

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("conflict", result.status)
            self.assertTrue(workspace.exists())
            self.assertEqual("local edit\n", (repo_root / "README.md").read_text(encoding="utf-8"))
            self.assertIn("overlap", result.reason or "")

    def test_dirty_current_checkout_holds_when_untracked_file_would_be_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Untracked", "agent.txt", "attempt\n")
            (repo_root / "agent.txt").write_text("local\n", encoding="utf-8")

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("conflict", result.status)
            self.assertTrue(workspace.exists())
            self.assertEqual("local\n", (repo_root / "agent.txt").read_text(encoding="utf-8"))
            self.assertIn("untracked", result.reason or "")

    def test_recover_latest_finds_recent_unapplied_attempt_without_text_workspace_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Recover", "recover.py", "value = 1\n")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "latest"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()
            result = recover_attempt(repo_root, attempt_selector="latest")

            self.assertEqual(0, exit_code)
            self.assertEqual(attempt_id, result.attempt_id)
            self.assertTrue(result.recoverable)
            self.assertIn("ait apply", stdout.getvalue())
            self.assertNotIn(".ait/workspaces", stdout.getvalue())

    def test_apply_json_keeps_workspace_ref_for_integrations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, _workspace = _succeeded_attempt(repo_root, "JSON apply", "json.py", "value = 1\n")
            (repo_root / "README.md").write_text("local edit\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "apply", "latest", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertIn("workspace_ref", payload)
            self.assertIn(".ait/workspaces", payload["workspace_ref"])

    def test_status_text_hides_workspace_and_debug_shows_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _succeeded_attempt(repo_root, "Status", "status.py", "value = 1\n")
            normal = io.StringIO()
            debug = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "status"]):
                    with redirect_stdout(normal):
                        normal_code = cli.main()
                with patch("sys.argv", ["ait", "status", "--debug"]):
                    with redirect_stdout(debug):
                        debug_code = cli.main()

            self.assertEqual(0, normal_code)
            self.assertEqual(0, debug_code)
            self.assertIn("Latest result: ready_to_apply", normal.getvalue())
            self.assertNotIn(".ait/workspaces", normal.getvalue())
            self.assertIn(".ait/workspaces", debug.getvalue())
            self.assertIn("Reason code: status.ready_to_apply", debug.getvalue())

    def test_recover_retry_apply_executes_apply_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, workspace = _succeeded_attempt(repo_root, "Retry", "retry.py", "value = 1\n")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "latest", "--retry-apply"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            self.assertEqual(0, exit_code)
            self.assertIn("Status: applied", stdout.getvalue())
            self.assertTrue((repo_root / "retry.py").exists())
            self.assertFalse(workspace.exists())

    def test_recover_discard_holds_dirty_recovery_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, workspace = _succeeded_attempt(repo_root, "Dirty discard", "discard.py", "value = 1\n")
            (workspace / "discard.py").write_text("dirty\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "latest", "--discard"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            self.assertEqual(0, exit_code)
            self.assertTrue(workspace.exists())
            self.assertIn("kept this result", stdout.getvalue())

    def test_recover_create_integration_does_not_modify_root_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, _workspace = _succeeded_attempt(repo_root, "Integration", "agent.py", "value = 1\n")
            _commit_ait_gitignore_if_needed(repo_root)
            (repo_root / "README.md").write_text("local tracked edit\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "latest", "--create-integration"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            self.assertEqual(0, exit_code)
            self.assertIn("integration attempt", stdout.getvalue())
            self.assertEqual("local tracked edit\n", (repo_root / "README.md").read_text(encoding="utf-8"))
            self.assertNotIn("agent.py", _git_stdout(repo_root, "status", "--short"))


def _succeeded_attempt(repo_root: Path, title: str, rel_path: str, content: str) -> tuple[str, Path]:
    intent = create_intent(repo_root, title=title, description=None, kind="test")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id)
    workspace = Path(attempt.workspace_ref)
    _git(workspace, "config", "user.email", "test@example.com")
    _git(workspace, "config", "user.name", "Test User")
    target = workspace / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(workspace, "add", rel_path)
    create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message=title)
    return attempt.attempt_id, workspace


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _commit_ait_gitignore_if_needed(repo_root: Path) -> None:
    if not (repo_root / ".gitignore").exists():
        return
    if not _git_stdout(repo_root, "status", "--short", "--", ".gitignore"):
        return
    _git(repo_root, "add", ".gitignore")
    _git(repo_root, "commit", "-m", "ignore ait state")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )


def _git_stdout(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
