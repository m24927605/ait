from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from ait.review_policy import resolve_review_adapter_policy


class ReviewAdapterError(RuntimeError):
    """Raised when a configured reviewer adapter cannot be invoked."""


_LOCAL_CLI_REVIEW_ADAPTERS: dict[str, tuple[str, ...]] = {
    "claude-code": ("claude", "-p"),
    "codex": ("codex", "exec", "--sandbox", "read-only", "-"),
}

_DEFAULT_REVIEW_ADAPTER_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
)

_LOCAL_CLI_REVIEW_ADAPTER_ENV_ALLOWLIST: tuple[str, ...] = (
    *_DEFAULT_REVIEW_ADAPTER_ENV_ALLOWLIST,
    "HOME",
)

_REVIEW_ADAPTER_ENV_BLOCKLIST: dict[str, tuple[str, ...]] = {
    "claude-code": ("ANTHROPIC_API_KEY",),
    "codex": ("OPENAI_API_KEY",),
}

_REVIEW_ADAPTER_ENV_BLOCK_PATTERNS: tuple[str, ...] = (
    "*TOKEN*",
    "*SECRET*",
    "*PASSWORD*",
    "*KEY*",
)


@dataclass(frozen=True, slots=True)
class ReviewAdapterResult:
    command: tuple[str, ...]
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    timeout_seconds: int | float | None
    resolved_binary_path: str | None
    blocked_env: dict[str, bool]


def run_review_adapter(
    repo_root: str | Path,
    *,
    review_id: str,
    adapter: str,
    brief: str,
    attempt_head_oid: str,
    baseline_ref_oid: str,
    timeout_seconds: int | float | None = None,
) -> ReviewAdapterResult:
    """Run a reviewer adapter against a pinned read-only snapshot of the attempt.

    Materializes a git worktree at ``attempt_head_oid`` under
    ``<cwd>/src`` and writes the full ``baseline_ref_oid..attempt_head_oid``
    diff to ``<cwd>/diff.patch``. The snapshot is cleaned up unconditionally
    on exit so review runs never leak git worktree state.
    """
    adapter_name = adapter.strip()
    local_cli_command = _LOCAL_CLI_REVIEW_ADAPTERS.get(adapter_name)
    config = resolve_review_adapter_policy(repo_root, adapter_name)
    if local_cli_command is not None:
        command = local_cli_command
        timeout = timeout_seconds
        default_env_allowlist = _LOCAL_CLI_REVIEW_ADAPTER_ENV_ALLOWLIST
        env_allowlist = () if config is None else config.env_allowlist
        env_blocklist = _REVIEW_ADAPTER_ENV_BLOCKLIST.get(adapter_name, ())
        configured_cwd: str | None = None
    elif config is None:
        command = _adapter_command(adapter)
        timeout = timeout_seconds
        default_env_allowlist = _DEFAULT_REVIEW_ADAPTER_ENV_ALLOWLIST
        env_allowlist = ()
        env_blocklist = _REVIEW_ADAPTER_ENV_BLOCKLIST.get(adapter_name, ())
        configured_cwd: str | None = None
    else:
        command = _adapter_command(" ".join([config.command, *config.args]) or adapter)
        timeout = timeout_seconds if timeout_seconds is not None else config.timeout_seconds
        default_env_allowlist = _DEFAULT_REVIEW_ADAPTER_ENV_ALLOWLIST
        env_allowlist = config.env_allowlist
        env_blocklist = ()
        configured_cwd = config.cwd
    root = Path(repo_root).resolve()
    cwd = _adapter_cwd(root, review_id=review_id, configured_cwd=configured_cwd)
    if _is_target_workspace(cwd):
        raise ReviewAdapterError("review adapter cwd must not be a target attempt workspace")
    cwd.mkdir(parents=True, exist_ok=True)
    env = _adapter_env(
        default_env_allowlist,
        explicit_allowlist=env_allowlist,
        blocklist=env_blocklist,
    )
    resolved_binary_path = shutil.which(command[0], path=env.get("PATH"))
    blocked_env = {
        name: bool(name in env)
        for name in env_blocklist
    }

    snapshot_path = cwd / "src"
    _materialize_snapshot(root, snapshot_path, attempt_head_oid)
    try:
        _write_full_diff(root, cwd, baseline_ref_oid, attempt_head_oid)
        try:
            completed = subprocess.run(
                list(command),
                cwd=cwd,
                input=brief,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ReviewAdapterError(f"review adapter timed out after {timeout} seconds") from exc
        except OSError as exc:
            raise ReviewAdapterError(
                _adapter_start_error(adapter_name=adapter_name, command=command, exc=exc)
            ) from exc
    finally:
        _cleanup_snapshot(root, snapshot_path)

    return ReviewAdapterResult(
        command=command,
        cwd=str(cwd),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timeout_seconds=timeout,
        resolved_binary_path=resolved_binary_path,
        blocked_env=blocked_env,
    )


def _materialize_snapshot(
    repo_root: Path, snapshot_path: Path, head_oid: str
) -> None:
    """Create a detached read-only worktree at ``head_oid`` under ``snapshot_path``.

    Raises ReviewAdapterError if git cannot produce the worktree, leaving the
    caller's cwd untouched. The caller is responsible for cleanup via
    ``_cleanup_snapshot`` even when this function succeeded.
    """
    if not head_oid:
        # No commit to materialize (e.g., benchmark fixture or attempt without
        # commits). The caller's brief should already steer the reviewer away
        # from referencing a snapshot in that case.
        return
    if snapshot_path.exists():
        # Stale snapshot from a prior crashed run — try to clean it up first.
        _cleanup_snapshot(repo_root, snapshot_path)
    try:
        completed = subprocess.run(
            ["git", "worktree", "add", "--detach", str(snapshot_path), head_oid],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewAdapterError(
            f"failed to materialize review snapshot at {head_oid}: {exc}"
        ) from exc
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise ReviewAdapterError(
            f"git worktree add failed for commit {head_oid}: {message}"
        )


def _cleanup_snapshot(repo_root: Path, snapshot_path: Path) -> None:
    """Best-effort removal of the snapshot worktree. Never raises."""
    if not snapshot_path.exists():
        return
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(snapshot_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    # If git left the directory in place (e.g., worktree was already pruned),
    # finish the job manually so the next run can recreate it.
    if snapshot_path.exists():
        shutil.rmtree(snapshot_path, ignore_errors=True)
    # Drop any stale worktree metadata that didn't get cleared by remove --force.
    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _write_full_diff(
    repo_root: Path, cwd: Path, base_oid: str, head_oid: str
) -> None:
    """Write the complete ``base_oid..head_oid`` diff to ``<cwd>/diff.patch``.

    Best-effort: if either OID is missing or git rejects the request, write a
    short explanatory text in place of the patch so the reviewer can still
    locate the file but knows the diff is unavailable.
    """
    patch_path = cwd / "diff.patch"
    if not base_oid or not head_oid:
        patch_path.write_text(
            f"# diff unavailable: base_oid={base_oid!r} head_oid={head_oid!r}\n",
            encoding="utf-8",
        )
        return
    try:
        completed = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--no-color", base_oid, head_oid],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        patch_path.write_text(
            f"# diff unavailable: {exc}\n",
            encoding="utf-8",
        )
        return
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        patch_path.write_text(
            f"# diff unavailable: git diff exited {completed.returncode}: {message}\n",
            encoding="utf-8",
        )
        return
    patch_path.write_text(completed.stdout, encoding="utf-8")


def _adapter_command(adapter: str) -> tuple[str, ...]:
    text = adapter.strip()
    if not text:
        raise ReviewAdapterError("review adapter command is empty")
    if text.startswith("command:"):
        text = text.removeprefix("command:").strip()
    elif text.startswith("shell:"):
        text = text.removeprefix("shell:").strip()
    if not text:
        raise ReviewAdapterError("review adapter command is empty")
    try:
        command = tuple(shlex.split(text))
    except ValueError as exc:
        raise ReviewAdapterError(str(exc)) from exc
    if not command:
        raise ReviewAdapterError("review adapter command is empty")
    return command


def _adapter_cwd(root: Path, *, review_id: str, configured_cwd: str | None) -> Path:
    if configured_cwd:
        configured = Path(configured_cwd)
        if not configured.is_absolute():
            configured = root / configured
        return configured.resolve()
    return (root / ".ait" / "reviewer-runs" / review_id.replace(":", "_")).resolve()


def _adapter_env(
    default_allowlist: tuple[str, ...],
    *,
    explicit_allowlist: tuple[str, ...] = (),
    blocklist: tuple[str, ...] = (),
) -> dict[str, str]:
    explicit_names = {_normalize_env_name(name) for name in explicit_allowlist}
    env: dict[str, str] = {}
    for raw_name in (*default_allowlist, *explicit_allowlist):
        name = _normalize_env_name(raw_name)
        if not name or name not in os.environ:
            continue
        if name not in explicit_names and _blocked_env_name(name, blocklist=blocklist):
            continue
        env[name] = os.environ[name]
    return env


def _normalize_env_name(name: str) -> str:
    return str(name).strip()


def _blocked_env_name(name: str, *, blocklist: tuple[str, ...]) -> bool:
    if name in blocklist:
        return True
    upper_name = name.upper()
    return any(fnmatch(upper_name, pattern) for pattern in _REVIEW_ADAPTER_ENV_BLOCK_PATTERNS)


def _adapter_start_error(
    *,
    adapter_name: str,
    command: tuple[str, ...],
    exc: OSError,
) -> str:
    binary = command[0] if command else adapter_name
    return (
        f"review adapter '{adapter_name}' could not start local command '{binary}': {exc}. "
        "AIT passes a minimal reviewer environment and does not fall back to provider API keys. "
        f"Install and log in with the local CLI, or add required non-secret variables to "
        f"review.adapters.{adapter_name}.env_allowlist."
    )


def _is_target_workspace(path: Path) -> bool:
    parts = path.parts
    return ".ait" in parts and ("worktrees" in parts or "workspaces" in parts)
