from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.config import (
    DEFAULT_DAEMON_SOCKET_PATH,
    GITIGNORE_ENTRY,
    LocalConfig,
    bootstrap_ait_dir,
    ensure_ait_ignored,
    ensure_local_config,
    load_local_config,
    save_local_config,
)
from ait.policy import effective_policy
from ait.repo import derive_repo_id, get_root_commit_oid
from ait.review_policy import review_policy_requires_escalation


class ConfigTests(unittest.TestCase):
    def test_bootstrap_ait_dir_creates_expected_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            ait_dir = bootstrap_ait_dir(repo_root)

            resolved_root = repo_root.resolve()
            self.assertEqual(ait_dir, resolved_root / ".ait")
            self.assertTrue((resolved_root / ".ait").is_dir())
            self.assertTrue((resolved_root / ".ait" / "objects").is_dir())

    def test_save_and_load_local_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            expected = LocalConfig(
                install_nonce="nonce-123",
                daemon_socket_path=".ait/custom.sock",
                reaper_ttl_seconds=600,
            )

            save_local_config(repo_root, expected)

            loaded = load_local_config(repo_root)
            self.assertEqual(loaded, expected)
            self.assertEqual([], list((repo_root / ".ait").glob("config.json.*.tmp")))

    def test_ensure_local_config_creates_and_reuses_install_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            created = ensure_local_config(repo_root)
            loaded = load_local_config(repo_root)
            reused = ensure_local_config(repo_root)

            self.assertIsNotNone(created.install_nonce)
            self.assertEqual(created, loaded)
            self.assertEqual(created.install_nonce, reused.install_nonce)
            self.assertEqual(created.daemon_socket_path, DEFAULT_DAEMON_SOCKET_PATH)
            self.assertIsNone(created.repo_identity)

    def test_ensure_ait_ignored_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            first = ensure_ait_ignored(repo_root)
            second = ensure_ait_ignored(repo_root)
            gitignore_contents = (repo_root / ".gitignore").read_text(encoding="utf-8")

            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual(gitignore_contents, f"{GITIGNORE_ENTRY}\n")

    def test_derive_repo_id_uses_root_commit_and_install_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._init_git_repo(repo_root)

            root_commit = get_root_commit_oid(repo_root)
            repo_id = derive_repo_id(repo_root, "nonce-xyz")

            self.assertEqual(repo_id, f"{root_commit}:nonce-xyz")

    def test_derive_repo_id_uses_unborn_identity_without_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)

            repo_id = derive_repo_id(repo_root, "nonce-xyz")

            self.assertRegex(repo_id, r"^unborn:[0-9a-f]{24}:nonce-xyz$")

    def test_review_policy_defaults_to_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            bootstrap_ait_dir(repo_root)

            result = effective_policy(repo_root)

            self.assertEqual("never", result.policy["review"]["default_mode"])
            self.assertFalse(result.policy["review"]["auto_apply_requires_review"])
            self.assertEqual([], result.policy["review"]["sensitive_paths"])

    def test_invalid_review_policy_values_fall_back_with_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ait_dir = bootstrap_ait_dir(repo_root)
            (ait_dir / "config.json").write_text(
                json.dumps(
                    {
                        "review": {
                            "default_mode": "always",
                            "auto_apply_requires_review": "yes",
                            "allow_override": "no",
                            "sensitive_paths": "auth/**",
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = effective_policy(repo_root)

            self.assertEqual("never", result.policy["review"]["default_mode"])
            self.assertFalse(result.policy["review"]["auto_apply_requires_review"])
            self.assertTrue(result.policy["review"]["allow_override"])
            self.assertEqual([], result.policy["review"]["sensitive_paths"])
            self.assertIn("review.default_mode invalid; using never", result.warnings)
            self.assertIn("review.auto_apply_requires_review invalid; using false", result.warnings)
            self.assertIn("review.allow_override invalid; using true", result.warnings)
            self.assertIn("review.sensitive_paths invalid; using []", result.warnings)

    def test_configured_sensitive_path_requires_risk_based_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ait_dir = bootstrap_ait_dir(repo_root)
            (ait_dir / "config.json").write_text(
                json.dumps(
                    {
                        "review": {
                            "default_mode": "risk-based",
                            "sensitive_paths": ["infra/**"],
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(
                review_policy_requires_escalation(
                    repo_root,
                    changed_files=("infra/main.tf",),
                    risk_level="medium",
                )
            )
            self.assertFalse(
                review_policy_requires_escalation(
                    repo_root,
                    changed_files=("docs/readme.md",),
                    risk_level="medium",
                )
            )

    def _init_git_repo(self, repo_root: Path) -> None:
        subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
