from __future__ import annotations

import re
import sqlite3

from ait.query.models import BlameRecord, BlameTarget, QueryError


def parse_blame_target(target: str) -> BlameTarget:
    if not target:
        raise QueryError("blame target must not be empty")
    invalid_line = re.fullmatch(r"(.+):(0|0\d+)", target)
    if invalid_line:
        raise QueryError("blame target line must be a positive integer without leading zeroes")
    match = re.fullmatch(r"(.+):([1-9]\d*)", target)
    if match:
        return BlameTarget(path=match.group(1), line=int(match.group(2)))
    return BlameTarget(path=target)


def blame_path(conn: sqlite3.Connection, target: str) -> list[BlameRecord]:
    blame_target = parse_blame_target(target)
    rows = conn.execute(
        """
        WITH file_hits AS (
            SELECT
                ef.attempt_id AS attempt_id,
                MIN(
                    CASE ef.kind
                        WHEN 'changed' THEN 0
                        WHEN 'touched' THEN 1
                        ELSE 2
                    END
                ) AS best_rank
            FROM evidence_files AS ef
            WHERE ef.file_path = ?
            GROUP BY ef.attempt_id
        )
        SELECT
            a.id AS attempt_id,
            a.intent_id AS intent_id,
            CASE file_hits.best_rank
                WHEN 0 THEN 'changed'
                WHEN 1 THEN 'touched'
                ELSE 'read'
            END AS file_kind,
            ac.commit_oid AS commit_oid,
            a.reported_status AS reported_status,
            a.verified_status AS verified_status,
            a.started_at AS started_at
        FROM file_hits
        JOIN attempts AS a ON a.id = file_hits.attempt_id
        LEFT JOIN attempt_commits AS ac ON ac.attempt_id = a.id
        ORDER BY
            file_hits.best_rank,
            a.started_at DESC,
            ac.commit_oid ASC
        """,
        (blame_target.path,),
    ).fetchall()
    return [
        BlameRecord(
            attempt_id=str(row["attempt_id"]),
            intent_id=str(row["intent_id"]),
            file_kind=str(row["file_kind"]),
            commit_oid=None if row["commit_oid"] is None else str(row["commit_oid"]),
            reported_status=str(row["reported_status"]),
            verified_status=str(row["verified_status"]),
            started_at=str(row["started_at"]),
        )
        for row in rows
    ]
