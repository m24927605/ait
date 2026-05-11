from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ait.app import init_repo
from ait.db import (
    NewAttempt,
    NewIntent,
    connect_db,
    insert_attempt,
    insert_attempt_commit,
    insert_intent,
    run_migrations,
)
from ait.review import create_command_reviewer_review


class ReviewAdapterConfigTests(unittest.TestCase):
    def test_policy_adapter_command_runs_with_configured_cwd_and_env(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        script = repo_root / "reviewer.py"
        script.write_text(
            "import json, os, pathlib, sys\n"
            "sys.stdin.read()\n"
            "print(json.dumps({"
            "'summary': 'adapter ok ' + os.environ.get('AIT_TEST_ALLOWED', ''),"
            "'findings': []"
            "}))\n",
            encoding="utf-8",
        )
        _write_review_adapter_config(
            repo_root,
            command=f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
            cwd=".ait/custom-reviewer-cwd",
            env_allowlist=["AIT_TEST_ALLOWED"],
        )

        import os

        previous = os.environ.get("AIT_TEST_ALLOWED")
        os.environ["AIT_TEST_ALLOWED"] = "yes"
        try:
            result = create_command_reviewer_review(
                repo_root,
                "latest-reviewable",
                reviewer_adapter="default",
            )
        finally:
            if previous is None:
                os.environ.pop("AIT_TEST_ALLOWED", None)
            else:
                os.environ["AIT_TEST_ALLOWED"] = previous

        artifact = json.loads((repo_root / result.review.artifact_ref).read_text(encoding="utf-8"))
        self.assertEqual("passed", result.review.status)
        self.assertIn("adapter ok yes", artifact["adapter_invocation"]["stdout"])
        self.assertTrue(artifact["adapter_invocation"]["cwd"].endswith(".ait/custom-reviewer-cwd"))

    def test_claude_code_reviewer_uses_local_cli_without_anthropic_api_key(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        bin_dir = repo_root / "bin"
        bin_dir.mkdir()
        claude = bin_dir / "claude"
        claude.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "brief = sys.stdin.read()\n"
            "print(json.dumps({"
            "'summary': "
            "'claude local api_key=' + str('ANTHROPIC_API_KEY' in os.environ).lower()"
            " + ' args=' + ' '.join(sys.argv[1:])"
            " + ' brief=' + str(bool(brief)).lower(),"
            "'findings': []"
            "}))\n",
            encoding="utf-8",
        )
        claude.chmod(0o755)
        env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "ANTHROPIC_API_KEY": "should-not-reach-claude",
        }

        with patch.dict(os.environ, env, clear=False):
            result = create_command_reviewer_review(
                repo_root,
                "latest-reviewable",
                reviewer_adapter="claude-code",
            )

        artifact = json.loads((repo_root / result.review.artifact_ref).read_text(encoding="utf-8"))
        stdout = artifact["adapter_invocation"]["stdout"]
        self.assertEqual("passed", result.review.status)
        self.assertEqual(["claude", "-p"], artifact["adapter_invocation"]["command"])
        self.assertIn("claude local api_key=false", stdout)
        self.assertIn("args=-p", stdout)
        self.assertIn("brief=true", stdout)

    def test_policy_adapter_timeout_fails_closed(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        script = repo_root / "slow_reviewer.py"
        script.write_text("import time\ntime.sleep(2)\n", encoding="utf-8")
        _write_review_adapter_config(
            repo_root,
            command=f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
            timeout_seconds=1,
        )

        result = create_command_reviewer_review(
            repo_root,
            "latest-reviewable",
            reviewer_adapter="default",
        )

        self.assertEqual("failed", result.review.status)
        self.assertIn("timed out", result.error or "")


def _write_review_adapter_config(
    repo_root: Path,
    *,
    command: str,
    timeout_seconds: int = 300,
    cwd: str = ".ait/reviewer-runs",
    env_allowlist: list[str] | None = None,
) -> None:
    config_path = repo_root / ".ait" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["review"] = {
        "adapters": {
            "default": {
                "command": command,
                "timeout_seconds": timeout_seconds,
                "cwd": cwd,
                "env_allowlist": env_allowlist or [],
            }
        }
    }
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def _repo_with_reviewable_attempt() -> Path:
    tmp = tempfile.TemporaryDirectory()
    repo_root = Path(tmp.name)
    _TEMP_DIRS.append(tmp)
    _git(repo_root, "init")
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        run_migrations(conn)
        insert_intent(
            conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Review adapter",
                created_at="2026-05-09T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
        insert_attempt(
            conn,
            NewAttempt(
                id="repo:01ATTEMPT",
                intent_id="repo:01INTENT",
                agent_id="codex:main",
                workspace_ref="/tmp/repo:01ATTEMPT",
                base_ref_oid="0" * 40,
                started_at="2026-05-09T00:01:00Z",
                ownership_token="token",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )
        insert_attempt_commit(
            conn,
            attempt_id="repo:01ATTEMPT",
            commit_oid="1" * 40,
            base_commit_oid="0" * 40,
            touched_files=("src/example.py",),
        )
    finally:
        conn.close()
    return repo_root


def _git(repo_root: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
