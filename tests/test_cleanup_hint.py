from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ait.app import create_attempt, create_intent
from ait.cleanup import classify_terminal, path_is_inside, safe_resolve_workspace_ref
from ait.cli.status_helpers import (
    _cleanup_hint_lines,
    _compute_cleanup_hint,
    _empty_cleanup_hint,
    _format_status_current_work,
    _recovery_dashboard_payload,
    _safe_workspace_fields,
)
from ait.db import connect_db
from ait.workspace import get_workspaces_root


def _attempt(attempt_id, verified, *, reported="finished", ended_at=None, ws=None):
    return SimpleNamespace(
        id=attempt_id,
        verified_status=verified,
        reported_status=reported,
        ended_at=ended_at,
        heartbeat_at=None,
        started_at=ended_at,
        workspace_ref=ws,
    )


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_days_ago(days: int) -> str:
    return (
        (datetime.now(tz=UTC).replace(microsecond=0) - timedelta(days=days))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _fixed_retention(days: int = 14):
    return patch(
        "ait.cli.status_helpers.cleanup_policy_from_config",
        return_value=SimpleNamespace(older_than_days=days),
    )


class ClassifyTerminalTests(unittest.TestCase):
    def test_promoted_and_discarded_are_reclaimable(self) -> None:
        for status in ("promoted", "discarded"):
            decision = classify_terminal(_attempt("a", status), retention_days=14)
            self.assertEqual((decision.category, decision.reason), ("reclaimable", status))

    def test_succeeded_is_retained(self) -> None:
        decision = classify_terminal(_attempt("a", "succeeded"), retention_days=14)
        self.assertEqual((decision.category, decision.reason), ("retained_succeeded", "reviewable"))

    def test_stale_failed_is_reclaimable(self) -> None:
        decision = classify_terminal(_attempt("a", "failed", ended_at=_iso_days_ago(30)), retention_days=14)
        self.assertEqual((decision.category, decision.reason), ("reclaimable", "stale-failed"))

    def test_recent_failed_within_retention(self) -> None:
        decision = classify_terminal(_attempt("a", "failed", ended_at=_iso_days_ago(1)), retention_days=14)
        self.assertEqual((decision.category, decision.reason), ("not_reclaimable", "retention-window"))

    def test_crashed_reported_status_counts_as_failed(self) -> None:
        decision = classify_terminal(
            _attempt("a", "pending", reported="crashed", ended_at=_iso_days_ago(30)), retention_days=14
        )
        self.assertEqual(decision.category, "reclaimable")

    def test_running_not_reclaimable(self) -> None:
        decision = classify_terminal(_attempt("a", "pending", reported="running"), retention_days=14)
        self.assertEqual(decision.category, "not_reclaimable")

    def test_missing_ended_at_is_conservative(self) -> None:
        decision = classify_terminal(_attempt("a", "failed", ended_at=None), retention_days=14)
        self.assertEqual(decision.category, "not_reclaimable")


class SafeResolveTests(unittest.TestCase):
    def test_relative_ref_returns_none(self) -> None:
        self.assertIsNone(safe_resolve_workspace_ref("rel/path"))

    def test_null_byte_returns_none(self) -> None:
        self.assertIsNone(safe_resolve_workspace_ref("/a\x00b"))

    def test_absolute_ref_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(safe_resolve_workspace_ref(tmp), Path(tmp).resolve())


class PathIsInsideTests(unittest.TestCase):
    def test_inside_and_outside(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            self.assertTrue(path_is_inside(root / "a" / "b", root))
            self.assertFalse(path_is_inside(Path("/etc"), root))


class SafeWorkspaceFieldsTests(unittest.TestCase):
    def test_malformed_ref_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exists, lease, dev_servers, lease_path = _safe_workspace_fields(Path(tmp), "/a\x00b")
            self.assertFalse(exists)
            self.assertIsNone(lease)
            self.assertEqual(dev_servers, [])
            self.assertEqual(lease_path, "")


class CleanupHintLinesTests(unittest.TestCase):
    def test_empty_when_all_zero(self) -> None:
        self.assertEqual(_cleanup_hint_lines(_empty_cleanup_hint()), [])

    def test_lines_for_each_signal(self) -> None:
        hint = {
            "reclaimable_worktrees": 2,
            "retained_succeeded_worktrees": 1,
            "anomalous_refs": 1,
            "config_warning": True,
        }
        lines = _cleanup_hint_lines(hint)
        self.assertEqual(len(lines), 4)
        self.assertTrue(any("ait cleanup" in line and "--apply" in line for line in lines))
        self.assertTrue(any("anomalies" in line for line in lines))

    def test_non_dict_returns_empty(self) -> None:
        self.assertEqual(_cleanup_hint_lines(None), [])


class ComputeCleanupHintTests(unittest.TestCase):
    def _ws(self, ws_root: Path, name: str) -> str:
        path = ws_root / name
        path.mkdir(parents=True)
        return str(path)

    def test_counts_reclaimable_and_retained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            ws_root = get_workspaces_root(root)
            ws_root.mkdir(parents=True)
            attempts = [
                _attempt("p", "promoted", ws=self._ws(ws_root, "attempt-0001")),
                _attempt("s", "succeeded", ws=self._ws(ws_root, "attempt-0002")),
                _attempt("f", "failed", ended_at=_iso_days_ago(30), ws=self._ws(ws_root, "attempt-0003")),
                _attempt("recent", "failed", ended_at=_iso_days_ago(1), ws=self._ws(ws_root, "attempt-0004")),
            ]
            with _fixed_retention():
                hint = _compute_cleanup_hint(attempts, root)
            self.assertEqual(hint["reclaimable_worktrees"], 2)
            self.assertEqual(hint["retained_succeeded_worktrees"], 1)
            self.assertEqual(hint["anomalous_refs"], 0)
            self.assertFalse(hint["config_warning"])

    def test_dedupe_precedence_prefers_reclaimable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            ws_root = get_workspaces_root(root)
            ws_root.mkdir(parents=True)
            shared = self._ws(ws_root, "attempt-shared")
            attempts = [
                _attempt("d1", "succeeded", ws=shared),
                _attempt("d2", "promoted", ws=shared),
            ]
            with _fixed_retention():
                hint = _compute_cleanup_hint(attempts, root)
            self.assertEqual(hint["reclaimable_worktrees"], 1)
            self.assertEqual(hint["retained_succeeded_worktrees"], 0)

    def test_anomalous_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            get_workspaces_root(root).mkdir(parents=True)
            attempts = [
                _attempt("rel", "failed", ended_at=_iso_days_ago(30), ws="relative/ref"),
                _attempt("out", "promoted", ws="/etc/passwd"),
            ]
            with _fixed_retention():
                hint = _compute_cleanup_hint(attempts, root)
            self.assertEqual(hint["anomalous_refs"], 2)
            self.assertEqual(hint["reclaimable_worktrees"], 0)
            reasons = {entry["reason"] for entry in hint["anomalies"]}
            self.assertEqual(reasons, {"relative-ref", "outside-root"})

    def test_missing_worktree_not_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            ws_root = get_workspaces_root(root)
            ws_root.mkdir(parents=True)
            attempts = [_attempt("gone", "promoted", ws=str(ws_root / "attempt-gone"))]
            with _fixed_retention():
                hint = _compute_cleanup_hint(attempts, root)
            self.assertEqual(hint["reclaimable_worktrees"], 0)
            self.assertEqual(hint["anomalous_refs"], 0)

    def test_config_warning_on_invalid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            get_workspaces_root(root).mkdir(parents=True)
            with patch(
                "ait.cli.status_helpers.cleanup_policy_from_config",
                side_effect=ValueError("bad config"),
            ):
                hint = _compute_cleanup_hint([], root)
            self.assertTrue(hint["config_warning"])
            self.assertEqual(hint["reclaimable_worktrees"], 0)


class CleanupHintEndToEndTests(unittest.TestCase):
    def test_status_payload_includes_cleanup_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="t", description=None, kind="test")
            promoted = create_attempt(repo_root, intent_id=intent.intent_id)
            succeeded = create_attempt(repo_root, intent_id=intent.intent_id)
            _set_status(repo_root, promoted.attempt_id, "finished", "promoted")
            _set_status(repo_root, succeeded.attempt_id, "finished", "succeeded")
            payload = _recovery_dashboard_payload(repo_root)
            hint = payload["cleanup_hint"]
            self.assertEqual(hint["reclaimable_worktrees"], 1)
            self.assertEqual(hint["retained_succeeded_worktrees"], 1)
            self.assertEqual(hint["anomalous_refs"], 0)

    def test_text_current_work_shows_cleanup_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="t", description=None, kind="test")
            promoted = create_attempt(repo_root, intent_id=intent.intent_id)
            _set_status(repo_root, promoted.attempt_id, "finished", "promoted")
            recovery = _recovery_dashboard_payload(repo_root)
            lines = _format_status_current_work(recovery)
            self.assertTrue(any("清理：" in line for line in lines))
            self.assertTrue(any("ait cleanup" in line for line in lines))

    def test_not_initialized_has_empty_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _recovery_dashboard_payload(Path(tmp))
            self.assertEqual(payload["status"], "not_initialized")
            self.assertEqual(payload["cleanup_hint"], _empty_cleanup_hint())

    def test_status_does_not_crash_on_malformed_latest_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="t", description=None, kind="test")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                conn.execute(
                    "UPDATE attempts SET workspace_ref = ? WHERE id = ?",
                    ("relative/corrupt-ref", attempt.attempt_id),
                )
                conn.commit()
            finally:
                conn.close()
            payload = _recovery_dashboard_payload(repo_root)  # must not raise
            self.assertIn("cleanup_hint", payload)
            self.assertEqual(payload["cleanup_hint"]["anomalous_refs"], 1)


def _set_status(repo_root: Path, attempt_id: str, reported: str, verified: str) -> None:
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        conn.execute(
            "UPDATE attempts SET reported_status = ?, verified_status = ?, ended_at = ? WHERE id = ?",
            (reported, verified, _iso_now(), attempt_id),
        )
        conn.commit()
    finally:
        conn.close()


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_root, check=True, text=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
