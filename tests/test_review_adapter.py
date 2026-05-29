from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.review_adapter import (
    ReviewAdapterError,
    _adapter_env,
    _cleanup_snapshot,
    _materialize_snapshot,
    _write_full_diff,
    run_review_adapter,
)


def _init_repo_with_two_commits(repo: Path) -> tuple[str, str]:
    """Initialize a git repo at `repo` and return (base_oid, head_oid)."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "untouched.py").write_text("def existing():\n    return 1\n", encoding="utf-8")
    (repo / "changed.py").write_text("def f():\n    return 'old'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    base_oid = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    (repo / "changed.py").write_text("def f():\n    return 'new'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "head"], cwd=repo, check=True)
    head_oid = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    return base_oid, head_oid


class SnapshotMaterializationTests(unittest.TestCase):
    def test_materialize_creates_worktree_at_head_oid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _, head_oid = _init_repo_with_two_commits(repo)
            snapshot = repo / ".ait" / "reviewer-runs" / "r1" / "src"
            try:
                _materialize_snapshot(repo, snapshot, head_oid)
                self.assertTrue((snapshot / "changed.py").exists())
                # Unchanged file present at the snapshot commit too
                self.assertTrue((snapshot / "untouched.py").exists())
                # Snapshot is a real git worktree → can git diff inside it
                r = subprocess.run(
                    ["git", "log", "-1", "--format=%H"],
                    cwd=snapshot, capture_output=True, text=True, check=True,
                )
                self.assertEqual(head_oid, r.stdout.strip())
            finally:
                _cleanup_snapshot(repo, snapshot)

    def test_materialize_empty_head_oid_is_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _init_repo_with_two_commits(repo)
            snapshot = repo / ".ait" / "reviewer-runs" / "r2" / "src"
            _materialize_snapshot(repo, snapshot, "")
            self.assertFalse(snapshot.exists())

    def test_cleanup_removes_worktree_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _, head_oid = _init_repo_with_two_commits(repo)
            snapshot = repo / ".ait" / "reviewer-runs" / "r3" / "src"
            _materialize_snapshot(repo, snapshot, head_oid)
            self.assertTrue(snapshot.exists())
            _cleanup_snapshot(repo, snapshot)
            self.assertFalse(snapshot.exists())
            # And `git worktree list` no longer lists it
            r = subprocess.run(
                ["git", "worktree", "list"],
                cwd=repo, capture_output=True, text=True, check=True,
            )
            self.assertNotIn(str(snapshot), r.stdout)

    def test_write_full_diff_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            base_oid, head_oid = _init_repo_with_two_commits(repo)
            cwd = repo / ".ait" / "reviewer-runs" / "r4"
            cwd.mkdir(parents=True)
            _write_full_diff(repo, cwd, base_oid, head_oid)
            patch_text = (cwd / "diff.patch").read_text(encoding="utf-8")
            # The diff includes the actual change and is NOT truncated.
            self.assertIn("-    return 'old'", patch_text)
            self.assertIn("+    return 'new'", patch_text)
            self.assertNotIn("[truncated]", patch_text)
            self.assertNotIn("truncated by budget", patch_text)

    def test_write_full_diff_with_empty_oids_emits_unavailable_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _init_repo_with_two_commits(repo)
            cwd = repo / ".ait" / "reviewer-runs" / "r5"
            cwd.mkdir(parents=True)
            _write_full_diff(repo, cwd, "", "")
            text = (cwd / "diff.patch").read_text(encoding="utf-8")
            self.assertIn("# diff unavailable", text)

    def test_run_review_adapter_cleans_up_snapshot_on_subprocess_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            base_oid, head_oid = _init_repo_with_two_commits(repo)
            # Force the adapter command to be one that doesn't exist on PATH so
            # subprocess.run raises OSError → ReviewAdapterError. The snapshot
            # must still be cleaned up.
            empty_bin = Path(tmp) / "bin_empty"
            empty_bin.mkdir()
            with patch.dict(os.environ, {"PATH": str(empty_bin)}, clear=True):
                with self.assertRaises(ReviewAdapterError):
                    run_review_adapter(
                        repo,
                        review_id="review:cleanup",
                        adapter="codex",
                        brief="b",
                        attempt_head_oid=head_oid,
                        baseline_ref_oid=base_oid,
                    )
            snapshot = repo / ".ait" / "reviewer-runs" / "review:cleanup" / "src"
            self.assertFalse(snapshot.exists())
            # And `git worktree list` shows no leftover
            r = subprocess.run(
                ["git", "worktree", "list"],
                cwd=repo, capture_output=True, text=True, check=True,
            )
            self.assertNotIn("/review:cleanup/src", r.stdout)


class ReviewAdapterEnvTests(unittest.TestCase):
    def test_default_adapter_env_filters_generic_secret_names(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin",
                "LANG": "C.UTF-8",
                "SECRET_TOKEN": "fixture-secret",
                "AWS_SECRET_ACCESS_KEY": "fixture-secret",
            },
            clear=True,
        ):
            env = _adapter_env(
                ("PATH", "LANG", "SECRET_TOKEN", "AWS_SECRET_ACCESS_KEY"),
                explicit_allowlist=(),
            )

        self.assertEqual({"PATH": "/usr/bin", "LANG": "C.UTF-8"}, env)

    def test_explicit_allowlist_can_pass_specific_var(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin",
                "AIT_REVIEW_SAFE": "allowed",
                "SECRET_TOKEN": "fixture-secret",
            },
            clear=True,
        ):
            env = _adapter_env(
                ("PATH",),
                explicit_allowlist=("AIT_REVIEW_SAFE", "SECRET_TOKEN"),
            )

        self.assertEqual(
            {
                "PATH": "/usr/bin",
                "AIT_REVIEW_SAFE": "allowed",
                "SECRET_TOKEN": "fixture-secret",
            },
            env,
        )

    def test_missing_local_cli_reports_no_api_key_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_bin = Path(tmp) / "bin"
            empty_bin.mkdir()
            with patch.dict(os.environ, {"PATH": str(empty_bin)}, clear=True):
                with self.assertRaises(ReviewAdapterError) as raised:
                    run_review_adapter(
                        Path(tmp),
                        review_id="review:test",
                        adapter="codex",
                        brief="review brief",
                        attempt_head_oid="",
                        baseline_ref_oid="",
                    )

        message = str(raised.exception)
        self.assertIn("does not fall back to provider API keys", message)
        self.assertIn("review.adapters.codex.env_allowlist", message)


if __name__ == "__main__":
    unittest.main()
