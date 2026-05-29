from __future__ import annotations

import io
import json
import os
import shutil
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
from ait.review import create_deterministic_review
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
            self.assertIsNotNone(result.decision_report)
            self.assertEqual("apply.dirty_overlap", result.decision_report.reasons[0].code)
            self.assertEqual(("README.md",), result.decision_report.reasons[0].paths)
            self.assertEqual("ait recover a1", result.decision_report.next_steps[0].command)

    def test_apply_held_next_step_uses_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Held apply", "README.md", "attempt edit\n")
            (repo_root / "README.md").write_text("local edit\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "apply", "a1"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            text = stdout.getvalue()
            self.assertEqual(1, exit_code)
            self.assertIn("Next: ait recover a1", text)
            self.assertNotIn(attempt_id, text)

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
            self.assertIsNotNone(result.decision_report)
            self.assertEqual("apply.untracked_overwrite", result.decision_report.reasons[0].code)
            self.assertEqual(("agent.txt",), result.decision_report.reasons[0].paths)

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
            self.assertIn("Attempt: a1", stdout.getvalue())
            self.assertIn("ait apply", stdout.getvalue())
            self.assertNotIn(".ait/workspaces", stdout.getvalue())

    def test_recover_text_shows_handle_and_debug_keeps_full_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Recover debug", "recover-debug.py", "value = 1\n")
            normal = io.StringIO()
            debug = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "a1"]):
                    with redirect_stdout(normal):
                        normal_code = cli.main()
                with patch("sys.argv", ["ait", "recover", "a1", "--debug"]):
                    with redirect_stdout(debug):
                        debug_code = cli.main()

            self.assertEqual(0, normal_code)
            self.assertEqual(0, debug_code)
            self.assertIn("Attempt: a1", normal.getvalue())
            self.assertNotIn(attempt_id, normal.getvalue())
            self.assertIn(f"Canonical ID: {attempt_id}", debug.getvalue())
            self.assertIn(".ait/workspaces", debug.getvalue())

    def test_recover_json_includes_identity_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Recover JSON identity", "recover-json.py", "value = 1\n")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "a1", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual(attempt_id, payload["attempt_id"])
            self.assertEqual("a1", payload["attempt_handle"])
            self.assertIn("changed recover-json.py", payload["attempt_description"])
            self.assertIn("workspace_ref", payload)

    def test_recover_accepts_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Recover handle", "recover-handle.py", "value = 1\n")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "a1", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual(attempt_id, payload["attempt_id"])

    def test_apply_accepts_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Apply handle", "apply-handle.py", "value = 1\n")
            _commit_ait_gitignore_if_needed(repo_root)

            result = apply_attempt(repo_root, attempt_selector="a1")

            self.assertEqual(attempt_id, result.attempt_id)
            self.assertEqual("applied", result.status)
            self.assertTrue((repo_root / "apply-handle.py").exists())
            self.assertFalse(workspace.exists())

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
                with patch("sys.argv", ["ait", "status", "--verbose"]):
                    with redirect_stdout(normal):
                        normal_code = cli.main()
                with patch("sys.argv", ["ait", "status", "--debug", "--verbose"]):
                    with redirect_stdout(debug):
                        debug_code = cli.main()

            self.assertEqual(0, normal_code)
            self.assertEqual(0, debug_code)
            self.assertIn("Latest result: ready_to_apply", normal.getvalue())
            self.assertIn("Attempt: a1", normal.getvalue())
            self.assertNotIn(".ait/workspaces", normal.getvalue())
            self.assertIn(".ait/workspaces", debug.getvalue())
            self.assertIn("Reason code: status.ready_to_apply", debug.getvalue())
            self.assertIn("Apply readiness: ready_to_apply", debug.getvalue())

    def test_status_json_keeps_recovery_decision_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _succeeded_attempt(repo_root, "Status JSON", "json-status.py", "value = 1\n")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "status", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            recovery = payload["recovery"]
            decision = recovery["decision_report"]
            self.assertEqual(0, exit_code)
            self.assertEqual("ready_to_apply", recovery["status"])
            self.assertEqual("status.ready_to_apply", decision["reasons"][0]["code"])
            self.assertEqual(["json-status.py"], decision["reasons"][0]["paths"])
            self.assertIn(".ait/workspaces", decision["reasons"][0]["debug"]["workspace_ref"])

    def test_status_reports_latest_review_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Status review", "review-status.py", "value = 1\n")
            review = create_deterministic_review(repo_root, attempt_id)
            text = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "status", "--verbose"]):
                    with redirect_stdout(text):
                        text_code = cli.main()
            payload = _status_json(repo_root)

            self.assertEqual(0, text_code)
            self.assertIn("Review: warning risk=medium findings=0", text.getvalue())
            self.assertEqual(review.review.id, payload["recovery"]["review"]["review_id"])
            self.assertEqual("warning", payload["recovery"]["review"]["status"])
            self.assertEqual("medium", payload["recovery"]["review"]["risk_level"])
            self.assertEqual(review.review.baseline_ref, payload["recovery"]["review"]["baseline_ref"])

    def test_status_reports_conflict_missing_and_applied_recovery_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            conflict_id, _workspace = _succeeded_attempt(repo_root, "Conflict status", "README.md", "attempt\n")
            (repo_root / "README.md").write_text("local\n", encoding="utf-8")
            apply_attempt(repo_root, attempt_selector=conflict_id)
            conflict_payload = _status_json(repo_root)

            self.assertEqual("needs_recovery", conflict_payload["recovery"]["status"])
            self.assertEqual("status.conflict", conflict_payload["recovery"]["decision_report"]["reasons"][0]["code"])

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, workspace = _succeeded_attempt(repo_root, "Missing status", "missing.py", "value = 1\n")
            shutil.rmtree(workspace)
            missing_payload = _status_json(repo_root)

            self.assertEqual("held", missing_payload["recovery"]["status"])
            self.assertEqual(
                "status.missing_recovery_state",
                missing_payload["recovery"]["decision_report"]["reasons"][0]["code"],
            )

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, _workspace = _succeeded_attempt(repo_root, "Applied status", "applied.py", "value = 1\n")
            _commit_ait_gitignore_if_needed(repo_root)
            apply_attempt(repo_root, attempt_selector="latest")
            applied_payload = _status_json(repo_root)

            self.assertEqual("applied", applied_payload["recovery"]["status"])
            self.assertEqual("status.latest_applied", applied_payload["recovery"]["decision_report"]["reasons"][0]["code"])

    def test_status_all_includes_repo_recovery_summary_without_text_workspace_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _succeeded_attempt(repo_root, "Status all", "all.py", "value = 1\n")
            normal = io.StringIO()
            debug = io.StringIO()
            json_out = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "status", "--all", "--verbose"]):
                    with redirect_stdout(normal):
                        normal_code = cli.main()
                with patch("sys.argv", ["ait", "status", "--all", "--debug"]):
                    with redirect_stdout(debug):
                        debug_code = cli.main()
                with patch("sys.argv", ["ait", "status", "--all", "--format", "json"]):
                    with redirect_stdout(json_out):
                        json_code = cli.main()

            self.assertEqual(0, normal_code)
            self.assertEqual(0, debug_code)
            self.assertEqual(0, json_code)
            self.assertIn("AIT Recovery", normal.getvalue())
            self.assertIn("- latest: ready_to_apply", normal.getvalue())
            self.assertNotIn(".ait/workspaces", normal.getvalue())
            self.assertIn(".ait/workspaces", debug.getvalue())
            payload = json.loads(json_out.getvalue())
            self.assertIsInstance(payload, list)
            self.assertTrue(payload)
            self.assertEqual("ready_to_apply", payload[0]["recovery"]["status"])
            self.assertEqual("status.ready_to_apply", payload[0]["recovery"]["decision_report"]["reasons"][0]["code"])

    def test_status_and_recover_debug_include_dev_server_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, workspace = _succeeded_attempt(repo_root, "Dev metadata", "dev.py", "value = 1\n")
            _write_dev_server_record(repo_root, workspace, port=8124)
            status_debug = io.StringIO()
            recover_debug = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "status", "--debug", "--verbose"]):
                    with redirect_stdout(status_debug):
                        self.assertEqual(0, cli.main())
                with patch("sys.argv", ["ait", "recover", "latest", "--debug"]):
                    with redirect_stdout(recover_debug):
                        self.assertEqual(0, cli.main())

            self.assertIn("Dev server: pid=", status_debug.getvalue())
            self.assertIn("port=8124", status_debug.getvalue())
            self.assertIn("Dev server: pid=", recover_debug.getvalue())
            self.assertIn("port=8124", recover_debug.getvalue())

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

    def test_apply_text_shows_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, workspace = _succeeded_attempt(repo_root, "Apply text", "apply-text.py", "value = 1\n")
            _commit_ait_gitignore_if_needed(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "apply", "a1"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            self.assertEqual(0, exit_code)
            self.assertIn("Attempt: a1", stdout.getvalue())
            self.assertTrue((repo_root / "apply-text.py").exists())
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


def _status_json(repo_root: Path) -> dict[str, object]:
    stdout = io.StringIO()
    with chdir(repo_root):
        with patch("sys.argv", ["ait", "status", "--format", "json"]):
            with redirect_stdout(stdout):
                exit_code = cli.main()
    if exit_code != 0:
        raise AssertionError(f"status failed: {exit_code}")
    payload = json.loads(stdout.getvalue())
    if not isinstance(payload, dict):
        raise AssertionError("status JSON payload must be an object")
    return payload


def _write_dev_server_record(repo_root: Path, workspace: Path, *, port: int) -> None:
    path = repo_root / ".ait" / "dev-servers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "servers": [
            {
                "port": port,
                "pid": os.getpid(),
                "command": ["python", "-m", "http.server"],
                "cwd": str(workspace),
                "branch": None,
                "worktree_path": str(workspace),
                "started_at": "2026-05-08T00:00:00+00:00",
                "log_path": str(repo_root / ".ait" / "dev-servers" / "test.log"),
            }
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
