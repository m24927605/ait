from __future__ import annotations

import unittest

from ait.transcript import normalize_transcript


class TranscriptTests(unittest.TestCase):
    def test_codex_normalization_removes_progress_noise_but_keeps_conversation(self) -> None:
        raw = "\n".join(
            [
                "› Summarize recent commits   gpt-5.5 medium",
                "WorkingWorkingWorking",
                "› 你是誰?",
                "• 我是 Codex，一個 AI coding agent。",
                "Token usage: total=10 input=8 output=2",
                "To continue this session, run codex resume 019dd9ba-fc1a",
            ]
        )

        normalized = normalize_transcript(raw, adapter="codex")

        self.assertNotIn("WorkingWorking", normalized)
        self.assertNotIn("Summarize recent commits", normalized)
        self.assertIn("› 你是誰?", normalized)
        self.assertIn("我是 Codex", normalized)
        self.assertIn("codex resume 019dd9ba", normalized)


if __name__ == "__main__":
    unittest.main()
