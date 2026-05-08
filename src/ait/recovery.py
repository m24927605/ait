from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import shutil
import subprocess

from ait.app import create_attempt, create_commit_for_attempt, create_intent, discard_attempt, init_repo
from ait.db import connect_db, get_attempt, list_attempt_commits, list_attempts
from ait.decision_codes import RecoverCode
from ait.decision_report import DecisionReport, daily_step, decision_report
from ait.dev_server import dev_servers_for_worktree
from ait.idresolver import resolve_attempt_id
from ait.integration import create_integration_attempt as _create_integration_attempt
from ait.workspace import WorkspaceError
from ait.workspace_lease import lease_payload, workspace_lease_path
from ait.workspace_lease import update_workspace_lease


@dataclass(frozen=True, slots=True)
class RecoverResult:
    attempt_id: str
    status: str
    reported_status: str | None
    verified_status: str | None
    changed_files: tuple[str, ...]
    recoverable: bool
    next_steps: tuple[str, ...]
    message: str
    workspace_ref: str | None = None
    lease: dict[str, object] | None = None
    decision_report: DecisionReport | None = None
    debug: dict[str, object] = field(default_factory=dict)


class RecoverError(RuntimeError):
    """Raised when a recovery handle cannot be resolved."""


def recover_attempt(
    repo_root: str | Path,
    *,
    attempt_selector: str = "latest",
) -> RecoverResult:
    init_result = init_repo(repo_root)
    root = init_result.repo_root
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        attempt_id = _resolve_recover_selector(conn, attempt_selector)
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise RecoverError(f"Unknown attempt: {attempt_id}")
        commits = list_attempt_commits(conn, attempt_id)
    finally:
        conn.close()

    changed_files = tuple(sorted({path for commit in commits for path in commit.touched_files}))
    workspace = Path(attempt.workspace_ref)
    lease = lease_payload(attempt.workspace_ref)
    dev_servers = _dev_server_payload(root, attempt.workspace_ref)
    integration_artifact = _integration_artifact_payload(root, attempt_id)
    recoverable = workspace.exists() and attempt.verified_status not in {"discarded", "promoted"}
    if attempt.verified_status == "promoted":
        status = "applied"
        message = "AIT already applied this result."
        next_steps = ("ait cleanup --apply",)
    elif attempt.verified_status == "discarded":
        status = "discarded"
        message = "AIT already discarded this result."
        next_steps = ()
    elif recoverable:
        status = _recover_status(attempt.reported_status, attempt.verified_status, lease)
        message = "AIT kept this result for recovery."
        next_steps = (f"ait apply {attempt_id}", f"ait recover {attempt_id} --debug")
    else:
        status = "missing"
        message = "AIT cannot find a recoverable workspace for this result."
        next_steps = ("ait recover latest --debug",)
    return RecoverResult(
        attempt_id=attempt_id,
        status=status,
        reported_status=attempt.reported_status,
        verified_status=attempt.verified_status,
        changed_files=changed_files,
        recoverable=recoverable,
        next_steps=next_steps,
        message=message,
        workspace_ref=attempt.workspace_ref,
        lease=lease,
        decision_report=_recover_decision_report(
            attempt_id=attempt_id,
            status=status,
            message=message,
            recoverable=recoverable,
            next_steps=next_steps,
        ),
        debug={
            "workspace_ref": attempt.workspace_ref,
            "workspace_exists": workspace.exists(),
            "lease_path": str(workspace_lease_path(attempt.workspace_ref)),
            "dev_servers": dev_servers,
            **(
                {
                    "strategy": integration_artifact.get("strategy"),
                    "classification": integration_artifact.get("classification"),
                    "base_attempt_id": integration_artifact.get("base_attempt_id"),
                    "reason_code": _artifact_reason_code(integration_artifact),
                    "integration_artifact": integration_artifact,
                }
                if integration_artifact
                else {}
            ),
        },
    )


def discard_recoverable_attempt(
    repo_root: str | Path,
    *,
    attempt_selector: str = "latest",
) -> RecoverResult:
    result = recover_attempt(repo_root, attempt_selector=attempt_selector)
    if not result.recoverable or result.workspace_ref is None:
        return result
    workspace = Path(result.workspace_ref)
    if _git_stdout(workspace, "status", "--porcelain", "--untracked-files=no", allow_failure=True).strip():
        return _recover_action_result(
            result,
            status="held",
            message="AIT kept this result because its recovery state has local changes.",
            next_steps=(f"ait recover {result.attempt_id} --debug",),
        )
    discard_attempt(repo_root, attempt_id=result.attempt_id)
    return _recover_action_result(
        result,
        status="discarded",
        message="AIT discarded the recoverable result.",
        next_steps=(),
        recoverable=False,
    )


def create_integration_attempt(
    repo_root: str | Path,
    *,
    attempt_selector: str = "latest",
    auto_integrate: bool = False,
    test_command: str | None = None,
) -> RecoverResult:
    base = recover_attempt(repo_root, attempt_selector=attempt_selector)
    result = _create_integration_attempt(
        repo_root,
        attempt_selector=attempt_selector,
        auto_integrate=auto_integrate,
        test_command=test_command,
    )
    if result.status == "integration_created":
        next_steps = (f"ait apply {result.attempt_id}",)
        message = "AIT created an integration attempt."
    elif result.status == "conflict":
        next_steps = (f"ait recover {result.attempt_id} --debug",)
        message = "AIT created an integration attempt, but the merge needs recovery."
    else:
        next_steps = (f"ait recover {base.attempt_id} --debug",)
        message = result.decision_report.reasons[0].message if result.decision_report.reasons else "AIT held integration."
    return RecoverResult(
        attempt_id=result.attempt_id,
        status=result.status,
        reported_status=base.reported_status,
        verified_status=base.verified_status,
        changed_files=result.changed_files,
        recoverable=result.status in {"integration_created", "conflict", "held"},
        next_steps=next_steps,
        message=message,
        workspace_ref=result.workspace_ref,
        lease=lease_payload(result.workspace_ref) if result.workspace_ref else None,
        decision_report=result.decision_report,
        debug={
            **base.debug,
            **result.debug,
            "base_attempt_id": result.base_attempt_id,
            "integration_attempt_id": result.attempt_id,
            "strategy": result.plan.strategy,
            "classification": result.plan.classification,
            "reason_code": result.decision_report.reasons[0].code if result.decision_report.reasons else None,
            "patch_artifact_ref": result.patch_artifact_ref,
            "result_artifact_ref": result.result_artifact_ref,
        },
    )


def recover_result_payload(result: RecoverResult, *, debug: bool = False) -> dict[str, object]:
    payload = asdict(result)
    if not debug:
        payload.pop("debug", None)
    return payload


def _recover_action_result(
    result: RecoverResult,
    *,
    status: str,
    message: str,
    next_steps: tuple[str, ...],
    workspace_ref: str | None = None,
    recoverable: bool | None = None,
    debug: dict[str, object] | None = None,
) -> RecoverResult:
    return RecoverResult(
        attempt_id=result.attempt_id,
        status=status,
        reported_status=result.reported_status,
        verified_status=result.verified_status,
        changed_files=result.changed_files,
        recoverable=result.recoverable if recoverable is None else recoverable,
        next_steps=next_steps,
        message=message,
        workspace_ref=result.workspace_ref if workspace_ref is None else workspace_ref,
        lease=lease_payload(result.workspace_ref if workspace_ref is None else workspace_ref)
        if (result.workspace_ref if workspace_ref is None else workspace_ref)
        else None,
        decision_report=_recover_decision_report(
            attempt_id=result.attempt_id,
            status=status,
            message=message,
            recoverable=result.recoverable if recoverable is None else recoverable,
            next_steps=next_steps,
        ),
        debug={**result.debug, **(debug or {})},
    )


def _recover_decision_report(
    *,
    attempt_id: str,
    status: str,
    message: str,
    recoverable: bool,
    next_steps: tuple[str, ...],
) -> DecisionReport:
    return decision_report(
        subject="recover",
        subject_id=attempt_id,
        decision=status,
        safety_level="recoverable" if recoverable else "terminal",
        reason_code=_recover_reason_code(status),
        reason_message=message,
        debug={"recoverable": recoverable},
        next_steps=tuple(daily_step(step, "continue recovery") for step in next_steps),
    )


def _recover_reason_code(status: str) -> str:
    return {
        "applied": RecoverCode.ALREADY_APPLIED,
        "discarded": RecoverCode.DISCARDED,
        "missing": RecoverCode.MISSING_STATE,
        "conflict": RecoverCode.CONFLICT,
        "integration_created": RecoverCode.INTEGRATION_CREATED,
        "held": RecoverCode.HELD,
        "failed": RecoverCode.FAILED,
        "succeeded": RecoverCode.READY_TO_APPLY,
        "active": RecoverCode.ACTIVE,
    }.get(status, f"recover.{status}")


def _integration_artifact_payload(repo_root: Path, attempt_id: str) -> dict[str, object] | None:
    path = repo_root / ".ait" / "results" / f"{_safe_attempt_filename(attempt_id)}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != "integration":
        return None
    return payload


def _artifact_reason_code(payload: dict[str, object]) -> str | None:
    report = payload.get("decision_report")
    if not isinstance(report, dict):
        return None
    reasons = report.get("reasons")
    if not isinstance(reasons, list) or not reasons:
        return None
    first = reasons[0]
    if not isinstance(first, dict):
        return None
    code = first.get("code")
    return str(code) if code else None


def _safe_attempt_filename(attempt_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in attempt_id.rsplit(":", 1)[-1])


def _resolve_recover_selector(conn, selector: str) -> str:
    if selector == "latest":
        attempts = [
            attempt
            for attempt in reversed(list_attempts(conn))
            if attempt.verified_status not in {"discarded", "promoted"}
        ]
        if attempts:
            return attempts[0].id
        all_attempts = list_attempts(conn)
        if not all_attempts:
            raise RecoverError("no attempts found")
        return all_attempts[-1].id
    return resolve_attempt_id(conn, selector)


def _recover_status(reported_status: str | None, verified_status: str | None, lease: dict[str, object] | None) -> str:
    if lease and lease.get("state") in {"active", "succeeded", "failed", "conflict", "stale", "orphan", "applied"}:
        return str(lease["state"])
    if reported_status == "crashed":
        return "failed"
    if verified_status == "failed":
        return "failed"
    if verified_status == "succeeded":
        return "succeeded"
    return "active"


def _dev_server_payload(repo_root: Path, workspace_ref: str) -> list[dict[str, object]]:
    try:
        return [asdict(record) for record in dev_servers_for_worktree(repo_root, workspace_ref)]
    except Exception:
        return []


def _dirty_tracked_files(root: Path) -> tuple[str, ...]:
    paths: set[str] = set()
    for args in (("diff", "--name-only"), ("diff", "--cached", "--name-only")):
        output = _git_stdout(root, *args, allow_failure=True)
        paths.update(line.strip() for line in output.splitlines() if line.strip())
    return tuple(sorted(paths))


def _untracked_files(root: Path) -> tuple[str, ...]:
    output = _git_stdout(root, "ls-files", "--others", "--exclude-standard", allow_failure=True)
    return tuple(sorted(line.strip() for line in output.splitlines() if line.strip()))


def _git_stdout(cwd: Path, *args: str, allow_failure: bool = False) -> str:
    completed = _git(cwd, *args, allow_failure=allow_failure)
    if completed.returncode != 0 and allow_failure:
        return ""
    return completed.stdout.strip()


def _git(
    cwd: Path,
    *args: str,
    input_text: str | None = None,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and not allow_failure:
        raise RecoverError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed
