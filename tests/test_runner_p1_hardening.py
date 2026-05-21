"""Tests for P1 hardening: shell=True opt-in, socket TOCTOU, SQLite
file mode, and PID + start-time liveness checks.

These cover four security-hardening fixes layered on top of the P0
runner streaming/timeout work. The shape mirrors how the existing
`test_runner_subprocess.py` is organised — one section per fix, each
isolated enough to read without context from the rest of the file.
"""

from __future__ import annotations

import os
import socket
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

import pytest

from ait import daemon_transport
from ait.db.core import connect_db
from ait.integration import _run_validation
from ait.workspace_lease import (
    WorkspaceLease,
    _pid_started_at,
    create_workspace_lease,
    lease_owner_alive,
    read_workspace_lease,
)


# ---------------------------------------------------------------------------
# P1 #3 — shell=True opt-in via shlex parsing
# ---------------------------------------------------------------------------


def test_run_validation_default_uses_shlex_not_shell(tmp_path: Path) -> None:
    """Without explicit opt-in, `_run_validation` parses the command via
    shlex and runs it without a shell. Shell metacharacters in a
    hostile policy.json therefore execute as literal argv tokens
    instead of as a piped pipeline."""
    # `printf '%s\n' $$` would (under shell) print AIT's PID via env
    # expansion. Under shlex+no-shell, `$$` is just an argv token and
    # printf prints it verbatim. We assert the verbatim form.
    completed = _run_validation(tmp_path, "printf %s $$")
    assert completed.returncode == 0
    # `printf %s $$` with shlex tokenises to ['printf', '%s', '$$'];
    # printf prints '$$' verbatim because no shell expanded it.
    assert completed.stdout == "$$"


def test_run_validation_shell_opt_in_uses_bin_sh(tmp_path: Path) -> None:
    """When shell=True is explicitly passed, shell metacharacters work
    again — but the code path goes through `/bin/sh -lc` as explicit
    argv, not `subprocess.run(..., shell=True)`."""
    completed = _run_validation(tmp_path, "printf %s $$", shell=True)
    assert completed.returncode == 0
    # /bin/sh expands $$ to its own pid (a positive integer).
    assert completed.stdout.strip().isdigit()


def test_run_validation_empty_command_returns_clean(tmp_path: Path) -> None:
    """An empty command yields a clean exit-0 with no execution."""
    completed = _run_validation(tmp_path, None)
    assert completed.returncode == 0
    assert completed.stdout == ""


def test_run_validation_unparseable_command_reports_actionable_error(
    tmp_path: Path,
) -> None:
    """A command shlex cannot parse (unterminated quote) is rejected
    with a clear error message that points the operator at the
    `auto_test_shell` opt-in."""
    completed = _run_validation(tmp_path, "echo 'unterminated")
    assert completed.returncode == 2
    assert "auto_test_shell" in completed.stderr


# ---------------------------------------------------------------------------
# P1 #4 — Unix socket bind+chmod TOCTOU + restricted parent directory
# ---------------------------------------------------------------------------


def _short_socket_dir() -> Path:
    """AF_UNIX paths are capped at ~104 bytes on macOS; pytest's
    `tmp_path` is too long. Use a short /tmp-prefixed mkdtemp so the
    bind() call does not fail with `path too long` on Darwin."""
    return Path(tempfile.mkdtemp(prefix="ait-p1-", dir="/tmp"))


def test_bind_unix_socket_file_is_0o600_immediately() -> None:
    """After `bind_unix_socket` returns the socket inode is mode 0o600.
    Any local process attempting to connect during the bind+chmod
    window would have to win against an inode that was never world-
    or group-readable. We can only observe the final state from the
    test, but reproducing the previous TOCTOU is not feasible in a
    unit test, so we assert the strongest defensible invariant: the
    file mode is locked down by the time the function returns."""
    root = _short_socket_dir()
    socket_path = root / "ait.sock"
    server = daemon_transport.bind_unix_socket(socket_path)
    try:
        st = socket_path.stat()
        mode = stat.S_IMODE(st.st_mode)
        assert mode == 0o600, f"socket mode is {oct(mode)}, expected 0o600"
    finally:
        server.close()
        try:
            socket_path.unlink()
        except OSError:
            pass
        try:
            root.rmdir()
        except OSError:
            pass


def test_bind_unix_socket_parent_dir_is_0o700() -> None:
    """The socket's parent directory is tightened to 0o700 so the inode
    is unreachable via directory traversal even if its own mode
    regresses on a future patch."""
    root = _short_socket_dir()
    socket_path = root / "ait.sock"
    server = daemon_transport.bind_unix_socket(socket_path)
    try:
        mode = stat.S_IMODE(socket_path.parent.stat().st_mode)
        assert mode == 0o700, f"parent dir mode is {oct(mode)}, expected 0o700"
    finally:
        server.close()
        try:
            socket_path.unlink()
        except OSError:
            pass
        try:
            root.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# P1 #4 — SQLite file mode 0o600 on creation
# ---------------------------------------------------------------------------


def test_connect_db_creates_file_with_0o600(tmp_path: Path) -> None:
    """A fresh SQLite database created via `connect_db` is mode 0o600
    immediately, so an attempt ledger is never exposed to other
    local accounts during the brief window between `sqlite3.connect`
    and any downstream chmod."""
    db_path = tmp_path / "attempts.db"
    # Loosen the umask before the call so we can detect whether the
    # fix correctly tightened the mode (otherwise the system umask
    # alone would make this pass spuriously).
    old_umask = os.umask(0o022)
    try:
        conn = connect_db(db_path)
        conn.close()
    finally:
        os.umask(old_umask)
    mode = stat.S_IMODE(db_path.stat().st_mode)
    assert mode == 0o600, f"db file mode is {oct(mode)}, expected 0o600"


def test_connect_db_tightens_preexisting_loose_mode(tmp_path: Path) -> None:
    """If a .db file already exists on disk from a pre-fix install with
    loose permissions, `connect_db` tightens it to 0o600 on next
    open. This protects upgraders without forcing them to recreate
    their ledger."""
    db_path = tmp_path / "ledger.db"
    # Pre-create the file with loose mode.
    conn = sqlite3.connect(db_path)
    conn.close()
    db_path.chmod(0o644)
    # Now reopen via `connect_db`.
    conn = connect_db(db_path)
    conn.close()
    mode = stat.S_IMODE(db_path.stat().st_mode)
    assert mode == 0o600


# ---------------------------------------------------------------------------
# P1 #5 — PID + start-time liveness check
# ---------------------------------------------------------------------------


def test_pid_started_at_for_self_is_stable(tmp_path: Path) -> None:
    """Two calls for the same live PID return the same start time.
    This is the invariant the liveness check relies on."""
    pid = os.getpid()
    first = _pid_started_at(pid)
    if first is None:
        pytest.skip("platform does not expose pid start time")
    second = _pid_started_at(pid)
    assert first == second


def test_pid_started_at_for_invalid_pid_returns_none() -> None:
    """A nonsensical PID returns None rather than raising — the
    liveness path treats None as "fall back to PID-only"."""
    assert _pid_started_at(-1) is None
    assert _pid_started_at(0) is None


def test_lease_owner_alive_detects_pid_reuse(tmp_path: Path) -> None:
    """A lease whose recorded `owner_started_at` no longer matches the
    current start time of that PID is treated as a dead owner — even
    if a process with that PID happens to exist now. This is the
    PID-reuse defense."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    workspace_root = tmp_path / ".ait" / "worktrees" / "attempt-x"
    workspace_root.parent.mkdir(parents=True)
    # We don't need a real worktree on disk for the lease file write.
    workspace_root.parent.parent.mkdir(parents=True, exist_ok=True)
    lease = create_workspace_lease(
        repo_root=repo_root,
        workspace_ref=workspace_root,
        attempt_id="atm_01TEST",
        base_ref_oid="0" * 40,
        base_ref_name="main",
    )
    # Confirm baseline: the lease's owner is our test process and is
    # therefore alive. If the platform did not provide a start time,
    # we skip the negative half of this test (PID-only fallback only).
    if lease.owner_started_at is None:
        pytest.skip("platform does not expose pid start time")
    assert lease_owner_alive(lease) is True
    # Synthesize a lease with the same PID but a deliberately stale
    # start time. The PID still exists (it is us), but the start
    # time mismatch must cause `lease_owner_alive` to return False.
    forged = WorkspaceLease(
        schema_version=lease.schema_version,
        attempt_id=lease.attempt_id,
        intent_id=lease.intent_id,
        repo_root=lease.repo_root,
        workspace_ref=lease.workspace_ref,
        base_ref_oid=lease.base_ref_oid,
        base_ref_name=lease.base_ref_name,
        created_at=lease.created_at,
        last_touched_at=lease.last_touched_at,
        owner_pid=lease.owner_pid,
        owner_command=lease.owner_command,
        state=lease.state,
        cleanup_policy=lease.cleanup_policy,
        preserve_reason=lease.preserve_reason,
        owner_started_at="1999-01-01T00:00:00Z",  # known-stale stamp
    )
    assert lease_owner_alive(forged) is False


def test_lease_owner_alive_falls_back_to_pid_only_on_old_lease(
    tmp_path: Path,
) -> None:
    """Lease files written before `owner_started_at` existed do not
    record the field. Liveness must still work for those — falling
    back to bare PID existence (the original behavior). This guards
    upgrade compatibility."""
    lease = WorkspaceLease(
        schema_version=1,
        attempt_id="atm_01OLD",
        intent_id=None,
        repo_root=str(tmp_path),
        workspace_ref=str(tmp_path / "ws"),
        base_ref_oid="0" * 40,
        base_ref_name="main",
        created_at="2026-01-01T00:00:00Z",
        last_touched_at="2026-01-01T00:00:00Z",
        owner_pid=os.getpid(),
        owner_command=None,
        state="active",
        cleanup_policy="auto",
        preserve_reason=None,
        owner_started_at=None,  # legacy lease file
    )
    assert lease_owner_alive(lease) is True


def test_lease_owner_alive_dead_pid_returns_false() -> None:
    """A PID that does not exist on the system returns False
    regardless of the start time field."""
    lease = WorkspaceLease(
        schema_version=1,
        attempt_id="atm_01DEAD",
        intent_id=None,
        repo_root="/tmp",
        workspace_ref="/tmp/ws",
        base_ref_oid="0" * 40,
        base_ref_name="main",
        created_at="2026-01-01T00:00:00Z",
        last_touched_at="2026-01-01T00:00:00Z",
        owner_pid=2**22 - 1,  # virtually guaranteed to be unallocated
        owner_command=None,
        state="active",
        cleanup_policy="auto",
        preserve_reason=None,
        owner_started_at="2026-01-01T00:00:00Z",
    )
    assert lease_owner_alive(lease) is False


def test_create_workspace_lease_round_trips_owner_started_at(
    tmp_path: Path,
) -> None:
    """The `owner_started_at` field is persisted to disk and read back
    losslessly — otherwise the PID-reuse defense would silently
    revert to PID-only after the daemon restarts."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    workspace_root = tmp_path / ".ait" / "worktrees" / "attempt-y"
    workspace_root.parent.mkdir(parents=True)
    lease = create_workspace_lease(
        repo_root=repo_root,
        workspace_ref=workspace_root,
        attempt_id="atm_01RT",
        base_ref_oid="0" * 40,
        base_ref_name="main",
    )
    if lease.owner_started_at is None:
        pytest.skip("platform does not expose pid start time")
    reloaded = read_workspace_lease(workspace_root)
    assert reloaded is not None
    assert reloaded.owner_started_at == lease.owner_started_at
