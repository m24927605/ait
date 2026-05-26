from __future__ import annotations

import json
import os
import shutil
import shlex
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
from support import init_git_repo


class ReviewAdapterConfigTests(unittest.TestCase):
    def test_local_reviewer_does_not_inherit_secret_env_by_default(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        script = repo_root / "reviewer_env.py"
        script.write_text(
            "import json, os, sys\n"
            "sys.stdin.read()\n"
            "print(json.dumps({"
            "'summary': 'secret=' + str('SECRET_TOKEN' in os.environ).lower(),"
            "'findings': [],"
            "'env': {'SECRET_TOKEN': 'SECRET_TOKEN' in os.environ}"
            "}))\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"SECRET_TOKEN": "fixture-secret"}, clear=False):
            result = create_command_reviewer_review(
                repo_root,
                "latest-reviewable",
                reviewer_adapter=f"command:{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
            )

        artifact = json.loads((repo_root / result.review.artifact_ref).read_text(encoding="utf-8"))
        stdout = json.loads(artifact["adapter_invocation"]["stdout"])
        self.assertEqual("passed", result.review.status)
        self.assertFalse(stdout["env"]["SECRET_TOKEN"])

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

    def test_policy_allowlist_can_pass_specific_safe_var(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        script = repo_root / "reviewer_allowlist.py"
        script.write_text(
            "import json, os, sys\n"
            "sys.stdin.read()\n"
            "print(json.dumps({"
            "'summary': 'safe=' + os.environ.get('AIT_REVIEW_SAFE', ''),"
            "'findings': [],"
            "'env': {"
            "'AIT_REVIEW_SAFE': os.environ.get('AIT_REVIEW_SAFE'),"
            "'SECRET_TOKEN': 'SECRET_TOKEN' in os.environ"
            "}"
            "}))\n",
            encoding="utf-8",
        )
        _write_review_adapter_config(
            repo_root,
            command=f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
            env_allowlist=["AIT_REVIEW_SAFE"],
        )

        with patch.dict(
            os.environ,
            {"AIT_REVIEW_SAFE": "allowed", "SECRET_TOKEN": "fixture-secret"},
            clear=False,
        ):
            result = create_command_reviewer_review(
                repo_root,
                "latest-reviewable",
                reviewer_adapter="default",
            )

        artifact = json.loads((repo_root / result.review.artifact_ref).read_text(encoding="utf-8"))
        stdout = json.loads(artifact["adapter_invocation"]["stdout"])
        self.assertEqual("passed", result.review.status)
        self.assertEqual("allowed", stdout["env"]["AIT_REVIEW_SAFE"])
        self.assertFalse(stdout["env"]["SECRET_TOKEN"])

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
        self.assertEqual({"ANTHROPIC_API_KEY": False}, artifact["adapter_invocation"]["blocked_env"])
        self.assertEqual(str(claude), artifact["adapter_invocation"]["resolved_binary_path"])
        self.assertIsNone(artifact["adapter_invocation"]["timeout_seconds"])

    def test_claude_reviewer_blocks_anthropic_key(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        bin_dir = repo_root / "bin"
        bin_dir.mkdir()
        claude = bin_dir / "claude"
        claude.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "sys.stdin.read()\n"
            "print(json.dumps({"
            "'summary': 'anthropic=' + str('ANTHROPIC_API_KEY' in os.environ).lower(),"
            "'findings': [],"
            "'env': {'ANTHROPIC_API_KEY': 'ANTHROPIC_API_KEY' in os.environ}"
            "}))\n",
            encoding="utf-8",
        )
        claude.chmod(0o755)

        with patch.dict(
            os.environ,
            {
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                "ANTHROPIC_API_KEY": "fixture-key",
            },
            clear=False,
        ):
            result = create_command_reviewer_review(
                repo_root,
                "latest-reviewable",
                reviewer_adapter="claude-code",
            )

        artifact = json.loads((repo_root / result.review.artifact_ref).read_text(encoding="utf-8"))
        stdout = json.loads(artifact["adapter_invocation"]["stdout"])
        self.assertEqual("passed", result.review.status)
        self.assertFalse(stdout["env"]["ANTHROPIC_API_KEY"])
        self.assertEqual({"ANTHROPIC_API_KEY": False}, artifact["adapter_invocation"]["blocked_env"])

    def test_codex_reviewer_uses_minimal_env(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        bin_dir = repo_root / "bin"
        bin_dir.mkdir()
        fake_codex = bin_dir / "codex"
        fake_codex.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "sys.stdin.read()\n"
            "print(json.dumps({"
            "'summary': 'codex env',"
            "'findings': [],"
            "'env_keys': sorted(os.environ),"
            "'has_openai': 'OPENAI_API_KEY' in os.environ,"
            "'has_secret': 'SECRET_TOKEN' in os.environ"
            "}))\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        home = repo_root / "home"
        home.mkdir()

        with patch.dict(
            os.environ,
            {
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                "HOME": str(home),
                "OPENAI_API_KEY": "fixture-openai-key",
                "SECRET_TOKEN": "fixture-secret",
                "AIT_REVIEW_UNLISTED": "not-passed",
            },
            clear=False,
        ):
            result = create_command_reviewer_review(
                repo_root,
                "latest-reviewable",
                reviewer_adapter="codex",
            )

        artifact = json.loads((repo_root / result.review.artifact_ref).read_text(encoding="utf-8"))
        stdout = json.loads(artifact["adapter_invocation"]["stdout"])
        allowed_keys = {
            "PATH",
            "HOME",
            "TMPDIR",
            "TEMP",
            "TMP",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "LC_MESSAGES",
        }
        self.assertEqual("passed", result.review.status)
        self.assertEqual(["codex", "exec", "--sandbox", "read-only", "-"], artifact["adapter_invocation"]["command"])
        env_keys = set(stdout["env_keys"]) - {"__CF_USER_TEXT_ENCODING"}
        self.assertTrue(env_keys.issubset(allowed_keys))
        self.assertIn("PATH", stdout["env_keys"])
        self.assertIn("HOME", stdout["env_keys"])
        self.assertNotIn("AIT_REVIEW_UNLISTED", stdout["env_keys"])
        self.assertFalse(stdout["has_openai"])
        self.assertFalse(stdout["has_secret"])
        self.assertEqual({"OPENAI_API_KEY": False}, artifact["adapter_invocation"]["blocked_env"])

    def test_claude_code_reviewer_ignores_policy_command_override(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        bin_dir = repo_root / "bin"
        bin_dir.mkdir()
        claude = bin_dir / "claude"
        claude.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "sys.stdin.read()\n"
            "print(json.dumps({'summary': 'local cli', 'findings': []}))\n",
            encoding="utf-8",
        )
        claude.chmod(0o755)
        override = repo_root / "override.py"
        override.write_text("raise SystemExit(99)\n", encoding="utf-8")
        _write_named_review_adapter_config(
            repo_root,
            name="claude-code",
            command=f"{shlex.quote(sys.executable)} {shlex.quote(str(override))}",
        )

        with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}, clear=False):
            result = create_command_reviewer_review(
                repo_root,
                "latest-reviewable",
                reviewer_adapter="claude-code",
            )

        artifact = json.loads((repo_root / result.review.artifact_ref).read_text(encoding="utf-8"))
        self.assertEqual("passed", result.review.status)
        self.assertEqual(["claude", "-p"], artifact["adapter_invocation"]["command"])
        self.assertIn("local cli", artifact["adapter_invocation"]["stdout"])

    def test_policy_adapter_timeout_fails_closed(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        script = repo_root / "slow_reviewer.py"
        script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        _write_review_adapter_config(
            repo_root,
            command=f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
            timeout_seconds=0.05,
        )

        result = create_command_reviewer_review(
            repo_root,
            "latest-reviewable",
            reviewer_adapter="default",
        )

        self.assertEqual("failed", result.review.status)
        self.assertIn("timed out", result.error or "")

    def test_missing_auth_fails_closed_with_actionable_error(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        git_only_bin = repo_root / "git-only-bin"
        git_only_bin.mkdir()
        git_path = shutil.which("git")
        assert git_path is not None
        os.symlink(git_path, git_only_bin / "git")

        with patch.dict(
            os.environ,
            {
                "PATH": str(git_only_bin),
                "OPENAI_API_KEY": "fixture-openai-key",
            },
            clear=False,
        ):
            result = create_command_reviewer_review(
                repo_root,
                "latest-reviewable",
                reviewer_adapter="codex",
            )

        self.assertEqual("failed", result.review.status)
        self.assertTrue(result.review.blocking)
        self.assertIn("does not fall back to provider API keys", result.error or "")
        self.assertIn("review.adapters.codex.env_allowlist", result.error or "")


def _write_review_adapter_config(
    repo_root: Path,
    *,
    command: str,
    timeout_seconds: int | float = 300,
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


def _write_named_review_adapter_config(
    repo_root: Path,
    *,
    name: str,
    command: str,
) -> None:
    config_path = repo_root / ".ait" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["review"] = {
        "adapters": {
            name: {
                "command": command,
                "timeout_seconds": 300,
                "cwd": ".ait/custom-reviewer-cwd",
                "env_allowlist": [],
            }
        }
    }
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def _repo_with_reviewable_attempt() -> Path:
    tmp = tempfile.TemporaryDirectory()
    repo_root = Path(tmp.name)
    _TEMP_DIRS.append(tmp)
    init_git_repo(repo_root)
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


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
