from __future__ import annotations

import os
import unittest
from unittest import mock


class ShellIntegrationProbeTests(unittest.TestCase):
    def test_probe_detects_all_helpers_present(self) -> None:
        from ait.cli.status_helpers import _shell_integration_probe

        with mock.patch.dict(
            os.environ,
            {
                "AIT_SHELL_PROBE_AIT": "1",
                "AIT_SHELL_PROBE_CONTINUE_SHOULD_CD": "1",
                "AIT_SHELL_PROBE_CONTINUE_REMINDER": "1",
            },
            clear=False,
        ):
            probe = _shell_integration_probe()
        self.assertEqual("defined", probe["ait_wrapper"])
        self.assertEqual("defined", probe["continue_should_cd"])
        self.assertEqual("defined", probe["continue_reminder"])
        self.assertFalse(probe["needs_fix"])

    def test_probe_flags_missing_helpers(self) -> None:
        from ait.cli.status_helpers import _shell_integration_probe

        keys = (
            "AIT_SHELL_PROBE_AIT",
            "AIT_SHELL_PROBE_CONTINUE_SHOULD_CD",
            "AIT_SHELL_PROBE_CONTINUE_REMINDER",
        )
        env_without = {k: v for k, v in os.environ.items() if k not in keys}
        env_without["AIT_SHELL_PROBE_AIT"] = "1"
        with mock.patch.dict(os.environ, env_without, clear=True):
            probe = _shell_integration_probe()
        self.assertEqual("defined", probe["ait_wrapper"])
        self.assertEqual("MISSING", probe["continue_should_cd"])
        self.assertEqual("MISSING", probe["continue_reminder"])
        self.assertTrue(probe["needs_fix"])

    def test_format_probe_emits_fix_lines_when_broken(self) -> None:
        from ait.cli.status_helpers import _format_shell_integration_probe

        text = _format_shell_integration_probe({
            "ait_wrapper": "defined",
            "continue_should_cd": "MISSING",
            "continue_reminder": "MISSING",
            "needs_fix": True,
        })
        self.assertIn("Shell integration", text)
        self.assertIn("MISSING", text)
        self.assertIn('eval "$(ait shell probe-env)"', text)
        self.assertIn("ait shell install", text)

    def test_format_probe_omits_fix_lines_when_clean(self) -> None:
        from ait.cli.status_helpers import _format_shell_integration_probe

        text = _format_shell_integration_probe({
            "ait_wrapper": "defined",
            "continue_should_cd": "defined",
            "continue_reminder": "defined",
            "needs_fix": False,
        })
        self.assertIn("Shell integration", text)
        self.assertNotIn("MISSING", text)
        self.assertNotIn("eval", text)


class ShellProbeEnvSnippetTests(unittest.TestCase):
    def test_emits_three_export_lines_with_command_v_guards(self) -> None:
        from ait.cli.shell import _emit_probe_env

        out = _emit_probe_env()
        self.assertIn("AIT_SHELL_PROBE_AIT", out)
        self.assertIn("AIT_SHELL_PROBE_CONTINUE_SHOULD_CD", out)
        self.assertIn("AIT_SHELL_PROBE_CONTINUE_REMINDER", out)
        # Each helper check must use `command -v` so the snippet
        # exits cleanly even when helpers are absent.
        self.assertEqual(3, out.count("command -v"))


if __name__ == "__main__":
    unittest.main()
