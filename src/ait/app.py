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
from ait.db import (
    insert_intent_edge,
    get_attempt,
    get_evidence_summary,
    list_attempt_commits,
    list_evidence_files,
    list_intent_attempts,
    update_attempt,
    update_intent_status,
)
from ait.hooks import install_post_rewrite_hook
from ait.ids import new_ulid
from ait.lifecycle import refresh_intent_status
from ait.repo import derive_repo_id, resolve_repo_root
from ait.verifier import verify_attempt_with_connection
from ait.workspace import (
    create_attempt_commit,
    create_attempt_workspace,
    remove_attempt_workspace,
    update_ref_to_workspace_head,
)


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


@dataclass(slots=True)
class IntentShowResult:
    intent: dict[str, object]
    attempts: list[dict[str, object]]
    files: dict[str, tuple[str, ...]]
    commit_oids: tuple[str, ...]


@dataclass(slots=True)
class AttemptShowResult:
    attempt: dict[str, object]
    evidence_summary: dict[str, object] | None
    files: dict[str, tuple[str, ...]]
    commits: list[dict[str, object]]


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
        if intent.status in {"abandoned", "superseded"}:
            raise ValueError(f"Intent is {intent.status}: {intent_id}")

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


def show_intent(repo_root: str | Path, *, intent_id: str) -> IntentShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        intent = get_intent(conn, intent_id)
        if intent is None:
            raise ValueError(f"Unknown intent: {intent_id}")
        attempts = list_intent_attempts(conn, intent_id)
        files: dict[str, set[str]] = {}
        commit_oids: list[str] = []
        for attempt in attempts:
            attempt_files = list_evidence_files(conn, attempt.id)
            for kind, paths in attempt_files.items():
                files.setdefault(kind, set()).update(paths)
            for commit in list_attempt_commits(conn, attempt.id):
                commit_oids.append(commit.commit_oid)
    finally:
        conn.close()
    return IntentShowResult(
        intent=intent.__dict__,
        attempts=[attempt.__dict__ for attempt in attempts],
        files={kind: tuple(sorted(paths)) for kind, paths in files.items()},
        commit_oids=tuple(sorted(set(commit_oids))),
    )


def show_attempt(repo_root: str | Path, *, attempt_id: str) -> AttemptShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ValueError(f"Unknown attempt: {attempt_id}")
        evidence = get_evidence_summary(conn, attempt_id)
        files = list_evidence_files(conn, attempt_id)
        commits = list_attempt_commits(conn, attempt_id)
    finally:
        conn.close()
    return AttemptShowResult(
        attempt=attempt.__dict__,
        evidence_summary=None if evidence is None else evidence.__dict__,
        files=files,
        commits=[commit.__dict__ for commit in commits],
    )


def discard_attempt(repo_root: str | Path, *, attempt_id: str) -> AttemptShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ValueError(f"Unknown attempt: {attempt_id}")
        if attempt.verified_status == "promoted":
            raise ValueError(f"Attempt is already promoted: {attempt_id}")
        update_attempt(
            conn,
            attempt_id,
            reported_status="finished" if attempt.reported_status in {"created", "running"} else attempt.reported_status,
            verified_status="discarded",
            ended_at=utc_now(),
        )
        refresh_intent_status(conn, attempt.intent_id)
    finally:
        conn.close()
    remove_attempt_workspace(attempt.workspace_ref)
    return show_attempt(repo_root, attempt_id=attempt_id)


def promote_attempt(
    repo_root: str | Path,
    *,
    attempt_id: str,
    target_ref: str,
) -> AttemptShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ValueError(f"Unknown attempt: {attempt_id}")
        intent = get_intent(conn, attempt.intent_id)
        if intent is None:
            raise ValueError(f"Missing intent for attempt: {attempt_id}")
        if intent.status in {"abandoned", "superseded"}:
            raise ValueError(f"Intent is {intent.status}: {intent.id}")
        if attempt.reported_status != "finished":
            raise ValueError(f"Attempt is not finished: {attempt_id}")
        ref_name = target_ref if target_ref.startswith("refs/") else f"refs/heads/{target_ref}"
        update_ref_to_workspace_head(init_result.repo_root, ref_name, attempt.workspace_ref)
        update_attempt(conn, attempt_id, result_promotion_ref=ref_name)
        verify_attempt_with_connection(conn, init_result.repo_root, attempt_id)
    finally:
        conn.close()
    return show_attempt(repo_root, attempt_id=attempt_id)


def verify_attempt(repo_root: str | Path, *, attempt_id: str) -> AttemptShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ValueError(f"Unknown attempt: {attempt_id}")
        verify_attempt_with_connection(conn, init_result.repo_root, attempt_id)
    finally:
        conn.close()
    return show_attempt(repo_root, attempt_id=attempt_id)


def create_commit_for_attempt(
    repo_root: str | Path,
    *,
    attempt_id: str,
    message: str,
) -> AttemptShowResult:
    if not message.strip():
        raise ValueError("Commit message must not be empty")
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ValueError(f"Unknown attempt: {attempt_id}")
        intent = get_intent(conn, attempt.intent_id)
        if intent is None:
            raise ValueError(f"Missing intent for attempt: {attempt_id}")
        if intent.status in {"abandoned", "superseded"}:
            raise ValueError(f"Intent is {intent.status}: {intent.id}")
        create_attempt_commit(
            attempt.workspace_ref,
            message=message,
            intent_id=intent.id,
            attempt_id=attempt.id,
        )
        update_attempt(
            conn,
            attempt_id,
            reported_status="finished",
            ended_at=utc_now(),
            result_exit_code=0,
        )
    finally:
        conn.close()
    return verify_attempt(repo_root, attempt_id=attempt_id)


def abandon_intent(repo_root: str | Path, *, intent_id: str) -> IntentShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        intent = get_intent(conn, intent_id)
        if intent is None:
            raise ValueError(f"Unknown intent: {intent_id}")
        update_intent_status(conn, intent_id, "abandoned")
    finally:
        conn.close()
    return show_intent(repo_root, intent_id=intent_id)


def supersede_intent(
    repo_root: str | Path,
    *,
    intent_id: str,
    by_intent_id: str,
) -> IntentShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        intent = get_intent(conn, intent_id)
        replacement = get_intent(conn, by_intent_id)
        if intent is None:
            raise ValueError(f"Unknown intent: {intent_id}")
        if replacement is None:
            raise ValueError(f"Unknown replacement intent: {by_intent_id}")
        if intent_id == by_intent_id:
            raise ValueError("Intent cannot supersede itself")
        insert_intent_edge(
            conn,
            parent_intent_id=intent_id,
            child_intent_id=by_intent_id,
            edge_type="superseded_by",
            created_at=utc_now(),
        )
        update_intent_status(conn, intent_id, "superseded")
    finally:
        conn.close()
    return show_intent(repo_root, intent_id=intent_id)


