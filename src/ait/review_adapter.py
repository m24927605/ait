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
    timeout_seconds: int | float | None = None,
) -> ReviewAdapterResult:
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
