from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.context_manifest import build_context_manifest_payload
from ait.metadata_bundle import export_metadata_bundle
from ait.memory.models import RelevantMemoryItem, RelevantMemoryRecall
from ait.runner import run_agent_command
from ait.team_policy import default_team_policy


class TeamReadinessTests(unittest.TestCase):
    def test_policy_validate_missing_uses_default_schema_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            payload, exit_code = _run_cli_json(
                repo_root,
                ["ait", "policy", "validate", "--format", "json"],
            )

            contract = _fixture("team_policy", "schema_v1_contract.json")
            self.assertEqual(0, exit_code)
            self.assertEqual(contract["schema"], payload["schema"])
            self.assertEqual(contract["schema_version"], payload["schema_version"])
            self.assertEqual(contract["top_level_keys"], sorted(payload.keys()))
            self.assertEqual("default", payload["source"])
            self.assertEqual("valid", payload["status"])
            self.assertEqual(contract["policy_schema"], payload["policy"]["schema"])
            self.assertEqual(contract["policy_keys"], sorted(payload["policy"].keys()))

    def test_policy_validate_rejects_candidate_trusted_memory_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            policy = default_team_policy()
            policy["memory"]["trusted_statuses"] = ["accepted", "candidate"]
            (repo_root / ".ait").mkdir()
            (repo_root / ".ait" / "policy.json").write_text(
                json.dumps(policy, indent=2),
                encoding="utf-8",
            )

            payload, exit_code = _run_cli_json(
                repo_root,
                ["ait", "policy", "validate", "--format", "json"],
            )

            self.assertEqual(2, exit_code)
            self.assertEqual("invalid", payload["status"])
            self.assertTrue(any("candidate" in error for error in payload["errors"]))

    def test_apply_policy_require_review_clearance_blocks_without_clear_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            result = run_agent_command(
                repo_root,
                intent_title="Policy apply gate",
                agent_id="shell:test",
                command=[sys.executable, "-c", "from pathlib import Path; Path('gate.txt').write_text('ok\\n')"],
                refresh_reports=False,
            )
            _write_policy(repo_root, default_team_policy())

            payload, exit_code = _run_cli_json(
                repo_root,
                ["ait", "apply", result.attempt_id, "--dry-run", "--format", "json"],
            )

            contract = _fixture("team_policy_enforcement", "schema_v1_contract.json")
            self.assertEqual(2, exit_code)
            self.assertEqual(contract["schema"], payload["schema"])
            self.assertEqual(contract["schema_version"], payload["schema_version"])
            self.assertEqual(contract["top_level_keys"], sorted(payload.keys()))
            self.assertEqual("apply", payload["operation"])
            self.assertEqual("blocked", payload["status"])
            self.assertEqual("blocked", _check_status(payload, "apply_review_clearance"))

    def test_invalid_policy_blocks_apply_review_console_and_context_trust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            result = run_agent_command(
                repo_root,
                intent_title="Invalid policy gate",
                agent_id="shell:test",
                command=[sys.executable, "-c", "from pathlib import Path; Path('invalid.txt').write_text('ok\\n')"],
                refresh_reports=False,
            )
            policy = default_team_policy()
            policy["memory"]["trusted_statuses"] = ["accepted", "candidate"]
            _write_policy(repo_root, policy)

            apply_payload, apply_exit = _run_cli_json(
                repo_root,
                ["ait", "apply", result.attempt_id, "--dry-run", "--format", "json"],
            )
            review_payload, review_exit = _run_cli_json(
                repo_root,
                ["ait", "review", "attempt", "latest-reviewable", "--format", "json"],
            )
            console_payload, console_exit = _run_cli_json(
                repo_root,
                [
                    "ait",
                    "console",
                    "action",
                    "apply",
                    "--attempt",
                    result.attempt_id,
                    "--dry-run",
                    "--format",
                    "json",
                ],
            )

            for payload, exit_code, operation in (
                (apply_payload, apply_exit, "apply"),
                (review_payload, review_exit, "review"),
            ):
                self.assertEqual(2, exit_code)
                self.assertEqual("ait.team_policy.enforcement", payload["schema"])
                self.assertEqual(operation, payload["operation"])
                self.assertEqual("blocked", payload["status"])
                self.assertEqual("blocked", _check_status(payload, "team_policy_valid"))
                self.assertEqual("invalid", payload["policy_validation"]["status"])

            self.assertEqual(1, console_exit)
            self.assertEqual("blocked", console_payload["status"])
            self.assertEqual("blocked", console_payload["policy_enforcement"]["status"])
            self.assertEqual("blocked", _check_status(console_payload["policy_enforcement"], "team_policy_valid"))

            with self.assertRaisesRegex(Exception, "candidate"):
                build_context_manifest_payload(
                    repo_root,
                    owner_kind="test",
                    owner_id="invalid-policy",
                    context_ref="",
                    recall=_recall_with_secret_source("visible body", source_file_path="docs/policy.md"),
                    context_text="",
                )

    def test_console_actions_disabled_blocks_console_action_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            result = run_agent_command(
                repo_root,
                intent_title="Console policy gate",
                agent_id="shell:test",
                command=[sys.executable, "-c", "from pathlib import Path; Path('console.txt').write_text('ok\\n')"],
                refresh_reports=False,
            )
            policy = default_team_policy()
            policy["console"]["actions_enabled"] = False
            policy["apply"]["require_review_clearance"] = False
            _write_policy(repo_root, policy)

            payload, exit_code = _run_cli_json(
                repo_root,
                [
                    "ait",
                    "console",
                    "action",
                    "apply",
                    "--attempt",
                    result.attempt_id,
                    "--dry-run",
                    "--format",
                    "json",
                ],
            )

            self.assertEqual(1, exit_code)
            self.assertEqual("blocked", payload["status"])
            self.assertEqual("blocked", payload["policy_enforcement"]["status"])
            self.assertEqual("blocked", _check_status(payload["policy_enforcement"], "console_actions_enabled"))

    def test_review_policy_never_blocks_review_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            policy = default_team_policy()
            policy["review"]["default_mode"] = "never"
            _write_policy(repo_root, policy)

            payload, exit_code = _run_cli_json(
                repo_root,
                ["ait", "review", "attempt", "latest-reviewable", "--format", "json"],
            )

            self.assertEqual(2, exit_code)
            self.assertEqual("review", payload["operation"])
            self.assertEqual("blocked", payload["status"])
            self.assertEqual("blocked", _check_status(payload, "review_policy_available"))

    def test_memory_block_paths_exclude_selected_fact_from_context_trust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            policy = default_team_policy()
            policy["memory"]["block_paths"] = ["secret/**"]
            _write_policy(repo_root, policy)

            payload = build_context_manifest_payload(
                repo_root,
                owner_kind="test",
                owner_id="team-policy-memory",
                context_ref="",
                recall=_recall_with_secret_source(
                    "DO_NOT_LEAK_TEAM_POLICY_MEMORY",
                    source_file_path="secret/auth.md",
                ),
                context_text="",
            )

            entry = next(item for item in payload["entries"] if item["source_id"] == "fact:team-policy-secret")
            self.assertEqual("policy_blocked", entry["trust_level"])
            self.assertEqual("policy_blocked", entry["reason"])
            self.assertNotIn("fact:team-policy-secret", payload["trusted_baseline_refs"])
            self.assertNotIn("DO_NOT_LEAK_TEAM_POLICY_MEMORY", json.dumps(payload))

    def test_metadata_export_dry_run_uses_schema_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            output = repo_root / "bundle.json"

            payload, exit_code = _run_cli_json(
                repo_root,
                [
                    "ait",
                    "metadata",
                    "export",
                    "--output",
                    str(output),
                    "--dry-run",
                    "--format",
                    "json",
                ],
            )

            contract = _fixture("metadata_bundle", "schema_v1_contract.json")
            self.assertEqual(0, exit_code)
            self.assertEqual(contract["schema"], payload["schema"])
            self.assertEqual(contract["schema_version"], payload["schema_version"])
            self.assertEqual(contract["top_level_keys"], sorted(payload.keys()))
            self.assertEqual(contract["object_count_keys"], sorted(payload["object_counts"].keys()))
            self.assertTrue(payload["dry_run"])
            self.assertFalse(payload["output"]["written"])
            self.assertFalse(output.exists())
            self.assertIn("no remote sync", payload["limitations"])

    def test_metadata_import_dry_run_plans_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            bundle = export_metadata_bundle(repo_root, dry_run=True)
            bundle_path = repo_root / "bundle.json"
            bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

            payload, exit_code = _run_cli_json(
                repo_root,
                [
                    "ait",
                    "metadata",
                    "import",
                    "--input",
                    str(bundle_path),
                    "--dry-run",
                    "--format",
                    "json",
                ],
            )

            contract = _fixture("metadata_import_plan", "schema_v1_contract.json")
            self.assertEqual(0, exit_code)
            self.assertEqual(contract["schema"], payload["schema"])
            self.assertEqual(contract["schema_version"], payload["schema_version"])
            self.assertEqual(contract["top_level_keys"], sorted(payload.keys()))
            self.assertEqual("planned", payload["status"])
            self.assertTrue(payload["dry_run"])
            self.assertFalse(payload["will_write"])


def _run_cli_json(repo_root: Path, argv: list[str]) -> tuple[dict[str, object], int]:
    stdout = io.StringIO()
    with chdir(repo_root):
        with patch("sys.argv", argv):
            with redirect_stdout(stdout):
                exit_code = cli.main()
    return json.loads(stdout.getvalue()), exit_code


def _fixture(directory: str, filename: str) -> dict[str, object]:
    return json.loads(
        (Path(__file__).parent / "fixtures" / directory / filename).read_text(
            encoding="utf-8"
        )
    )


def _write_policy(repo_root: Path, policy: dict[str, object]) -> None:
    (repo_root / ".ait").mkdir(exist_ok=True)
    (repo_root / ".ait" / "policy.json").write_text(
        json.dumps(policy, indent=2),
        encoding="utf-8",
    )


def _check_status(payload: dict[str, object], name: str) -> str | None:
    for check in payload.get("checks", []):
        if isinstance(check, dict) and check.get("name") == name:
            return str(check.get("status"))
    return None


def _recall_with_secret_source(body: str, *, source_file_path: str) -> RelevantMemoryRecall:
    item = RelevantMemoryItem(
        kind="fact",
        id="fact:team-policy-secret",
        source="manual",
        topic="policy",
        score=1.0,
        text=body,
        metadata={
            "status": "accepted",
            "source_file_path": source_file_path,
        },
    )
    return RelevantMemoryRecall(
        query="team policy memory",
        selected=(item,),
        skipped=(),
        budget_chars=4000,
        rendered_chars=len(body),
        compacted=False,
    )


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
