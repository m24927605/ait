from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.daemon import daemon_status, stop_daemon
from ait.db import connect_db, get_evidence_summary


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


class DaemonEndToEndTests(unittest.TestCase):
    def test_two_cli_run_processes_share_one_daemon_without_corrupting_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}

            first = _start_cli_run(repo_root, env=env, label="one")
            second = _start_cli_run(repo_root, env=env, label="two")
            try:
                first_stdout, first_stderr = first.communicate(timeout=60)
                second_stdout, second_stderr = second.communicate(timeout=60)
                pid_text = (repo_root / ".ait" / "daemon.pid").read_text(encoding="utf-8")
            finally:
                stop_daemon(repo_root)

            self.assertEqual(0, first.returncode, first_stderr)
            self.assertEqual(0, second.returncode, second_stderr)
            first_payload = json.loads(first_stdout)
            second_payload = json.loads(second_stdout)
            attempts = [first_payload["attempt"], second_payload["attempt"]]

            self.assertEqual(
                ["succeeded", "succeeded"],
                [attempt["attempt"]["verified_status"] for attempt in attempts],
            )
            self.assertEqual(
                [1, 1],
                [
                    attempt["evidence_summary"]["observed_commands_run"]
                    for attempt in attempts
                ],
            )
            self.assertNotEqual(first_payload["attempt_id"], second_payload["attempt_id"])

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                for payload in (first_payload, second_payload):
                    evidence = get_evidence_summary(conn, payload["attempt_id"])
                    assert evidence is not None
                    self.assertEqual(1, evidence.observed_commands_run)
            finally:
                conn.close()

            self.assertEqual(1, len({pid_text.strip()}))
            status = daemon_status(repo_root)
            self.assertFalse(status.running)


def _start_cli_run(
    repo_root: Path, *, env: dict[str, str], label: str
) -> subprocess.Popen[str]:
    code = (
        "from pathlib import Path; "
        f"Path('agent-{label}.txt').write_text('ok-{label}\\n')"
    )
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ait.cli",
            "run",
            "--adapter",
            "shell",
            "--intent",
            f"Concurrent {label}",
            "--format",
            "json",
            "--",
            sys.executable,
            "-c",
            code,
        ],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_root, check=True)


if __name__ == "__main__":
    unittest.main()
