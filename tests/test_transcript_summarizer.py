from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.app import create_attempt, create_intent, init_repo
from ait.db import connect_db
from ait.memory import build_relevant_memory_recall
from ait.memory.notes import list_memory_notes
from ait.memory_policy import init_memory_policy
from ait.transcript_summarizer import (
    TranscriptEvent,
    heuristic_summary,
    parse_transcript,
    summarize_attempt_transcript,
    summarize_transcript_to_note,
)


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )


class ParseTranscriptTests(unittest.TestCase):
    def test_parses_common_envelope_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            _write_jsonl(
                path,
                [
                    {"role": "user", "text": "fix the auth bug"},
                    {"role": "assistant", "text": "looking now"},
                    {"role": "tool_use", "tool": "Edit", "files": ["src/auth.py"]},
                    {"role": "tool_result", "tool": "Edit", "ok": True},
                ],
            )

            events = list(parse_transcript(path))

            self.assertEqual(4, len(events))
            self.assertEqual("user", events[0].role)
            self.assertEqual("fix the auth bug", events[0].text)
            self.assertEqual("Edit", events[2].tool)
            self.assertEqual(("src/auth.py",), events[2].files)
            self.assertEqual(True, events[3].ok)

    def test_parses_claude_code_message_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            _write_jsonl(
                path,
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "refactor query parser"},
                    },
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "I will use a state machine"},
                                {
                                    "type": "tool_use",
                                    "name": "Edit",
                                    "input": {"file_path": "src/parser.py"},
                                },
                            ],
                        },
                    },
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "x",
                                    "is_error": True,
                                    "content": "ENOENT",
                                }
                            ],
                        },
                    },
                ],
            )

            events = list(parse_transcript(path))

            roles = [e.role for e in events]
            self.assertIn("user", roles)
            self.assertIn("assistant", roles)
            self.assertIn("tool_use", roles)
            self.assertIn("tool_result", roles)
            tool_use = next(e for e in events if e.role == "tool_use")
            self.assertEqual("Edit", tool_use.tool)
            self.assertEqual(("src/parser.py",), tool_use.files)
            tool_result = next(e for e in events if e.role == "tool_result")
            self.assertEqual(False, tool_result.ok)

    def test_skips_invalid_lines_and_returns_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(
                "this is not json\n"
                "\n"
                + json.dumps({"role": "assistant", "text": "ok"})
                + "\n"
                "[1, 2]\n",
                encoding="utf-8",
            )

            events = list(parse_transcript(path))

            self.assertEqual(1, len(events))
            self.assertEqual("ok", events[0].text)

    def test_missing_file_returns_no_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([], list(parse_transcript(Path(tmp) / "missing.jsonl")))


class HeuristicSummaryTests(unittest.TestCase):
    def test_summary_includes_user_intent_and_assistant_close(self) -> None:
        events = [
            TranscriptEvent(role="user", text="fix the auth retry"),
            TranscriptEvent(role="assistant", text="checked token expiry"),
            TranscriptEvent(role="assistant", text="patched the retry path"),
        ]

        summary = heuristic_summary(events)

        self.assertIn("User intent: fix the auth retry", summary)
        self.assertIn("Agent ended with: patched the retry path", summary)

    def test_summary_lists_structural_tools_and_files(self) -> None:
        events = [
            TranscriptEvent(role="tool_use", tool="Edit", files=("src/a.py",)),
            TranscriptEvent(role="tool_use", tool="Bash", files=()),
            TranscriptEvent(role="tool_use", tool="Grep", files=()),
        ]

        summary = heuristic_summary(events)

        self.assertIn("Structural tools: Bash, Edit (2 calls)", summary)
        self.assertIn("Files touched: src/a.py", summary)
        self.assertNotIn("Grep", summary)

    def test_summary_reports_failures(self) -> None:
        events = [
            TranscriptEvent(role="tool_use", tool="Bash"),
            TranscriptEvent(role="tool_result", ok=False),
            TranscriptEvent(role="tool_result", ok=False),
        ]

        summary = heuristic_summary(events)

        self.assertIn("Tool failures: 2", summary)

    def test_empty_events_produce_empty_summary(self) -> None:
        self.assertEqual("", heuristic_summary([]))

    def test_summary_is_truncated_to_max_chars(self) -> None:
        events = [TranscriptEvent(role="assistant", text="x" * 1000)]

        summary = heuristic_summary(events, max_chars=50)

        self.assertLessEqual(len(summary), 50)
        self.assertTrue(summary.endswith("…"))


class SummarizeToNoteTests(unittest.TestCase):
    def test_summarize_writes_memory_note_with_expected_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_repo(str(repo_root))
            transcript = repo_root / ".ait" / "transcripts" / "attempt-xyz.jsonl"
            transcript.parent.mkdir(parents=True, exist_ok=True)
            _write_jsonl(
                transcript,
                [
                    {"role": "user", "text": "make tests pass"},
                    {"role": "assistant", "text": "fixed the assertion"},
                    {"role": "tool_use", "tool": "Edit", "files": ["tests/foo.py"]},
                ],
            )

            note = summarize_transcript_to_note(
                repo_root,
                attempt_id="attempt-xyz",
                transcript_path=transcript,
                agent_id="claude-code:default",
            )

            self.assertIsNotNone(note)
            assert note is not None
            self.assertEqual("transcript-summary", note.topic)
            self.assertEqual(
                "transcript-summary:claude-code:default:attempt-xyz",
                note.source,
            )
            self.assertIn("make tests pass", note.body)
            stored = list_memory_notes(repo_root, topic="transcript-summary")
            self.assertEqual(1, len(stored))

    def test_summarize_returns_none_when_summary_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_repo(str(repo_root))
            transcript = repo_root / ".ait" / "transcripts" / "attempt-empty.jsonl"
            transcript.parent.mkdir(parents=True, exist_ok=True)
            transcript.write_text("", encoding="utf-8")

            note = summarize_transcript_to_note(
                repo_root,
                attempt_id="attempt-empty",
                transcript_path=transcript,
                agent_id="claude-code:default",
            )

            self.assertIsNone(note)


class SummarizeAttemptTranscriptTests(unittest.TestCase):
    def _setup_repo_with_attempt(
        self, repo_root: Path, *, raw_trace_ref: str | None
    ) -> str:
        _init_git_repo(repo_root)
        init_repo(str(repo_root))
        intent = create_intent(
            str(repo_root),
            title="dummy intent",
            description=None,
            kind="test",
        )
        attempt = create_attempt(
            str(repo_root),
            intent_id=intent.intent_id,
            agent_id="claude-code:default",
        )
        if raw_trace_ref is not None:
            db_path = repo_root / ".ait" / "state.sqlite3"
            conn = connect_db(db_path)
            try:
                conn.execute(
                    "UPDATE attempts SET raw_trace_ref = ? WHERE id = ?",
                    (raw_trace_ref, attempt.attempt_id),
                )
                conn.commit()
            finally:
                conn.close()
        return attempt.attempt_id

    def test_summarizes_attempt_with_internal_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            attempt_id = self._setup_repo_with_attempt(
                repo_root,
                raw_trace_ref=None,
            )
            transcript = (
                repo_root / ".ait" / "transcripts" / f"{attempt_id}.jsonl"
            )
            transcript.parent.mkdir(parents=True, exist_ok=True)
            _write_jsonl(
                transcript,
                [
                    {"role": "user", "text": "do thing"},
                    {"role": "assistant", "text": "did thing"},
                ],
            )
            db_path = repo_root / ".ait" / "state.sqlite3"
            conn = connect_db(db_path)
            try:
                conn.execute(
                    "UPDATE attempts SET raw_trace_ref = ? WHERE id = ?",
                    (f".ait/transcripts/{attempt_id}.jsonl", attempt_id),
                )
                conn.commit()
            finally:
                conn.close()

            note = summarize_attempt_transcript(repo_root, attempt_id)

            self.assertIsNotNone(note)
            assert note is not None
            self.assertIn("do thing", note.body)
            self.assertEqual(
                f"transcript-summary:claude-code:default:{attempt_id}",
                note.source,
            )

    def test_skips_attempt_with_external_trace_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            attempt_id = self._setup_repo_with_attempt(
                repo_root,
                raw_trace_ref="/Users/me/.claude/projects/x/session.jsonl",
            )

            note = summarize_attempt_transcript(repo_root, attempt_id)

            self.assertIsNone(note)

    def test_skips_attempt_with_no_trace_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            attempt_id = self._setup_repo_with_attempt(
                repo_root,
                raw_trace_ref=None,
            )

            note = summarize_attempt_transcript(repo_root, attempt_id)

            self.assertIsNone(note)

    def test_skips_when_internal_transcript_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            attempt_id = self._setup_repo_with_attempt(
                repo_root,
                raw_trace_ref=".ait/transcripts/nonexistent.jsonl",
            )

            note = summarize_attempt_transcript(repo_root, attempt_id)

            self.assertIsNone(note)


class RecallIntegrationTests(unittest.TestCase):
    def test_transcript_summary_note_is_surfaced_by_default_recall_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_repo(str(repo_root))
            init_memory_policy(repo_root, overwrite=True)
            transcript = repo_root / ".ait" / "transcripts" / "attempt-recall.jsonl"
            transcript.parent.mkdir(parents=True, exist_ok=True)
            _write_jsonl(
                transcript,
                [
                    {"role": "user", "text": "fix billing retry cache mode"},
                    {"role": "assistant", "text": "switched to durable queue"},
                    {
                        "role": "tool_use",
                        "tool": "Edit",
                        "files": ["src/billing/retry.py"],
                    },
                ],
            )

            note = summarize_transcript_to_note(
                repo_root,
                attempt_id="attempt-recall",
                transcript_path=transcript,
                agent_id="claude-code:default",
            )
            self.assertIsNotNone(note)

            recall = build_relevant_memory_recall(
                repo_root,
                "billing retry cache",
                limit=12,
            )

            recalled_sources = [item.metadata.get("source") for item in recall.selected]
            self.assertIn(
                "transcript-summary:claude-code:default:attempt-recall",
                recalled_sources,
            )


if __name__ == "__main__":
    unittest.main()
