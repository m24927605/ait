from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import (
    create_attempt,
    create_commit_for_attempt,
    create_intent,
    discard_attempt,
    promote_attempt,
)
from ait.cleanup import CleanupPolicy, cleanup_policy_from_config, cleanup_repo
from ait.db import connect_db, update_attempt


class CleanupTests(unittest.TestCase):
    def test_cleanup_dry_run_reports_promoted_worktree_without_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _promoted_attempt_with_workspace(repo_root)

            report = cleanup_repo(repo_root, CleanupPolicy())

            self.assertTrue(workspace.exists())
            self.assertEqual("dry-run", report.mode)
            item = _item_for_attempt(report, attempt_id)
            self.assertEqual("remove", item.action)
            self.assertEqual("promoted", item.reason)
            self.assertFalse(item.deleted)

    def test_cleanup_apply_removes_promoted_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _promoted_attempt_with_workspace(repo_root)

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True))

            self.assertFalse(workspace.exists())
            item = _item_for_attempt(report, attempt_id)
            self.assertEqual("remove", item.action)
            self.assertTrue(item.deleted)
            self.assertGreaterEqual(report.reclaimed_bytes, 0)

    def test_cleanup_apply_handles_discarded_missing_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Discard cleanup", description=None, kind="test")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            workspace = Path(attempt.workspace_ref)

            discard_attempt(repo_root, attempt_id=attempt.attempt_id)
            report = cleanup_repo(repo_root, CleanupPolicy(apply=True))

            self.assertFalse(workspace.exists())
            item = _item_for_attempt(report, attempt.attempt_id)
            self.assertEqual("remove", item.action)
            self.assertEqual("discarded", item.reason)
            self.assertEqual(0, item.bytes)
            self.assertTrue(item.deleted)
            self.assertIsNone(item.error)

    def test_cleanup_apply_is_idempotent_when_run_twice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _promoted_attempt_with_workspace(repo_root)

            first = cleanup_repo(repo_root, CleanupPolicy(apply=True))
            second = cleanup_repo(repo_root, CleanupPolicy(apply=True))

            self.assertFalse(workspace.exists())
            self.assertTrue(_item_for_attempt(first, attempt_id).deleted)
            second_item = _item_for_attempt(second, attempt_id)
            self.assertEqual("remove", second_item.action)
            self.assertEqual("promoted", second_item.reason)
            self.assertEqual(0, second_item.bytes)
            self.assertTrue(second_item.deleted)
            self.assertIsNone(second_item.error)
            self.assertEqual(0, second.reclaimed_bytes)

    def test_cleanup_retains_active_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Keep active", description=None, kind="test")
            created = create_attempt(repo_root, intent_id=intent.intent_id)
            running = create_attempt(repo_root, intent_id=intent.intent_id)
            created_workspace = Path(created.workspace_ref)
            running_workspace = Path(running.workspace_ref)
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    running.attempt_id,
                    reported_status="running",
                    heartbeat_at="2026-05-05T00:00:00Z",
                )
            finally:
                conn.close()

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True))

            self.assertTrue(created_workspace.exists())
            self.assertTrue(running_workspace.exists())
            created_item = _item_for_attempt(report, created.attempt_id)
            running_item = _item_for_attempt(report, running.attempt_id)
            self.assertEqual("retain", created_item.action)
            self.assertEqual("active", created_item.reason)
            self.assertEqual("created", created_item.reported_status)
            self.assertEqual("retain", running_item.action)
            self.assertEqual("active", running_item.reason)
            self.assertEqual("running", running_item.reported_status)

    def test_cleanup_retains_pending_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Keep pending", description=None, kind="test")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            workspace = Path(attempt.workspace_ref)
            _set_attempt_status(
                repo_root,
                attempt.attempt_id,
                reported_status="finished",
                verified_status="pending",
                ended_at=_iso_now(),
            )

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True))

            self.assertTrue(workspace.exists())
            item = _item_for_attempt(report, attempt.attempt_id)
            self.assertEqual("retain", item.action)
            self.assertEqual("pending", item.reason)
            self.assertEqual("pending", item.verified_status)

    def test_cleanup_retains_failed_and_crashed_attempts_inside_retention_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Keep recent failures", description=None, kind="test")
            failed = create_attempt(repo_root, intent_id=intent.intent_id)
            crashed = create_attempt(repo_root, intent_id=intent.intent_id)
            failed_workspace = Path(failed.workspace_ref)
            crashed_workspace = Path(crashed.workspace_ref)
            recent = _iso_now()
            _set_attempt_status(
                repo_root,
                failed.attempt_id,
                reported_status="finished",
                verified_status="failed",
                ended_at=recent,
            )
            _set_attempt_status(
                repo_root,
                crashed.attempt_id,
                reported_status="crashed",
                verified_status="pending",
                ended_at=recent,
            )

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True, older_than_days=14))

            self.assertTrue(failed_workspace.exists())
            self.assertTrue(crashed_workspace.exists())
            failed_item = _item_for_attempt(report, failed.attempt_id)
            crashed_item = _item_for_attempt(report, crashed.attempt_id)
            self.assertEqual("retain", failed_item.action)
            self.assertEqual("retention-window", failed_item.reason)
            self.assertEqual("retain", crashed_item.action)
            self.assertEqual("retention-window", crashed_item.reason)

    def test_cleanup_removes_stale_failed_and_crashed_clean_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Remove stale failures", description=None, kind="test")
            failed = create_attempt(repo_root, intent_id=intent.intent_id)
            crashed = create_attempt(repo_root, intent_id=intent.intent_id)
            failed_workspace = Path(failed.workspace_ref)
            crashed_workspace = Path(crashed.workspace_ref)
            stale = _iso_days_ago(30)
            _set_attempt_status(
                repo_root,
                failed.attempt_id,
                reported_status="finished",
                verified_status="failed",
                ended_at=stale,
            )
            _set_attempt_status(
                repo_root,
                crashed.attempt_id,
                reported_status="crashed",
                verified_status="pending",
                ended_at=stale,
            )

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True, older_than_days=14))

            self.assertFalse(failed_workspace.exists())
            self.assertFalse(crashed_workspace.exists())
            failed_item = _item_for_attempt(report, failed.attempt_id)
            crashed_item = _item_for_attempt(report, crashed.attempt_id)
            self.assertEqual("remove", failed_item.action)
            self.assertEqual("stale-failed", failed_item.reason)
            self.assertTrue(failed_item.deleted)
            self.assertEqual("remove", crashed_item.action)
            self.assertEqual("stale-failed", crashed_item.reason)
            self.assertTrue(crashed_item.deleted)

    def test_cleanup_retains_unpromoted_succeeded_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Keep reviewable", description=None, kind="test")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            workspace = Path(attempt.workspace_ref)
            (workspace / "change.txt").write_text("ok\n", encoding="utf-8")
            _git(workspace, "add", "change.txt")
            result = create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message="change")

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True))

            self.assertEqual("succeeded", result.attempt["verified_status"])
            self.assertTrue(workspace.exists())
            item = _item_for_attempt(report, attempt.attempt_id)
            self.assertEqual("retain", item.action)
            self.assertEqual("reviewable", item.reason)

    def test_cleanup_skips_dirty_promoted_worktree_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _promoted_attempt_with_workspace(repo_root)
            (workspace / "scratch.txt").write_text("dirty\n", encoding="utf-8")

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True))

            self.assertTrue(workspace.exists())
            item = _item_for_attempt(report, attempt_id)
            self.assertEqual("skip", item.action)
            self.assertEqual("dirty", item.reason)
            self.assertTrue(item.dirty)

    def test_cleanup_force_removes_dirty_promoted_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _promoted_attempt_with_workspace(repo_root)
            (workspace / "scratch.txt").write_text("dirty\n", encoding="utf-8")

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True, force=True))

            self.assertFalse(workspace.exists())
            item = _item_for_attempt(report, attempt_id)
            self.assertEqual("remove", item.action)
            self.assertEqual("promoted", item.reason)
            self.assertTrue(item.dirty)
            self.assertTrue(item.deleted)

    def test_cleanup_artifacts_dry_run_reports_allowlisted_generated_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt_with_workspace(repo_root)
            artifact = workspace / "node_modules"
            artifact.mkdir()
            (artifact / "dep.txt").write_text("dependency\n", encoding="utf-8")

            report = cleanup_repo(repo_root, CleanupPolicy(artifacts=True))

            self.assertTrue(artifact.exists())
            item = _item_for_path(report, artifact)
            self.assertEqual("artifact", item.kind)
            self.assertEqual(attempt_id, item.attempt_id)
            self.assertEqual("remove", item.action)
            self.assertEqual("allowlisted-artifact", item.reason)
            self.assertFalse(item.deleted)

    def test_cleanup_artifacts_apply_removes_allowlisted_paths_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, workspace = _succeeded_attempt_with_workspace(repo_root)
            artifact = workspace / "node_modules"
            artifact.mkdir()
            (artifact / "dep.txt").write_text("dependency\n", encoding="utf-8")
            non_allowlisted = workspace / "custom-cache"
            non_allowlisted.mkdir()
            (non_allowlisted / "keep.txt").write_text("keep\n", encoding="utf-8")

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True, artifacts=True))

            self.assertFalse(artifact.exists())
            self.assertTrue(non_allowlisted.exists())
            item = _item_for_path(report, artifact)
            self.assertEqual("artifact", item.kind)
            self.assertEqual("remove", item.action)
            self.assertTrue(item.deleted)
            with self.assertRaises(AssertionError):
                _item_for_path(report, non_allowlisted)

    def test_cleanup_orphan_worktree_is_skipped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            create_intent(repo_root, title="Initialize AIT", description=None, kind="test")
            orphan = repo_root / ".ait" / "workspaces" / "attempt-orphan"
            orphan.mkdir(parents=True)
            (orphan / "orphan.txt").write_text("keep\n", encoding="utf-8")

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True))

            self.assertTrue(orphan.exists())
            item = _item_for_path(report, orphan)
            self.assertEqual("orphan", item.kind)
            self.assertEqual("skip", item.action)
            self.assertEqual("unknown-attempt", item.reason)
            self.assertFalse(item.deleted)

    def test_cleanup_include_orphans_removes_only_ait_workspace_orphans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            create_intent(repo_root, title="Initialize AIT", description=None, kind="test")
            orphan = repo_root / ".ait" / "workspaces" / "attempt-orphan"
            orphan.mkdir(parents=True)
            (orphan / "orphan.txt").write_text("remove\n", encoding="utf-8")
            outside = repo_root.parent / f"{repo_root.name}-attempt-outside"
            outside.mkdir()
            (outside / "outside.txt").write_text("keep\n", encoding="utf-8")

            report = cleanup_repo(repo_root, CleanupPolicy(apply=True, include_orphans=True))

            self.assertFalse(orphan.exists())
            self.assertTrue(outside.exists())
            item = _item_for_path(report, orphan)
            self.assertEqual("orphan", item.kind)
            self.assertEqual("remove", item.action)
            self.assertTrue(item.deleted)
            with self.assertRaises(AssertionError):
                _item_for_path(report, outside)

    def test_cleanup_skips_workspace_ref_outside_ait_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Reject outside", description=None, kind="test")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            outside = repo_root.parent / f"{repo_root.name}-attempt-outside"
            outside.mkdir()
            (outside / "outside.txt").write_text("keep\n", encoding="utf-8")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                with conn:
                    conn.execute(
                        "UPDATE attempts SET workspace_ref = ? WHERE id = ?",
                        (str(outside), attempt.attempt_id),
                    )
            finally:
                conn.close()

            report = cleanup_repo(
                repo_root,
                CleanupPolicy(apply=True, force=True, include_orphans=True),
            )

            self.assertTrue(outside.exists())
            item = _item_for_attempt(report, attempt.attempt_id)
            self.assertEqual("skip", item.action)
            self.assertEqual("outside-ait-root", item.reason)
            self.assertFalse(item.deleted)

    def test_cli_cleanup_json_outputs_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _promoted_attempt_with_workspace(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "cleanup", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("dry-run", payload["mode"])
            self.assertEqual(attempt_id, payload["items"][0]["attempt_id"])
            self.assertEqual("remove", payload["items"][0]["action"])

    def test_cli_cleanup_json_matches_contract_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, _workspace = _promoted_attempt_with_workspace(repo_root)
            stdout = io.StringIO()
            schema_path = (
                Path(__file__).resolve().parents[1]
                / "specs"
                / "001-worktree-cleanup"
                / "contracts"
                / "cleanup-report.schema.json"
            )
            schema = json.loads(schema_path.read_text(encoding="utf-8"))

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "cleanup", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            item_schema = schema["$defs"]["cleanup_item"]
            self.assertEqual(0, exit_code)
            self.assertEqual(set(schema["required"]), set(payload))
            self.assertEqual(set(item_schema["required"]), set(payload["items"][0]))
            self.assertIn(payload["mode"], schema["properties"]["mode"]["enum"])
            self.assertIn(payload["items"][0]["kind"], item_schema["properties"]["kind"]["enum"])
            self.assertIn(payload["items"][0]["action"], item_schema["properties"]["action"]["enum"])

    def test_cli_cleanup_rejects_negative_older_than(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            create_intent(repo_root, title="Initialize AIT", description=None, kind="test")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "cleanup", "--older-than", "-1"]):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = cli.main()

            self.assertEqual(2, exit_code)
            self.assertEqual("", stdout.getvalue())
            self.assertIn("--older-than must be >= 0", stderr.getvalue())

    def test_cli_cleanup_text_outputs_report_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _attempt_id, _workspace = _promoted_attempt_with_workspace(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "cleanup"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            self.assertIn("AIT Cleanup", output)
            self.assertIn("Mode: dry-run", output)
            self.assertIn("remove worktree", output)
            self.assertIn("promoted", output)
            self.assertIn("Run with --apply", output)

    def test_cleanup_policy_reads_repo_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            create_intent(repo_root, title="Initialize AIT", description=None, kind="test")
            config_path = repo_root / ".ait" / "config.json"
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            payload["cleanup"] = {
                "failed_retention_days": 3,
                "include_orphans": True,
                "artifact_allowlist": ["node_modules", "../unsafe", ".next"],
            }
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            policy = cleanup_policy_from_config(repo_root)

            self.assertEqual(3, policy.older_than_days)
            self.assertTrue(policy.include_orphans)
            self.assertEqual(("node_modules", ".next"), policy.artifact_allowlist)


def _promoted_attempt_with_workspace(repo_root: Path) -> tuple[str, Path]:
    intent = create_intent(repo_root, title="Promote cleanup", description=None, kind="test")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id)
    workspace = Path(attempt.workspace_ref)
    (workspace / "feature.txt").write_text("ok\n", encoding="utf-8")
    _git(workspace, "add", "feature.txt")
    create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message="feature")
    promote_attempt(repo_root, attempt_id=attempt.attempt_id, target_ref="cleanup-target")
    return attempt.attempt_id, workspace


def _succeeded_attempt_with_workspace(repo_root: Path) -> tuple[str, Path]:
    intent = create_intent(repo_root, title="Succeeded cleanup", description=None, kind="test")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id)
    workspace = Path(attempt.workspace_ref)
    (workspace / "change.txt").write_text("ok\n", encoding="utf-8")
    _git(workspace, "add", "change.txt")
    create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message="change")
    return attempt.attempt_id, workspace


def _item_for_attempt(report, attempt_id: str):
    for item in report.items:
        if item.attempt_id == attempt_id:
            return item
    raise AssertionError(f"cleanup item not found for attempt {attempt_id}")


def _item_for_path(report, path: Path):
    resolved = str(path.resolve())
    for item in report.items:
        if item.path == resolved:
            return item
    raise AssertionError(f"cleanup item not found for path {resolved}")


def _set_attempt_status(
    repo_root: Path,
    attempt_id: str,
    *,
    reported_status: str,
    verified_status: str,
    ended_at: str,
) -> None:
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        update_attempt(
            conn,
            attempt_id,
            reported_status=reported_status,
            verified_status=verified_status,
            ended_at=ended_at,
        )
    finally:
        conn.close()


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_days_ago(days: int) -> str:
    return (
        datetime.now(tz=UTC)
        .replace(microsecond=0)
        - timedelta(days=days)
    ).isoformat().replace("+00:00", "Z")


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
