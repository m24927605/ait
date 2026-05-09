from __future__ import annotations

import unittest

from ait.review_parser import ReviewOutputParseError, parse_review_output


class ReviewParserTests(unittest.TestCase):
    def test_parses_raw_json(self) -> None:
        parsed = parse_review_output(
            """
            {
              "summary": "No blocking issues found.",
              "findings": [
                {
                  "severity": "low",
                  "blocking": false,
                  "path": "src/app.py",
                  "title": "Missing edge test",
                  "body": "The branch lacks a regression test.",
                  "confidence": "high"
                }
              ]
            }
            """
        )

        self.assertEqual("No blocking issues found.", parsed.summary)
        self.assertEqual(1, len(parsed.findings))
        self.assertEqual("low", parsed.findings[0].severity)
        self.assertFalse(parsed.findings[0].blocking)
        self.assertEqual("src/app.py", parsed.findings[0].path)
        self.assertEqual("high", parsed.findings[0].confidence)

    def test_parses_fenced_json(self) -> None:
        parsed = parse_review_output(
            """
            Here is the review:

            ```json
            {
              "summary": "One issue.",
              "findings": [
                {
                  "severity": "critical",
                  "path": "src/auth.py",
                  "title": "Bypass",
                  "body": "The owner check is skipped.",
                  "line": "42"
                }
              ]
            }
            ```
            """
        )

        self.assertEqual("critical", parsed.findings[0].severity)
        self.assertTrue(parsed.findings[0].blocking)
        self.assertEqual(42, parsed.findings[0].line)

    def test_rejects_plain_prose(self) -> None:
        with self.assertRaises(ReviewOutputParseError):
            parse_review_output("Looks good to me.")

    def test_rejects_malformed_json(self) -> None:
        with self.assertRaises(ReviewOutputParseError):
            parse_review_output('{"summary": "bad", "findings": [}')

    def test_rejects_non_object_top_level(self) -> None:
        with self.assertRaises(ReviewOutputParseError):
            parse_review_output("[]")

    def test_rejects_missing_findings_list(self) -> None:
        with self.assertRaises(ReviewOutputParseError):
            parse_review_output('{"summary": "missing"}')

    def test_rejects_high_finding_missing_path_title_or_body(self) -> None:
        with self.assertRaisesRegex(ReviewOutputParseError, "missing required fields"):
            parse_review_output(
                """
                {
                  "summary": "bad",
                  "findings": [
                    {
                      "severity": "high",
                      "title": "Auth issue",
                      "body": "Ownership is not checked."
                    }
                  ]
                }
                """
            )

    def test_unknown_severity_fails_closed(self) -> None:
        with self.assertRaisesRegex(ReviewOutputParseError, "unknown severity"):
            parse_review_output(
                """
                {
                  "summary": "bad",
                  "findings": [
                    {
                      "severity": "severe",
                      "path": "src/app.py",
                      "title": "Issue",
                      "body": "Details."
                    }
                  ]
                }
                """
            )

    def test_normalizes_documented_severity_alias(self) -> None:
        parsed = parse_review_output(
            """
            {
              "summary": "warn",
              "findings": [
                {
                  "severity": "warning",
                  "path": "src/app.py",
                  "title": "Issue",
                  "body": "Details."
                }
              ]
            }
            """
        )

        self.assertEqual("medium", parsed.findings[0].severity)

    def test_rejects_non_boolean_blocking(self) -> None:
        with self.assertRaisesRegex(ReviewOutputParseError, "blocking"):
            parse_review_output(
                """
                {
                  "summary": "bad",
                  "findings": [
                    {
                      "severity": "low",
                      "blocking": "false",
                      "path": "src/app.py",
                      "title": "Issue",
                      "body": "Details."
                    }
                  ]
                }
                """
            )


if __name__ == "__main__":
    unittest.main()
