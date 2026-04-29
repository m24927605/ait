from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from ait.db import (
    AttemptCommitRecord,
    connect_db,
    get_attempt,
    get_evidence_summary,
    get_intent,
    list_attempt_commits,
    replace_attempt_commits,
    replace_evidence_files_kind,
    update_attempt,
    upsert_attempt_outcome,
    utc_now,
)
from ait.lifecycle import refresh_intent_status
from ait.memory import extract_memory_candidates
from ait.outcome import OutcomeClassification, classify_attempt_outcome
from ait.repo import resolve_repo_root
from ait.workspace import (
    commit_parent_oid,
    commit_stats,
    list_attempt_commit_oids,
    ref_contains_commits,
)


@dataclass(frozen=True, slots=True)
class VerifyResult:
    attempt_id: str
    verified_status: str
    commit_oids: tuple[str, ...]
    files_changed: tuple[str, ...]
    outcome_class: str


def verify_attempt(repo_root: str | Path, attempt_id: str) -> VerifyResult:
    root = resolve_repo_root(repo_root)
    db_path = root / ".ait" / "state.sqlite3"
    conn = connect_db(db_path)
    try:
        return verify_attempt_with_connection(conn, root, attempt_id)
    finally:
        conn.close()


def verify_attempt_with_connection(
    conn: sqlite3.Connection, repo_root: Path, attempt_id: str
) -> VerifyResult:
    attempt = get_attempt(conn, attempt_id)
    if attempt is None:
        raise ValueError(f"Unknown attempt: {attempt_id}")
    intent = get_intent(conn, attempt.intent_id)
    if intent is None:
        raise ValueError(f"Missing intent for attempt: {attempt_id}")
    evidence = get_evidence_summary(conn, attempt_id)
    if evidence is None:
        raise ValueError(f"Missing evidence summary: {attempt_id}")

    commits = _materialize_attempt_commits(attempt)
    replace_attempt_commits(conn, attempt_id=attempt_id, commits=commits)

    changed_files = tuple(
        sorted({file_path for commit in commits for file_path in commit.touched_files})
    )
    replace_evidence_files_kind(
        conn,
        attempt_id=attempt_id,
        kind="changed",
        file_paths=changed_files,
    )

    verified_status = _determine_verified_status(repo_root, intent.status, attempt, evidence, commits)
    update_attempt(conn, attempt_id, verified_status=verified_status)
    refreshed_attempt = get_attempt(conn, attempt_id)
    if refreshed_attempt is None:
        raise ValueError(f"Unknown attempt after verification: {attempt_id}")
    outcome = _classify_and_store_outcome(
        conn,
        repo_root=repo_root,
        attempt=refreshed_attempt,
        evidence=evidence,
        changed_files=changed_files,
        commit_oids=tuple(commit.commit_oid for commit in commits),
    )
    refresh_intent_status(conn, attempt.intent_id)
    return VerifyResult(
        attempt_id=attempt_id,
        verified_status=verified_status,
        commit_oids=tuple(commit.commit_oid for commit in commits),
        files_changed=changed_files,
        outcome_class=outcome.outcome_class,
    )


def _materialize_attempt_commits(attempt) -> tuple[AttemptCommitRecord, ...]:
    commit_oids = list_attempt_commit_oids(attempt.workspace_ref, attempt.base_ref_oid)
    commits: list[AttemptCommitRecord] = []
    for commit_oid in commit_oids:
        base_commit_oid = commit_parent_oid(attempt.workspace_ref, commit_oid) or attempt.base_ref_oid
        insertions, deletions, touched_files = commit_stats(attempt.workspace_ref, commit_oid)
        commits.append(
            AttemptCommitRecord(
                attempt_id=attempt.id,
                commit_oid=commit_oid,
                base_commit_oid=base_commit_oid,
                insertions=insertions,
                deletions=deletions,
                touched_files=touched_files,
            )
        )
    return tuple(commits)


def _determine_verified_status(repo_root: Path, intent_status: str, attempt, evidence, commits) -> str:
    if attempt.verified_status == "discarded":
        return "discarded"
    if attempt.reported_status != "finished":
        return "failed" if attempt.reported_status == "crashed" else attempt.verified_status
    if attempt.result_exit_code not in (None, 0):
        return "failed"
    if attempt.raw_trace_ref and not _ref_exists(repo_root, attempt.raw_trace_ref):
        return "failed"
    if attempt.logs_ref and not _ref_exists(repo_root, attempt.logs_ref):
        return "failed"
    if evidence.raw_trace_ref and not _ref_exists(repo_root, evidence.raw_trace_ref):
        return "failed"
    if evidence.logs_ref and not _ref_exists(repo_root, evidence.logs_ref):
        return "failed"

    commit_oids = tuple(commit.commit_oid for commit in commits)
    if attempt.result_promotion_ref:
        if intent_status == "abandoned":
            return "failed"
        if commit_oids and ref_contains_commits(repo_root, attempt.result_promotion_ref, commit_oids):
            return "promoted"
        return "failed"
    return "succeeded"


def _classify_and_store_outcome(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    attempt,
    evidence,
    changed_files: tuple[str, ...],
    commit_oids: tuple[str, ...],
) -> OutcomeClassification:
    raw_trace_ref = attempt.raw_trace_ref or evidence.raw_trace_ref or ""
    raw_trace_text = _read_ref_text(repo_root, raw_trace_ref, limit=12000)
    candidates = extract_memory_candidates(
        raw_trace_text,
        attempt_id=attempt.id,
        source_ref=raw_trace_ref,
        verified_status=attempt.verified_status,
    )
    outcome = classify_attempt_outcome(
        reported_status=attempt.reported_status,
        verified_status=attempt.verified_status,
        result_exit_code=attempt.result_exit_code,
        changed_files=changed_files,
        commit_oids=commit_oids,
        observed_tool_calls=evidence.observed_tool_calls,
        observed_file_writes=evidence.observed_file_writes,
        observed_tests_run=evidence.observed_tests_run,
        observed_tests_failed=evidence.observed_tests_failed,
        raw_trace_text=raw_trace_text,
        has_memory_candidates=bool(candidates),
    )
    upsert_attempt_outcome(
        conn,
        attempt_id=attempt.id,
        outcome_class=outcome.outcome_class,
        confidence=outcome.confidence,
        reasons=outcome.reasons,
        classified_at=utc_now(),
    )
    return outcome


def _ref_exists(repo_root: Path, ref_path: str) -> bool:
    path = Path(ref_path)
    if path.is_absolute():
        return path.exists()
    return (repo_root / ref_path).exists()


def _read_ref_text(repo_root: Path, ref_path: str, *, limit: int) -> str:
    if not ref_path:
        return ""
    path = Path(ref_path)
    if not path.is_absolute():
        path = repo_root / path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""
