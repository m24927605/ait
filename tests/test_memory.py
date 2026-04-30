from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
from pathlib import Path

from ait.app import create_commit_for_attempt, create_attempt, create_intent, show_attempt
from ait.db import connect_db, list_memory_facts, run_migrations
from ait.db.repositories import update_attempt
from ait.memory import (
    add_memory_note,
    add_attempt_memory_note,
    add_memory_candidates_for_attempt,
    agent_memory_status,
    build_relevant_memory_recall,
    build_repo_memory,
    ensure_agent_memory_imported,
    import_agent_memory,
    lint_memory_notes,
    list_memory_notes,
    remove_memory_note,
    render_repo_memory_text,
    search_repo_memory,
)
from ait.memory_policy import init_memory_policy


class MemoryTests(unittest.TestCase):
    def test_build_repo_memory_summarizes_recent_attempts_and_hot_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Remember change", description=None, kind="feature")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="claude-code:test")
            worktree = Path(attempt.workspace_ref)
            (worktree / "memory.txt").write_text("remember me\n", encoding="utf-8")
            _git(worktree, "add", "memory.txt")
            create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message="memory")

            memory = build_repo_memory(repo_root)
            text = render_repo_memory_text(memory)

            self.assertEqual(str(repo_root.resolve()), memory.repo_root)
            self.assertEqual(1, len(memory.recent_attempts))
            self.assertEqual("Remember change", memory.recent_attempts[0].intent_title)
            self.assertEqual(("memory.txt",), memory.recent_attempts[0].changed_files)
            self.assertEqual(("memory.txt",), memory.hot_files)
            self.assertIn("AIT Long-Term Repo Memory", text)
            self.assertIn("Remember change", text)
            self.assertIn("memory.txt", text)

    def test_memory_notes_can_be_added_listed_filtered_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            note = add_memory_note(
                repo_root,
                topic="architecture",
                body="Keep API adapters thin.",
            )

            self.assertEqual((note,), list_memory_notes(repo_root, topic="architecture"))
            memory = build_repo_memory(repo_root, topic="architecture")
            text = render_repo_memory_text(memory)
            self.assertEqual((note,), memory.notes)
            self.assertIn("Curated Notes:", text)
            self.assertIn("Keep API adapters thin.", text)

            self.assertTrue(remove_memory_note(repo_root, note_id=note.id))
            self.assertEqual((), list_memory_notes(repo_root))

    def test_memory_candidates_promote_high_confidence_successful_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id = _record_trace_attempt(
                repo_root,
                title="Project rule",
                trace_text="以後所有 API route 必須使用 zod 驗證。\nToken usage: total=1\n",
            )
            attempt_result = show_attempt(repo_root, attempt_id=attempt_id)

            notes = add_memory_candidates_for_attempt(repo_root, attempt_result)
            durable_notes = list_memory_notes(repo_root, topic="durable-memory")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            self.addCleanup(conn.close)
            facts = list_memory_facts(conn, status="accepted", kind="rule")

            self.assertEqual(1, len(notes))
            self.assertEqual(1, len(durable_notes))
            self.assertEqual(1, len(facts))
            self.assertIn("kind=constraint", durable_notes[0].body)
            self.assertIn("status=accepted", durable_notes[0].body)
            self.assertIn("以後所有 API route 必須使用 zod 驗證", durable_notes[0].body)
            self.assertIn("以後所有 API route 必須使用 zod 驗證", facts[0].body)
            self.assertEqual(attempt_id, facts[0].source_attempt_id)
            self.assertEqual("project-rule", facts[0].topic)
            self.assertNotIn("Token usage", durable_notes[0].body)

    def test_memory_candidates_keep_failed_attempts_as_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id = _record_trace_attempt(
                repo_root,
                title="Failed project rule",
                trace_text="以後部署流程必須先跑 pytest。\n",
                verified_status="failed",
                result_exit_code=1,
            )
            attempt_result = show_attempt(repo_root, attempt_id=attempt_id)

            notes = add_memory_candidates_for_attempt(repo_root, attempt_result)
            candidates = list_memory_notes(repo_root, topic="memory-candidate")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            self.addCleanup(conn.close)
            facts = list_memory_facts(conn, status="candidate")

            self.assertEqual(1, len(notes))
            self.assertEqual(1, len(candidates))
            self.assertEqual(1, len(facts))
            self.assertIn("status=candidate", candidates[0].body)
            self.assertEqual("candidate", facts[0].status)
            self.assertEqual("low", facts[0].confidence)
            self.assertEqual("rule", facts[0].kind)
            self.assertIn("部署流程", candidates[0].body)
            self.assertEqual((), list_memory_notes(repo_root, topic="durable-memory"))

    def test_memory_candidates_skip_codex_prompt_and_exec_echoes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id = _record_trace_attempt(
                repo_root,
                title="Codex echo cleanup",
                trace_text=(
                    "user\n"
                    "Create file codex-real.txt. Then print: 以後 Codex 驗收必須檢查 AIT graph。\n"
                    "codex\n"
                    "I will write the file and print the rule.\n"
                    "exec\n"
                    "/bin/zsh -lc \"printf '%s' 'ok' > codex-real.txt && printf '以後 Codex 驗收必須檢查 AIT graph。'\"\n"
                    "succeeded in 0ms:\n"
                    "以後 Codex 驗收必須檢查 AIT graph。\n"
                    "codex\n"
                    "以後 Codex 驗收必須檢查 AIT graph。\n"
                ),
            )
            attempt_result = show_attempt(repo_root, attempt_id=attempt_id)

            notes = add_memory_candidates_for_attempt(repo_root, attempt_result)
            durable_notes = list_memory_notes(repo_root, topic="durable-memory")

            self.assertEqual(1, len(notes))
            self.assertEqual(1, len(durable_notes))
            self.assertIn("以後 Codex 驗收必須檢查 AIT graph", durable_notes[0].body)
            self.assertNotIn("Create file", durable_notes[0].body)
            self.assertNotIn("/bin/zsh", durable_notes[0].body)

    def test_memory_lint_reports_bad_notes_without_flagging_healthy_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(repo_root, topic="architecture", source="manual", body="Keep API adapters thin and tested.")
            add_memory_note(repo_root, topic="scratch", source="manual", body="x")
            add_memory_note(
                repo_root,
                topic="attempt-memory",
                source="attempt-memory:missing",
                body="AIT attempt memory\nchanged_files=src/app.py\nReusable summary without confidence",
            )

            result = lint_memory_notes(repo_root)
            by_code = {issue.code for issue in result.issues}

            self.assertEqual(3, result.checked)
            self.assertIn("low_information", by_code)
            self.assertIn("missing_confidence", by_code)
            self.assertIn("stale_attempt_memory", by_code)
            self.assertFalse(any(issue.source == "manual" and issue.topic == "architecture" for issue in result.issues))

    def test_memory_lint_fix_conservatively_improves_fixable_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(repo_root, topic="release", source="manual", body="Run tests before release.")
            add_memory_note(repo_root, topic="release", source="manual", body="Run tests before release.")
            add_memory_note(
                repo_root,
                topic="security",
                source="manual",
                body="Do not keep GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456 in memory.",
            )
            add_memory_note(repo_root, topic="long", source="manual", body="word " * 120)

            before = lint_memory_notes(repo_root, max_chars=80)
            fixed = lint_memory_notes(repo_root, fix=True, max_chars=80)
            after = lint_memory_notes(repo_root, max_chars=80)
            notes_text = "\n".join(note.body for note in list_memory_notes(repo_root, limit=20))

            self.assertGreater(len([issue for issue in before.issues if issue.fixable]), 0)
            self.assertGreaterEqual(len(fixed.fixes), 3)
            self.assertLess(len([issue for issue in after.issues if issue.fixable]), len([issue for issue in before.issues if issue.fixable]))
            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", notes_text)
            self.assertEqual(3, len(list_memory_notes(repo_root, limit=20)))

    def test_relevant_memory_recall_skips_lint_error_notes_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            healthy = add_memory_note(
                repo_root,
                topic="attempt-memory",
                source="attempt-memory:healthy",
                body="Billing retry path changed_files=billing_retry.py confidence=high",
            )
            unhealthy = add_memory_note(
                repo_root,
                topic="attempt-memory",
                source="attempt-memory:secret",
                body="Billing retry path stores GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456 confidence=high",
            )

            recall = build_relevant_memory_recall(repo_root, "billing retry")
            selected_ids = {item.id for item in recall.selected}
            skipped = {str(item["id"]): item for item in recall.skipped}
            include_all = build_relevant_memory_recall(repo_root, "billing retry", include_unhealthy=True)

            self.assertIn(healthy.id, selected_ids)
            self.assertNotIn(unhealthy.id, selected_ids)
            self.assertEqual("lint issue", skipped[unhealthy.id]["reason"])
            self.assertIn("possible_secret", skipped[unhealthy.id]["lint_codes"])
            self.assertIn(unhealthy.id, {item.id for item in include_all.selected})

    def test_relevant_memory_recall_respects_policy_source_allow_and_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_memory_policy(repo_root)
            policy_path = repo_root / ".ait" / "memory-policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "recall_source_allow": ["attempt-memory:*"],
                        "recall_source_block": ["attempt-memory:blocked"],
                        "recall_lint_block_severities": ["error"],
                    }
                ),
                encoding="utf-8",
            )
            allowed = add_memory_note(
                repo_root,
                topic="attempt-memory",
                source="attempt-memory:allowed",
                body="Billing retry path changed_files=billing_retry.py confidence=high",
            )
            blocked = add_memory_note(
                repo_root,
                topic="attempt-memory",
                source="attempt-memory:blocked",
                body="Billing retry blocked path changed_files=billing_retry.py confidence=high",
            )
            agent = add_memory_note(
                repo_root,
                topic="agent-memory",
                source="agent-memory:claude:CLAUDE.md",
                body="Billing retry agent guidance confidence=advisory",
            )

            recall = build_relevant_memory_recall(repo_root, "billing retry")
            selected_ids = {item.id for item in recall.selected}
            skipped = {str(item["id"]): item for item in recall.skipped}

            self.assertIn(allowed.id, selected_ids)
            self.assertNotIn(blocked.id, selected_ids)
            self.assertNotIn(agent.id, selected_ids)
            self.assertEqual("source blocked by memory policy", skipped[blocked.id]["reason"])
            self.assertEqual("source not allowed by memory policy", skipped[agent.id]["reason"])

    def test_relevant_memory_recall_policy_can_block_warning_severities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_memory_policy(repo_root)
            policy_path = repo_root / ".ait" / "memory-policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "recall_source_allow": ["attempt-memory:*"],
                        "recall_lint_block_severities": ["error", "warning"],
                    }
                ),
                encoding="utf-8",
            )
            warning = add_memory_note(
                repo_root,
                topic="attempt-memory",
                source="attempt-memory:missing-confidence",
                body="Billing retry path changed_files=billing_retry.py",
            )

            recall = build_relevant_memory_recall(repo_root, "billing retry")
            selected_ids = {item.id for item in recall.selected}
            skipped = {str(item["id"]): item for item in recall.skipped}

            self.assertNotIn(warning.id, selected_ids)
            self.assertEqual("lint issue", skipped[warning.id]["reason"])
            self.assertIn("missing_confidence", skipped[warning.id]["lint_codes"])

    def test_import_agent_memory_detects_common_agent_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("Use pytest before release.\n", encoding="utf-8")
            (repo_root / "AGENTS.md").write_text("Keep CLI output parseable.\n", encoding="utf-8")

            result = import_agent_memory(repo_root)
            notes = list_memory_notes(repo_root, topic="agent-memory")

            self.assertEqual(2, len(result.imported))
            self.assertEqual(2, len(notes))
            self.assertTrue(all(note.topic == "agent-memory" for note in notes))
            self.assertTrue(any(note.source == "agent-memory:claude:CLAUDE.md" for note in notes))
            self.assertTrue(any(note.source == "agent-memory:codex:AGENTS.md" for note in notes))
            self.assertIn("confidence=advisory", notes[0].body)
            self.assertIn("Use pytest before release.", "\n".join(note.body for note in notes))

    def test_import_agent_memory_custom_path_redacts_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            memory_path = repo_root / "docs" / "agent-memory.md"
            memory_path.parent.mkdir()
            memory_path.write_text(
                "Release with token GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456\n",
                encoding="utf-8",
            )

            first = import_agent_memory(repo_root, source="custom", paths=("docs/agent-memory.md",))
            second = import_agent_memory(repo_root, source="custom", paths=("docs/agent-memory.md",))

            self.assertEqual(1, len(first.imported))
            self.assertEqual(0, len(second.imported))
            self.assertEqual("already imported", second.skipped[0]["reason"])
            self.assertIn("[REDACTED]", first.imported[0].body)
            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", first.imported[0].body)

    def test_import_agent_memory_respects_memory_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_memory_policy(repo_root)
            (repo_root / ".ait" / "memory-policy.json").write_text(
                json.dumps({"exclude_paths": ["CLAUDE.md"], "exclude_transcript_patterns": []}),
                encoding="utf-8",
            )
            (repo_root / "CLAUDE.md").write_text("Do not import this.\n", encoding="utf-8")

            result = import_agent_memory(repo_root, source="claude")

            self.assertEqual(0, len(result.imported))
            self.assertEqual("excluded by memory policy", result.skipped[0]["reason"])

    def test_ensure_agent_memory_imported_uses_repo_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("Prefer repair before release.\n", encoding="utf-8")

            first = ensure_agent_memory_imported(repo_root)
            second = ensure_agent_memory_imported(repo_root)
            status = agent_memory_status(repo_root)

            self.assertEqual(1, len(first.imported))
            self.assertEqual(0, len(second.imported))
            self.assertTrue((repo_root / ".ait" / "memory" / "agent-import-state.json").exists())
            self.assertTrue(status.initialized)
            self.assertEqual(("CLAUDE.md",), status.candidate_paths)
            self.assertEqual((), status.pending_paths)
            self.assertEqual(("agent-memory:claude:CLAUDE.md",), status.imported_sources)

    def test_add_attempt_memory_note_deduplicates_by_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id = _commit_attempt(repo_root, "Attempt memory", "src/app.py")

            shown = show_attempt(repo_root, attempt_id=attempt_id)
            first = add_attempt_memory_note(repo_root, shown)
            second = add_attempt_memory_note(repo_root, shown)
            notes = list_memory_notes(repo_root, topic="attempt-memory")

            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertEqual(1, len(notes))
            self.assertEqual(f"attempt-memory:{attempt_id}", notes[0].source)
            self.assertIn("changed_files=src/app.py", notes[0].body)

    def test_memory_filters_attempts_by_path_and_promoted_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            src_attempt = _commit_attempt(repo_root, "Source change", "src/app.py")
            docs_attempt = _commit_attempt(repo_root, "Docs change", "docs/guide.md")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            self.addCleanup(conn.close)
            run_migrations(conn)
            with conn:
                conn.execute(
                    "UPDATE attempts SET verified_status = 'promoted' WHERE id = ?",
                    (src_attempt,),
                )

            src_memory = build_repo_memory(repo_root, path_filter="src/")
            self.assertEqual(1, len(src_memory.recent_attempts))
            self.assertEqual(src_attempt, src_memory.recent_attempts[0].attempt_id)
            self.assertEqual(("src/app.py",), src_memory.hot_files)

            promoted_memory = build_repo_memory(repo_root, promoted_only=True)
            self.assertEqual(1, len(promoted_memory.recent_attempts))
            self.assertEqual(src_attempt, promoted_memory.recent_attempts[0].attempt_id)
            self.assertNotEqual(docs_attempt, promoted_memory.recent_attempts[0].attempt_id)

    def test_render_repo_memory_text_compacts_to_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(repo_root, body="x" * 400)

            text = render_repo_memory_text(build_repo_memory(repo_root), budget_chars=160)

            self.assertLessEqual(len(text), 160)
            self.assertIn("ait memory compacted", text)

    def test_search_repo_memory_finds_notes_and_attempt_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(
                repo_root,
                topic="architecture",
                body="Adapters should keep repo-local context handoff stable.",
            )
            attempt_id = _commit_attempt(repo_root, "Refactor billing adapter", "src/billing.py")

            note_results = search_repo_memory(repo_root, "context handoff")
            attempt_results = search_repo_memory(repo_root, "billing adapter")

            self.assertEqual("note", note_results[0].kind)
            self.assertIn("repo-local context", note_results[0].text)
            self.assertEqual("attempt", attempt_results[0].kind)
            self.assertEqual(attempt_id, attempt_results[0].id)
            self.assertEqual(["src/billing.py"], attempt_results[0].metadata["changed_files"])
            self.assertEqual("vector", attempt_results[0].metadata["ranker"])

    def test_search_repo_memory_can_use_lexical_ranker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(
                repo_root,
                topic="release",
                body="Run smoke tests before publishing packages.",
            )

            results = search_repo_memory(repo_root, "smoke packages", ranker="lexical")

            self.assertEqual("note", results[0].kind)
            self.assertEqual("lexical", results[0].metadata["ranker"])

    def test_search_repo_memory_finds_short_chinese_trace_literals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id = _record_trace_attempt(
                repo_root,
                title="Codex session",
                trace_text="使用者: 你是誰?\n助理: 我是 Codex，一個 AI coding agent。\n",
            )

            results = search_repo_memory(repo_root, "你是誰")

            self.assertEqual(attempt_id, results[0].id)
            self.assertEqual("attempt", results[0].kind)
            self.assertEqual("literal", results[0].metadata["ranker"])
            self.assertIn("你是誰", results[0].metadata["snippet"])
            self.assertIn("raw_trace_ref", results[0].metadata)

    def test_search_repo_memory_finds_short_ascii_trace_literals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id = _record_trace_attempt(
                repo_root,
                title="Codex session",
                trace_text="To continue this session, run codex resume 019dd9ba-fc1a\n",
            )

            results = search_repo_memory(repo_root, "019dd9ba")

            self.assertEqual(attempt_id, results[0].id)
            self.assertEqual("literal", results[0].metadata["ranker"])
            self.assertIn("019dd9ba", results[0].metadata["snippet"])

    def test_search_repo_memory_rejects_unknown_ranker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            with self.assertRaises(ValueError):
                search_repo_memory(repo_root, "anything", ranker="unknown")

    def test_memory_notes_are_redacted_in_rendering_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(
                repo_root,
                topic="security",
                body="Do not leak GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456",
            )

            text = render_repo_memory_text(build_repo_memory(repo_root))
            results = search_repo_memory(repo_root, "redacted")

            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", text)
            self.assertIn("[REDACTED]", text)
            self.assertIn("redacted: true", text)
            self.assertEqual("note", results[0].kind)
            self.assertTrue(results[0].metadata["redacted"])

    def test_memory_policy_excludes_sensitive_changed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_memory_policy(repo_root)
            policy_path = repo_root / ".ait" / "memory-policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "exclude_paths": [".env", "secrets/"],
                        "exclude_transcript_patterns": ["BEGIN PRIVATE KEY"],
                    }
                ),
                encoding="utf-8",
            )

            attempt_id = _commit_attempt_with_files(
                repo_root,
                "Mixed policy change",
                {
                    ".env": "SECRET_VALUE=hidden\n",
                    "src/app.py": "visible change\n",
                    "secrets/token.txt": "hidden\n",
                },
            )

            memory = build_repo_memory(repo_root)
            search_results = search_repo_memory(repo_root, "src/app.py")

            self.assertEqual(attempt_id, memory.recent_attempts[0].attempt_id)
            self.assertEqual(("src/app.py",), memory.recent_attempts[0].changed_files)
            self.assertEqual(("src/app.py",), memory.hot_files)
            self.assertNotIn(".env", render_repo_memory_text(memory))
            self.assertEqual(["src/app.py"], search_results[0].metadata["changed_files"])


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _commit_attempt(repo_root: Path, title: str, file_path: str) -> str:
    intent = create_intent(repo_root, title=title, description=None, kind="feature")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="claude-code:test")
    worktree = Path(attempt.workspace_ref)
    target = worktree / file_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{title}\n", encoding="utf-8")
    _git(worktree, "add", file_path)
    create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message=title)
    return attempt.attempt_id


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


def _record_trace_attempt(
    repo_root: Path,
    *,
    title: str,
    trace_text: str,
    verified_status: str = "succeeded",
    result_exit_code: int = 0,
) -> str:
    intent = create_intent(repo_root, title=title, description=None, kind="codex-run")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="codex:main")
    trace_dir = repo_root / ".ait" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_ref = f".ait/traces/{attempt.attempt_id.replace(':', '_')}.txt"
    (repo_root / trace_ref).write_text(trace_text, encoding="utf-8")
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        update_attempt(
            conn,
            attempt.attempt_id,
            reported_status="finished",
            verified_status=verified_status,
            raw_trace_ref=trace_ref,
            result_exit_code=result_exit_code,
        )
    finally:
        conn.close()
    return attempt.attempt_id


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


if __name__ == "__main__":
    unittest.main()
