from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.submitter import SubmitResult, submit


class GhSubmitTests(unittest.TestCase):
    def _fake_run(self, returncode=0, stdout="", stderr=""):
        m = mock.Mock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_gh_happy_path(self):
        with mock.patch("ait.bug_report.submitter.which", return_value="/usr/bin/gh"), \
             mock.patch("ait.bug_report.submitter._gh_auth_ok", return_value=True), \
             mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = self._fake_run(
                returncode=0,
                stdout="https://github.com/m24927605/ait/issues/123\n",
            )
            result = submit(title="t", body="b",
                            browser_opener=lambda _u: True)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.method, "gh")
            self.assertEqual(result.issue_url,
                             "https://github.com/m24927605/ait/issues/123")

    def test_gh_missing_falls_through(self):
        with mock.patch("ait.bug_report.submitter.which", return_value=None), \
             mock.patch("ait.bug_report.submitter._gh_auth_ok", return_value=False):
            opens = []
            result = submit(title="t", body="b",
                            browser_opener=lambda u: (opens.append(u) or True))
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.method, "url")
            self.assertEqual(len(opens), 1)

    def test_gh_nonzero_exit_falls_through(self):
        with mock.patch("ait.bug_report.submitter.which", return_value="/usr/bin/gh"), \
             mock.patch("ait.bug_report.submitter._gh_auth_ok", return_value=True), \
             mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = self._fake_run(returncode=1, stderr="oops")
            opens = []
            result = submit(title="t", body="b",
                            browser_opener=lambda u: (opens.append(u) or True))
            self.assertEqual(result.method, "url")

    def test_gh_timeout_falls_through(self):
        with mock.patch("ait.bug_report.submitter.which", return_value="/usr/bin/gh"), \
             mock.patch("ait.bug_report.submitter._gh_auth_ok", return_value=True), \
             mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=15)):
            opens = []
            result = submit(title="t", body="b",
                            browser_opener=lambda u: (opens.append(u) or True))
            self.assertEqual(result.method, "url")


if __name__ == "__main__":
    unittest.main()
