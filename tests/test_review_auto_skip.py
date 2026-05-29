from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ait.review_policy import (
    DEFAULT_AUTO_SKIP_GLOBS,
    is_docs_only_change,
    load_review_policy,
)


class IsDocsOnlyChangeTests(unittest.TestCase):
    def test_returns_true_for_pure_markdown_change(self) -> None:
        self.assertTrue(
            is_docs_only_change(
                changed_files=("README.md", "docs/intro.md"),
                globs=DEFAULT_AUTO_SKIP_GLOBS,
            )
        )

    def test_returns_false_when_any_code_file_changed(self) -> None:
        self.assertFalse(
            is_docs_only_change(
                changed_files=("README.md", "src/ait/cli.py"),
                globs=DEFAULT_AUTO_SKIP_GLOBS,
            )
        )

    def test_returns_false_for_empty_change_set(self) -> None:
        # No changes → no review to skip, but auto-skip should NOT
        # claim docs-only on an empty set; let the upstream decide.
        self.assertFalse(
            is_docs_only_change(
                changed_files=(),
                globs=DEFAULT_AUTO_SKIP_GLOBS,
            )
        )

    def test_default_globs_cover_spec_set(self) -> None:
        for pattern in ("**/*.md", "docs/**", "LICENSE*", "CHANGELOG*", "README*"):
            self.assertIn(pattern, DEFAULT_AUTO_SKIP_GLOBS)


class PolicyAutoSkipOverrideTests(unittest.TestCase):
    def test_config_can_override_auto_skip_globs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ait").mkdir()
            (root / ".ait" / "config.json").write_text(
                json.dumps({"review": {"auto_skip_globs": ["custom/**"]}})
            )
            policy = load_review_policy(root)
            self.assertEqual(("custom/**",), policy.auto_skip_globs)

    def test_default_policy_uses_default_globs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # No .ait/config.json → policy defaults
            policy = load_review_policy(root)
            self.assertEqual(DEFAULT_AUTO_SKIP_GLOBS, policy.auto_skip_globs)


if __name__ == "__main__":
    unittest.main()
