from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli


class LiveMemorySourcesTests(unittest.TestCase):
    def test_memory_sources_is_zero_touch_and_lists_repo_local_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("Claude project policy.\n", encoding="utf-8")
            (repo_root / "AGENTS.md").write_text("Codex project policy.\n", encoding="utf-8")
            (repo_root / ".cursor").mkdir()
            (repo_root / ".cursor" / "rules").write_text("Cursor project policy.\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "sources", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            by_id = {item["source_id"]: item for item in payload}

            self.assertEqual(0, exit_code)
            self.assertFalse((repo_root / ".ait").exists())
            self.assertIn("live:claude:CLAUDE.md", by_id)
            self.assertIn("live:codex:AGENTS.md", by_id)
            self.assertIn("live:cursor:.cursor/rules", by_id)
            for item in by_id.values():
                self.assertEqual("allowed", item["policy_status"])
                self.assertTrue(item["sha256"])
                self.assertIsNotNone(item["mtime"])
                self.assertGreater(item["size_bytes"], 0)

    def test_memory_sources_does_not_scan_global_by_default_and_requires_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            repo_root.mkdir()
            (home / ".claude").mkdir(parents=True)
            global_memory = home / ".claude" / "memory.md"
            global_memory.write_text("GLOBAL_ONLY_LIVE_MEMORY\n", encoding="utf-8")
            _init_git_repo(repo_root)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch.dict(os.environ, {"HOME": str(home)}):
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "memory", "sources", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
                    with patch("sys.argv", ["ait", "memory", "sources", "--global"]):
                        with redirect_stderr(stderr):
                            global_without_path_exit = cli.main()
                    with patch(
                        "sys.argv",
                        [
                            "ait",
                            "memory",
                            "sources",
                            "--global",
                            "--path",
                            str(global_memory),
                            "--format",
                            "json",
                        ],
                    ):
                        explicit_stdout = io.StringIO()
                        with redirect_stdout(explicit_stdout):
                            explicit_exit = cli.main()

            default_payload = json.loads(stdout.getvalue())
            explicit_payload = json.loads(explicit_stdout.getvalue())

            self.assertEqual(0, exit_code)
            self.assertEqual([], default_payload)
            self.assertNotIn("GLOBAL_ONLY_LIVE_MEMORY", stdout.getvalue())
            self.assertFalse((repo_root / ".ait").exists())
            self.assertEqual(2, global_without_path_exit)
            self.assertIn("explicit --path", stderr.getvalue())
            self.assertEqual(0, explicit_exit)
            self.assertEqual(1, len(explicit_payload))
            self.assertEqual("global", explicit_payload[0]["scope"])
            self.assertTrue(explicit_payload[0]["source_id"].startswith("live:custom:global:"))

    def test_memory_sources_rejects_unsafe_symlink_and_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            outside = Path(tmp) / "outside.md"
            repo_root.mkdir()
            outside.write_text("outside memory\n", encoding="utf-8")
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").symlink_to(outside)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "sources", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()
                traversal_stdout = io.StringIO()
                with patch("sys.argv", ["ait", "memory", "sources", "--path", "../outside.md", "--format", "json"]):
                    with redirect_stdout(traversal_stdout):
                        traversal_exit = cli.main()

            payload = json.loads(stdout.getvalue())
            traversal_payload = json.loads(traversal_stdout.getvalue())

            self.assertEqual(0, exit_code)
            self.assertEqual(0, traversal_exit)
            self.assertFalse(payload[0]["allowed_by_policy"])
            self.assertIn("outside repo", payload[0]["skip_reason"])
            self.assertFalse(traversal_payload[0]["allowed_by_policy"])
            self.assertIn("outside repo", traversal_payload[0]["skip_reason"])
            self.assertFalse((repo_root / ".ait").exists())


def _init_git_repo(repo_root: Path) -> None:
    result = subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
