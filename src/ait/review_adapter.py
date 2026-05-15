from __future__ import annotations

from dataclasses import dataclass
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
}

_REVIEW_ADAPTER_ENV_BLOCKLIST: dict[str, tuple[str, ...]] = {
    "claude-code": ("ANTHROPIC_API_KEY",),
}


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
) -> ReviewAdapterResult:
    adapter_name = adapter.strip()
    local_cli_command = _LOCAL_CLI_REVIEW_ADAPTERS.get(adapter_name)
    config = None if local_cli_command is not None else resolve_review_adapter_policy(repo_root, adapter)
    if local_cli_command is not None:
        command = local_cli_command
        timeout = None
        env_allowlist: tuple[str, ...] = ()
        env_blocklist = _REVIEW_ADAPTER_ENV_BLOCKLIST.get(adapter_name, ())
        configured_cwd: str | None = None
    elif config is None:
        command = _adapter_command(adapter)
        timeout = None
        env_allowlist: tuple[str, ...] = ()
        env_blocklist = _REVIEW_ADAPTER_ENV_BLOCKLIST.get(adapter_name, ())
        configured_cwd: str | None = None
    else:
        command = _adapter_command(" ".join([config.command, *config.args]))
        timeout = config.timeout_seconds
        env_allowlist = config.env_allowlist
        env_blocklist = ()
        configured_cwd = config.cwd
    root = Path(repo_root).resolve()
    cwd = _adapter_cwd(root, review_id=review_id, configured_cwd=configured_cwd)
    if _is_target_workspace(cwd):
        raise ReviewAdapterError("review adapter cwd must not be a target attempt workspace")
    cwd.mkdir(parents=True, exist_ok=True)
    env = _adapter_env(env_allowlist, blocklist=env_blocklist)
    resolved_binary_path = shutil.which(command[0], path=None if env is None else env.get("PATH"))
    blocked_env = {
        name: bool(env is not None and name in env)
        for name in env_blocklist
    }
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
        raise ReviewAdapterError(str(exc)) from exc
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
    allowlist: tuple[str, ...],
    *,
    blocklist: tuple[str, ...] = (),
) -> dict[str, str] | None:
    if not allowlist:
        if not blocklist:
            return None
        env = dict(os.environ)
        for name in blocklist:
            env.pop(name, None)
        return env
    env = {name: os.environ[name] for name in allowlist if name in os.environ}
    for name in blocklist:
        env.pop(name, None)
    return env


def _is_target_workspace(path: Path) -> bool:
    parts = path.parts
    return ".ait" in parts and ("worktrees" in parts or "workspaces" in parts)
