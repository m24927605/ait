from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.shell_integration import END_MARKER, START_MARKER


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


if __name__ == "__main__":
    unittest.main()
