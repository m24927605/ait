from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.app import create_attempt, create_intent, init_repo
from ait.daemon import daemon_status, prune_daemon, start_daemon, stop_daemon
from ait.daemon_transport import bind_unix_socket
from ait.db import connect_db, get_attempt
from ait.harness import AitHarness


class DaemonLifecycleTests(unittest.TestCase):
    def test_daemon_status_does_not_trust_unrelated_live_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_repo(repo_root)
            pid_file = repo_root / ".ait" / "daemon.pid"
            pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")

            status = daemon_status(repo_root)

            self.assertFalse(status.running)
            self.assertTrue(status.pid_running)
            self.assertFalse(status.pid_matches)
            self.assertEqual("pid_not_ait_daemon", status.stale_reason)

    def test_start_daemon_cleans_stale_pid_and_socket_before_starting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_repo(repo_root)
            socket_path = repo_root / ".ait" / "daemon.sock"
            stale_server = bind_unix_socket(socket_path)
            stale_server.close()
            pid_file = repo_root / ".ait" / "daemon.pid"
            pid_file.write_text("not-a-pid\n", encoding="utf-8")

            before = daemon_status(repo_root)
            try:
                started = start_daemon(repo_root)

                self.assertFalse(before.running)
                self.assertIsNotNone(before.stale_reason)
                self.assertTrue(started.running)
                self.assertTrue(started.socket_connectable)
                self.assertTrue(started.pid_matches)
                self.assertIsNotNone(started.pid)
                self.assertNotEqual("not-a-pid\n", pid_file.read_text(encoding="utf-8"))

                stopped = stop_daemon(repo_root)
                self.assertFalse(stopped.running)
                assert started.pid is not None
                self.assertTrue(_pid_has_exited(started.pid))
            finally:
                if repo_root.exists():
                    stop_daemon(repo_root)

    def test_prune_daemon_removes_stale_pid_and_socket_without_starting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_repo(repo_root)
            socket_path = repo_root / ".ait" / "daemon.sock"
            stale_server = bind_unix_socket(socket_path)
            stale_server.close()
            pid_file = repo_root / ".ait" / "daemon.pid"
            pid_file.write_text("not-a-pid\n", encoding="utf-8")

            pruned = prune_daemon(repo_root)

            self.assertFalse(pruned.running)
            self.assertFalse(socket_path.exists())
            self.assertFalse(pid_file.exists())
            self.assertIsNone(pruned.stale_reason)

    def test_start_daemon_recovers_running_attempt_after_sigkill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_repo(repo_root)
            config_path = repo_root / ".ait" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["reaper_ttl_seconds"] = 1
            config["daemon_idle_timeout_seconds"] = 10
            config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")
            intent = create_intent(
                repo_root,
                title="Daemon sigkill recovery",
                description=None,
                kind="codex-run",
            )
            attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="codex:test")
            started = start_daemon(repo_root)
            self.assertTrue(started.running)
            self.assertIsNotNone(started.pid)
            harness = AitHarness.open(
                attempt_id=attempt.attempt_id,
                ownership_token=attempt.ownership_token,
                socket_path=started.socket_path,
                agent={"agent_id": "codex:test", "harness": "codex", "harness_version": "test"},
            )
            try:
                harness.start()
            finally:
                harness.close()

            assert started.pid is not None
            os.kill(started.pid, signal.SIGKILL)
            _wait_for_daemon_to_stop(repo_root)
            time.sleep(1.1)
            restarted = start_daemon(repo_root)

            try:
                self.assertTrue(restarted.running)
                conn = connect_db(repo_root / ".ait" / "state.sqlite3")
                try:
                    recovered = get_attempt(conn, attempt.attempt_id)
                finally:
                    conn.close()
                assert recovered is not None
                self.assertEqual("crashed", recovered.reported_status)
                self.assertEqual("failed", recovered.verified_status)
            finally:
                stop_daemon(repo_root)


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_root, check=True)


def _wait_for_daemon_to_stop(repo_root: Path) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not daemon_status(repo_root).running:
            return
        time.sleep(0.05)
    raise AssertionError("daemon did not stop")


def _pid_has_exited(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


if __name__ == "__main__":
    unittest.main()
