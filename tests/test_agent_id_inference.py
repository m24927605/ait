from __future__ import annotations

import unittest


class ResolveAgentIdTests(unittest.TestCase):
    def test_bare_slug_gets_adapter_prefix(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _resolve_agent_id

        adapter = get_adapter("claude-code")
        self.assertEqual(
            "claude-code:backend-architect",
            _resolve_agent_id("backend-architect", adapter),
        )

    def test_already_qualified_is_passthrough(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _resolve_agent_id

        adapter = get_adapter("claude-code")
        self.assertEqual(
            "claude-code:backend-architect",
            _resolve_agent_id("claude-code:backend-architect", adapter),
        )

    def test_other_harness_prefix_is_preserved(self) -> None:
        # User explicitly passes a different harness — don't override
        from ait.adapter_registry import get_adapter
        from ait.runner import _resolve_agent_id

        adapter = get_adapter("claude-code")
        self.assertEqual(
            "manual:reviewer",
            _resolve_agent_id("manual:reviewer", adapter),
        )

    def test_empty_falls_back_to_adapter_default(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _resolve_agent_id

        adapter = get_adapter("claude-code")
        self.assertEqual(adapter.default_agent_id, _resolve_agent_id(None, adapter))
        self.assertEqual(adapter.default_agent_id, _resolve_agent_id("", adapter))

    def test_bare_slug_for_codex_adapter(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _resolve_agent_id

        adapter = get_adapter("codex")
        self.assertEqual(
            "codex:database-optimizer",
            _resolve_agent_id("database-optimizer", adapter),
        )


if __name__ == "__main__":
    unittest.main()
