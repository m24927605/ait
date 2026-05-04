from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.cli.init_helpers import _maybe_auto_install_shell_hook
from ait.shell_integration import END_MARKER, START_MARKER


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )


class _FakeAdapterItem:
    """Minimal stand-in for AdapterBootstrapResult."""

    def __init__(self, name: str) -> None:
        class _Adapter:
            pass

        self.adapter = _Adapter()
        self.adapter.name = name


class MaybeAutoInstallShellHookTests(unittest.TestCase):
    def test_skip_flag_returns_skipped(self) -> None:
        result = _maybe_auto_install_shell_hook(
            skip=True,
            installed_adapters=[_FakeAdapterItem("claude-code")],
        )
        self.assertEqual("skipped", result["status"])
        self.assertIn("--no-shell-install", str(result["reason"]))

    def test_no_adapters_returns_skipped(self) -> None:
        result = _maybe_auto_install_shell_hook(
            skip=False,
            installed_adapters=[],
        )
        self.assertEqual("skipped", result["status"])
        self.assertIn("no adapters", str(result["reason"]))

    def test_unsupported_shell_returns_skipped(self) -> None:
        with patch.dict(os.environ, {"SHELL": "/usr/bin/fish"}):
            result = _maybe_auto_install_shell_hook(
                skip=False,
                installed_adapters=[_FakeAdapterItem("claude-code")],
            )
        self.assertEqual("skipped", result["status"])
        self.assertIn("zsh", str(result["reason"]))

    def test_zsh_writes_hook_into_rc_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.dict(os.environ, {"SHELL": "/bin/zsh", "HOME": str(home)}):
                result = _maybe_auto_install_shell_hook(
                    skip=False,
                    installed_adapters=[_FakeAdapterItem("claude-code")],
                )
            rc_path = home / ".zshrc"
            self.assertEqual("installed", result["status"])
            self.assertEqual("zsh", result["shell"])
            self.assertEqual(str(rc_path), result["rc_path"])
            self.assertTrue(rc_path.exists())
            text = rc_path.read_text(encoding="utf-8")
            self.assertIn(START_MARKER, text)
            self.assertIn(END_MARKER, text)

    def test_idempotent_returns_already_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            rc_path = home / ".zshrc"
            rc_path.write_text(
                START_MARKER + "\n_ait_auto_path() { :; }\n" + END_MARKER + "\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SHELL": "/bin/zsh", "HOME": str(home)}):
                result = _maybe_auto_install_shell_hook(
                    skip=False,
                    installed_adapters=[_FakeAdapterItem("claude-code")],
                )
            self.assertEqual("already_installed", result["status"])
            self.assertEqual("zsh", result["shell"])


class InitCliShellInstallE2ETests(unittest.TestCase):
    def test_init_writes_zsh_hook_when_adapter_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            repo = Path(tmp) / "repo"
            home.mkdir()
            repo.mkdir()
            _init_git_repo(repo)
            cwd = os.getcwd()
            try:
                os.chdir(repo)
                with patch.dict(
                    os.environ,
                    {"SHELL": "/bin/zsh", "HOME": str(home)},
                ):
                    with patch("sys.argv", ["ait", "init", "--format", "json"]):
                        stdout = io.StringIO()
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
                payload = json.loads(stdout.getvalue())
            finally:
                os.chdir(cwd)
            self.assertEqual(0, exit_code)
            shell_install = payload.get("shell_install")
            self.assertIsInstance(shell_install, dict)
            self.assertIn(
                shell_install["status"],
                {"installed", "skipped", "already_installed"},
                shell_install,
            )
            if shell_install["status"] == "installed":
                self.assertEqual("zsh", shell_install["shell"])
                self.assertTrue((home / ".zshrc").exists())

    def test_init_no_shell_install_flag_suppresses_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            repo = Path(tmp) / "repo"
            home.mkdir()
            repo.mkdir()
            _init_git_repo(repo)
            cwd = os.getcwd()
            try:
                os.chdir(repo)
                with patch.dict(
                    os.environ,
                    {"SHELL": "/bin/zsh", "HOME": str(home)},
                ):
                    with patch(
                        "sys.argv",
                        ["ait", "init", "--no-shell-install", "--format", "json"],
                    ):
                        stdout = io.StringIO()
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
                payload = json.loads(stdout.getvalue())
            finally:
                os.chdir(cwd)
            self.assertEqual(0, exit_code)
            self.assertEqual("skipped", payload["shell_install"]["status"])
            self.assertIn(
                "--no-shell-install",
                str(payload["shell_install"]["reason"]),
            )
            self.assertFalse((home / ".zshrc").exists())


if __name__ == "__main__":
    unittest.main()
