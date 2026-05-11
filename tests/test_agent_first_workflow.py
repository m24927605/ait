from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
import io
import json
import multiprocessing
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait import cli
from ait.app import create_attempt, create_commit_for_attempt, create_intent, init_repo, promote_attempt
from ait.daemon import daemon_status, stop_daemon
from ait.daemon_transport import bind_unix_socket, remove_socket_file


class AgentFirstWorkflowTests(unittest.TestCase):
    def test_bad_prompt_mass_rewrite_stays_isolated_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            (repo / "src").mkdir()
            (repo / "docs").mkdir()
            (repo / "src" / "core.py").write_text("def value():\n    return 1\n", encoding="utf-8")
            (repo / "src" / "keep.py").write_text("KEEP = True\n", encoding="utf-8")
            (repo / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
            _git(repo, "add", "src/core.py", "src/keep.py", "docs/guide.md")
            _git(repo, "commit", "-m", "add tracked project files")
            init_repo(repo)
            _commit_ait_gitignore_if_needed(repo)
            (repo / "scratch.local").write_text("root scratch\n", encoding="utf-8")
            (repo / "notes").mkdir()
            (repo / "notes" / "todo.txt").write_text("do not delete\n", encoding="utf-8")

            root_head = _git_stdout(repo, "rev-parse", "--verify", "HEAD")
            root_status = _git_stdout(repo, "status", "--short")
            tracked_snapshot = {
                rel_path: (repo / rel_path).read_text(encoding="utf-8")
                for rel_path in ("README.md", "src/core.py", "src/keep.py", "docs/guide.md")
            }
            agent_code = "\n".join(
                [
                    "from pathlib import Path",
                    "Path('README.md').write_text('rewritten by bad prompt\\n')",
                    "Path('src/core.py').write_text('def value():\\n    return 999\\n')",
                    "Path('docs/guide.md').unlink()",
                    "Path('src/new_module.py').write_text('NEW = True\\n')",
                    "Path('generated').mkdir(exist_ok=True)",
                    "for index in range(12):",
                    "    Path('generated', f'file_{index:02d}.txt').write_text(f'generated {index}\\n')",
                    "print('mass rewrite stdout')",
                    "import sys",
                    "print('mass rewrite stderr', file=sys.stderr)",
                ]
            )

            try:
                payload = _cli_json(
                    repo,
                    [
                        "ait",
                        "run",
                        "--adapter",
                        "shell",
                        "--intent",
                        "Bad prompt mass rewrite",
                        "--format",
                        "json",
                        "--",
                        sys.executable,
                        "-c",
                        agent_code,
                    ],
                )
            finally:
                stop_daemon(repo)

            self.assertEqual(root_head, _git_stdout(repo, "rev-parse", "--verify", "HEAD"))
            self.assertEqual(root_status, _git_stdout(repo, "status", "--short"))
            for rel_path, content in tracked_snapshot.items():
                self.assertEqual(content, (repo / rel_path).read_text(encoding="utf-8"), rel_path)
            self.assertEqual("root scratch\n", (repo / "scratch.local").read_text(encoding="utf-8"))
            self.assertEqual("do not delete\n", (repo / "notes" / "todo.txt").read_text(encoding="utf-8"))

            workspace = Path(str(payload["workspace_ref"]))
            self.assertTrue(workspace.exists())
            self.assertTrue(_is_relative_to(workspace, repo / ".ait" / "workspaces"))
            self.assertEqual("rewritten by bad prompt\n", (workspace / "README.md").read_text(encoding="utf-8"))
            self.assertEqual("def value():\n    return 999\n", (workspace / "src" / "core.py").read_text(encoding="utf-8"))
            self.assertFalse((workspace / "docs" / "guide.md").exists())
            self.assertTrue((workspace / "generated" / "file_11.txt").exists())

            self.assertEqual("mass rewrite stdout\n", payload["command_stdout"])
            self.assertEqual("mass rewrite stderr\n", payload["command_stderr"])
            self.assertEqual(payload["intent_id"], payload["attempt"]["attempt"]["intent_id"])
            self.assertEqual("succeeded", payload["attempt"]["attempt"]["verified_status"])
            self.assertGreaterEqual(len(payload["attempt"]["commits"]), 1)
            changed = set(payload["attempt"]["files"]["changed"])
            self.assertTrue(
                {
                    "README.md",
                    "src/core.py",
                    "docs/guide.md",
                    "src/new_module.py",
                    "generated/file_00.txt",
                }.issubset(changed)
            )
            evidence = payload["attempt"]["evidence_summary"]
            self.assertEqual(1, evidence["observed_commands_run"])
            raw_prompt_ref = evidence["raw_prompt_ref"]
            self.assertIsInstance(raw_prompt_ref, str)
            self.assertIn("src/core.py", (repo / raw_prompt_ref).read_text(encoding="utf-8"))

            query_rows = _cli_jsonl(
                repo,
                [
                    "ait",
                    "query",
                    "--on",
                    "attempt",
                    'title~"Bad prompt mass rewrite"',
                    "--format",
                    "jsonl",
                ],
            )
            self.assertEqual([payload["attempt_id"]], [row["id"] for row in query_rows])
            whereami = _cli_json(workspace, ["ait", "whereami", "--json"])
            self.assertEqual(payload["attempt_id"], whereami["detected_context"]["attempt_id"])
            self.assertTrue(whereami["detected_context"]["is_ait_workspace"])
            _assert_decision_contract(whereami["next_action"])
            self.assertEqual(whereami["current_state"], whereami["next_action"]["current_state"])

    def test_local_only_workflow_uses_unix_socket_and_repo_local_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            repo = parent / "repo"
            _init_git_repo(repo)
            init_repo(repo)
            _commit_ait_gitignore_if_needed(repo)
            socket_families: list[int] = []
            real_socket = socket.socket

            def guarded_socket(
                family: int = socket.AF_INET,
                type: int = socket.SOCK_STREAM,
                proto: int = 0,
                fileno: int | None = None,
            ):
                if family in {socket.AF_INET, socket.AF_INET6}:
                    raise AssertionError(f"AIT attempted to create a network socket family={family}")
                socket_families.append(family)
                return real_socket(family, type, proto, fileno=fileno)

            with patch("socket.socket", side_effect=guarded_socket):
                server = bind_unix_socket(repo / ".ait" / "daemon.sock")
                try:
                    daemon = daemon_status(repo)
                    self.assertTrue(daemon.socket_connectable)
                    self.assertTrue(_is_relative_to(daemon.socket_path, repo / ".ait"))

                    status_payload = _cli_json(repo, ["ait", "status", "--json"])
                    self.assertIn("recovery", status_payload)
                    _assert_decision_contract(status_payload["next_action"])
                    self.assertEqual(
                        status_payload["agent_state"]["current_state"],
                        status_payload["next_action"]["current_state"],
                    )

                    intent = create_intent(repo, title="Local-only product claim", description=None, kind="test")
                    attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id="codex:local")
                    attempt_rows = _cli_jsonl(
                        repo,
                        [
                            "ait",
                            "attempt",
                            "list",
                            "--intent",
                            intent.intent_id,
                            "--format",
                            "jsonl",
                        ],
                    )
                    query_rows = _cli_jsonl(
                        repo,
                        [
                            "ait",
                            "query",
                            "--on",
                            "attempt",
                            f'id="{attempt.attempt_id}"',
                            "--format",
                            "jsonl",
                        ],
                    )
                finally:
                    server.close()
                    remove_socket_file(repo / ".ait" / "daemon.sock")

            self.assertIn(socket.AF_UNIX, socket_families)
            self.assertEqual([attempt.attempt_id], [row["id"] for row in attempt_rows])
            self.assertEqual([attempt.attempt_id], [row["id"] for row in query_rows])
            self.assertTrue((repo / ".ait" / "state.sqlite3").exists())
            self.assertEqual([repo / ".ait"], sorted(parent.rglob(".ait")))

    def test_parallel_agents_same_task_keep_attempt_records_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            init_repo(repo)
            _commit_ait_gitignore_if_needed(repo)
            intent = create_intent(repo, title="Parallel product claim", description=None, kind="test")
            root_head = _git_stdout(repo, "rev-parse", "--verify", "HEAD")
            root_status = _git_stdout(repo, "status", "--short")
            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()
            processes = [
                ctx.Process(
                    target=_parallel_attempt_worker,
                    args=(str(repo), intent.intent_id, label, queue),
                )
                for label in ("alpha", "beta")
            ]

            for process in processes:
                process.start()

            results = [queue.get(timeout=30.0) for _ in processes]

            for process in processes:
                process.join(timeout=10.0)
                self.assertEqual(0, process.exitcode)

            errors = [result for result in results if result["status"] != "ok"]
            self.assertEqual([], errors)
            by_label = {str(result["label"]): result for result in results}
            attempt_ids = [str(result["attempt_id"]) for result in results]
            workspace_refs = [Path(str(result["workspace_ref"])) for result in results]
            self.assertEqual(2, len(set(attempt_ids)))
            self.assertEqual(2, len(set(workspace_refs)))
            self.assertEqual(root_head, _git_stdout(repo, "rev-parse", "--verify", "HEAD"))
            self.assertEqual(root_status, _git_stdout(repo, "status", "--short"))
            self.assertFalse((repo / "agent-alpha.txt").exists())
            self.assertFalse((repo / "agent-beta.txt").exists())
            for label, result in by_label.items():
                workspace = Path(str(result["workspace_ref"]))
                self.assertTrue(_is_relative_to(workspace, repo / ".ait" / "workspaces"))
                self.assertTrue((workspace / f"agent-{label}.txt").exists())
                self.assertEqual("succeeded", result["verified_status"])
                self.assertEqual([f"agent-{label}.txt"], result["changed_files"])

            query_rows = _cli_jsonl(
                repo,
                [
                    "ait",
                    "query",
                    "--on",
                    "attempt",
                    'title~"Parallel product claim"',
                    "--format",
                    "jsonl",
                ],
            )
            self.assertEqual(set(attempt_ids), {str(row["id"]) for row in query_rows})

            discarded_id = str(by_label["alpha"]["attempt_id"])
            promoted_id = str(by_label["beta"]["attempt_id"])
            discarded_workspace = Path(str(by_label["alpha"]["workspace_ref"]))
            promoted_workspace = Path(str(by_label["beta"]["workspace_ref"]))
            discard_payload = _cli_json(repo, ["ait", "attempt", "discard", discarded_id])
            self.assertEqual("discarded", discard_payload["attempt"]["verified_status"])
            self.assertFalse(discarded_workspace.exists())
            survivor = _cli_json(repo, ["ait", "attempt", "show", promoted_id])
            self.assertEqual("succeeded", survivor["attempt"]["verified_status"])
            self.assertTrue(promoted_workspace.exists())

            promote_payload = _cli_json(repo, ["ait", "attempt", "promote", promoted_id, "--to", "parallel/promoted"])

            self.assertEqual("promoted", promote_payload["attempt"]["verified_status"])
            self.assertEqual("main", _git_stdout(repo, "branch", "--show-current"))
            self.assertEqual(root_head, _git_stdout(repo, "rev-parse", "--verify", "HEAD"))
            self.assertEqual(root_status, _git_stdout(repo, "status", "--short"))
            self.assertEqual(
                promote_payload["commits"][-1]["commit_oid"],
                _git_stdout(repo, "rev-parse", "--verify", "refs/heads/parallel/promoted"),
            )
            discarded = _cli_json(repo, ["ait", "attempt", "show", discarded_id])
            self.assertEqual("discarded", discarded["attempt"]["verified_status"])

    def test_parallel_promote_same_target_does_not_silently_overwrite_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            init_repo(repo)
            _commit_ait_gitignore_if_needed(repo)
            intent = create_intent(repo, title="Parallel promote race", description=None, kind="test")
            attempts: dict[str, dict[str, object]] = {}
            for label in ("alpha", "beta"):
                attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id=f"codex:{label}")
                workspace = Path(attempt.workspace_ref)
                rel_path = f"promote-{label}.txt"
                (workspace / rel_path).write_text(f"{label}\n", encoding="utf-8")
                _git(workspace, "add", rel_path)
                shown = create_commit_for_attempt(repo, attempt_id=attempt.attempt_id, message=f"{label} result")
                attempts[label] = {
                    "attempt_id": attempt.attempt_id,
                    "workspace_ref": attempt.workspace_ref,
                    "commit_oid": shown.commits[-1]["commit_oid"],
                }

            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()
            start = ctx.Event()
            processes = [
                ctx.Process(
                    target=_parallel_promote_worker,
                    args=(str(repo), str(data["attempt_id"]), "race/shared-target", start, queue),
                )
                for data in attempts.values()
            ]
            for process in processes:
                process.start()
            start.set()
            results = [queue.get(timeout=30.0) for _ in processes]
            for process in processes:
                process.join(timeout=10.0)
                self.assertEqual(0, process.exitcode)

            successes = [result for result in results if result["status"] == "ok"]
            errors = [result for result in results if result["status"] == "error"]
            self.assertEqual(1, len(successes), results)
            self.assertEqual(1, len(errors), results)
            self.assertIn("target ref changed since the attempt base", str(errors[0]["message"]))
            promoted_oid = _git_stdout(repo, "rev-parse", "--verify", "refs/heads/race/shared-target")
            self.assertEqual(successes[0]["commit_oid"], promoted_oid)
            losing_attempt = _cli_json(repo, ["ait", "attempt", "show", str(errors[0]["attempt_id"])])
            self.assertEqual("succeeded", losing_attempt["attempt"]["verified_status"])
            self.assertIsNone(losing_attempt["attempt"]["result_promotion_ref"])

    def test_next_json_contract_covers_common_agent_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            init_repo(repo)
            _commit_ait_gitignore_if_needed(repo)

            idle = _cli_json(repo, ["ait", "next", "--json"])
            _assert_decision_contract(idle)
            self.assertEqual("idle", idle["current_state"])
            self.assertEqual("ait status --json", idle["recommended_command"])

            (repo / "scratch.txt").write_text("local\n", encoding="utf-8")
            dirty = _cli_json(repo, ["ait", "next", "--json"], expected=1)
            _assert_decision_contract(dirty)
            self.assertEqual("dirty_worktree", dirty["current_state"])
            self.assertIn("git status --short", dirty["recommended_command"])
            self.assertTrue(dirty["blocking_reasons"])
            (repo / "scratch.txt").unlink()

            intent = create_intent(repo, title="Decision contract", description=None, kind="test")
            attempt = create_attempt(repo, intent_id=intent.intent_id)
            workspace = Path(attempt.workspace_ref)

            workspace_idle = _cli_json(workspace, ["ait", "next", "--json"])
            _assert_decision_contract(workspace_idle)
            self.assertEqual("ait_workspace_idle", workspace_idle["current_state"])
            self.assertEqual("ait status --json", workspace_idle["recommended_command"])

            (workspace / "result.txt").write_text("result\n", encoding="utf-8")
            _git(workspace, "add", "result.txt")
            create_commit_for_attempt(repo, attempt_id=attempt.attempt_id, message="result")
            recorded = _cli_json(workspace, ["ait", "next", "--json"])
            _assert_decision_contract(recorded)
            self.assertEqual("recorded_result_ready", recorded["current_state"])
            self.assertEqual("ait merge --to main --dry-run --json", recorded["recommended_command"])

            _git(repo, "checkout", "-b", "feature/decision-contract")
            (repo / "branch.txt").write_text("branch\n", encoding="utf-8")
            _git(repo, "add", "branch.txt")
            _git(repo, "commit", "-m", "branch ahead")
            branch = _cli_json(repo, ["ait", "next", "--to", "main", "--json"])
            _assert_decision_contract(branch)
            self.assertEqual("branch_ahead_of_target", branch["current_state"])
            self.assertEqual("ait merge --to main --dry-run --json", branch["recommended_command"])

    def test_next_reconcile_and_merge_dry_run_for_manual_workspace_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="manual", description=None, kind="test")
            attempt = create_attempt(repo, intent_id=intent.intent_id)
            _commit_ait_gitignore_if_needed(repo)
            workspace = Path(attempt.workspace_ref)
            _git(workspace, "config", "user.email", "test@example.com")
            _git(workspace, "config", "user.name", "Test User")
            (workspace / "manual.txt").write_text("manual\n", encoding="utf-8")
            _git(workspace, "add", "manual.txt")
            _git(workspace, "commit", "-m", "manual commit")

            next_payload = _cli_json(workspace, ["ait", "next", "--json"])

            _assert_decision_contract(next_payload)
            self.assertEqual("manual_commit_without_recorded_result", next_payload["current_state"])
            self.assertEqual("ait reconcile --json", next_payload["recommended_command"])

            reconcile_payload = _cli_json(workspace, ["ait", "reconcile", "--json"])

            self.assertTrue(reconcile_payload["synthetic_result_created"])
            self.assertEqual(attempt.attempt_id, reconcile_payload["attempt_id"])
            self.assertEqual(["manual.txt"], reconcile_payload["changed_files"])

            merge_payload = _cli_json(workspace, ["ait", "merge", "--to", "main", "--dry-run", "--json"])

            self.assertEqual("planned", merge_payload["status"])
            self.assertTrue(any(op["command"][:2] == ["ait", "apply"] for op in merge_payload["operations"]))
            self.assertEqual(attempt.attempt_id, merge_payload["detected_context"]["attempt_id"])

    def test_merge_blocks_dirty_worktree_with_actionable_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _git(repo, "checkout", "-b", "feature")
            (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
            _git(repo, "add", "feature.txt")
            _git(repo, "commit", "-m", "feature")
            (repo / "scratch.txt").write_text("local\n", encoding="utf-8")

            payload = _cli_json(repo, ["ait", "merge", "--to", "main", "--dry-run", "--json"], expected=1)

            self.assertEqual("blocked", payload["status"])
            self.assertEqual("DIRTY_WORKTREE", payload["error"]["error_code"])
            self.assertTrue(payload["error"]["user_data_safe"])
            self.assertIn("git status --short", payload["recommended_commands"])

    def test_branch_merge_fast_forward_executes_without_deleting_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _git(repo, "checkout", "-b", "feature")
            (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
            _git(repo, "add", "feature.txt")
            _git(repo, "commit", "-m", "feature")

            dry_run = _cli_json(repo, ["ait", "merge", "--to", "main", "--mode", "ff-only", "--dry-run", "--json"])
            self.assertEqual("planned", dry_run["status"])

            payload = _cli_json(repo, ["ait", "merge", "--to", "main", "--mode", "ff-only", "--json"])

            self.assertEqual("merged", payload["status"])
            self.assertEqual("main", _git_stdout(repo, "branch", "--show-current"))
            self.assertEqual("feature\n", (repo / "feature.txt").read_text(encoding="utf-8"))

    def test_adapter_doctor_reports_local_cli_auth_without_api_key_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _init_git_repo(repo)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            claude = bin_dir / "claude"
            claude.write_text("#!/bin/sh\nprintf 'claude local\\n'\n", encoding="utf-8")
            claude.chmod(0o755)
            with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", "ANTHROPIC_API_KEY": "sk-test"}):
                payload = _cli_json(repo, ["ait", "adapter", "doctor", "claude-code", "--json"])

            auth = payload["agent_auth"]
            self.assertEqual("local_cli", auth["auth_mode"])
            self.assertFalse(auth["will_use_api_key"])
            self.assertFalse(auth["will_fallback_to_credits"])
            self.assertTrue(auth["api_key_env_present"])

    def test_review_report_json_and_markdown_include_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="review", description=None, kind="test")
            attempt = create_attempt(repo, intent_id=intent.intent_id)
            workspace = Path(attempt.workspace_ref)
            (workspace / "review.txt").write_text("review\n", encoding="utf-8")
            _git(workspace, "add", "review.txt")
            create_commit_for_attempt(repo, attempt_id=attempt.attempt_id, message="review")

            report = _cli_json(repo, ["ait", "review", "report", "--attempt", attempt.attempt_id, "--json"])

            self.assertEqual(attempt.attempt_id, report["attempt_id"])
            self.assertEqual(["review.txt"], report["changed_files"])
            self.assertIn("final_approval_status", report)

            md_path = repo / "docs" / "reviews" / "attempt.md"
            output = _cli_text(
                repo,
                [
                    "ait",
                    "review",
                    "report",
                    "--attempt",
                    attempt.attempt_id,
                    "--format",
                    "markdown",
                    "--output",
                    str(md_path),
                ],
            )
            self.assertIn("Wrote", output)
            self.assertIn("# AIT Review Report", md_path.read_text(encoding="utf-8"))


def _cli_json(cwd: Path, argv: list[str], *, expected: int = 0) -> dict[str, object]:
    out = io.StringIO()
    with chdir(cwd):
        with patch("sys.argv", argv):
            with redirect_stdout(out):
                code = cli.main()
    if code != expected:
        raise AssertionError(f"exit {code}, expected {expected}; output={out.getvalue()}")
    return json.loads(out.getvalue())


def _cli_text(cwd: Path, argv: list[str], *, expected: int = 0) -> str:
    out = io.StringIO()
    with chdir(cwd):
        with patch("sys.argv", argv):
            with redirect_stdout(out):
                code = cli.main()
    if code != expected:
        raise AssertionError(f"exit {code}, expected {expected}; output={out.getvalue()}")
    return out.getvalue()


def _cli_jsonl(cwd: Path, argv: list[str], *, expected: int = 0) -> list[dict[str, object]]:
    text = _cli_text(cwd, argv, expected=expected)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _parallel_attempt_worker(repo_root: str, intent_id: str, label: str, queue) -> None:
    try:
        repo = Path(repo_root)
        attempt = create_attempt(repo, intent_id=intent_id, agent_id=f"codex:{label}")
        workspace = Path(attempt.workspace_ref)
        rel_path = f"agent-{label}.txt"
        (workspace / rel_path).write_text(f"{label} result\n", encoding="utf-8")
        _git(workspace, "add", rel_path)
        shown = create_commit_for_attempt(repo, attempt_id=attempt.attempt_id, message=f"{label} result")
        queue.put(
            {
                "status": "ok",
                "label": label,
                "attempt_id": attempt.attempt_id,
                "workspace_ref": attempt.workspace_ref,
                "verified_status": shown.attempt["verified_status"],
                "changed_files": list(shown.files.get("changed", ())),
            }
        )
    except BaseException as exc:
        queue.put({"status": "error", "label": label, "type": type(exc).__name__, "message": str(exc)})


def _parallel_promote_worker(repo_root: str, attempt_id: str, target_ref: str, start, queue) -> None:
    try:
        start.wait(timeout=10.0)
        promoted = promote_attempt(repo_root, attempt_id=attempt_id, target_ref=target_ref)
        queue.put(
            {
                "status": "ok",
                "attempt_id": attempt_id,
                "commit_oid": promoted.commits[-1]["commit_oid"],
            }
        )
    except BaseException as exc:
        queue.put(
            {
                "status": "error",
                "attempt_id": attempt_id,
                "type": type(exc).__name__,
                "message": str(exc),
            }
        )


def _assert_decision_contract(payload: object) -> None:
    if not isinstance(payload, dict):
        raise AssertionError("decision payload must be a JSON object")
    required = {
        "current_state",
        "detected_context",
        "safe_actions",
        "unsafe_actions",
        "recommended_command",
        "blocking_reasons",
        "recovery_commands",
    }
    missing = required.difference(payload)
    if missing:
        raise AssertionError(f"decision payload missing keys: {sorted(missing)}")
    if not isinstance(payload["detected_context"], dict):
        raise AssertionError("detected_context must be an object")
    for key in ("safe_actions", "unsafe_actions", "blocking_reasons", "recovery_commands"):
        if not isinstance(payload[key], list):
            raise AssertionError(f"{key} must be a list")
    if not payload["recommended_command"]:
        raise AssertionError("recommended_command must be populated for agent workflows")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _commit_ait_gitignore_if_needed(repo_root: Path) -> None:
    status = _git_stdout(repo_root, "status", "--short", "--", ".gitignore")
    if not status:
        return
    _git(repo_root, "add", ".gitignore")
    _git(repo_root, "commit", "-m", "chore: ignore ait state")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_stdout(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@contextmanager
def chdir(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


if __name__ == "__main__":
    unittest.main()
