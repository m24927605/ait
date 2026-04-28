from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ait.app import create_attempt, create_commit_for_attempt, create_intent
from ait.brain import (
    build_auto_briefing_query,
    build_auto_repo_brain_briefing,
    build_repo_brain,
    build_repo_brain_briefing,
    query_repo_brain,
    render_repo_brain_briefing,
    render_repo_brain_text,
    write_repo_brain,
)
from ait.db import connect_db, run_migrations
from ait.memory import add_memory_note
from ait.memory_policy import init_memory_policy
from ait.runner import run_agent_command


class BrainTests(unittest.TestCase):
    def test_repo_brain_indexes_docs_notes_attempts_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "docs").mkdir()
            (repo_root / "docs" / "design.md").write_text("# Design\nRepo brain invariant.\n", encoding="utf-8")
            _git(repo_root, "add", "docs/design.md")
            _git(repo_root, "commit", "-m", "docs")
            add_memory_note(
                repo_root,
                topic="architecture",
                body="Repo brain must stay local.",
            )
            attempt_id = _commit_attempt(repo_root, "Build repo brain", "src/brain.py")

            brain = build_repo_brain(repo_root)
            node_ids = {node.id for node in brain.nodes}
            edge_keys = {(edge.source, edge.kind, edge.target) for edge in brain.edges}
            text = render_repo_brain_text(brain)

            self.assertIn("repo:root", node_ids)
            self.assertIn("doc:README.md", node_ids)
            self.assertIn("doc:docs/design.md", node_ids)
            self.assertIn("topic:architecture", node_ids)
            self.assertIn(f"attempt:{attempt_id}", node_ids)
            self.assertIn("file:src/brain.py", node_ids)
            self.assertIn(("repo:root", "has_doc", "doc:README.md"), edge_keys)
            self.assertIn((f"attempt:{attempt_id}", "changed_file", "file:src/brain.py"), edge_keys)
            self.assertIn("AIT Repo Brain", text)
            self.assertIn("Build repo brain", text)

    def test_repo_brain_respects_memory_policy_and_redacts_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_memory_policy(repo_root)
            (repo_root / ".ait" / "memory-policy.json").write_text(
                json.dumps(
                    {
                        "exclude_paths": ["docs/private.md", ".env"],
                        "exclude_transcript_patterns": ["BEGIN PRIVATE KEY"],
                    }
                ),
                encoding="utf-8",
            )
            (repo_root / "docs").mkdir()
            (repo_root / "docs" / "private.md").write_text("secret doc\n", encoding="utf-8")
            (repo_root / "docs" / "public.md").write_text(
                "Public doc token sk-abcdefghijklmnopqrstuvwxyz123456\n",
                encoding="utf-8",
            )
            _git(repo_root, "add", "docs/private.md", "docs/public.md")
            _git(repo_root, "commit", "-m", "policy docs")
            add_memory_note(
                repo_root,
                topic="security TOKEN=hidden",
                body="Do not leak GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456",
                source="source SECRET=hidden",
            )
            _commit_attempt_with_files(
                repo_root,
                "Policy change sk-abcdefghijklmnopqrstuvwxyz123456",
                {
                    ".env": "SECRET=hidden\n",
                    "src/app.py": "visible\n",
                },
            )

            brain = build_repo_brain(repo_root)
            text = render_repo_brain_text(brain)
            node_ids = {node.id for node in brain.nodes}

            self.assertNotIn("doc:docs/private.md", node_ids)
            self.assertNotIn("file:.env", node_ids)
            self.assertIn("file:src/app.py", node_ids)
            self.assertIn("[REDACTED]", text)
            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", text)
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", text)
            self.assertNotIn("TOKEN=hidden", text)
            self.assertNotIn("SECRET=hidden", text)

    def test_repo_brain_write_is_idempotent_and_query_includes_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id = _commit_attempt(repo_root, "Release PyPI package", "pyproject.toml")

            first = write_repo_brain(repo_root)
            first_text = (repo_root / ".ait" / "brain" / "graph.json").read_text(encoding="utf-8")
            second = write_repo_brain(repo_root)
            second_text = (repo_root / ".ait" / "brain" / "graph.json").read_text(encoding="utf-8")
            results = query_repo_brain(repo_root, "pypi package")

            self.assertEqual(first_text, second_text)
            self.assertEqual(first.generated_at, second.generated_at)
            self.assertEqual(f"attempt:{attempt_id}", results[0].node.id)
            self.assertTrue(any(neighbor.id == "file:pyproject.toml" for neighbor in results[0].neighbors))

    def test_repo_brain_write_from_worktree_targets_root_ait_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Worktree brain", description=None, kind="feature")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="codex:test")

            brain = write_repo_brain(Path(attempt.workspace_ref))

            self.assertEqual(str(repo_root.resolve()), brain.repo_root)
            self.assertTrue((repo_root / ".ait" / "brain" / "graph.json").exists())
            self.assertFalse((Path(attempt.workspace_ref) / ".ait" / "brain" / "graph.json").exists())

    def test_repo_brain_build_initializes_ait_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            write_repo_brain(repo_root)

            status = _git_stdout(repo_root, "status", "--short")
            self.assertNotIn(".ait/", status)
            self.assertIn(".ait/", (repo_root / ".gitignore").read_text(encoding="utf-8"))

    def test_repo_brain_query_finds_redacted_trace_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Trace brain",
                adapter_name="codex",
                command=[
                    sys.executable,
                    "-c",
                    "print('TRACE_BRAIN_TOKEN sk-abcdefghijklmnopqrstuvwxyz123456')",
                ],
                capture_command_output=True,
            )
            query_results = query_repo_brain(repo_root, "TRACE_BRAIN_TOKEN")
            text = render_repo_brain_text(build_repo_brain(repo_root))

            self.assertEqual(0, result.exit_code)
            self.assertEqual("trace", query_results[0].node.kind)
            self.assertIn("[REDACTED]", query_results[0].node.text)
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", text)

    def test_repo_brain_query_rejects_negative_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            with self.assertRaises(ValueError):
                query_repo_brain(repo_root, "hello", limit=-1)

    def test_repo_brain_text_preserves_attempt_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            failed_id = _commit_attempt(repo_root, "Failed brain attempt", "failed.txt")
            succeeded_id = _commit_attempt(repo_root, "Succeeded brain attempt", "succeeded.txt")
            promoted_id = _commit_attempt(repo_root, "Promoted brain attempt", "promoted.txt")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            self.addCleanup(conn.close)
            run_migrations(conn)
            with conn:
                conn.execute("UPDATE attempts SET verified_status = 'failed' WHERE id = ?", (failed_id,))
                conn.execute("UPDATE attempts SET verified_status = 'succeeded' WHERE id = ?", (succeeded_id,))
                conn.execute("UPDATE attempts SET verified_status = 'promoted' WHERE id = ?", (promoted_id,))

            text = render_repo_brain_text(build_repo_brain(repo_root))

            self.assertIn("status=failed", text)
            self.assertIn("status=succeeded", text)
            self.assertIn("status=promoted", text)

    def test_repo_brain_briefing_selects_relevant_nodes_and_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(repo_root, topic="release", body="Run twine check before PyPI publish.")
            attempt_id = _commit_attempt(repo_root, "Release PyPI package", "pyproject.toml")

            briefing = build_repo_brain_briefing(repo_root, "pypi package", limit=4)
            text = render_repo_brain_briefing(briefing)

            self.assertEqual("pypi package", briefing.query)
            self.assertEqual(f"attempt:{attempt_id}", briefing.results[0].node.id)
            self.assertIn("AIT Repo Brain Briefing", text)
            self.assertIn("Likely Files:", text)
            self.assertIn("file:pyproject.toml", text)
            self.assertIn("Relevant Docs And Notes:", text)

    def test_repo_brain_briefing_compacts_to_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _commit_attempt(repo_root, "Large briefing package release", "pyproject.toml")

            text = render_repo_brain_briefing(
                build_repo_brain_briefing(repo_root, "package release"),
                budget_chars=180,
            )

            self.assertLessEqual(len(text), 180)
            self.assertIn("briefing compacted", text)

    def test_auto_briefing_query_uses_agent_command_failures_and_hot_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            failed_id = _commit_attempt(repo_root, "Failed release upload", "pyproject.toml")
            _commit_attempt(repo_root, "Package metadata update", "pyproject.toml")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            self.addCleanup(conn.close)
            run_migrations(conn)
            with conn:
                conn.execute("UPDATE attempts SET verified_status = 'failed' WHERE id = ?", (failed_id,))
            add_memory_note(repo_root, topic="release", body="Use twine check before upload.")

            auto_query = build_auto_briefing_query(
                repo_root,
                intent_title="Publish package",
                description="Upload to PyPI",
                kind="release",
                command=("twine", "upload", "dist/*"),
                agent_id="codex:main",
            )
            briefing = build_auto_repo_brain_briefing(
                repo_root,
                intent_title="Publish package",
                command=("twine", "upload", "dist/*"),
                agent_id="codex:main",
            )
            text = render_repo_brain_briefing(briefing)
            source_names = {source.source for source in auto_query.sources}

            self.assertIn("intent_title", source_names)
            self.assertIn("command_args", source_names)
            self.assertIn("agent", source_names)
            self.assertIn("recent_failed_attempt", source_names)
            self.assertIn("hot_file", source_names)
            self.assertIn("memory_topic", source_names)
            self.assertIn("Failed release upload", auto_query.query)
            self.assertIn("pyproject.toml", auto_query.query)
            self.assertIn("Briefing Query Sources:", text)
            self.assertTrue(briefing.results)


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _commit_attempt(repo_root: Path, title: str, file_path: str) -> str:
    return _commit_attempt_with_files(repo_root, title, {file_path: f"{title}\n"})


def _commit_attempt_with_files(repo_root: Path, title: str, files: dict[str, str]) -> str:
    intent = create_intent(repo_root, title=title, description=None, kind="feature")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="claude-code:test")
    worktree = Path(attempt.workspace_ref)
    for file_path, contents in files.items():
        target = worktree / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
        _git(worktree, "add", file_path)
    create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message=title)
    return attempt.attempt_id


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_stdout(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    unittest.main()
