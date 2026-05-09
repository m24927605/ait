from __future__ import annotations

import io
import json
import subprocess
import unittest
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import init_repo
from ait.db import connect_db, insert_attempt, insert_attempt_commit, insert_intent
from ait.db import list_attempt_reviews
from ait.db.records import NewAttempt, NewIntent
from ait.review import NoReviewableAttemptError, resolve_review_target


class CliReviewTests(unittest.TestCase):
    def test_parser_accepts_review_attempt_json(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            ["review", "attempt", "latest-reviewable", "--format", "json"]
        )

        self.assertEqual("review", args.command)
        self.assertEqual("attempt", args.review_command)
        self.assertEqual("latest-reviewable", args.selector)
        self.assertEqual("json", args.format)

    def test_parser_accepts_review_attempt_text(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            ["review", "attempt", "latest-reviewable", "--format", "text"]
        )

        self.assertEqual("review", args.command)
        self.assertEqual("attempt", args.review_command)
        self.assertEqual("latest-reviewable", args.selector)
        self.assertEqual("text", args.format)

    def test_parser_rejects_invalid_review_format(self) -> None:
        parser = cli.build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(
                ["review", "attempt", "latest-reviewable", "--format", "xml"]
            )

    def test_parser_rejects_ambiguous_review_latest(self) -> None:
        parser = cli.build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["review", "latest"])

    def test_review_attempt_json_outputs_phase1_contract(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        stdout = io.StringIO()

        with (
            _chdir(repo_root),
            patch(
                "sys.argv",
                ["ait", "review", "attempt", "latest-reviewable", "--format", "json"],
            ),
            redirect_stdout(stdout),
        ):
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(
            {
                "schema_version",
                "review_id",
                "target_attempt_id",
                "selector",
                "verified_status",
                "reported_status",
                "workspace_ref",
                "base_ref_oid",
                "base_ref_name",
                "changed_files",
                "risk_level",
                "risk_score",
                "risk_reasons",
                "review_required",
                "suggested_mode",
                "artifact_ref",
            },
            set(payload),
        )
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual("latest-reviewable", payload["selector"])
        self.assertEqual("repo:01ATTEMPT1", payload["target_attempt_id"])
        self.assertEqual("succeeded", payload["verified_status"])
        self.assertEqual("finished", payload["reported_status"])
        self.assertEqual(["src/example.py"], payload["changed_files"])
        self.assertEqual("medium", payload["risk_level"])
        self.assertEqual(20, payload["risk_score"])
        self.assertEqual(
            [
                {
                    "code": "missing_test_evidence",
                    "message": "attempt changed files but no test evidence was observed",
                    "paths": [],
                }
            ],
            payload["risk_reasons"],
        )
        self.assertFalse(payload["review_required"])
        self.assertEqual("light", payload["suggested_mode"])
        self.assertTrue(payload["review_id"].startswith("review:"))
        self.assertTrue(payload["artifact_ref"].startswith(".ait/reviews/"))
        self.assertTrue((repo_root / payload["artifact_ref"]).exists())

        conn = connect_db(repo_root / ".ait" / "state.sqlite3")
        try:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT1")
        finally:
            conn.close()
        self.assertEqual(1, len(reviews))
        self.assertEqual(payload["review_id"], reviews[0].id)
        self.assertIsNotNone(reviews[0].baseline_ref)
        assert reviews[0].baseline_ref is not None
        self.assertTrue((repo_root / reviews[0].baseline_ref).exists())

    def test_review_attempt_text_outputs_target_and_placeholder_risk(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        stdout = io.StringIO()

        with (
            _chdir(repo_root),
            patch("sys.argv", ["ait", "review", "attempt", "latest-reviewable"]),
            redirect_stdout(stdout),
        ):
            exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertIn("Review target: repo:01ATTEMPT1", stdout.getvalue())
        self.assertIn("Review: review:", stdout.getvalue())
        self.assertIn("Risk: medium (20)", stdout.getvalue())
        self.assertIn("Suggested mode: light", stdout.getvalue())

    def test_latest_reviewable_selects_newest_succeeded_changed_attempt(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        conn = connect_db(repo_root / ".ait" / "state.sqlite3")
        try:
            _insert_attempt(
                conn,
                "repo:01ATTEMPT2",
                started_at="2026-04-23T00:02:00Z",
                reported_status="finished",
                verified_status="succeeded",
                touched_files=("src/newer.py",),
            )

            target = resolve_review_target(conn, "latest-reviewable")
        finally:
            conn.close()

        self.assertEqual("repo:01ATTEMPT2", target.attempt_id)
        self.assertEqual(("src/newer.py",), target.changed_files)

    def test_latest_reviewable_skips_failed_promoted_and_noop_attempts(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        conn = connect_db(repo_root / ".ait" / "state.sqlite3")
        try:
            _insert_attempt(
                conn,
                "repo:01FAILED",
                started_at="2026-04-23T00:02:00Z",
                reported_status="finished",
                verified_status="failed",
                touched_files=("src/failed.py",),
            )
            _insert_attempt(
                conn,
                "repo:01PROMOTED",
                started_at="2026-04-23T00:03:00Z",
                reported_status="finished",
                verified_status="promoted",
                touched_files=("src/promoted.py",),
            )
            _insert_attempt(
                conn,
                "repo:01NOOP",
                started_at="2026-04-23T00:04:00Z",
                reported_status="finished",
                verified_status="succeeded",
                touched_files=(),
            )

            target = resolve_review_target(conn, "latest-reviewable")
        finally:
            conn.close()

        self.assertEqual("repo:01ATTEMPT1", target.attempt_id)

    def test_latest_reviewable_raises_when_no_attempt_matches(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        conn = connect_db(repo_root / ".ait" / "state.sqlite3")
        try:
            conn.execute("DELETE FROM attempt_commits")
            conn.commit()

            with self.assertRaises(NoReviewableAttemptError):
                resolve_review_target(conn, "latest-reviewable")
        finally:
            conn.close()

    def test_explicit_attempt_selector_resolves_reviewable_attempt(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        conn = connect_db(repo_root / ".ait" / "state.sqlite3")
        try:
            target = resolve_review_target(conn, "01ATTEMPT1")
        finally:
            conn.close()

        self.assertEqual("repo:01ATTEMPT1", target.attempt_id)
        self.assertEqual(("src/example.py",), target.changed_files)

    def test_review_attempt_no_reviewable_cli_returns_actionable_error(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        conn = connect_db(repo_root / ".ait" / "state.sqlite3")
        try:
            conn.execute("DELETE FROM attempt_commits")
            conn.commit()
        finally:
            conn.close()
        stderr = io.StringIO()

        with (
            _chdir(repo_root),
            patch("sys.argv", ["ait", "review", "attempt", "latest-reviewable"]),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main()

        self.assertEqual(1, exit_code)
        self.assertIn("No reviewable attempt found.", stderr.getvalue())
        self.assertIn("ait attempt list --verified-status succeeded", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()


class _chdir:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._previous: Path | None = None

    def __enter__(self) -> None:
        import os

        self._previous = Path.cwd()
        os.chdir(self._path)

    def __exit__(self, exc_type, exc, tb) -> bool:
        import os

        assert self._previous is not None
        os.chdir(self._previous)
        return False


def _repo_with_reviewable_attempt() -> Path:
    tmp = tempfile.TemporaryDirectory()
    repo_root = Path(tmp.name)
    # Keep the temporary directory alive for the duration of the process. The
    # unittest process is short-lived, and this avoids plumbing cleanup state
    # through every test helper.
    _TEMP_DIRS.append(tmp)
    _git(repo_root, "init")
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        insert_intent(
            conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Review target",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
        _insert_attempt(
            conn,
            "repo:01ATTEMPT1",
            started_at="2026-04-23T00:01:00Z",
            reported_status="finished",
            verified_status="succeeded",
            touched_files=("src/example.py",),
        )
    finally:
        conn.close()
    return repo_root


def _insert_attempt(
    conn,
    attempt_id: str,
    *,
    started_at: str,
    reported_status: str,
    verified_status: str,
    touched_files: tuple[str, ...],
) -> None:
    insert_attempt(
        conn,
        NewAttempt(
            id=attempt_id,
            intent_id="repo:01INTENT",
            agent_id="codex:main",
            workspace_ref=f"/tmp/{attempt_id}",
            base_ref_oid="0" * 40,
            started_at=started_at,
            ownership_token=f"token-{attempt_id}",
            reported_status=reported_status,
            verified_status=verified_status,
        ),
    )
    if touched_files:
        insert_attempt_commit(
            conn,
            attempt_id=attempt_id,
            commit_oid=f"{attempt_id}:commit",
            base_commit_oid="0" * 40,
            touched_files=touched_files,
        )


def _git(repo_root: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []
