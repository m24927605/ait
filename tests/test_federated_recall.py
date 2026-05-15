from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.memory import add_memory_note, build_relevant_memory_recall, list_memory_notes
from ait.runner import run_agent_command


class FederatedRecallTests(unittest.TestCase):
    def test_memory_recall_is_zero_touch_and_reads_live_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            source = repo_root / "CLAUDE.md"
            source.write_text("AIT_LIVE_MEMORY_RULE=v1\n", encoding="utf-8")

            first = _recall_json(repo_root, "AIT_LIVE_MEMORY_RULE")
            source.write_text("AIT_LIVE_MEMORY_RULE=v2\n", encoding="utf-8")
            second = _recall_json(repo_root, "AIT_LIVE_MEMORY_RULE")

            self.assertFalse((repo_root / ".ait").exists())
            self.assertIn("v1", first["selected"][0]["text"])
            self.assertIn("v2", second["selected"][0]["text"])
            self.assertNotIn("v1", second["selected"][0]["text"])
            self.assertEqual("read_only", second["write_mode"])
            self.assertEqual("live:claude:CLAUDE.md", second["source_manifest"][0]["source_id"])
            self.assertTrue(second["source_manifest"][0]["selected"])

    def test_recall_federates_claude_codex_and_cursor_live_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("project policy claude live memory\n", encoding="utf-8")
            (repo_root / "AGENTS.md").write_text("project policy codex live memory\n", encoding="utf-8")
            (repo_root / ".cursor").mkdir()
            (repo_root / ".cursor" / "rules").write_text("project policy cursor live memory\n", encoding="utf-8")

            payload = _recall_json(repo_root, "project policy")
            source_ids = {item["source"] for item in payload["selected"]}

            self.assertIn("live:claude:CLAUDE.md", source_ids)
            self.assertIn("live:codex:AGENTS.md", source_ids)
            self.assertIn("live:cursor:.cursor/rules", source_ids)
            self.assertFalse((repo_root / ".ait").exists())

    def test_policy_blocked_live_source_is_not_in_context_and_redaction_runs_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text(
                "Use live safe context. TOKEN=supersecretvalue\n",
                encoding="utf-8",
            )
            (repo_root / "AGENTS.md").write_text("BLOCKED_LIVE_CONTEXT\n", encoding="utf-8")
            (repo_root / ".ait").mkdir()
            (repo_root / ".ait" / "memory-policy.json").write_text(
                json.dumps({"exclude_paths": ["AGENTS.md"]}) + "\n",
                encoding="utf-8",
            )

            result = run_agent_command(
                repo_root,
                intent_title="Live memory context",
                agent_id="shell:test",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import os;"
                        "from pathlib import Path;"
                        "Path('context-copy.txt').write_text(Path(os.environ['AIT_CONTEXT_FILE']).read_text())"
                    ),
                ],
                with_context=True,
            )

            context_text = (Path(result.workspace_ref) / "context-copy.txt").read_text(encoding="utf-8")
            manifest_path = next((repo_root / ".ait" / "context").glob("attempt-*.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(0, result.exit_code)
            self.assertIn("Use live safe context", context_text)
            self.assertNotIn("supersecretvalue", context_text)
            self.assertIn("[REDACTED]", context_text)
            self.assertNotIn("BLOCKED_LIVE_CONTEXT", context_text)
            blocked = [item for item in manifest["source_manifest"] if item["source_id"] == "live:codex:AGENTS.md"]
            self.assertEqual(1, len(blocked))
            self.assertEqual("blocked", blocked[0]["policy_status"])
            self.assertFalse(blocked[0]["selected"])

    def test_old_ait_memory_notes_remain_searchable_with_live_sources_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(
                repo_root,
                topic="legacy",
                body="OLD_AIT_MEMORY_NOTE remains searchable.",
                source="manual",
            )
            before_sources = {note.source for note in list_memory_notes(repo_root)}

            recall = build_relevant_memory_recall(repo_root, "OLD_AIT_MEMORY_NOTE")

            self.assertEqual({"manual"}, before_sources)
            self.assertTrue(any(item.source == "manual" for item in recall.selected))
            self.assertIn("OLD_AIT_MEMORY_NOTE", json.dumps(recall.to_dict()))

    def test_memory_recall_record_explicitly_writes_retrieval_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("AIT_RECORD_RULE=enabled\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "recall", "AIT_RECORD_RULE", "--record", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            record_ref = payload["record_ref"]

            self.assertEqual(0, exit_code)
            self.assertEqual("recorded", payload["write_mode"])
            self.assertTrue(record_ref.startswith(".ait/memory-retrievals/"))
            self.assertTrue((repo_root / record_ref).exists())


def _recall_json(repo_root: Path, query: str) -> dict[str, object]:
    stdout = io.StringIO()
    with chdir(repo_root):
        with patch("sys.argv", ["ait", "memory", "recall", query, "--format", "json"]):
            with redirect_stdout(stdout):
                exit_code = cli.main()
    if exit_code != 0:
        raise AssertionError(f"recall failed with {exit_code}: {stdout.getvalue()}")
    payload = json.loads(stdout.getvalue())
    assert isinstance(payload, dict)
    return payload


def _init_git_repo(repo_root: Path) -> None:
    result = subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
