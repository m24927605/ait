from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.review_adapter import ReviewAdapterError, _adapter_env, run_review_adapter


class ReviewAdapterEnvTests(unittest.TestCase):
    def test_default_adapter_env_filters_generic_secret_names(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin",
                "LANG": "C.UTF-8",
                "SECRET_TOKEN": "fixture-secret",
                "AWS_SECRET_ACCESS_KEY": "fixture-secret",
            },
            clear=True,
        ):
            env = _adapter_env(
                ("PATH", "LANG", "SECRET_TOKEN", "AWS_SECRET_ACCESS_KEY"),
                explicit_allowlist=(),
            )

        self.assertEqual({"PATH": "/usr/bin", "LANG": "C.UTF-8"}, env)

    def test_explicit_allowlist_can_pass_specific_var(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin",
                "AIT_REVIEW_SAFE": "allowed",
                "SECRET_TOKEN": "fixture-secret",
            },
            clear=True,
        ):
            env = _adapter_env(
                ("PATH",),
                explicit_allowlist=("AIT_REVIEW_SAFE", "SECRET_TOKEN"),
            )

        self.assertEqual(
            {
                "PATH": "/usr/bin",
                "AIT_REVIEW_SAFE": "allowed",
                "SECRET_TOKEN": "fixture-secret",
            },
            env,
        )

    def test_missing_local_cli_reports_no_api_key_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_bin = Path(tmp) / "bin"
            empty_bin.mkdir()
            with patch.dict(os.environ, {"PATH": str(empty_bin)}, clear=True):
                with self.assertRaises(ReviewAdapterError) as raised:
                    run_review_adapter(
                        Path(tmp),
                        review_id="review:test",
                        adapter="codex",
                        brief="review brief",
                    )

        message = str(raised.exception)
        self.assertIn("does not fall back to provider API keys", message)
        self.assertIn("review.adapters.codex.env_allowlist", message)


if __name__ == "__main__":
    unittest.main()
