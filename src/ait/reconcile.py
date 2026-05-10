from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ait.agent_state import detected_context_payload, inspect_agent_state
from ait.db import connect_db, get_attempt, list_attempt_commits, run_migrations, update_attempt, utc_now
from ait.repo import resolve_repo_root
from ait.verifier import verify_attempt_with_connection
from ait.workspace_lease import update_workspace_lease

POST_REWRITE_LAST = ".ait/post-rewrite.last"
MANUAL_RECONCILE_REQUIRED = ".ait/manual-reconcile-required"


@dataclass(frozen=True, slots=True)
class RewriteMapping:
    old_commit_oid: str
    new_commit_oid: str


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    processed_mappings: int
    updated_commit_rows: int
    updated_base_rows: int
    unmapped_mappings: int
    manual_repair_required: bool
    synthetic_result_created: bool = False
    attempt_id: str | None = None
    commit_oids: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    blocking_reason: str | None = None
    detected_context: dict[str, object] = field(default_factory=dict)


def reconcile_repo(repo_root: str | Path) -> ReconcileResult:
    cwd = Path(repo_root).resolve()
    root = resolve_repo_root(cwd)
    mappings = load_rewrite_mappings(root)
    post_rewrite_path = root / POST_REWRITE_LAST
    manual_marker = root / MANUAL_RECONCILE_REQUIRED
    if not mappings:
        if manual_marker.exists():
            manual_marker.unlink()
        manual = _reconcile_manual_workspace_commits(root, cwd)
        return ReconcileResult(
            0,
            0,
            0,
            0,
            bool(manual["blocking_reason"]),
            synthetic_result_created=bool(manual["synthetic_result_created"]),
            attempt_id=_str_or_none(manual["attempt_id"]),
            commit_oids=tuple(str(item) for item in manual["commit_oids"]),
            changed_files=tuple(str(item) for item in manual["changed_files"]),
            blocking_reason=_str_or_none(manual["blocking_reason"]),
            detected_context=dict(manual["detected_context"]),
        )

    db_path = root / ".ait" / "state.sqlite3"
    conn = connect_db(db_path)
    updated_commit_rows = 0
    updated_base_rows = 0
    unmapped: list[RewriteMapping] = []
    try:
        with conn:
            for mapping in mappings:
                commit_rows = _rewrite_commit_oid(conn, mapping)
                base_rows = conn.execute(
                    """
                    UPDATE attempt_commits
                    SET base_commit_oid = ?
                    WHERE base_commit_oid = ?
                    """,
                    (mapping.new_commit_oid, mapping.old_commit_oid),
                ).rowcount
                updated_commit_rows += commit_rows
                updated_base_rows += base_rows
                if commit_rows == 0 and base_rows == 0:
                    unmapped.append(mapping)
    finally:
        conn.close()

    manual_repair_required = bool(unmapped)
    if post_rewrite_path.exists() and not manual_repair_required:
        post_rewrite_path.unlink()
    if manual_repair_required:
        _write_manual_reconcile_marker(manual_marker, unmapped)
    elif manual_marker.exists():
        manual_marker.unlink()
    manual = _reconcile_manual_workspace_commits(root, cwd)
    return ReconcileResult(
        processed_mappings=len(mappings),
        updated_commit_rows=updated_commit_rows,
        updated_base_rows=updated_base_rows,
        unmapped_mappings=len(unmapped),
        manual_repair_required=manual_repair_required or bool(manual["blocking_reason"]),
        synthetic_result_created=bool(manual["synthetic_result_created"]),
        attempt_id=_str_or_none(manual["attempt_id"]),
        commit_oids=tuple(str(item) for item in manual["commit_oids"]),
        changed_files=tuple(str(item) for item in manual["changed_files"]),
        blocking_reason=_str_or_none(manual["blocking_reason"]),
        detected_context=dict(manual["detected_context"]),
    )


def load_rewrite_mappings(repo_root: str | Path) -> tuple[RewriteMapping, ...]:
    path = Path(repo_root).resolve() / POST_REWRITE_LAST
    if not path.exists():
        return ()
    mappings: list[RewriteMapping] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"Malformed post-rewrite mapping line: {raw_line}")
        mappings.append(RewriteMapping(old_commit_oid=parts[0], new_commit_oid=parts[1]))
    return tuple(mappings)


def _rewrite_commit_oid(conn, mapping: RewriteMapping) -> int:
    rows = conn.execute(
        """
        SELECT attempt_id
        FROM attempt_commits
        WHERE commit_oid = ?
        """,
        (mapping.old_commit_oid,),
    ).fetchall()
    updated = 0
    for row in rows:
        attempt_id = str(row["attempt_id"])
        existing = conn.execute(
            """
            SELECT 1
            FROM attempt_commits
            WHERE attempt_id = ? AND commit_oid = ?
            """,
            (attempt_id, mapping.new_commit_oid),
        ).fetchone()
        if existing is not None:
            conn.execute(
                """
                DELETE FROM attempt_commits
                WHERE attempt_id = ? AND commit_oid = ?
                """,
                (attempt_id, mapping.old_commit_oid),
            )
            updated += 1
            continue
        updated += conn.execute(
            """
            UPDATE attempt_commits
            SET commit_oid = ?
            WHERE attempt_id = ? AND commit_oid = ?
            """,
            (mapping.new_commit_oid, attempt_id, mapping.old_commit_oid),
        ).rowcount
    return updated


def _write_manual_reconcile_marker(path: Path, mappings: list[RewriteMapping]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "AIT manual reconcile required",
        "The following post-rewrite mappings did not match any tracked attempt commit or base commit:",
    ]
    lines.extend(f"- {mapping.old_commit_oid} {mapping.new_commit_oid}" for mapping in mappings)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _reconcile_manual_workspace_commits(root: Path, cwd: Path) -> dict[str, object]:
    state = inspect_agent_state(cwd)
    context = detected_context_payload(state)
    empty = {
        "synthetic_result_created": False,
        "attempt_id": state.attempt.attempt_id,
        "commit_oids": list(state.attempt.actual_commit_oids),
        "changed_files": list(state.attempt.actual_changed_files),
        "blocking_reason": None,
        "detected_context": context,
    }
    if not state.attempt.manual_commits_can_be_synthetic:
        return empty
    if state.blocking_reasons:
        return {
            **empty,
            "blocking_reason": "; ".join(state.blocking_reasons),
        }
    attempt_id = state.attempt.attempt_id
    if attempt_id is None:
        return empty

    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            return {
                **empty,
                "blocking_reason": f"attempt not found: {attempt_id}",
            }
        update_attempt(
            conn,
            attempt_id,
            reported_status="finished",
            ended_at=utc_now(),
            result_exit_code=0,
        )
        verified = verify_attempt_with_connection(conn, root, attempt_id)
        commits = list_attempt_commits(conn, attempt_id)
    finally:
        conn.close()
    update_workspace_lease(
        attempt.workspace_ref,
        state="succeeded",
        cleanup_policy="auto",
        clear_preserve_reason=True,
    )
    return {
        "synthetic_result_created": True,
        "attempt_id": attempt_id,
        "commit_oids": list(verified.commit_oids),
        "changed_files": list(verified.files_changed),
        "blocking_reason": None,
        "detected_context": {
            **context,
            "result_metadata_exists": True,
            "manual_commits_can_be_synthetic": False,
            "recorded_commit_count": len(commits),
        },
    }


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
