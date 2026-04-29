from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.app import init_repo
from ait.daemon import daemon_status, prune_daemon, start_daemon, stop_daemon
from ait.daemon_transport import bind_unix_socket


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
                self.assertNotEqual("not-a-pid\n", pid_file.read_text(encoding="utf-8"))

                stopped = stop_daemon(repo_root)
                self.assertFalse(stopped.running)
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


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_root, check=True)


if __name__ == "__main__":
    unittest.main()
