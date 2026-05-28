from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.redactor import redact, redact_argv


class RedactTests(unittest.TestCase):
    def test_home_replaced(self):
        home = os.path.expanduser("~")
        self.assertIn("~/projects/foo", redact(f"{home}/projects/foo"))

    def test_gh_token_redacted(self):
        s = "token=ghp_" + "A" * 36
        self.assertIn("[REDACTED_TOKEN]", redact(s))
        self.assertNotIn("ghp_", redact(s))

    def test_openai_key_redacted(self):
        s = "key=sk-" + "B" * 32
        self.assertIn("[REDACTED_TOKEN]", redact(s))

    def test_email_redacted(self):
        s = "from alice@example.com to me"
        self.assertIn("[REDACTED_EMAIL]", redact(s))
        self.assertNotIn("alice@example.com", redact(s))

    def test_passthrough_safe_text(self):
        s = "plain stack trace line"
        self.assertEqual(redact(s), s)

    def test_unset_home_does_not_replace_tildes(self):
        saved = os.environ.pop("HOME", None)
        try:
            # When HOME is unset, expanduser("~") returns "~" — must NOT
            # replace literal ~ characters in the input.
            self.assertEqual(redact("a ~ b ~ c"), "a ~ b ~ c")
        finally:
            if saved is not None:
                os.environ["HOME"] = saved


class RedactArgvTests(unittest.TestCase):
    def test_space_separated(self):
        argv = ["ait", "run", "--api-key", "secret123", "--intent", "foo"]
        out = redact_argv(argv)
        self.assertEqual(out, ["ait", "run", "--api-key", "[REDACTED]",
                               "--intent", "foo"])

    def test_equals_joined(self):
        argv = ["ait", "run", "--token=abc", "--intent=foo"]
        out = redact_argv(argv)
        self.assertEqual(out, ["ait", "run", "--token=[REDACTED]",
                               "--intent=foo"])

    def test_password_flag(self):
        argv = ["x", "--password", "p"]
        self.assertEqual(redact_argv(argv), ["x", "--password", "[REDACTED]"])

    def test_unknown_flag_untouched(self):
        argv = ["x", "--foo", "bar"]
        self.assertEqual(redact_argv(argv), ["x", "--foo", "bar"])

    def test_trailing_sensitive_flag(self):
        argv = ["x", "--api-key"]  # no value
        self.assertEqual(redact_argv(argv), ["x", "--api-key"])


if __name__ == "__main__":
    unittest.main()
