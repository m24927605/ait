from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ait.aider_capture import (
    aider_history_path,
    parse_aider_history,
    persist_aider_session,
)


SAMPLE_HISTORY = """\
# aider chat started at 2026-05-04 12:00:00


#### refactor the auth retry to use durable queue

I'll trace the retry path first. The retry currently lives in
`src/billing/retry.py` and uses an in-memory queue. I'll switch the
queue type to durable.

Updated src/billing/retry.py:
```python
queue = DurableQueue()
```

Tests pass.

#### bump the version and add a changelog entry

Bumped to 1.4.0. CHANGELOG.md updated.

# aider chat started at 2026-05-04 13:30:00


#### add unit tests for the durable retry path

Added 3 tests covering enqueue, retry-on-failure, and recovery after
restart. All pass.
"""


class ParseAiderHistoryTests(unittest.TestCase):
    def test_parse_yields_meta_user_assistant_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".aider.chat.history.md"
            path.write_text(SAMPLE_HISTORY, encoding="utf-8")

            events = list(parse_aider_history(path))

        roles = [e["role"] for e in events]
        self.assertEqual(
            ["meta", "user", "assistant", "user", "assistant", "meta", "user", "assistant"],
            roles,
        )
        self.assertIn("aider chat started", events[0]["text"])
        self.assertEqual(
            "refactor the auth retry to use durable queue",
            events[1]["text"],
        )
        self.assertIn("DurableQueue", events[2]["text"])
        self.assertEqual(
            "bump the version and add a changelog entry",
            events[3]["text"],
        )
        self.assertIn("CHANGELOG.md updated", events[4]["text"])
        self.assertIn("aider chat started at 2026-05-04 13:30:00", events[5]["text"])
        self.assertIn(
            "add unit tests for the durable retry path",
            events[6]["text"],
        )
        self.assertIn("All pass", events[7]["text"])

    def test_parse_handles_assistant_only_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "h.md"
            path.write_text(
                "#### one shot\n\nDid the thing.\n",
                encoding="utf-8",
            )

            events = list(parse_aider_history(path))

        self.assertEqual(2, len(events))
        self.assertEqual("user", events[0]["role"])
        self.assertEqual("one shot", events[0]["text"])
        self.assertEqual("assistant", events[1]["role"])
        self.assertEqual("Did the thing.", events[1]["text"])

    def test_parse_returns_no_events_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                [], list(parse_aider_history(Path(tmp) / "nope.md"))
            )

    def test_parse_returns_no_events_for_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "h.md"
            path.write_text("", encoding="utf-8")
            self.assertEqual([], list(parse_aider_history(path)))


class PersistAiderSessionTests(unittest.TestCase):
    def test_persist_writes_envelope_jsonl_under_ait_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workspace = repo_root / "wt"
            workspace.mkdir()
            (workspace / ".aider.chat.history.md").write_text(
                SAMPLE_HISTORY, encoding="utf-8"
            )

            ref = persist_aider_session(
                repo_root,
                attempt_id="attempt-aaa",
                workspace=workspace,
            )

            self.assertEqual(".ait/transcripts/attempt-aaa.jsonl", ref)
            dest = repo_root / ".ait" / "transcripts" / "attempt-aaa.jsonl"
            self.assertTrue(dest.exists())
            lines = [
                json.loads(line)
                for line in dest.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            roles = [e["role"] for e in lines]
            self.assertEqual(
                ["meta", "user", "assistant", "user", "assistant", "meta", "user", "assistant"],
                roles,
            )

    def test_persist_returns_none_when_no_history_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workspace = repo_root / "wt"
            workspace.mkdir()
            ref = persist_aider_session(
                repo_root,
                attempt_id="attempt-bbb",
                workspace=workspace,
            )
            self.assertIsNone(ref)
            self.assertFalse((repo_root / ".ait" / "transcripts").exists())

    def test_aider_history_path_is_in_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            self.assertEqual(
                workspace / ".aider.chat.history.md",
                aider_history_path(workspace),
            )


class AiderRunnerIntegrationTests(unittest.TestCase):
    def test_run_agent_command_persists_aider_history_into_transcripts(self) -> None:
        import subprocess
        import sys
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

            fake_aider_program = (
                "from pathlib import Path\n"
                "Path('.aider.chat.history.md').write_text(\n"
                "    '# aider chat started at 2026-05-04 12:00:00\\n\\n'\n"
                "    '#### refactor parser\\n\\nDone in src/parser.py.\\n',\n"
                "    encoding='utf-8',\n"
                ")\n"
            )

            result = run_agent_command(
                repo_root,
                intent_title="aider session",
                adapter_name="aider",
                command=[sys.executable, "-c", fake_aider_program],
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
