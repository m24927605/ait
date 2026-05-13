from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import subprocess

from ait.recovery import RecoverError, recover_attempt
from ait.repo import resolve_repo_root


@dataclass(frozen=True, slots=True)
class ResumeResult:
    attempt_id: str
    workspace_ref: str
    repo_root: str
    status: str
    reported_status: str | None
    verified_status: str | None
    shell: str
    finish_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ResumeError(RuntimeError):
    """Raised when an attempt cannot be resumed in a local workspace."""


def build_resume_result(
    repo_root: str | Path,
    *,
    attempt_selector: str = "latest",
) -> ResumeResult:
    root = resolve_repo_root(repo_root)
    recovery = recover_attempt(root, attempt_selector=attempt_selector)
    if not recovery.workspace_ref:
        raise ResumeError(f"attempt has no workspace: {recovery.attempt_id}")
    workspace = Path(recovery.workspace_ref)
    if not workspace.exists():
        raise ResumeError(f"attempt workspace is missing: {workspace}")
    if recovery.verified_status in {"discarded", "promoted"}:
        raise ResumeError(
            f"attempt is already {recovery.verified_status}: {recovery.attempt_id}"
        )
    shell = os.environ.get("SHELL") or "/bin/sh"
    finish_steps = (
        "git status",
        "git add -A",
        'ait attempt commit "$AIT_RESUME_ATTEMPT_ID" -m "continue interrupted work"',
        'cd "$AIT_RESUME_REPO_ROOT"',
        'ait apply "$AIT_RESUME_ATTEMPT_ID"',
    )
    return ResumeResult(
        attempt_id=recovery.attempt_id,
        workspace_ref=str(workspace),
        repo_root=str(root),
        status=recovery.status,
        reported_status=recovery.reported_status,
        verified_status=recovery.verified_status,
        shell=shell,
        finish_steps=finish_steps,
    )


def launch_resume_shell(result: ResumeResult) -> int:
    env = _resume_env(result)
    completed = subprocess.run(
        [result.shell],
        cwd=result.workspace_ref,
        env=env,
        check=False,
    )
    return int(completed.returncode)


def _resume_env(result: ResumeResult) -> dict[str, str]:
    env = dict(os.environ)
    env["AIT_RESUME_ATTEMPT_ID"] = result.attempt_id
    env["AIT_WORKSPACE_REF"] = result.workspace_ref
    env["AIT_RESUME_REPO_ROOT"] = result.repo_root
    env["AIT_RESUME_FINISH_HINT"] = " && ".join(result.finish_steps)
    env["PATH"] = _path_without_ait_wrappers(
        env.get("PATH", ""),
        repo_root=Path(result.repo_root),
        workspace=Path(result.workspace_ref),
    )
    return env


def _path_without_ait_wrappers(path: str, *, repo_root: Path, workspace: Path) -> str:
    blocked = {
        str((repo_root / ".ait" / "bin").resolve()),
        str((workspace / ".ait" / "bin").resolve()),
    }
    kept: list[str] = []
    for entry in path.split(os.pathsep):
        if not entry:
            continue
        if str(Path(entry).expanduser().resolve()) in blocked:
            continue
        kept.append(entry)
    return os.pathsep.join(kept)
