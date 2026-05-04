from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.shell_integration import (
    END_MARKER,
    START_MARKER,
    detect_user_shell,
    is_shell_integration_installed,
)


class CliShellTests(unittest.TestCase):
    def test_shell_show_outputs_snippet_without_writing_files(self) -> None:
        stdout = io.StringIO()

        with patch("sys.argv", ["ait", "shell", "show", "--shell", "zsh"]):
            with redirect_stdout(stdout):
                exit_code = cli.main()

        text = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn(START_MARKER, text)
        self.assertIn("add-zsh-hook chpwd _ait_auto_path", text)
        self.assertIn(END_MARKER, text)

    def test_shell_install_json_writes_rc_file_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc_path = Path(tmp) / ".zshrc"
            first_stdout = io.StringIO()
            second_stdout = io.StringIO()

            with patch(
                "sys.argv",
                ["ait", "shell", "install", "--shell", "zsh", "--rc-path", str(rc_path), "--format", "json"],
            ):
                with redirect_stdout(first_stdout):
                    first_exit = cli.main()
            with patch(
                "sys.argv",
                ["ait", "shell", "install", "--shell", "zsh", "--rc-path", str(rc_path), "--format", "json"],
            ):
                with redirect_stdout(second_stdout):
                    second_exit = cli.main()

            first = json.loads(first_stdout.getvalue())
            second = json.loads(second_stdout.getvalue())
            rc_text = rc_path.read_text(encoding="utf-8")

        self.assertEqual(0, first_exit)
        self.assertEqual(0, second_exit)
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(str(rc_path), first["rc_path"])
        self.assertEqual(1, rc_text.count(START_MARKER))

    def test_shell_uninstall_removes_marker_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc_path = Path(tmp) / ".bashrc"
            install_stdout = io.StringIO()
            uninstall_stdout = io.StringIO()

            with patch(
                "sys.argv",
                ["ait", "shell", "install", "--shell", "bash", "--rc-path", str(rc_path)],
            ):
                with redirect_stdout(install_stdout):
                    install_exit = cli.main()
            with patch(
                "sys.argv",
                ["ait", "shell", "uninstall", "--shell", "bash", "--rc-path", str(rc_path), "--format", "json"],
            ):
                with redirect_stdout(uninstall_stdout):
                    uninstall_exit = cli.main()

            payload = json.loads(uninstall_stdout.getvalue())
            rc_text = rc_path.read_text(encoding="utf-8")

        self.assertEqual(0, install_exit)
        self.assertEqual(0, uninstall_exit)
        self.assertTrue(payload["changed"])
        self.assertNotIn(START_MARKER, rc_text)


class ShellIntegrationHelperTests(unittest.TestCase):
    def test_detect_user_shell_returns_known_shell(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
            self.assertEqual("zsh", detect_user_shell())
        with patch.dict("os.environ", {"SHELL": "/usr/bin/bash"}):
            self.assertEqual("bash", detect_user_shell())

    def test_detect_user_shell_returns_none_for_unknown(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
            self.assertIsNone(detect_user_shell())
        with patch.dict("os.environ", {"SHELL": ""}):
            self.assertIsNone(detect_user_shell())

    def test_is_shell_integration_installed_true_after_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc_path = Path(tmp) / ".zshrc"
            rc_path.write_text(
                "echo hi\n"
                + START_MARKER
                + "\n_ait_auto_path() { :; }\n"
                + END_MARKER
                + "\n",
                encoding="utf-8",
            )

            self.assertTrue(
                is_shell_integration_installed("zsh", rc_path=rc_path)
            )

    def test_is_shell_integration_installed_false_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc_path = Path(tmp) / ".zshrc"
            self.assertFalse(
                is_shell_integration_installed("zsh", rc_path=rc_path)
            )

            rc_path.write_text("echo hi\n", encoding="utf-8")
            self.assertFalse(
                is_shell_integration_installed("zsh", rc_path=rc_path)
            )

    def test_is_shell_integration_installed_false_for_unsupported_shell(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc_path = Path(tmp) / ".fishrc"
            rc_path.write_text(START_MARKER + "\n" + END_MARKER + "\n", encoding="utf-8")
            self.assertFalse(
                is_shell_integration_installed("fish", rc_path=rc_path)
            )


if __name__ == "__main__":
    unittest.main()
