from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.builder import BuildInput, build_issue
from ait.bug_report.collector import CollectedEntry
from ait.bug_report.fingerprint import Frame


def _entry(fp="fp:aaaa1111", cat="db.operational", msg="disk fail"):
    return CollectedEntry(
        category=cat,
        exc_type="ValueError",
        exc_message=msg,
        frames=[Frame("foo.py", "bar")],
        fingerprint=fp,
        count=1,
        context=None,
        first_recorded_at="2026-05-28T10:00:00Z",
        last_recorded_at="2026-05-28T10:00:00Z",
    )


class BuilderTests(unittest.TestCase):
    def test_title_includes_category_and_fp(self):
        b = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3",
            python_version="3.14.4",
            os_arch="darwin/arm64",
            argv=["ait", "run"],
            include_tier2=False,
            include_tier3=False,
            install_nonce="abc12345",
            daemon_log_tail="",
            daemon_state="",
            phase="",
            env_vars={},
            extra_transcript=None,
            repo_id=None,
        ))
        self.assertIn("[crash]", b.title)
        self.assertIn("db.operational", b.title)
        self.assertIn("fp:aaaa1111", b.title)

    def test_body_tier1_always_present(self):
        b = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3", python_version="3.14.4",
            os_arch="darwin/arm64", argv=["ait", "run"],
            include_tier2=False, include_tier3=False,
            install_nonce="x", daemon_log_tail="", daemon_state="",
            phase="", env_vars={}, extra_transcript=None, repo_id=None,
        ))
        self.assertIn("AIT: 1.4.3", b.body)
        self.assertIn("Python: 3.14.4", b.body)
        self.assertIn("darwin/arm64", b.body)
        self.assertIn("ait run", b.body)
        self.assertIn("fp:aaaa1111", b.body)

    def test_tier2_gated(self):
        with_t2 = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3", python_version="3.14.4",
            os_arch="darwin/arm64", argv=["ait"],
            include_tier2=True, include_tier3=False,
            install_nonce="abc12345",
            daemon_log_tail="log line 1\nlog line 2",
            daemon_state="running", phase="provision",
            env_vars={}, extra_transcript=None, repo_id=None,
        ))
        self.assertIn("abc12345", with_t2.body)
        self.assertIn("log line 1", with_t2.body)

        no_t2 = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3", python_version="3.14.4",
            os_arch="darwin/arm64", argv=["ait"],
            include_tier2=False, include_tier3=False,
            install_nonce="abc12345",
            daemon_log_tail="log line 1",
            daemon_state="running", phase="provision",
            env_vars={}, extra_transcript=None, repo_id=None,
        ))
        self.assertNotIn("abc12345", no_t2.body)
        self.assertNotIn("log line 1", no_t2.body)

    def test_scope_banner_present(self):
        b = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3", python_version="3.14.4",
            os_arch="darwin/arm64", argv=["ait"],
            include_tier2=False, include_tier3=False,
            install_nonce="x", daemon_log_tail="", daemon_state="",
            phase="", env_vars={}, extra_transcript=None, repo_id=None,
        ))
        self.assertIn("bug in **AIT itself**", b.body)


if __name__ == "__main__":
    unittest.main()
