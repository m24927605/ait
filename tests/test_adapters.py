from __future__ import annotations

import unittest

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from ait.adapters import (
    AdapterError,
    doctor_adapter,
    get_adapter,
    list_adapters,
    setup_adapter,
)


class AdapterTests(unittest.TestCase):
    def test_shell_adapter_defaults_to_no_context(self) -> None:
        adapter = get_adapter("shell")

        self.assertEqual("shell:local", adapter.default_agent_id)
        self.assertFalse(adapter.default_with_context)

    def test_claude_code_adapter_defaults_to_context(self) -> None:
        adapter = get_adapter("claude-code")

        self.assertEqual("claude-code:manual", adapter.default_agent_id)
        self.assertTrue(adapter.default_with_context)
        self.assertTrue(adapter.native_hooks)
        self.assertEqual("claude-code", adapter.env["AIT_ADAPTER"])
        self.assertIn("Claude Code", adapter.description)

    def test_list_adapters_returns_sorted_adapters(self) -> None:
        adapters = list_adapters()

        self.assertEqual(["aider", "claude-code", "codex", "shell"], [item.name for item in adapters])
        self.assertIn("default_agent_id", asdict(adapters[0]))

    def test_unknown_adapter_raises_clear_error(self) -> None:
        with self.assertRaises(AdapterError) as raised:
            get_adapter("missing")

        self.assertIn("unknown adapter", str(raised.exception))

    def test_doctor_claude_code_passes_in_repo_checkout(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        result = doctor_adapter("claude-code", repo_root)

        self.assertTrue(result.ok)
        self.assertEqual(
            {"git_repo", "ait_importable", "claude_hook_resource", "claude_settings_resource"},
            {check.name for check in result.checks},
        )

    def test_doctor_reports_non_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = doctor_adapter("shell", tmp)

        self.assertFalse(result.ok)
        self.assertIn("git_repo", {check.name for check in result.checks if not check.ok})

    def test_setup_claude_code_writes_hook_and_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp))

            result = setup_adapter("claude-code", repo_root)

            hook_path = repo_root / ".ait" / "adapters" / "claude-code" / "claude_code_hook.py"
            settings_path = repo_root / ".claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))

            self.assertEqual("claude-code", result.adapter.name)
            self.assertTrue(hook_path.exists())
            self.assertIn("Claude Code hook bridge", hook_path.read_text(encoding="utf-8"))
            self.assertIn(str(hook_path.resolve()), result.wrote_files)
            self.assertIn(str(settings_path.resolve()), result.wrote_files)
            self.assertIn("SessionStart", settings["hooks"])
            self.assertIn(sys.executable, json.dumps(settings))
            self.assertIn(".ait/adapters/claude-code/claude_code_hook.py", json.dumps(settings))

    def test_setup_claude_code_merges_existing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp))
            target = repo_root / ".claude" / "settings.json"
            target.parent.mkdir(parents=True)
            target.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "SessionStart": [
                                {"hooks": [{"type": "command", "command": "echo existing"}]}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            setup_adapter("claude-code", repo_root)
            setup_adapter("claude-code", repo_root)
            settings = json.loads(target.read_text(encoding="utf-8"))

        session_start = settings["hooks"]["SessionStart"]
        self.assertEqual(2, len(session_start))
        self.assertEqual("echo existing", session_start[0]["hooks"][0]["command"])

    def test_setup_print_only_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp))

            result = setup_adapter("claude-code", repo_root, print_only=True)

            self.assertFalse((repo_root / ".ait" / "adapters").exists())
            self.assertFalse((repo_root / ".claude").exists())
            self.assertEqual((), result.wrote_files)
            self.assertIsNone(result.settings_path)

    def test_setup_unknown_adapter_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp))

            with self.assertRaises(AdapterError) as raised:
                setup_adapter("shell", repo_root)

        self.assertIn("not implemented", str(raised.exception))


def _init_git_repo(repo_root: Path) -> Path:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    return repo_root


if __name__ == "__main__":
    unittest.main()
