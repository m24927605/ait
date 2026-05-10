from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait import cli
from ait.app import create_attempt, create_commit_for_attempt, create_intent


class AgentFirstWorkflowTests(unittest.TestCase):
    def test_next_reconcile_and_merge_dry_run_for_manual_workspace_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="manual", description=None, kind="test")
            attempt = create_attempt(repo, intent_id=intent.intent_id)
            _commit_ait_gitignore_if_needed(repo)
            workspace = Path(attempt.workspace_ref)
            _git(workspace, "config", "user.email", "test@example.com")
            _git(workspace, "config", "user.name", "Test User")
            (workspace / "manual.txt").write_text("manual\n", encoding="utf-8")
            _git(workspace, "add", "manual.txt")
            _git(workspace, "commit", "-m", "manual commit")

            next_payload = _cli_json(workspace, ["ait", "next", "--json"])

            self.assertEqual("manual_commit_without_recorded_result", next_payload["current_state"])
            self.assertEqual("ait reconcile --json", next_payload["recommended_command"])

            reconcile_payload = _cli_json(workspace, ["ait", "reconcile", "--json"])

            self.assertTrue(reconcile_payload["synthetic_result_created"])
            self.assertEqual(attempt.attempt_id, reconcile_payload["attempt_id"])
            self.assertEqual(["manual.txt"], reconcile_payload["changed_files"])

            merge_payload = _cli_json(workspace, ["ait", "merge", "--to", "main", "--dry-run", "--json"])

            self.assertEqual("planned", merge_payload["status"])
            self.assertTrue(any(op["command"][:2] == ["ait", "apply"] for op in merge_payload["operations"]))
            self.assertEqual(attempt.attempt_id, merge_payload["detected_context"]["attempt_id"])

    def test_merge_blocks_dirty_worktree_with_actionable_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _git(repo, "checkout", "-b", "feature")
            (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
            _git(repo, "add", "feature.txt")
            _git(repo, "commit", "-m", "feature")
            (repo / "scratch.txt").write_text("local\n", encoding="utf-8")

            payload = _cli_json(repo, ["ait", "merge", "--to", "main", "--dry-run", "--json"], expected=1)

            self.assertEqual("blocked", payload["status"])
            self.assertEqual("DIRTY_WORKTREE", payload["error"]["error_code"])
            self.assertTrue(payload["error"]["user_data_safe"])
            self.assertIn("git status --short", payload["recommended_commands"])

    def test_branch_merge_fast_forward_executes_without_deleting_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _git(repo, "checkout", "-b", "feature")
            (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
            _git(repo, "add", "feature.txt")
            _git(repo, "commit", "-m", "feature")

            dry_run = _cli_json(repo, ["ait", "merge", "--to", "main", "--mode", "ff-only", "--dry-run", "--json"])
            self.assertEqual("planned", dry_run["status"])

            payload = _cli_json(repo, ["ait", "merge", "--to", "main", "--mode", "ff-only", "--json"])

            self.assertEqual("merged", payload["status"])
            self.assertEqual("main", _git_stdout(repo, "branch", "--show-current"))
            self.assertEqual("feature\n", (repo / "feature.txt").read_text(encoding="utf-8"))

    def test_adapter_doctor_reports_local_cli_auth_without_api_key_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_git_repo(repo)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            claude = bin_dir / "claude"
            claude.write_text("#!/bin/sh\nprintf 'claude local\\n'\n", encoding="utf-8")
            claude.chmod(0o755)
            with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", "ANTHROPIC_API_KEY": "sk-test"}):
                payload = _cli_json(repo, ["ait", "adapter", "doctor", "claude-code", "--json"])

            auth = payload["agent_auth"]
            self.assertEqual("local_cli", auth["auth_mode"])
            self.assertFalse(auth["will_use_api_key"])
            self.assertFalse(auth["will_fallback_to_credits"])
            self.assertTrue(auth["api_key_env_present"])

    def test_review_report_json_and_markdown_include_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="review", description=None, kind="test")
            attempt = create_attempt(repo, intent_id=intent.intent_id)
            workspace = Path(attempt.workspace_ref)
            (workspace / "review.txt").write_text("review\n", encoding="utf-8")
            _git(workspace, "add", "review.txt")
            create_commit_for_attempt(repo, attempt_id=attempt.attempt_id, message="review")

            report = _cli_json(repo, ["ait", "review", "report", "--attempt", attempt.attempt_id, "--json"])

            self.assertEqual(attempt.attempt_id, report["attempt_id"])
            self.assertEqual(["review.txt"], report["changed_files"])
            self.assertIn("final_approval_status", report)

            md_path = repo / "docs" / "reviews" / "attempt.md"
            output = _cli_text(
                repo,
                [
                    "ait",
                    "review",
                    "report",
                    "--attempt",
                    attempt.attempt_id,
                    "--format",
                    "markdown",
                    "--output",
                    str(md_path),
                ],
            )
            self.assertIn("Wrote", output)
            self.assertIn("# AIT Review Report", md_path.read_text(encoding="utf-8"))


def _cli_json(cwd: Path, argv: list[str], *, expected: int = 0) -> dict[str, object]:
    out = io.StringIO()
    with chdir(cwd):
        with patch("sys.argv", argv):
            with redirect_stdout(out):
                code = cli.main()
    if code != expected:
        raise AssertionError(f"exit {code}, expected {expected}; output={out.getvalue()}")
    return json.loads(out.getvalue())


def _cli_text(cwd: Path, argv: list[str], *, expected: int = 0) -> str:
    out = io.StringIO()
    with chdir(cwd):
        with patch("sys.argv", argv):
            with redirect_stdout(out):
                code = cli.main()
    if code != expected:
        raise AssertionError(f"exit {code}, expected {expected}; output={out.getvalue()}")
    return out.getvalue()


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _commit_ait_gitignore_if_needed(repo_root: Path) -> None:
    status = _git_stdout(repo_root, "status", "--short", "--", ".gitignore")
    if not status:
        return
    _git(repo_root, "add", ".gitignore")
    _git(repo_root, "commit", "-m", "chore: ignore ait state")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_stdout(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@contextmanager
def chdir(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


if __name__ == "__main__":
    unittest.main()
