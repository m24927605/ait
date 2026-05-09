from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.app import create_attempt, create_commit_for_attempt, create_intent
from ait.db import (
    NewAttemptReview,
    NewAttemptReviewFinding,
    NewAttemptReviewOverride,
    connect_db,
    get_attempt,
    insert_attempt_review,
    insert_attempt_review_finding,
    insert_attempt_review_override,
    list_attempt_commits,
    utc_now,
)
from ait.ids import new_ulid
from ait.landing import apply_attempt
from ait.review_policy import current_baseline_policy_hash, review_policy_hash


class ReviewGateHardeningTests(unittest.TestCase):
    def test_stale_passed_review_holds_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Stale", "stale.py", "ok\n")
            _enable_review_gate(repo_root)
            _insert_review(repo_root, attempt_id, status="passed", blocking=False)
            with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
                conn.execute("UPDATE attempt_reviews SET target_head_oid = ? WHERE target_attempt_id = ?", ("9" * 40, attempt_id))
                conn.commit()

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("held", result.status)
            self.assertTrue(workspace.exists())
            self.assertEqual("stale", result.debug["review_gate"]["status"])

    def test_override_disabled_does_not_allow_blocked_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Override disabled", "override-disabled.py", "ok\n")
            _enable_review_gate(repo_root, allow_override=False)
            review_id = _insert_review(repo_root, attempt_id, status="blocked", blocking=True)
            _insert_override(repo_root, review_id)

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("held", result.status)
            self.assertEqual("blocked", result.debug["review_gate"]["status"])

    def test_open_high_blocking_finding_holds_even_when_review_status_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Open high", "open-high.py", "ok\n")
            _enable_review_gate(repo_root)
            review_id = _insert_review(repo_root, attempt_id, status="passed", blocking=False)
            _insert_high_finding(repo_root, review_id)

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("held", result.status)
            self.assertEqual("blocked", result.debug["review_gate"]["status"])


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


def _enable_review_gate(repo_root: Path, *, allow_override: bool = True) -> None:
    config_path = repo_root / ".ait" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["review"] = {
        "default_mode": "risk-based",
        "auto_apply_requires_review": True,
        "allow_override": allow_override,
    }
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _insert_review(repo_root: Path, attempt_id: str, *, status: str, blocking: bool) -> str:
    review_id = f"review:{new_ulid()}"
    with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
        attempt = get_attempt(conn, attempt_id)
        assert attempt is not None
        commits = list_attempt_commits(conn, attempt_id)
        insert_attempt_review(
            conn,
            NewAttemptReview(
                id=review_id,
                target_attempt_id=attempt_id,
                mode="light",
                budget="quick",
                profiles=(),
                risk_level="low",
                risk_score=0,
                risk_reasons=(),
                status=status,
                blocking=blocking,
                policy_hash=review_policy_hash(
                    repo_root,
                    mode="light",
                    budget="quick",
                    profiles=(),
                    adapter=None,
                ),
                baseline_policy_hash=current_baseline_policy_hash(repo_root),
                created_at=utc_now(),
                artifact_ref=".ait/reviews/test.json",
                baseline_ref=".ait/review-baselines/test.json",
                target_head_oid=commits[-1].commit_oid,
                base_ref_oid=attempt.base_ref_oid,
                summary=f"review {status}",
            ),
        )
    return review_id


def _insert_high_finding(repo_root: Path, review_id: str) -> None:
    with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
        insert_attempt_review_finding(
            conn,
            NewAttemptReviewFinding(
                id=f"finding:{new_ulid()}",
                review_id=review_id,
                severity="high",
                blocking=True,
                lifecycle_status="open",
                path="open-high.py",
                title="Open high finding",
                body="This should block.",
            ),
        )


def _insert_override(repo_root: Path, review_id: str) -> None:
    with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
        insert_attempt_review_override(
            conn,
            NewAttemptReviewOverride(
                id="override:1",
                review_id=review_id,
                reason="accepted risk",
                created_at=utc_now(),
                actor="test",
                audit_ref=".ait/reviews/override.json",
            ),
        )


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _git(repo_root: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
