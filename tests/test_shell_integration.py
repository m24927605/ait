from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ait.shell_integration import (
    END_MARKER,
    START_MARKER,
    ShellIntegrationError,
    install_shell_integration,
    shell_snippet,
    uninstall_shell_integration,
)


class ShellIntegrationTests(unittest.TestCase):
    def test_shell_snippet_contains_auto_path_hook(self) -> None:
        snippet = shell_snippet("zsh")

        self.assertIn(START_MARKER, snippet)
        self.assertIn("_ait_auto_path", snippet)
        self.assertIn("add-zsh-hook -d chpwd _ait_auto_path", snippet)
        self.assertIn("add-zsh-hook chpwd _ait_auto_path", snippet)
        self.assertIn(END_MARKER, snippet)

    def test_bash_snippet_uses_prompt_command(self) -> None:
        snippet = shell_snippet("bash")

        self.assertIn("PROMPT_COMMAND", snippet)
        self.assertIn("_ait_auto_path", snippet)
        self.assertIn('case ";${PROMPT_COMMAND:-};" in', snippet)

    def test_install_is_idempotent_and_uninstall_removes_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc_path = Path(tmp) / ".zshrc"
            rc_path.write_text("export EXISTING=1\n", encoding="utf-8")

            first = install_shell_integration(shell="zsh", rc_path=rc_path)
            second = install_shell_integration(shell="zsh", rc_path=rc_path)

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertEqual(1, rc_path.read_text(encoding="utf-8").count(START_MARKER))

            removed = uninstall_shell_integration(shell="zsh", rc_path=rc_path)

            self.assertTrue(removed.changed)
            self.assertEqual("export EXISTING=1\n", rc_path.read_text(encoding="utf-8"))

    def test_unsupported_shell_raises_clear_error(self) -> None:
        with self.assertRaises(ShellIntegrationError):
            shell_snippet("fish")


if __name__ == "__main__":
    unittest.main()
