from __future__ import annotations

import unittest

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ait.adapters import (
    AdapterError,
    bootstrap_adapter,
    bootstrap_shell_snippet,
    doctor_adapter,
    doctor_automation,
    enable_available_adapters,
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
        self.assertEqual("claude", adapter.command_name)
        self.assertTrue(adapter.default_with_context)
        self.assertTrue(adapter.native_hooks)
        self.assertEqual("claude-code", adapter.env["AIT_ADAPTER"])
        self.assertIn("Claude Code", adapter.description)

    def test_fixed_binary_adapters_have_context_hints(self) -> None:
        for name in ("aider", "codex", "cursor", "gemini"):
            adapter = get_adapter(name)
            self.assertEqual(name, adapter.command_name)
            self.assertTrue(adapter.default_with_context)
            self.assertEqual(name, adapter.env["AIT_ADAPTER"])
            self.assertIn("AIT_CONTEXT_FILE", adapter.env["AIT_CONTEXT_HINT"])

    def test_list_adapters_returns_sorted_adapters(self) -> None:
        adapters = list_adapters()

        self.assertEqual(
            ["aider", "claude-code", "codex", "cursor", "gemini", "shell"],
            [item.name for item in adapters],
        )
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

    def test_doctor_automation_reports_wrapper_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                setup_adapter("claude-code", repo_root, install_direnv=True)
                os.environ["PATH"] = (
                    str(repo_root / ".ait" / "bin") + os.pathsep + str(bin_dir) + os.pathsep + old_path
                )
                result = doctor_automation("claude-code", repo_root)
            finally:
                os.environ["PATH"] = old_path

        self.assertTrue(result.ok)
        checks = {check.name: check for check in result.checks}
        self.assertTrue(checks["wrapper_file"].ok)
        self.assertTrue(checks["path_wrapper_active"].ok)
        self.assertTrue(checks["envrc_path"].ok)
        self.assertEqual(str(real_claude.resolve()), checks["real_claude_binary"].detail)

    def test_bootstrap_claude_code_installs_wrapper_and_envrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                result = bootstrap_adapter("claude-code", repo_root)
            finally:
                os.environ["PATH"] = old_path

            wrapper_path = repo_root / ".ait" / "bin" / "claude"
            envrc_path = repo_root / ".envrc"

            self.assertEqual("claude-code", result.adapter.name)
            self.assertTrue(wrapper_path.exists())
            self.assertIn("PATH_add .ait/bin", envrc_path.read_text(encoding="utf-8"))
            self.assertIn(str(wrapper_path.resolve()), result.setup.wrote_files)
            self.assertIn(str(envrc_path.resolve()), result.setup.wrote_files)

    def test_bootstrap_aider_installs_wrapper_and_envrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_aider = bin_dir / "aider"
            real_aider.write_text("#!/bin/sh\nprintf 'real aider\\n'\n", encoding="utf-8")
            real_aider.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                result = bootstrap_adapter("aider", repo_root)
            finally:
                os.environ["PATH"] = old_path

            wrapper_path = repo_root / ".ait" / "bin" / "aider"
            wrapper = wrapper_path.read_text(encoding="utf-8")

            self.assertEqual("aider", result.adapter.name)
            self.assertTrue(result.ok)
            self.assertTrue(wrapper_path.exists())
            self.assertIn("PATH_add .ait/bin", (repo_root / ".envrc").read_text(encoding="utf-8"))
            self.assertIn("AIT_WRAPPER_FORMAT=text", wrapper)
            self.assertIn("AIT_WRAPPER_FORMAT=json", wrapper)
            self.assertIn('run --adapter aider --format "$AIT_WRAPPER_FORMAT"', wrapper)
            self.assertIn(str(real_aider.resolve()), wrapper)

    def test_doctor_automation_reports_codex_wrapper_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                setup_adapter("codex", repo_root, install_direnv=True)
                os.environ["PATH"] = (
                    str(repo_root / ".ait" / "bin") + os.pathsep + str(bin_dir) + os.pathsep + old_path
                )
                result = doctor_automation("codex", repo_root)
            finally:
                os.environ["PATH"] = old_path

        checks = {check.name: check for check in result.checks}
        self.assertTrue(result.ok)
        self.assertTrue(checks["wrapper_file"].ok)
        self.assertTrue(checks["path_wrapper_active"].ok)
        self.assertEqual(str(real_codex.resolve()), checks["real_agent_binary"].detail)

    def test_bootstrap_shell_snippet_installs_and_exports_wrapper_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                snippet = bootstrap_shell_snippet("claude-code", repo_root)
            finally:
                os.environ["PATH"] = old_path

            wrapper_path = repo_root / ".ait" / "bin" / "claude"

            self.assertTrue(wrapper_path.exists())
            self.assertEqual(f'export PATH={wrapper_path.parent.resolve()}:"$PATH"', snippet)

    def test_enable_available_adapters_installs_detected_agents_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                result = enable_available_adapters(repo_root, names=("codex",))
            finally:
                os.environ["PATH"] = old_path

            self.assertTrue(result.ok)
            self.assertEqual(("codex",), tuple(item.adapter.name for item in result.installed))
            self.assertTrue((repo_root / ".ait" / "bin" / "codex").exists())
            self.assertFalse((repo_root / ".ait" / "bin" / "aider").exists())
            self.assertIn("PATH_add .ait/bin", (repo_root / ".envrc").read_text(encoding="utf-8"))
            self.assertEqual(
                f'export PATH={(repo_root / ".ait" / "bin").resolve()}:"$PATH"',
                result.shell_snippet,
            )
            self.assertEqual((), result.skipped)

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

    def test_setup_claude_code_can_install_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                result = setup_adapter("claude-code", repo_root, install_wrapper=True)
            finally:
                os.environ["PATH"] = old_path

            wrapper_path = repo_root / ".ait" / "bin" / "claude"
            wrapper = wrapper_path.read_text(encoding="utf-8")

            self.assertEqual(str(wrapper_path.resolve()), result.wrapper_path)
            self.assertIn(str(wrapper_path.resolve()), result.wrote_files)
            self.assertIn(str(real_claude), wrapper)
            self.assertIn("AIT_WRAPPER_FORMAT=text", wrapper)
            self.assertIn("AIT_WRAPPER_FORMAT=json", wrapper)
            self.assertIn('run --adapter claude-code --format "$AIT_WRAPPER_FORMAT"', wrapper)
            self.assertTrue(os.access(wrapper_path, os.X_OK))

    def test_wrapper_reports_missing_real_binary_with_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                setup_adapter("codex", repo_root, install_wrapper=True)
            finally:
                os.environ["PATH"] = old_path
            real_codex.unlink()

            wrapper_path = repo_root / ".ait" / "bin" / "codex"
            completed = subprocess.run(
                [str(wrapper_path), "--version"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(127, completed.returncode)
            self.assertIn("ait wrapper failed: real codex binary not found", completed.stderr)
            self.assertIn("adapter: codex", completed.stderr)
            self.assertIn(f"wrapper: {wrapper_path}", completed.stderr)
            self.assertIn(str(real_codex), completed.stderr)
            self.assertIn("next: run ait status codex", completed.stderr)

    def test_wrapper_reports_recursion_with_init_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_aider = bin_dir / "aider"
            real_aider.write_text("#!/bin/sh\nprintf 'real aider\\n'\n", encoding="utf-8")
            real_aider.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                setup_adapter("aider", repo_root, install_wrapper=True)
            finally:
                os.environ["PATH"] = old_path

            wrapper_path = repo_root / ".ait" / "bin" / "aider"
            wrapper = wrapper_path.read_text(encoding="utf-8")
            wrapper_path.write_text(
                wrapper.replace(
                    f"AIT_WRAPPER_REAL_BINARY={real_aider.resolve()}",
                    f"AIT_WRAPPER_REAL_BINARY={wrapper_path}",
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [str(wrapper_path), "--version"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(126, completed.returncode)
            self.assertIn("ait wrapper failed: wrapper recursion detected", completed.stderr)
            self.assertIn("adapter: aider", completed.stderr)
            self.assertIn("next: run ait init --adapter aider --shell", completed.stderr)

    def test_setup_claude_code_can_install_direnv_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                result = setup_adapter("claude-code", repo_root, install_direnv=True)
            finally:
                os.environ["PATH"] = old_path

            wrapper_path = repo_root / ".ait" / "bin" / "claude"
            direnv_path = repo_root / ".envrc"

            self.assertEqual(str(wrapper_path.resolve()), result.wrapper_path)
            self.assertEqual(str(direnv_path.resolve()), result.direnv_path)
            self.assertIn(str(direnv_path.resolve()), result.wrote_files)
            self.assertTrue(os.access(wrapper_path, os.X_OK))
            self.assertIn("PATH_add .ait/bin", direnv_path.read_text(encoding="utf-8"))

    def test_setup_claude_code_merges_envrc_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp) / "repo")
            envrc_path = repo_root / ".envrc"
            envrc_path.write_text("export FOO=bar\n", encoding="utf-8")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                setup_adapter("claude-code", repo_root, install_direnv=True)
                setup_adapter("claude-code", repo_root, install_direnv=True)
            finally:
                os.environ["PATH"] = old_path

            envrc = envrc_path.read_text(encoding="utf-8")

            self.assertIn("export FOO=bar", envrc)
            self.assertEqual(1, envrc.count("PATH_add .ait/bin"))

    def test_setup_unknown_adapter_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _init_git_repo(Path(tmp))

            with self.assertRaises(AdapterError) as raised:
                setup_adapter("shell", repo_root)

        self.assertIn("not implemented", str(raised.exception))


def _init_git_repo(repo_root: Path) -> Path:
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    return repo_root


if __name__ == "__main__":
    unittest.main()
