from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ait.config import bootstrap_ait_dir
from ait.review_policy import required_review_profiles


class ReviewProfilesTests(unittest.TestCase):
    def test_auth_path_requires_security_and_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            profiles = required_review_profiles(
                repo_root,
                changed_files=("src/auth/session.py",),
                risk_level="high",
            )

            self.assertEqual(("security", "regression"), profiles)

    def test_workflow_path_requires_security(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            profiles = required_review_profiles(
                repo_root,
                changed_files=(".github/workflows/release.yml",),
                risk_level="high",
            )

            self.assertEqual(("security",), profiles)

    def test_migration_path_requires_regression_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            profiles = required_review_profiles(
                repo_root,
                changed_files=("db/migrations/001_add_users.sql",),
                risk_level="high",
            )

            self.assertEqual(("regression", "release"), profiles)

    def test_low_risk_generic_path_does_not_trigger_multi_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            profiles = required_review_profiles(
                repo_root,
                changed_files=("docs/readme.md",),
                risk_level="low",
            )

            self.assertEqual((), profiles)

    def test_required_profiles_are_policy_driven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ait_dir = bootstrap_ait_dir(repo_root)
            (ait_dir / "config.json").write_text(
                json.dumps(
                    {
                        "review": {
                            "required_profiles": {
                                "infra/**": ["security", "release"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            profiles = required_review_profiles(
                repo_root,
                changed_files=("infra/main.tf",),
                risk_level="medium",
            )

            self.assertEqual(("security", "release"), profiles)


if __name__ == "__main__":
    unittest.main()
