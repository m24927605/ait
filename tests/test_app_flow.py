from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.app import (
    abandon_intent,
    create_commit_for_attempt,
    create_attempt,
    create_intent,
    discard_attempt,
    land_attempt,
    promote_attempt,
    rebase_attempt,
    show_attempt,
    show_intent,
    supersede_intent,
    verify_attempt,
)
from ait.db import connect_db, update_attempt
from ait.workspace import commit_message


class AppFlowTests(unittest.TestCase):
    def test_show_attempt_materializes_plain_git_commit_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Plain commit", description=None, kind="chore")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)

            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "plain.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "plain.py")
            _git(worktree, "commit", "-m", "plain git commit")

            shown = show_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual(1, len(shown.commits))
            self.assertEqual(("plain.py",), shown.files["changed"])
            self.assertEqual(
                _git_stdout(worktree, "rev-parse", "--verify", "HEAD"),
                shown.commits[0]["commit_oid"],
            )

    def test_land_attempt_checks_out_target_branch_in_original_repo_and_removes_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Land", description=None, kind="chore")
            _commit_ait_gitignore_if_needed(repo_root)
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)

            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "landed.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "landed.py")
            _git(worktree, "commit", "-m", "landed")
            attempt_head = _git_stdout(worktree, "rev-parse", "--verify", "HEAD")

            landed = land_attempt(repo_root, attempt_id=attempt.attempt_id, target_ref="feature/land")

            self.assertEqual("feature/land", _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD"))
            self.assertEqual(attempt_head, _git_stdout(repo_root, "rev-parse", "--verify", "HEAD"))
            self.assertEqual(attempt_head, landed.commit_oid)
            self.assertTrue((repo_root / "landed.py").exists())
            self.assertFalse(worktree.exists())
            self.assertTrue(landed.worktree_cleaned)
            self.assertEqual("", _git_stdout(repo_root, "status", "--short"))
            self.assertEqual("promoted", landed.attempt["verified_status"])

    def test_land_attempt_releases_branch_checked_out_by_attempt_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Occupied branch", description=None, kind="chore")
            _commit_ait_gitignore_if_needed(repo_root)
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)

            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            _git(worktree, "checkout", "-b", "feature/occupied")
            (worktree / "occupied.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "occupied.py")
            _git(worktree, "commit", "-m", "occupied")
            attempt_head = _git_stdout(worktree, "rev-parse", "--verify", "HEAD")

            land_attempt(repo_root, attempt_id=attempt.attempt_id, target_ref="feature/occupied")

            self.assertEqual("feature/occupied", _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD"))
            self.assertEqual(attempt_head, _git_stdout(repo_root, "rev-parse", "--verify", "HEAD"))
            self.assertFalse(worktree.exists())
            _git(repo_root, "checkout", "feature/occupied")

    def test_cli_land_reports_original_repo_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="CLI land", description=None, kind="chore")
            _commit_ait_gitignore_if_needed(repo_root)
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "cli_land.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "cli_land.py")
            _git(worktree, "commit", "-m", "cli land")
            attempt_head = _git_stdout(worktree, "rev-parse", "--verify", "HEAD")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ait.cli",
                    "attempt",
                    "land",
                    attempt.attempt_id,
                    "--to",
                    "feature/cli-land",
                ],
                cwd=repo_root,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(str(repo_root.resolve()), payload["repo_root"])
            self.assertEqual("feature/cli-land", payload["branch"])
            self.assertEqual(attempt_head, payload["commit_oid"])
            self.assertTrue(payload["worktree_cleaned"])
            self.assertEqual(attempt_head, _git_stdout(repo_root, "rev-parse", "--verify", "HEAD"))
            self.assertEqual("", _git_stdout(repo_root, "status", "--short"))

    def test_verify_and_promote_attempt_materializes_commits_and_changes_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Fix auth", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)

            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "src").mkdir()
            (worktree / "src" / "auth.py").write_text("print('ok')\n", encoding="utf-8")
            _git(worktree, "add", "src/auth.py")
            _git(worktree, "commit", "-m", "add auth")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                )
            finally:
                conn.close()

            verified = verify_attempt(repo_root, attempt_id=attempt.attempt_id)
            promoted = promote_attempt(repo_root, attempt_id=attempt.attempt_id, target_ref="fix/auth")
            intent_view = show_intent(repo_root, intent_id=intent.intent_id)

            self.assertEqual("succeeded", verified.attempt["verified_status"])
            self.assertEqual(("src/auth.py",), verified.files["changed"])
            self.assertEqual(1, len(verified.commits))
            self.assertEqual("promoted", promoted.attempt["verified_status"])
            self.assertEqual("finished", intent_view.intent["status"])
            self.assertEqual("refs/heads/fix/auth", promoted.attempt["result_promotion_ref"])
            self.assertEqual(1, len(intent_view.attempts))
            self.assertEqual(
                _git_stdout(repo_root, "rev-parse", "--verify", "refs/heads/fix/auth"),
                promoted.commits[0]["commit_oid"],
            )

    def test_promote_rejects_non_branch_target_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Tag target", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "feature.py").write_text("flag = True\n", encoding="utf-8")
            _git(worktree, "add", "feature.py")
            _git(worktree, "commit", "-m", "feature")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                )
            finally:
                conn.close()

            with self.assertRaisesRegex(ValueError, "refs/heads"):
                promote_attempt(
                    repo_root,
                    attempt_id=attempt.attempt_id,
                    target_ref="refs/tags/release",
                )

    def test_attempt_commit_writes_git_trailers_and_updates_attempt_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Trailer", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "feature.py").write_text("flag = True\n", encoding="utf-8")
            _git(worktree, "add", "feature.py")

            result = create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="add feature",
            )

            self.assertEqual("succeeded", result.attempt["verified_status"])
            self.assertEqual(("feature.py",), result.files["changed"])
            self.assertEqual(1, len(result.commits))
            message = commit_message(attempt.workspace_ref, result.commits[0]["commit_oid"])
            self.assertIn("Intent-Id: " + intent.intent_id, message)
            self.assertIn("Attempt-Id: " + attempt.attempt_id, message)

    def test_discard_attempt_marks_record_and_removes_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Try fix", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            workspace = Path(attempt.workspace_ref)

            discarded = discard_attempt(repo_root, attempt_id=attempt.attempt_id)
            shown = show_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual("discarded", discarded.attempt["verified_status"])
            self.assertEqual("finished", discarded.attempt["reported_status"])
            self.assertFalse(workspace.exists())
            self.assertEqual("discarded", shown.attempt["verified_status"])

    def test_abandon_intent_updates_status_and_show_aggregates_attempt_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Aggregate", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "lib.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "lib.py")
            _git(worktree, "commit", "-m", "add lib")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                )
            finally:
                conn.close()
            verify_attempt(repo_root, attempt_id=attempt.attempt_id)

            with self.assertRaises(ValueError):
                abandon_intent(repo_root, intent_id=intent.intent_id)
            shown = show_intent(repo_root, intent_id=intent.intent_id)

            self.assertEqual("finished", shown.intent["status"])
            self.assertEqual(("lib.py",), shown.files["changed"])
            self.assertEqual(1, len(shown.commit_oids))

    def test_supersede_intent_marks_original_superseded_and_writes_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            original = create_intent(repo_root, title="Original", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")

            result = supersede_intent(
                repo_root,
                intent_id=original.intent_id,
                by_intent_id=replacement.intent_id,
            )

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                edge = conn.execute(
                    """
                    SELECT parent_intent_id, child_intent_id, edge_type
                    FROM intent_edges
                    WHERE parent_intent_id = ? AND child_intent_id = ?
                    """,
                    (original.intent_id, replacement.intent_id),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual("superseded", result.intent["status"])
            self.assertEqual("superseded_by", edge["edge_type"])

    def test_create_attempt_default_agent_id_is_cli_human(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Default agent", description=None, kind="chore")

            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            shown = show_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual("cli:human", shown.attempt["agent_id"])
            self.assertEqual("cli", shown.attempt["agent_harness"])

    def test_create_attempt_accepts_custom_agent_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Custom agent", description=None, kind="chore")

            attempt = create_attempt(
                repo_root,
                intent_id=intent.intent_id,
                agent_id="claude-code:worker-1",
            )
            shown = show_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual("claude-code:worker-1", shown.attempt["agent_id"])
            self.assertEqual("claude-code", shown.attempt["agent_harness"])

    def test_create_attempt_rejects_malformed_agent_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Bad", description=None, kind="chore")

            for bad in ("no-colon", ":empty-harness", "empty-name:", "two:colons:here"):
                with self.assertRaises(ValueError):
                    create_attempt(
                        repo_root,
                        intent_id=intent.intent_id,
                        agent_id=bad,
                    )

    def test_short_id_suffix_resolves_in_app_calls(self) -> None:
        # Regression for dogfood-session-1 Friction C: CLI callers must be
        # able to pass a ULID suffix rather than the full 100-character id.
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Short", description=None, kind="chore")
            short_suffix = intent.intent_id.rsplit(":", 1)[-1]

            # show_intent accepts the suffix
            shown = show_intent(repo_root, intent_id=short_suffix)
            self.assertEqual(intent.intent_id, shown.intent["id"])

            # create_attempt resolves the suffix through to the full intent
            attempt = create_attempt(repo_root, intent_id=short_suffix)
            attempt_suffix = attempt.attempt_id.rsplit(":", 1)[-1]

            # show_attempt accepts the attempt suffix
            attempt_view = show_attempt(repo_root, attempt_id=attempt_suffix)
            self.assertEqual(attempt.attempt_id, attempt_view.attempt["id"])

            # discard_attempt resolves the attempt suffix
            discarded = discard_attempt(repo_root, attempt_id=attempt_suffix)
            self.assertEqual("discarded", discarded.attempt["verified_status"])

    def test_promote_to_head_branch_fast_forwards_main_working_tree(self) -> None:
        # Regression for dogfood-session-1 Bug B: promoting to the
        # currently-checked-out branch must advance the main working tree,
        # not leave it inverted.
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            head_branch = _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD")

            intent = create_intent(repo_root, title="FF", description=None, kind="chore")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "ff.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "ff.py")
            create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="ff",
            )

            promoted = promote_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                target_ref=head_branch,
            )

            # Main working tree must carry the new file — not be in an
            # inverted "changes to be committed" state. Filter untracked
            # because `.ait/`-adjacent artifacts (e.g. a fresh .gitignore)
            # are created by init and are not relevant to the regression.
            self.assertTrue((repo_root / "ff.py").exists())
            porcelain = _git_stdout(
                repo_root, "status", "--porcelain", "--untracked-files=no"
            )
            self.assertEqual("", porcelain)
            self.assertEqual("promoted", promoted.attempt["verified_status"])

    def test_verify_treats_squash_equivalent_promotion_as_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            original_branch = _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD")
            base_oid = _git_stdout(repo_root, "rev-parse", "--verify", "HEAD")

            intent = create_intent(repo_root, title="Squash", description=None, kind="chore")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "squash_a.py").write_text("a = 1\n", encoding="utf-8")
            _git(worktree, "add", "squash_a.py")
            create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="attempt commit 1",
            )
            (worktree / "squash_b.py").write_text("b = 2\n", encoding="utf-8")
            _git(worktree, "add", "squash_b.py")
            create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="attempt commit 2",
            )

            _git(repo_root, "checkout", "-b", "squashed", base_oid)
            (repo_root / "squash_a.py").write_text("a = 1\n", encoding="utf-8")
            (repo_root / "squash_b.py").write_text("b = 2\n", encoding="utf-8")
            _git(repo_root, "add", "squash_a.py", "squash_b.py")
            _git(repo_root, "commit", "-m", "squashed equivalent")
            _git(repo_root, "checkout", original_branch)

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                    result_promotion_ref="refs/heads/squashed",
                )
            finally:
                conn.close()

            verified = verify_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual("promoted", verified.attempt["verified_status"])

    def test_verify_treats_cherry_pick_conflict_resolution_as_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            original_branch = _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD")
            base_oid = _git_stdout(repo_root, "rev-parse", "--verify", "HEAD")

            intent = create_intent(repo_root, title="Cherry", description=None, kind="chore")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "README.md").write_text("attempt version\n", encoding="utf-8")
            _git(worktree, "add", "README.md")
            create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="attempt conflict resolution",
            )

            _git(repo_root, "checkout", "-b", "cherry-resolved", base_oid)
            (repo_root / "README.md").write_text("target version\n", encoding="utf-8")
            _git(repo_root, "add", "README.md")
            _git(repo_root, "commit", "-m", "target conflict")
            (repo_root / "README.md").write_text("attempt version\n", encoding="utf-8")
            _git(repo_root, "add", "README.md")
            _git(repo_root, "commit", "-m", "manual conflict resolution")
            _git(repo_root, "checkout", original_branch)

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                    result_promotion_ref="refs/heads/cherry-resolved",
                )
            finally:
                conn.close()

            verified = verify_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual("promoted", verified.attempt["verified_status"])

    def test_promote_to_head_branch_refuses_when_main_working_tree_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            head_branch = _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD")

            intent = create_intent(repo_root, title="Dirty", description=None, kind="chore")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "dirty.py").write_text("x = 1\n", encoding="utf-8")
            _git(worktree, "add", "dirty.py")
            create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="dirty",
            )
            # Dirty the main working tree (modify an already-tracked file).
            (repo_root / "README.md").write_text("changed\n", encoding="utf-8")

            with self.assertRaises(RuntimeError) as raised:
                promote_attempt(
                    repo_root,
                    attempt_id=attempt.attempt_id,
                    target_ref=head_branch,
                )

            self.assertIn("uncommitted", str(raised.exception))
            self.assertIn("Commit or stash", str(raised.exception))
            self.assertIn("not currently checked out", str(raised.exception))

    def test_cli_promote_dirty_head_branch_reports_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            head_branch = _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD")

            intent = create_intent(repo_root, title="CLI dirty", description=None, kind="chore")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "cli_dirty.py").write_text("x = 1\n", encoding="utf-8")
            _git(worktree, "add", "cli_dirty.py")
            create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="cli dirty",
            )
            (repo_root / "README.md").write_text("changed\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ait.cli",
                    "attempt",
                    "promote",
                    attempt.attempt_id,
                    "--to",
                    head_branch,
                ],
                cwd=repo_root,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
                capture_output=True,
                text=True,
            )

            self.assertEqual(2, completed.returncode)
            self.assertEqual("", completed.stdout)
            self.assertIn("error: refusing to promote", completed.stderr)
            self.assertIn("Commit or stash", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)

    def test_rebase_attempt_onto_advanced_head_branch_before_promote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            head_branch = _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD")

            intent = create_intent(repo_root, title="Drift", description=None, kind="chore")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            original_base_oid = attempt.base_ref_oid
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "feature.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "feature.py")
            create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="feature",
            )

            (repo_root / "main.py").write_text("main = True\n", encoding="utf-8")
            _git(repo_root, "add", "main.py")
            _git(repo_root, "commit", "-m", "advance main")
            advanced_main_oid = _git_stdout(repo_root, "rev-parse", "--verify", "HEAD")

            with self.assertRaises(RuntimeError) as raised:
                promote_attempt(
                    repo_root,
                    attempt_id=attempt.attempt_id,
                    target_ref=head_branch,
                )
            self.assertIn("Rebase the attempt worktree", str(raised.exception))

            rebased = rebase_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                onto_ref=head_branch,
            )
            promoted = promote_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                target_ref=head_branch,
            )

            self.assertEqual(advanced_main_oid, rebased.attempt["base_ref_oid"])
            self.assertNotEqual(original_base_oid, rebased.attempt["base_ref_oid"])
            self.assertEqual(("feature.py",), rebased.files["changed"])
            self.assertEqual(1, len(rebased.commits))
            self.assertTrue((repo_root / "main.py").exists())
            self.assertTrue((repo_root / "feature.py").exists())
            self.assertEqual("promoted", promoted.attempt["verified_status"])

    def test_rebase_attempt_refuses_dirty_attempt_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            head_branch = _git_stdout(repo_root, "symbolic-ref", "--short", "HEAD")

            intent = create_intent(repo_root, title="Dirty rebase", description=None, kind="chore")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            (worktree / "README.md").write_text("dirty\n", encoding="utf-8")

            with self.assertRaises(RuntimeError) as raised:
                rebase_attempt(
                    repo_root,
                    attempt_id=attempt.attempt_id,
                    onto_ref=head_branch,
                )

            self.assertIn("uncommitted tracked changes", str(raised.exception))
            self.assertIn("Commit or stash", str(raised.exception))

    def test_superseded_intent_rejects_new_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            original = create_intent(repo_root, title="Original", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")
            supersede_intent(
                repo_root,
                intent_id=original.intent_id,
                by_intent_id=replacement.intent_id,
            )

            with self.assertRaises(ValueError) as raised:
                create_attempt(repo_root, intent_id=original.intent_id)

            self.assertIn("superseded", str(raised.exception))

    def test_superseded_intent_rejects_commit_for_existing_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            original = create_intent(repo_root, title="Original", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=original.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "edge.py").write_text("x = 1\n", encoding="utf-8")
            _git(worktree, "add", "edge.py")
            supersede_intent(
                repo_root,
                intent_id=original.intent_id,
                by_intent_id=replacement.intent_id,
            )

            with self.assertRaises(ValueError) as raised:
                create_commit_for_attempt(
                    repo_root,
                    attempt_id=attempt.attempt_id,
                    message="edge",
                )

            self.assertIn("superseded", str(raised.exception))

    def test_superseded_intent_rejects_promotion_for_existing_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            original = create_intent(repo_root, title="Original", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=original.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "drop.py").write_text("x = 1\n", encoding="utf-8")
            _git(worktree, "add", "drop.py")
            _git(worktree, "commit", "-m", "drop")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                )
            finally:
                conn.close()
            supersede_intent(
                repo_root,
                intent_id=original.intent_id,
                by_intent_id=replacement.intent_id,
            )

            with self.assertRaises(ValueError) as raised:
                promote_attempt(
                    repo_root,
                    attempt_id=attempt.attempt_id,
                    target_ref="fix/drop",
                )

            self.assertIn("superseded", str(raised.exception))

    def test_abandoned_intent_rejects_promoted_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Abandoned", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "reject.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "reject.py")
            _git(worktree, "commit", "-m", "reject")
            abandon_intent(repo_root, intent_id=intent.intent_id)

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                    result_promotion_ref="refs/heads/fix/reject",
                )
            finally:
                conn.close()

            verified = verify_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual("failed", verified.attempt["verified_status"])

    def test_terminal_finished_intent_rejects_abandon_and_supersede(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            finished = create_intent(repo_root, title="Finished", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                from ait.db import update_intent_status

                update_intent_status(conn, finished.intent_id, "finished")
            finally:
                conn.close()

            with self.assertRaises(ValueError) as abandon_error:
                abandon_intent(repo_root, intent_id=finished.intent_id)
            with self.assertRaises(ValueError) as supersede_error:
                supersede_intent(
                    repo_root,
                    intent_id=finished.intent_id,
                    by_intent_id=replacement.intent_id,
                )

            self.assertIn("finished", str(abandon_error.exception))
            self.assertIn("finished", str(supersede_error.exception))


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


def _commit_ait_gitignore_if_needed(repo_root: Path) -> None:
    if (repo_root / ".gitignore").exists() and _git_stdout(repo_root, "status", "--short", ".gitignore"):
        _git(repo_root, "add", ".gitignore")
        _git(repo_root, "commit", "-m", "ignore ait state")


if __name__ == "__main__":
    unittest.main()
