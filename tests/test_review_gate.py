from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.app import create_attempt, create_commit_for_attempt, create_intent
from ait.db import (
    NewAttemptReview,
    NewAttemptReviewOverride,
    connect_db,
    get_attempt,
    insert_attempt_review,
    insert_attempt_review_override,
    list_attempt_commits,
    utc_now,
)
from ait.landing import apply_attempt
from ait.review import create_fake_reviewer_review
from ait.review_policy import current_baseline_policy_hash, review_policy_hash


class ReviewGateTests(unittest.TestCase):
    def test_apply_unaffected_when_review_policy_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Disabled", "disabled.py", "ok\n")
            _commit_ait_gitignore_if_needed(repo_root)

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("applied", result.status)
            self.assertTrue((repo_root / "disabled.py").exists())
            self.assertFalse(workspace.exists())

    def test_apply_holds_when_required_review_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Missing", "missing-review.py", "ok\n")
            _enable_review_gate(repo_root)

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("held", result.status)
            self.assertTrue(workspace.exists())
            self.assertFalse((repo_root / "missing-review.py").exists())
            self.assertIn("review gate", result.reason or "")
            assert result.decision_report is not None
            self.assertEqual("apply.review_gate", result.decision_report.reasons[0].code)
            with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
                attempt = get_attempt(conn, attempt_id)
            assert attempt is not None
            self.assertEqual("succeeded", attempt.verified_status)

    def test_apply_holds_when_required_review_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Blocked", "blocked.py", "ok\n")
            _enable_review_gate(repo_root)
            _insert_review(repo_root, attempt_id, status="blocked", blocking=True)

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("held", result.status)
            self.assertTrue(workspace.exists())
            self.assertFalse((repo_root / "blocked.py").exists())
            self.assertEqual("blocked", result.debug["review_gate"]["status"])

    def test_apply_holds_when_required_review_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Failed", "failed-review.py", "ok\n")
            _enable_review_gate(repo_root)
            _insert_review(repo_root, attempt_id, status="failed", blocking=False)

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("held", result.status)
            self.assertEqual("failed", result.debug["review_gate"]["status"])

    def test_apply_proceeds_when_required_review_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Passed", "passed.py", "ok\n")
            _commit_ait_gitignore_if_needed(repo_root)
            _enable_review_gate(repo_root)
            review_id = _insert_review(repo_root, attempt_id, status="passed", blocking=False)

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("applied", result.status)
            self.assertFalse(workspace.exists())
            self.assertEqual("passed", result.debug["review_gate"]["status"])
            self.assertEqual(review_id, result.debug["review_gate"]["review_id"])
            assert result.decision_report is not None
            self.assertEqual(review_id, result.decision_report.metadata["review_gate"]["review_id"])

    def test_apply_override_proceeds_with_audit_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Override", "override.py", "ok\n")
            _commit_ait_gitignore_if_needed(repo_root)
            _enable_review_gate(repo_root)
            review_id = _insert_review(repo_root, attempt_id, status="blocked", blocking=True)
            _insert_override(repo_root, review_id)

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("applied", result.status)
            self.assertEqual("overridden", result.debug["review_gate"]["status"])
            self.assertEqual("override:1", result.debug["review_gate"]["override_id"])
            assert result.decision_report is not None
            self.assertEqual("overridden", result.decision_report.metadata["review_gate"]["status"])

    def test_required_adversarial_blocked_review_holds_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Adversarial blocked", "adv-blocked.py", "ok\n")
            _enable_review_gate(repo_root)
            review = create_fake_reviewer_review(repo_root, attempt_id, fake_adapter="fake:high")

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("blocked", review.review.status)
            self.assertEqual("held", result.status)
            self.assertTrue(workspace.exists())
            self.assertEqual("blocked", result.debug["review_gate"]["status"])

    def test_required_adversarial_failed_review_holds_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, _workspace = _succeeded_attempt(repo_root, "Adversarial failed", "adv-failed.py", "ok\n")
            _enable_review_gate(repo_root)
            review = create_fake_reviewer_review(repo_root, attempt_id, fake_adapter="fake:malformed")

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("failed", review.review.status)
            self.assertEqual("held", result.status)
            self.assertEqual("failed", result.debug["review_gate"]["status"])

    def test_required_adversarial_passed_review_allows_existing_apply_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id, workspace = _succeeded_attempt(repo_root, "Adversarial passed", "adv-passed.py", "ok\n")
            _commit_ait_gitignore_if_needed(repo_root)
            _enable_review_gate(repo_root)
            review = create_fake_reviewer_review(repo_root, attempt_id, fake_adapter="fake:pass")

            result = apply_attempt(repo_root, attempt_selector=attempt_id)

            self.assertEqual("passed", review.review.status)
            self.assertEqual("applied", result.status)
            self.assertFalse(workspace.exists())
            self.assertEqual("passed", result.debug["review_gate"]["status"])


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


def _insert_review(
    repo_root: Path,
    attempt_id: str,
    *,
    status: str,
    blocking: bool,
) -> str:
    review_id = f"review:{status}"
    with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
        attempt = get_attempt(conn, attempt_id)
        assert attempt is not None
        commits = list_attempt_commits(conn, attempt_id)
        target_head_oid = commits[-1].commit_oid if commits else None
        insert_attempt_review(
            conn,
            NewAttemptReview(
                id=review_id,
                target_attempt_id=attempt_id,
                mode="light",
                budget="quick",
                profiles=(),
                risk_level="high" if blocking else "low",
                risk_score=70 if blocking else 0,
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
                target_head_oid=target_head_oid,
                base_ref_oid=attempt.base_ref_oid,
                summary=f"test review {status}",
            ),
        )
    return review_id


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
