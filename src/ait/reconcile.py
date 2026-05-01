from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ait.db import connect_db
from ait.repo import resolve_repo_root

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


def reconcile_repo(repo_root: str | Path) -> ReconcileResult:
    root = resolve_repo_root(repo_root)
    mappings = load_rewrite_mappings(root)
    post_rewrite_path = root / POST_REWRITE_LAST
    manual_marker = root / MANUAL_RECONCILE_REQUIRED
    if not mappings:
        if manual_marker.exists():
            manual_marker.unlink()
        return ReconcileResult(0, 0, 0, 0, False)

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
    return ReconcileResult(
        processed_mappings=len(mappings),
        updated_commit_rows=updated_commit_rows,
        updated_base_rows=updated_base_rows,
        unmapped_mappings=len(unmapped),
        manual_repair_required=manual_repair_required,
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
