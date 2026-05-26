from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shlex
import subprocess

from ait.app import create_commit_for_attempt
from ait.landing import ApplyError, ApplyResult, apply_attempt, apply_result_payload
from ait.recovery import RecoverError, recover_attempt
from ait.repo import resolve_repo_root
from ait.workspace import WorkspaceError


@dataclass(frozen=True, slots=True)
class ResumeResult:
    attempt_id: str
    attempt_handle: str | None
    attempt_description: str | None
    workspace_ref: str
    repo_root: str
    status: str
    reported_status: str | None
    verified_status: str | None
    shell: str
    finish_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResumeFinishResult:
    attempt_id: str
    attempt_handle: str | None
    attempt_description: str | None
    status: str
    message: str
    commit_created: bool
    next_steps: tuple[str, ...]
    workspace_ref: str
    apply_result: ApplyResult | None = None
    debug: dict[str, object] | None = None

    def to_dict(self, *, debug: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "attempt_id": self.attempt_id,
            "attempt_handle": self.attempt_handle,
            "attempt_description": self.attempt_description,
            "status": self.status,
            "message": self.message,
            "commit_created": self.commit_created,
            "next_steps": list(self.next_steps),
            "workspace_ref": self.workspace_ref,
            "apply": None
            if self.apply_result is None
            else apply_result_payload(self.apply_result, debug=debug),
        }
        if debug and self.debug is not None:
            payload["debug"] = self.debug
        return payload


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
    label = recovery.attempt_handle or recovery.attempt_id.rsplit(":", 1)[-1]
    finish_steps = (f"ait resume {shlex.quote(label)} --finish",)
    return ResumeResult(
        attempt_id=recovery.attempt_id,
        attempt_handle=recovery.attempt_handle,
        attempt_description=recovery.attempt_description,
        workspace_ref=str(workspace),
        repo_root=str(root),
        status=recovery.status,
        reported_status=recovery.reported_status,
        verified_status=recovery.verified_status,
        shell=shell,
        finish_steps=finish_steps,
    )


def finish_resume_attempt(
    repo_root: str | Path,
    *,
    attempt_selector: str = "latest",
    message: str | None = None,
) -> ResumeFinishResult:
    root = _resume_repo_root(repo_root)
    result = build_resume_result(root, attempt_selector=attempt_selector)
    label = _attempt_label(result)
    workspace = Path(result.workspace_ref)
    commit_message = message or "continue interrupted work"
    commit_created = False
    try:
        _git_run(workspace, "add", "-A")
        has_workspace_changes = bool(_git_stdout(workspace, "status", "--porcelain"))
        if not has_workspace_changes and result.verified_status != "succeeded":
            return ResumeFinishResult(
                attempt_id=result.attempt_id,
                attempt_handle=result.attempt_handle,
                attempt_description=result.attempt_description,
                status="blocked",
                message="AIT found no resumed workspace changes to commit.",
                commit_created=False,
                next_steps=(f"ait resume {label}",),
                workspace_ref=result.workspace_ref,
                debug={"reason": "no workspace changes"},
            )
        if has_workspace_changes:
            create_commit_for_attempt(root, attempt_id=result.attempt_id, message=commit_message)
            commit_created = True
    except (ValueError, WorkspaceError, ResumeError) as exc:
        return ResumeFinishResult(
            attempt_id=result.attempt_id,
            attempt_handle=result.attempt_handle,
            attempt_description=result.attempt_description,
            status="blocked",
            message=f"AIT could not commit the resumed workspace: {exc}",
            commit_created=False,
            next_steps=(f"ait resume {label}",),
            workspace_ref=result.workspace_ref,
            debug={"reason": str(exc)},
        )
    try:
        applied = apply_attempt(root, attempt_selector=result.attempt_id)
    except (ApplyError, ValueError, WorkspaceError) as exc:
        return ResumeFinishResult(
            attempt_id=result.attempt_id,
            attempt_handle=result.attempt_handle,
            attempt_description=result.attempt_description,
            status="blocked",
            message=f"AIT committed the resumed work, but apply is blocked: {exc}",
            commit_created=commit_created,
            next_steps=(f"ait recover {label}",),
            workspace_ref=result.workspace_ref,
            debug={"reason": str(exc)},
        )
    if applied.status in {"applied", "already_applied"}:
        status = applied.status
        next_steps: tuple[str, ...] = ()
    else:
        status = "blocked"
        next_steps = (f"ait recover {label}",)
    return ResumeFinishResult(
        attempt_id=result.attempt_id,
        attempt_handle=result.attempt_handle,
        attempt_description=applied.attempt_description or result.attempt_description,
        status=status,
        message=(
            "AIT committed the resumed work and ran apply."
            if commit_created
            else "AIT ran apply for the resumed work."
        ),
        commit_created=commit_created,
        next_steps=next_steps,
        workspace_ref=result.workspace_ref,
        apply_result=applied,
        debug={"apply_status": applied.status},
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


def resume_shell_script(result: ResumeResult) -> str:
    """Return shell code that moves the current interactive shell into a resume state."""
    env = _resume_env(result)
    exports = {
        "AIT_RESUME_ATTEMPT_ID": env["AIT_RESUME_ATTEMPT_ID"],
        "AIT_WORKSPACE_REF": env["AIT_WORKSPACE_REF"],
        "AIT_RESUME_REPO_ROOT": env["AIT_RESUME_REPO_ROOT"],
        "AIT_RESUME_FINISH_HINT": env["AIT_RESUME_FINISH_HINT"],
        "PATH": env["PATH"],
    }
    lines = [
        f"cd {shlex.quote(result.workspace_ref)} || return $?",
    ]
    lines.extend(f"export {name}={shlex.quote(value)}" for name, value in exports.items())
    lines.extend(
        [
            "printf '%s\\n' "
            f"{shlex.quote('Continuing AIT attempt ' + _attempt_label(result))} >&2",
            f"printf '%s\\n' {shlex.quote('Workspace: ' + result.workspace_ref)} >&2",
        ]
    )
    return "\n".join(lines) + "\n"


def resume_env(result: ResumeResult) -> dict[str, str]:
    """Return an environment suitable for continuing inside an attempt workspace."""
    return _resume_env(result)


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


def _resume_repo_root(repo_root: str | Path) -> Path:
    cwd = Path(repo_root).resolve()
    env_root = os.environ.get("AIT_RESUME_REPO_ROOT")
    env_workspace = os.environ.get("AIT_WORKSPACE_REF")
    if env_root and env_workspace:
        workspace = Path(env_workspace).resolve()
        if cwd == workspace or workspace in cwd.parents:
            return Path(env_root).resolve()
    return cwd


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


def _attempt_label(result: ResumeResult) -> str:
    return result.attempt_handle or result.attempt_id.rsplit(":", 1)[-1]


def _git_stdout(repo_root: Path, *args: str) -> str:
    return _git_run(repo_root, *args).stdout.strip()


def _git_run(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ResumeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed
