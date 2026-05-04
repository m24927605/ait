from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ait.cursor_capture import (
    parse_cursor_stream_json,
    persist_cursor_session,
)


SAMPLE_STREAM = "\n".join(
    [
        json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "cursor-fast"}),
        json.dumps({"type": "user", "message": "refactor billing retry"}),
        json.dumps({"type": "assistant", "content": "I'll switch to a "}),
        json.dumps({"type": "assistant", "content": "durable queue."}),
        json.dumps({
            "type": "tool_call",
            "subtype": "started",
            "name": "Edit",
            "input": {"file_path": "src/billing/retry.py"},
        }),
        json.dumps({
            "type": "tool_call",
            "subtype": "completed",
            "name": "Edit",
            "ok": True,
        }),
        json.dumps({"type": "assistant", "content": " Tests pass."}),
        json.dumps({"type": "result", "subtype": "success"}),
        "",
    ]
)


class ParseCursorStreamJsonTests(unittest.TestCase):
    def test_parse_yields_meta_user_assistant_tool_in_order(self) -> None:
        events = list(parse_cursor_stream_json(SAMPLE_STREAM))
        roles = [e["role"] for e in events]

        self.assertEqual(
            [
                "meta",
                "user",
                "assistant",
                "tool_use",
                "tool_result",
                "assistant",
                "meta",
            ],
            roles,
        )
        self.assertIn("system:init", events[0]["text"])
        self.assertIn("session_id=s1", events[0]["text"])
        self.assertEqual("refactor billing retry", events[1]["text"])
        self.assertEqual("I'll switch to a durable queue.", events[2]["text"])
        self.assertEqual("Edit", events[3]["tool"])
        self.assertEqual(["src/billing/retry.py"], events[3]["files"])
        self.assertEqual("Edit", events[4]["tool"])
        self.assertTrue(events[4]["ok"])
        self.assertEqual("Tests pass.", events[5]["text"])
        self.assertIn("result:success", events[6]["text"])

    def test_parse_skips_invalid_lines(self) -> None:
        text = (
            "this is not json\n"
            + json.dumps({"type": "user", "message": "hi"})
            + "\n[1, 2]\n"
        )
        events = list(parse_cursor_stream_json(text))

        self.assertEqual(1, len(events))
        self.assertEqual("user", events[0]["role"])
        self.assertEqual("hi", events[0]["text"])

    def test_parse_handles_tool_call_with_is_error(self) -> None:
        text = "\n".join(
            [
                json.dumps({"type": "tool_call", "subtype": "completed", "name": "Bash", "is_error": True}),
                "",
            ]
        )
        events = list(parse_cursor_stream_json(text))

        self.assertEqual(1, len(events))
        self.assertFalse(events[0]["ok"])

    def test_parse_empty_text_yields_nothing(self) -> None:
        self.assertEqual([], list(parse_cursor_stream_json("")))


class PersistCursorSessionTests(unittest.TestCase):
    def test_persist_writes_envelope_jsonl_under_ait_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            ref = persist_cursor_session(
                repo_root,
                attempt_id="attempt-aaa",
                stdout_text=SAMPLE_STREAM,
            )

            self.assertEqual(".ait/transcripts/attempt-aaa.jsonl", ref)
            dest = repo_root / ".ait" / "transcripts" / "attempt-aaa.jsonl"
            self.assertTrue(dest.exists())
            lines = [
                json.loads(line)
                for line in dest.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(7, len(lines))

    def test_persist_returns_none_when_stdout_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self.assertIsNone(
                persist_cursor_session(
                    repo_root,
                    attempt_id="attempt-bbb",
                    stdout_text="",
                )
            )
            self.assertFalse((repo_root / ".ait" / "transcripts").exists())

    def test_persist_returns_none_when_stream_has_no_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self.assertIsNone(
                persist_cursor_session(
                    repo_root,
                    attempt_id="attempt-ccc",
                    stdout_text="this is not json at all\n",
                )
            )


class CursorRunnerIntegrationTests(unittest.TestCase):
    def test_run_agent_command_persists_cursor_stream_json_into_transcripts(
        self,
    ) -> None:
        from ait.runner import run_agent_command

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(
                ["git", "init"], cwd=repo_root, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "t@t"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "t"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )

            program = (
                "import json, sys\n"
                "events = ["
                "{'type': 'user', 'message': 'fix retry'},"
                "{'type': 'assistant', 'content': 'switching to durable queue'},"
                "{'type': 'result', 'subtype': 'success'},"
                "]\n"
                "for e in events:\n"
                "    sys.stdout.write(json.dumps(e) + '\\n')\n"
            )

            result = run_agent_command(
                repo_root,
                intent_title="cursor session",
                adapter_name="cursor",
                command=[sys.executable, "-c", program],
                with_context=False,
            )

            attempt_id = result.attempt_id
            transcript = repo_root / ".ait" / "transcripts" / f"{attempt_id}.jsonl"
            self.assertTrue(transcript.exists(), f"expected {transcript}")
            self.assertEqual(
                f".ait/transcripts/{attempt_id}.jsonl",
                result.attempt.attempt["raw_trace_ref"],
            )
            events = [
                json.loads(line)
                for line in transcript.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            roles = [e["role"] for e in events]
            self.assertIn("user", roles)
            self.assertIn("assistant", roles)


if __name__ == "__main__":
    unittest.main()
