from __future__ import annotations

import unittest

from ait.redaction import REDACTION_MARKER, redact_text


class RedactionTests(unittest.TestCase):
    def test_redacts_common_agent_and_service_secrets(self) -> None:
        text = "\n".join(
            [
                "anthropic=sk-ant-api03-" + ("a" * 32),
                "google=AIza" + ("b" * 35),
                "slack=xoxb-" + ("1234567890-" * 4),
                "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature",
                "Authorization: Bearer " + ("c" * 32),
                "db=postgresql://user:pass@example.com:5432/app",
                "-----BEGIN PRIVATE KEY-----\n" + ("A" * 64) + "\n-----END PRIVATE KEY-----",
            ]
        )

        redacted, changed = redact_text(text)

        self.assertTrue(changed)
        self.assertGreaterEqual(redacted.count(REDACTION_MARKER), 7)
        self.assertNotIn("sk-ant-api03", redacted)
        self.assertNotIn("AIza", redacted)
        self.assertNotIn("xoxb-", redacted)
        self.assertNotIn("postgresql://", redacted)
        self.assertNotIn("BEGIN PRIVATE KEY", redacted)

    def test_redacts_tokens_ending_with_underscore_characters(self) -> None:
        token = "sk-" + ("abc_" * 8)

        redacted, changed = redact_text(f"value={token}")

        self.assertTrue(changed)
        self.assertNotIn(token, redacted)


if __name__ == "__main__":
    unittest.main()
