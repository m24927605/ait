from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import subprocess

from ait.review_policy import resolve_review_adapter_policy


class ReviewAdapterError(RuntimeError):
    """Raised when a configured reviewer adapter cannot be invoked."""


@dataclass(frozen=True, slots=True)
class ReviewAdapterResult:
    command: tuple[str, ...]
    cwd: str
    returncode: int
    stdout: str
    stderr: str


def run_review_adapter(
    repo_root: str | Path,
    *,
    review_id: str,
    adapter: str,
    brief: str,
) -> ReviewAdapterResult:
    config = resolve_review_adapter_policy(repo_root, adapter)
    if config is None:
        command = _adapter_command(adapter)
        timeout = None
        env_allowlist: tuple[str, ...] = ()
        configured_cwd: str | None = None
    else:
        command = _adapter_command(" ".join([config.command, *config.args]))
        timeout = config.timeout_seconds
        env_allowlist = config.env_allowlist
        configured_cwd = config.cwd
    root = Path(repo_root).resolve()
    cwd = _adapter_cwd(root, review_id=review_id, configured_cwd=configured_cwd)
    if _is_target_workspace(cwd):
        raise ReviewAdapterError("review adapter cwd must not be a target attempt workspace")
    cwd.mkdir(parents=True, exist_ok=True)
    env = _adapter_env(env_allowlist)
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


def _adapter_env(allowlist: tuple[str, ...]) -> dict[str, str] | None:
    if not allowlist:
        return None
    return {name: os.environ[name] for name in allowlist if name in os.environ}


def _is_target_workspace(path: Path) -> bool:
    parts = path.parts
    return ".ait" in parts and "worktrees" in parts
