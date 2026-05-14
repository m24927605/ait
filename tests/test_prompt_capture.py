from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ait.db import connect_db, run_migrations
from ait.db.repositories import NewAttempt, NewIntent, insert_attempt, insert_intent
from ait.prompt_capture import record_command_prompt, record_payload_prompt


class PromptCaptureTests(unittest.TestCase):
    def test_command_prompt_marks_binary_only_interactive_prompt_as_not_observable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_prompt_db(repo_root, attempt_id="attempt:prompt")

            ref = record_command_prompt(
                repo_root,
                attempt_id="attempt:prompt",
                adapter_name="codex",
                command=("/opt/codex/bin/codex.js",),
            )

            self.assertEqual(".ait/prompts/attempt_prompt.txt", ref)
            text = (repo_root / str(ref)).read_text(encoding="utf-8")
            self.assertIn("# prompt-status: not-observable", text)
            self.assertIn("no user prompt was observable", text)
            self.assertIn("/opt/codex/bin/codex.js", text)

    def test_command_prompt_captures_agent_prompt_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_prompt_db(repo_root, attempt_id="attempt:prompt-args")

            ref = record_command_prompt(
                repo_root,
                attempt_id="attempt:prompt-args",
                adapter_name="codex",
                command=("/opt/codex/bin/codex", "Fix billing retry idempotency"),
            )

            self.assertEqual(".ait/prompts/attempt_prompt-args.txt", ref)
            text = (repo_root / str(ref)).read_text(encoding="utf-8")
            self.assertIn("# prompt-status: captured-from-command-args", text)
            self.assertIn("Fix billing retry idempotency", text)
            self.assertIn("agent positional argument", text)

    def test_payload_prompt_captures_hook_prompt_fields_and_updates_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_prompt_db(repo_root, attempt_id="attempt:payload")

            ref = record_payload_prompt(
                repo_root,
                attempt_id="attempt:payload",
                adapter_name="claude-code",
                event_name="SessionStart",
                payload={"prompt": "Review the auth middleware.", "session_id": "session-1"},
            )

            self.assertEqual(".ait/prompts/attempt_payload.txt", ref)
            text = (repo_root / str(ref)).read_text(encoding="utf-8")
            self.assertIn("# prompt-status: captured-from-hook-payload", text)
            self.assertIn("Review the auth middleware.", text)
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                stored = conn.execute(
                    "SELECT raw_prompt_ref FROM evidence_summaries WHERE attempt_id = ?",
                    ("attempt:payload",),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(ref, stored)


def _init_prompt_db(repo_root: Path, *, attempt_id: str) -> None:
    ait_dir = repo_root / ".ait"
    workspace = ait_dir / "workspaces" / attempt_id.replace(":", "_")
    workspace.mkdir(parents=True)
    conn = connect_db(ait_dir / "state.sqlite3")
    try:
        run_migrations(conn)
        insert_intent(
            conn,
            NewIntent(
                id="intent:prompt",
                repo_id="repo",
                title="Prompt capture",
                created_at="2026-05-14T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="test",
                trigger_source="test",
            ),
        )
        insert_attempt(
            conn,
            NewAttempt(
                id=attempt_id,
                intent_id="intent:prompt",
                agent_id="codex:test",
                workspace_ref=str(workspace),
                base_ref_oid="base",
                started_at="2026-05-14T00:00:00Z",
                ownership_token="token",
            ),
        )
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
