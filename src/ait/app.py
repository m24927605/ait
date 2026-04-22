from __future__ import annotations

from dataclasses import dataclass
import secrets
from pathlib import Path

from ait.config import (
    bootstrap_ait_dir,
    ensure_ait_ignored,
    ensure_local_config,
)
from ait.db import NewAttempt, NewIntent, connect_db, get_intent, insert_attempt, insert_intent, run_migrations, utc_now
from ait.hooks import install_post_rewrite_hook
from ait.ids import new_ulid
from ait.repo import derive_repo_id, resolve_repo_root
from ait.workspace import create_attempt_workspace


@dataclass(slots=True)
class InitResult:
    repo_root: Path
    ait_dir: Path
    db_path: Path
    repo_id: str
    socket_path: Path


@dataclass(slots=True)
class IntentResult:
    intent_id: str
    repo_id: str


@dataclass(slots=True)
class AttemptResult:
    attempt_id: str
    workspace_ref: str
    base_ref_oid: str
    ownership_token: str


def object_id(repo_id: str) -> str:
    return f"{repo_id}:{new_ulid()}"


def init_repo(repo_root: str | Path) -> InitResult:
    root = resolve_repo_root(repo_root)
    ait_dir = bootstrap_ait_dir(root)
    config = ensure_local_config(root)
    ensure_ait_ignored(root)
    db_path = ait_dir / "state.sqlite3"
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()
    install_post_rewrite_hook(root)
    repo_id = derive_repo_id(root, config.install_nonce)
    socket_path = Path(config.daemon_socket_path)
    if not socket_path.is_absolute():
        socket_path = root / socket_path
    return InitResult(
        repo_root=root,
        ait_dir=ait_dir,
        db_path=db_path,
        repo_id=repo_id,
        socket_path=socket_path,
    )


def create_intent(
    repo_root: str | Path,
    *,
    title: str,
    description: str | None,
    kind: str | None,
) -> IntentResult:
    init_result = init_repo(repo_root)
    intent_id = object_id(init_result.repo_id)
    conn = connect_db(init_result.db_path)
    try:
        record = insert_intent(
            conn,
            NewIntent(
                id=intent_id,
                repo_id=init_result.repo_id,
                title=title,
                description=description,
                kind=kind,
                created_at=utc_now(),
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
    finally:
        conn.close()
    return IntentResult(intent_id=record.id, repo_id=init_result.repo_id)


def create_attempt(repo_root: str | Path, *, intent_id: str) -> AttemptResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        intent = get_intent(conn, intent_id)
        if intent is None:
            raise ValueError(f"Unknown intent: {intent_id}")
        if intent.status == "abandoned":
            raise ValueError(f"Intent is abandoned: {intent_id}")

        ordinal_row = conn.execute(
            "SELECT COALESCE(MAX(ordinal), 0) + 1 AS next_ordinal FROM attempts WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        ordinal = int(ordinal_row["next_ordinal"])
        attempt_id = object_id(init_result.repo_id)
        workspace = create_attempt_workspace(
            repo_root=init_result.repo_root,
            attempt_id=attempt_id,
            ordinal=ordinal,
        )
        ownership_token = secrets.token_urlsafe(24)
        attempt = insert_attempt(
            conn,
            NewAttempt(
                id=attempt_id,
                intent_id=intent_id,
                agent_id="codex:main",
                workspace_ref=workspace.workspace_ref,
                base_ref_oid=workspace.base_ref_oid,
                base_ref_name=workspace.base_ref_name,
                started_at=utc_now(),
                ownership_token=ownership_token,
                agent_harness="codex",
            ),
        )
    finally:
        conn.close()
    return AttemptResult(
        attempt_id=attempt.id,
        workspace_ref=attempt.workspace_ref,
        base_ref_oid=attempt.base_ref_oid,
        ownership_token=ownership_token,
    )
