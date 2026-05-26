from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.app import create_attempt, create_intent
from ait.db import connect_db, update_attempt
from ait.report.graph import build_work_graph
from ait.report.html import render_work_graph_html


class ReportTranscriptRedactionTests(unittest.TestCase):
    def test_graph_html_uses_redacted_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            secret = "sk-" + ("c" * 32)
            trace = repo_root / ".ait" / "transcripts" / "legacy.jsonl"
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(
                f'{{"role":"assistant","text":"legacy token {secret}"}}\n',
                encoding="utf-8",
            )
            _create_attempt_with_trace(
                repo_root,
                raw_trace_ref=".ait/transcripts/legacy.jsonl",
            )

            graph = build_work_graph(repo_root)
            graph_json = json.dumps(graph)
            html = render_work_graph_html(graph)

            self.assertIn("[REDACTED]", graph_json)
            self.assertIn("[REDACTED]", html)
            self.assertIn("mode=<code>redacted</code>", html)
            self.assertNotIn(secret, graph_json)
            self.assertNotIn(secret, html)


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_root, check=True)


def _create_attempt_with_trace(repo_root: Path, *, raw_trace_ref: str) -> str:
    intent = create_intent(
        repo_root,
        title="Report trace safety",
        description=None,
        kind="agent-session",
    )
    attempt = create_attempt(
        repo_root,
        intent_id=intent.intent_id,
        agent_id="claude-code:default",
    )
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        update_attempt(
            conn,
            attempt.attempt_id,
            reported_status="finished",
            verified_status="succeeded",
            raw_trace_ref=raw_trace_ref,
            result_exit_code=0,
        )
    finally:
        conn.close()
    return attempt.attempt_id


if __name__ == "__main__":
    unittest.main()
