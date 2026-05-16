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
from ait.console_actions import CONSOLE_ACTION_JOURNAL
from ait.runner import run_agent_command


class ConsoleActionTests(unittest.TestCase):
    def test_console_action_apply_dry_run_writes_schema_v1_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            result = run_agent_command(
                repo_root,
                intent_title="Console action apply",
                agent_id="shell:test",
                command=[sys.executable, "-c", "from pathlib import Path; Path('action.py').write_text('ok\\n')"],
                refresh_reports=False,
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
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
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            contract = json.loads(
                (Path(__file__).parent / "fixtures" / "console_action" / "schema_v1_contract.json").read_text(
                    encoding="utf-8"
                )
            )
            journal = repo_root / CONSOLE_ACTION_JOURNAL
            journal_payload = json.loads(journal.read_text(encoding="utf-8").splitlines()[-1])

            self.assertEqual(0, exit_code)
            self.assertEqual(contract["schema"], payload["schema"])
            self.assertEqual(contract["schema_version"], payload["schema_version"])
            self.assertEqual(contract["top_level_keys"], sorted(payload.keys()))
            self.assertEqual("planned", payload["status"])
            self.assertEqual("passed", payload["preflight"]["status"])
            self.assertFalse(payload["will_execute"])
            self.assertEqual(payload["action_id"], journal_payload["action_id"])

    def test_console_action_missing_attempt_records_blocked_failure_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "console",
                        "action",
                        "recover",
                        "--attempt",
                        "missing",
                        "--dry-run",
                        "--format",
                        "json",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            journal_payload = json.loads((repo_root / CONSOLE_ACTION_JOURNAL).read_text(encoding="utf-8").splitlines()[-1])

            self.assertEqual(1, exit_code)
            self.assertEqual("blocked", payload["status"])
            self.assertEqual("blocked", payload["preflight"]["status"])
            self.assertIn("missing", payload["preflight"]["checks"][0]["message"])
            self.assertEqual(payload["action_id"], journal_payload["action_id"])

    def test_console_action_recover_and_discard_dry_run_smoke_write_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            result = run_agent_command(
                repo_root,
                intent_title="Console action smoke",
                agent_id="shell:test",
                command=[sys.executable, "-c", "from pathlib import Path; Path('smoke.py').write_text('ok\\n')"],
                refresh_reports=False,
            )

            payloads = []
            for action in ("recover", "discard"):
                stdout = io.StringIO()
                with chdir(repo_root):
                    with patch(
                        "sys.argv",
                        [
                            "ait",
                            "console",
                            "action",
                            action,
                            "--attempt",
                            result.attempt_id,
                            "--dry-run",
                            "--format",
                            "json",
                        ],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
                payload = json.loads(stdout.getvalue())
                payloads.append(payload)
                self.assertEqual(0, exit_code)
                self.assertEqual("planned", payload["status"])
                self.assertEqual("passed", payload["preflight"]["status"])
                self.assertFalse(payload["will_execute"])

            journal_lines = (repo_root / CONSOLE_ACTION_JOURNAL).read_text(encoding="utf-8").splitlines()
            journal_ids = {json.loads(line)["action_id"] for line in journal_lines[-2:]}
            self.assertEqual({payload["action_id"] for payload in payloads}, journal_ids)


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
