from __future__ import annotations

import unittest

from ait.adapters import AdapterError, get_adapter


class AdapterTests(unittest.TestCase):
    def test_shell_adapter_defaults_to_no_context(self) -> None:
        adapter = get_adapter("shell")

        self.assertEqual("shell:local", adapter.default_agent_id)
        self.assertFalse(adapter.default_with_context)

    def test_claude_code_adapter_defaults_to_context(self) -> None:
        adapter = get_adapter("claude-code")

        self.assertEqual("claude-code:manual", adapter.default_agent_id)
        self.assertTrue(adapter.default_with_context)
        self.assertEqual("claude-code", adapter.env["AIT_ADAPTER"])

    def test_unknown_adapter_raises_clear_error(self) -> None:
        with self.assertRaises(AdapterError) as raised:
            get_adapter("missing")

        self.assertIn("unknown adapter", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
