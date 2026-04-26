from __future__ import annotations

import unittest

from dataclasses import asdict

from ait.adapters import AdapterError, get_adapter, list_adapters


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


if __name__ == "__main__":
    unittest.main()
