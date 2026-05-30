from __future__ import annotations

import unittest


class EnoentHintTests(unittest.TestCase):
    def test_hint_helper_for_prose_positional_with_claude_code_adapter(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _enoent_command_hint

        adapter = get_adapter("claude-code")
        hint = _enoent_command_hint(
            command=["implement per docs/foo.md; follow checklist"],
            adapter=adapter,
        )
        # Should suggest the right wrapping:
        # ait run [opts] -- claude -p "<prompt>"
        self.assertIn("claude -p", hint)
        self.assertIn("ait run", hint)

    def test_hint_omitted_when_command_looks_like_valid_binary_name(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _enoent_command_hint

        adapter = get_adapter("claude-code")
        hint = _enoent_command_hint(
            command=["nonexistent-binary"],
            adapter=adapter,
        )
        # Bare token (no spaces) — operator probably just typo'd a
        # binary name; do NOT suggest the prompt-wrap form.
        self.assertEqual("", hint)

    def test_hint_omitted_for_shell_adapter(self) -> None:
        # Shell adapter has no command_name, so the hint isn't
        # applicable — there's no agent to wrap the prompt in.
        from ait.adapter_registry import get_adapter
        from ait.runner import _enoent_command_hint

        adapter = get_adapter("shell")
        hint = _enoent_command_hint(
            command=["implement per docs/foo.md; follow checklist"],
            adapter=adapter,
        )
        self.assertEqual("", hint)

    def test_hint_truncates_long_prompts(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _enoent_command_hint

        adapter = get_adapter("claude-code")
        long_prompt = "implement per docs/foo.md " * 50  # 1300+ chars
        hint = _enoent_command_hint(command=[long_prompt], adapter=adapter)
        self.assertIn("…", hint)
        self.assertLess(len(hint), 200)


if __name__ == "__main__":
    unittest.main()
