from __future__ import annotations

from dataclasses import dataclass
import secrets
from pathlib import Path

from ait.config import (
    bootstrap_ait_dir,
    ensure_ait_ignored,
    ensure_local_config,
    ensure_repo_identity,
)
from ait.db import NewAttempt, NewIntent, connect_db, get_intent, insert_attempt, insert_intent, run_migrations, utc_now
from ait.db import (
    insert_intent_edge,
    get_attempt,
    get_evidence_summary,
    get_attempt_outcome,
    list_attempt_commits,
    list_evidence_files,
    list_intent_attempts,
    update_attempt,
    update_intent_status,
)
from ait.hooks import install_post_rewrite_hook
from ait.ids import new_ulid
from ait.idresolver import resolve_attempt_id, resolve_intent_id
from ait.lifecycle import refresh_intent_status
from ait.repo import (
    compose_repo_id,
    derive_repo_identity,
    ensure_initial_commit,
    initialize_git_repo,
    resolve_repo_root,
)
from ait.verifier import verify_attempt_with_connection
from ait.workspace import (
    create_attempt_commit,
    create_attempt_workspace,
    rebase_attempt_workspace,
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
    git_initialized: bool = False
    baseline_commit_created: bool = False


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
    outcome: dict[str, object] | None
    files: dict[str, tuple[str, ...]]
    commits: list[dict[str, object]]


def object_id(repo_id: str) -> str:
    return f"{repo_id}:{new_ulid()}"


def init_repo(repo_root: str | Path, *, auto_git_init: bool = False) -> InitResult:
    git_initialized = False
    baseline_commit_created = False
    try:
        root = resolve_repo_root(repo_root)
    except ValueError:
        if not auto_git_init:
            raise
        root = initialize_git_repo(repo_root)
        git_initialized = True
    ait_dir = bootstrap_ait_dir(root)
    config = ensure_local_config(root)
    ensure_ait_ignored(root)
    baseline_commit_created = ensure_initial_commit(root)
    if not config.repo_identity:
        config = ensure_repo_identity(root, derive_repo_identity(root))
    db_path = ait_dir / "state.sqlite3"
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()
    install_post_rewrite_hook(root)
    repo_id = compose_repo_id(str(config.repo_identity), config.install_nonce)
    socket_path = Path(config.daemon_socket_path)
    if not socket_path.is_absolute():
        socket_path = root / socket_path
    return InitResult(
        repo_root=root,
        ait_dir=ait_dir,
        db_path=db_path,
        repo_id=repo_id,
        socket_path=socket_path,
        git_initialized=git_initialized,
        baseline_commit_created=baseline_commit_created,
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


DEFAULT_CLI_AGENT_ID = "cli:human"


def create_attempt(
    repo_root: str | Path,
    *,
    intent_id: str,
    agent_id: str | None = None,
) -> AttemptResult:
    resolved_agent_id = _validate_agent_id(agent_id)
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    workspace = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        intent_id = resolve_intent_id(conn, intent_id)
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
        harness_prefix = resolved_agent_id.split(":", 1)[0]
        attempt = insert_attempt(
            conn,
            NewAttempt(
                id=attempt_id,
                intent_id=intent_id,
                agent_id=resolved_agent_id,
                workspace_ref=workspace.workspace_ref,
                base_ref_oid=workspace.base_ref_oid,
                base_ref_name=workspace.base_ref_name,
                started_at=utc_now(),
                ownership_token=ownership_token,
                agent_harness=harness_prefix,
            ),
        )
        if conn.in_transaction:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        if workspace is not None:
            try:
                remove_attempt_workspace(workspace.workspace_ref)
            except Exception:
                pass
        raise
    finally:
        conn.close()
    return AttemptResult(
        attempt_id=attempt.id,
        workspace_ref=attempt.workspace_ref,
        base_ref_oid=attempt.base_ref_oid,
        ownership_token=ownership_token,
    )


def _validate_agent_id(agent_id: str | None) -> str:
    if agent_id is None or not agent_id.strip():
        return DEFAULT_CLI_AGENT_ID
    trimmed = agent_id.strip()
    if trimmed.count(":") != 1:
        raise ValueError(
            f"agent_id must be <harness>:<name>: got {agent_id!r}"
        )
    harness, name = trimmed.split(":", 1)
    if not harness or not name:
        raise ValueError(
            f"agent_id must be <harness>:<name>: got {agent_id!r}"
        )
    return trimmed


def show_intent(repo_root: str | Path, *, intent_id: str) -> IntentShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        intent_id = resolve_intent_id(conn, intent_id)
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
        attempt_id = resolve_attempt_id(conn, attempt_id)
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ValueError(f"Unknown attempt: {attempt_id}")
        evidence = get_evidence_summary(conn, attempt_id)
        outcome = get_attempt_outcome(conn, attempt_id)
        files = list_evidence_files(conn, attempt_id)
        commits = list_attempt_commits(conn, attempt_id)
    finally:
        conn.close()
    return AttemptShowResult(
        attempt=attempt.__dict__,
        evidence_summary=None if evidence is None else evidence.__dict__,
        outcome=None if outcome is None else outcome.__dict__,
        files=files,
        commits=[commit.__dict__ for commit in commits],
    )


def discard_attempt(repo_root: str | Path, *, attempt_id: str) -> AttemptShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt_id = resolve_attempt_id(conn, attempt_id)
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
        attempt_id = resolve_attempt_id(conn, attempt_id)
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
        ref_name = _normalize_target_branch_ref(target_ref)
        update_ref_to_workspace_head(init_result.repo_root, ref_name, attempt.workspace_ref)
        update_attempt(conn, attempt_id, result_promotion_ref=ref_name)
        verify_attempt_with_connection(conn, init_result.repo_root, attempt_id)
    finally:
        conn.close()
    return show_attempt(repo_root, attempt_id=attempt_id)


def _normalize_target_branch_ref(target_ref: str) -> str:
    ref = target_ref.strip()
    if not ref:
        raise ValueError("target ref must not be empty")
    if ref.startswith("refs/") and not ref.startswith("refs/heads/"):
        raise ValueError("target ref must be a branch under refs/heads/")
    branch_ref = ref if ref.startswith("refs/heads/") else f"refs/heads/{ref}"
    branch_name = branch_ref.removeprefix("refs/heads/")
    if branch_name in {"", ".", ".."} or branch_name.endswith("/") or "//" in branch_name:
        raise ValueError(f"invalid branch name: {target_ref}")
    return branch_ref


def rebase_attempt(
    repo_root: str | Path,
    *,
    attempt_id: str,
    onto_ref: str,
) -> AttemptShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt_id = resolve_attempt_id(conn, attempt_id)
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ValueError(f"Unknown attempt: {attempt_id}")
        intent = get_intent(conn, attempt.intent_id)
        if intent is None:
            raise ValueError(f"Missing intent for attempt: {attempt_id}")
        if intent.status in {"abandoned", "superseded"}:
            raise ValueError(f"Intent is {intent.status}: {intent.id}")
        if attempt.verified_status in {"discarded", "promoted"}:
            raise ValueError(f"Attempt is already {attempt.verified_status}: {attempt_id}")

        result = rebase_attempt_workspace(
            init_result.repo_root,
            attempt.workspace_ref,
            old_base_ref_oid=attempt.base_ref_oid,
            onto_ref=onto_ref,
        )
        update_attempt(
            conn,
            attempt_id,
            base_ref_oid=result.base_ref_oid,
            base_ref_name=result.onto_ref,
        )
        if attempt.reported_status == "finished":
            verify_attempt_with_connection(conn, init_result.repo_root, attempt_id)
    finally:
        conn.close()
    return show_attempt(repo_root, attempt_id=attempt_id)


def verify_attempt(repo_root: str | Path, *, attempt_id: str) -> AttemptShowResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt_id = resolve_attempt_id(conn, attempt_id)
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
        attempt_id = resolve_attempt_id(conn, attempt_id)
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
        intent_id = resolve_intent_id(conn, intent_id)
        intent = get_intent(conn, intent_id)
        if intent is None:
            raise ValueError(f"Unknown intent: {intent_id}")
        if intent.status not in {"open", "running"}:
            raise ValueError(f"Cannot abandon {intent.status} intent")
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
        intent_id = resolve_intent_id(conn, intent_id)
        by_intent_id = resolve_intent_id(conn, by_intent_id)
        intent = get_intent(conn, intent_id)
        replacement = get_intent(conn, by_intent_id)
        if intent is None:
            raise ValueError(f"Unknown intent: {intent_id}")
        if replacement is None:
            raise ValueError(f"Unknown replacement intent: {by_intent_id}")
        if intent_id == by_intent_id:
            raise ValueError("Intent cannot supersede itself")
        if intent.status not in {"open", "running"}:
            raise ValueError(f"Cannot supersede {intent.status} intent")
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
