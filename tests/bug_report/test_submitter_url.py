from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.submitter import URL_MAX, build_prefill_url, submit


class UrlSubmitTests(unittest.TestCase):
    def test_prefill_url_encodes_title_and_body(self):
        url = build_prefill_url("a title", "b & body")
        self.assertIn("title=a+title", url)
        self.assertIn("body=b+%26+body", url)
        self.assertTrue(url.startswith(
            "https://github.com/m24927605/ait/issues/new"))

    def test_url_too_long_defers(self):
        big = "X" * (URL_MAX + 5000)
        with mock.patch("ait.bug_report.submitter.which", return_value=None):
            opens = []
            result = submit(title="t", body=big,
                            browser_opener=lambda u: opens.append(u) or True)
            self.assertEqual(result.status, "deferred")
            self.assertEqual(opens, [])

    def test_browser_open_false_defers(self):
        with mock.patch("ait.bug_report.submitter.which", return_value=None):
            result = submit(title="t", body="b",
                            browser_opener=lambda _u: False)
            self.assertEqual(result.status, "deferred")


if __name__ == "__main__":
    unittest.main()
