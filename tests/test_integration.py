from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import create_attempt, create_commit_for_attempt, create_intent
from ait.cleanup import CleanupPolicy, cleanup_repo
from ait.integration import classify_paths, create_integration_attempt, dirty_snapshot
from ait.workspace_lease import read_workspace_lease


class IntegrationTests(unittest.TestCase):
    def test_dirty_snapshot_clean_tracked_untracked_staged_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            (repo / "deleted.txt").write_text("delete\n", encoding="utf-8")
            _git(repo, "add", "tracked.txt", "deleted.txt")
            _git(repo, "commit", "-m", "tracked files")

            clean = dirty_snapshot(repo)
            self.assertEqual((), clean.tracked)
            self.assertEqual((), clean.untracked)

            (repo / "tracked.txt").write_text("edit\n", encoding="utf-8")
            (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
            _git(repo, "add", "staged.txt")
            (repo / "deleted.txt").unlink()
            (repo / "untracked.txt").write_text("local\n", encoding="utf-8")

            snap = dirty_snapshot(repo)
            tracked = {item.path: item for item in snap.tracked}
            self.assertIn("tracked.txt", tracked)
            self.assertIn("staged.txt", tracked)
            self.assertIn("deleted.txt", tracked)
            self.assertTrue(snap.index_dirty)
            self.assertEqual(("untracked.txt",), tuple(item.path for item in snap.untracked))
            self.assertIsNotNone(tracked["tracked.txt"].worktree_sha256)

    def test_path_classification_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            (repo / "user.txt").write_text("local\n", encoding="utf-8")
            _git(repo, "add", "user.txt")
            _git(repo, "commit", "-m", "user base")
            (repo / "user.txt").write_text("local edit\n", encoding="utf-8")
            snap = dirty_snapshot(repo)

            safe = classify_paths(snap, agent_paths=("agent.txt",), agent_statuses={"agent.txt": "A"})
            self.assertEqual("safe_non_overlap", safe.classification)
            self.assertEqual("integration.safe_non_overlap", safe.reason_code)

            text = classify_paths(snap, agent_paths=("user.txt",), agent_statuses={"user.txt": "M"})
            self.assertEqual("text_overlap", text.classification)

            binary = classify_paths(snap, agent_paths=("user.txt",), agent_statuses={"user.txt": "M"}, agent_binary_paths=("user.txt",))
            self.assertEqual("binary_overlap", binary.classification)

            delete = classify_paths(snap, agent_paths=("user.txt",), agent_statuses={"user.txt": "D"})
            self.assertEqual("delete_overlap", delete.classification)

            rename = classify_paths(snap, agent_paths=("user.txt",), agent_statuses={"user.txt": "R"})
            self.assertEqual("rename_overlap", rename.classification)

            (repo / "new.txt").write_text("mine\n", encoding="utf-8")
            with_untracked = dirty_snapshot(repo)
            untracked = classify_paths(with_untracked, agent_paths=("new.txt",), agent_statuses={"new.txt": "A"})
            self.assertEqual("untracked_conflict", untracked.classification)

    def test_safe_non_overlap_integration_writes_artifacts_and_keeps_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            base_root = _root_fingerprint(repo)
            _attempt_id, _workspace = _succeeded_attempt(repo, "agent", "agent.txt", "agent\n")
            (repo / "README.md").write_text("local\n", encoding="utf-8")

            result = create_integration_attempt(repo, attempt_selector="latest")

            self.assertEqual("integration_created", result.status)
            self.assertEqual("safe_non_overlap", result.plan.classification)
            self.assertTrue(Path(result.workspace_ref or "").exists())
            self.assertTrue(Path(result.patch_artifact_ref or "").exists())
            self.assertTrue(Path(result.result_artifact_ref or "").exists())
            payload = json.loads(Path(result.result_artifact_ref or "").read_text(encoding="utf-8"))
            self.assertEqual("integration", payload["kind"])
            self.assertEqual("safe_non_overlap", payload["classification"])
            self.assertEqual("local\n", (repo / "README.md").read_text(encoding="utf-8"))
            self.assertEqual(base_root["head"], _root_fingerprint(repo)["head"])

    def test_text_overlap_non_conflicting_hunks_auto_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo, readme="a\nb\nc\nd\n")
            _attempt_id, _workspace = _succeeded_attempt(repo, "agent overlap", "README.md", "a\nB-agent\nc\nd\n")
            (repo / "README.md").write_text("a\nb\nc\nD-local\n", encoding="utf-8")

            result = create_integration_attempt(repo, attempt_selector="latest")

            self.assertEqual("integration_created", result.status)
            self.assertEqual("text_overlap", result.plan.classification)
            merged = Path(result.workspace_ref or "", "README.md").read_text(encoding="utf-8")
            self.assertEqual("a\nB-agent\nc\nD-local\n", merged)
            self.assertEqual("a\nb\nc\nD-local\n", (repo / "README.md").read_text(encoding="utf-8"))

    def test_text_overlap_conflict_retains_integration_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo, readme="base\n")
            _attempt_id, _workspace = _succeeded_attempt(repo, "agent conflict", "README.md", "agent\n")
            (repo / "README.md").write_text("local\n", encoding="utf-8")

            result = create_integration_attempt(repo, attempt_selector="latest")

            self.assertEqual("conflict", result.status)
            self.assertEqual("integration.merge_file_conflict", result.decision_report.reasons[0].code)
            self.assertEqual(("README.md",), result.decision_report.reasons[0].paths)
            self.assertEqual("text_overlap", result.decision_report.reasons[0].debug["classification"])
            self.assertTrue(Path(result.workspace_ref or "").exists())
            lease = read_workspace_lease(result.workspace_ref or "")
            self.assertIsNotNone(lease)
            self.assertEqual("conflict", lease.state if lease else None)
            self.assertEqual("local\n", (repo / "README.md").read_text(encoding="utf-8"))

    def test_untracked_and_binary_overlap_hold_without_modifying_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _attempt_id, _workspace = _succeeded_attempt(repo, "untracked", "new.txt", "agent\n")
            (repo / "new.txt").write_text("local\n", encoding="utf-8")

            result = create_integration_attempt(repo, attempt_selector="latest")

            self.assertEqual("held", result.status)
            self.assertEqual("integration.untracked_conflict", result.decision_report.reasons[0].code)
            self.assertEqual("local\n", (repo / "new.txt").read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            (repo / "bin.dat").write_bytes(b"base\0data")
            _git(repo, "add", "bin.dat")
            _git(repo, "commit", "-m", "binary")
            _attempt_id, _workspace = _succeeded_attempt_bytes(repo, "binary", "bin.dat", b"agent\0data")
            (repo / "bin.dat").write_bytes(b"local\0data")

            result = create_integration_attempt(repo, attempt_selector="latest")

            self.assertEqual("held", result.status)
            self.assertEqual("integration.binary_overlap", result.decision_report.reasons[0].code)
            self.assertEqual(b"local\0data", (repo / "bin.dat").read_bytes())

    def test_integration_success_can_be_applied_and_text_outputs_hide_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _attempt_id, _workspace = _succeeded_attempt(repo, "agent", "agent.txt", "agent\n")
            (repo / "README.md").write_text("local\n", encoding="utf-8")

            create_out = io.StringIO()
            with chdir(repo):
                with patch("sys.argv", ["ait", "recover", "latest", "--create-integration"]):
                    with redirect_stdout(create_out):
                        create_code = cli.main()

            self.assertEqual(0, create_code)
            self.assertNotIn(".ait/workspaces", create_out.getvalue())

            apply_out = io.StringIO()
            with chdir(repo):
                with patch("sys.argv", ["ait", "apply", "latest"]):
                    with redirect_stdout(apply_out):
                        apply_code = cli.main()

            self.assertEqual(0, apply_code)
            self.assertEqual("agent\n", (repo / "agent.txt").read_text(encoding="utf-8"))
            self.assertEqual("local\n", (repo / "README.md").read_text(encoding="utf-8"))

    def test_debug_and_json_include_integration_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _attempt_id, _workspace = _succeeded_attempt(repo, "agent", "agent.txt", "agent\n")
            (repo / "README.md").write_text("local\n", encoding="utf-8")

            debug = io.StringIO()
            json_out = io.StringIO()
            with chdir(repo):
                with patch("sys.argv", ["ait", "recover", "latest", "--create-integration", "--debug"]):
                    with redirect_stdout(debug):
                        self.assertEqual(0, cli.main())
                with patch("sys.argv", ["ait", "recover", "latest", "--format", "json", "--debug"]):
                    with redirect_stdout(json_out):
                        self.assertEqual(0, cli.main())

            self.assertIn(".ait/workspaces", debug.getvalue())
            self.assertIn("Strategy:", debug.getvalue())
            payload = json.loads(json_out.getvalue())
            self.assertIn("workspace_ref", payload)
            self.assertIn("decision_report", payload)
            self.assertIn("classification", payload["debug"])
            self.assertIn("debug", payload["decision_report"]["reasons"][0])
            self.assertIn("paths", payload["decision_report"]["reasons"][0])

    def test_cleanup_gates_integration_workspace_with_durable_artifact_and_dev_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _attempt_id, _workspace = _succeeded_attempt(repo, "agent", "agent.txt", "agent\n")
            (repo / "README.md").write_text("local\n", encoding="utf-8")
            result = create_integration_attempt(repo, attempt_selector="latest")

            report = cleanup_repo(repo, CleanupPolicy(apply=True))

            item = next(item for item in report.items if item.attempt_id == result.attempt_id)
            self.assertEqual("retain", item.action)
            self.assertEqual("reviewable", item.reason)
            self.assertTrue(Path(result.workspace_ref or "").exists())


def _succeeded_attempt(repo_root: Path, title: str, rel_path: str, content: str) -> tuple[str, Path]:
    return _succeeded_attempt_bytes(repo_root, title, rel_path, content.encode("utf-8"))


def _succeeded_attempt_bytes(repo_root: Path, title: str, rel_path: str, content: bytes) -> tuple[str, Path]:
    intent = create_intent(repo_root, title=title, description=None, kind="test")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id)
    workspace = Path(attempt.workspace_ref)
    target = workspace / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    _git(workspace, "add", rel_path)
    create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message=title)
    return attempt.attempt_id, workspace


def _init_git_repo(repo_root: Path, *, readme: str = "hello\n") -> None:
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text(readme, encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _root_fingerprint(repo_root: Path) -> dict[str, str]:
    return {
        "head": _git_stdout(repo_root, "rev-parse", "--verify", "HEAD"),
        "status": _git_stdout(repo_root, "status", "--short"),
    }


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_root, check=True, text=True, capture_output=True)


def _git_stdout(repo_root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo_root, check=True, text=True, capture_output=True).stdout.strip()


if __name__ == "__main__":
    unittest.main()
