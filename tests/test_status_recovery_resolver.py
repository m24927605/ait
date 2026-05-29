from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.cli.status_helpers import _recovery_dashboard_payload


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class RecoveryDashboardResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.host = Path(self._td.name) / "host"
        self.host.mkdir()
        _git(self.host, "init", "-q")
        _git(self.host, "config", "user.email", "t@example.com")
        _git(self.host, "config", "user.name", "test")
        (self.host / "README.md").write_text("seed\n")
        _git(self.host, "add", ".")
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        subprocess.run(
            ["git", "commit", "-q", "-m", "seed"],
            cwd=self.host, env=env, check=True, capture_output=True,
        )
        (self.host / ".ait").mkdir()
        # Realistic AIT state file (empty is fine; the dashboard only
        # needs to find .ait/state.sqlite3 to take the non-error path).
        (self.host / ".ait" / "state.sqlite3").touch()

    def _add_worktree(self, name: str) -> Path:
        workspaces = self.host / ".ait" / "workspaces"
        workspaces.mkdir(parents=True, exist_ok=True)
        ws = workspaces / name
        _git(self.host, "worktree", "add", "--detach", str(ws), "HEAD")
        return ws

    def test_recovery_dashboard_finds_host_state_from_attempt_workspace(self) -> None:
        ws = self._add_worktree("attempt-0001-01HZTEST")
        # Acting as: user cd'd into the workspace and ran `ait status`.
        # main.py:102 passes Path.cwd() (the workspace path) to the
        # status handler, which eventually calls this dashboard.
        payload = _recovery_dashboard_payload(ws)
        # Must NOT return the "not_initialized" branch — the host repo
        # is initialized and its state.sqlite3 lives one level up via
        # the .ait/workspaces/<attempt> shape.
        self.assertNotEqual("not_initialized", payload.get("status"))

    def test_recovery_dashboard_returns_not_initialized_outside_git_repo(self) -> None:
        # No .ait/, no .git/ — the legitimate "not_initialized" case
        # outside any repo must still report that status.
        with tempfile.TemporaryDirectory() as tmp:
            payload = _recovery_dashboard_payload(Path(tmp))
            self.assertEqual("not_initialized", payload.get("status"))

    def test_recovery_dashboard_works_at_host_repo_root(self) -> None:
        # Regression check: the existing happy path (cwd == host root)
        # must still resolve correctly.
        payload = _recovery_dashboard_payload(self.host)
        self.assertNotEqual("not_initialized", payload.get("status"))


if __name__ == "__main__":
    unittest.main()
