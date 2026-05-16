from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ait.db import connect_db, list_memory_facts, utc_now
from ait.memory.models import RelevantMemoryItem, RelevantMemoryRecall
from ait.memory_policy import load_memory_policy, path_excluded, transcript_excluded
from ait.repo import resolve_repo_root
from ait.team_policy import TeamPolicyEnforcementError, team_policy_blocks_path, validate_team_policy

CONTEXT_MANIFEST_SCHEMA = "ait.context_manifest"
CONTEXT_MANIFEST_SCHEMA_VERSION = 1


def render_context_memory_trust_markdown(repo_root: str | Path, recall: RelevantMemoryRecall) -> str:
    recall = apply_context_trust_policy(repo_root, recall)
    payload = build_context_manifest_payload(
        repo_root,
        owner_kind="preview",
        owner_id="preview",
        context_ref="",
        recall=recall,
    )
    trusted = [entry for entry in payload["entries"] if entry.get("trusted_baseline")]
    excluded = [entry for entry in payload["entries"] if not entry.get("trusted_baseline")]
    by_id = {item.id: item for item in recall.selected}
    lines = [
        "# AIT Memory Trust Context",
        "",
        "## Trusted Baseline",
        "",
    ]
    if not trusted:
        lines.append("- none")
    for entry in trusted:
        item = by_id.get(str(entry.get("source_id")))
        text = " ".join((item.text if item else "").split())
        suffix = f": {text[:800]}" if text else ""
        lines.append(f"- {entry.get('source_id')} ({entry.get('topic') or 'general'}){suffix}")
    lines.extend(["", "## Advisory Or Excluded Memory", ""])
    if not excluded:
        lines.append("- none")
    for entry in excluded:
        lines.append(
            "- "
            f"{entry.get('source_id')}: {entry.get('reason')} "
            f"(status={entry.get('status')}, trust={entry.get('trust_level')})"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_context_manifest(
    repo_root: str | Path,
    *,
    owner_kind: str,
    owner_id: str,
    context_ref: str,
    recall: RelevantMemoryRecall,
    context_text: str = "",
    extra_payload: dict[str, object] | None = None,
) -> str:
    root = resolve_repo_root(repo_root)
    payload = build_context_manifest_payload(
        root,
        owner_kind=owner_kind,
        owner_id=owner_id,
        context_ref=context_ref,
        recall=recall,
        context_text=context_text,
    )
    if extra_payload:
        protected = {
            "schema",
            "schema_version",
            "entries",
            "trusted_baseline_refs",
            "policy_exclusions",
            "selected_memory",
            "skipped_memory",
            "source_manifest",
            "write_mode",
            "content_sha256",
        }
        payload.update({key: value for key, value in extra_payload.items() if key not in protected})
    safe_owner_id = owner_id.replace(":", "_").replace("/", "_")
    manifest_ref = f".ait/context/{owner_kind}-{safe_owner_id}.manifest.json"
    path = root / manifest_ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    context_path = Path(context_ref)
    if context_ref and context_path.is_absolute():
        _write_sidecar_manifest(context_path, payload)
    elif context_ref:
        _write_sidecar_manifest(root / context_path, payload)
    return manifest_ref


def build_context_manifest_payload(
    repo_root: str | Path,
    *,
    owner_kind: str,
    owner_id: str,
    context_ref: str,
    recall: RelevantMemoryRecall,
    context_text: str = "",
) -> dict[str, object]:
    root = resolve_repo_root(repo_root)
    recall = apply_context_trust_policy(root, recall)
    policy = load_memory_policy(root)
    entries: list[dict[str, object]] = []
    selected_ids: set[str] = set()
    for item in recall.selected:
        selected_ids.add(item.id)
        entries.append(_selected_entry(item))
    skipped_ids: set[str] = set()
    for item in recall.skipped:
        entry = _skipped_entry(item)
        if entry is not None:
            skipped_ids.add(str(entry["source_id"]))
            entries.append(entry)
    entries.extend(
        _memory_fact_entries(
            root,
            selected_ids=selected_ids,
            skipped_ids=skipped_ids,
        )
    )
    trusted_refs = [entry["source_id"] for entry in entries if entry.get("trusted_baseline")]
    policy_exclusions = [
        entry
        for entry in entries
        if entry.get("reason") in {"policy_blocked", "fact_source_blocked", "excluded_source_path", "excluded_content"}
    ]
    payload = {
        "schema": CONTEXT_MANIFEST_SCHEMA,
        "schema_version": CONTEXT_MANIFEST_SCHEMA_VERSION,
        "context_id": f"ctx_{_stable_hash([owner_kind, owner_id, context_ref])[:24]}",
        "owner_kind": owner_kind,
        "owner_id": owner_id,
        "context_ref": context_ref,
        "generated_at": utc_now(),
        "memory_query": recall.query,
        "policy_hash": _stable_hash(policy.to_dict()),
        "entries": entries,
        "trusted_baseline_refs": trusted_refs,
        "policy_exclusions": policy_exclusions,
        "source_manifest": list(recall.source_manifest),
        "selected_memory": [item.to_dict() for item in recall.selected],
        "skipped_memory": list(recall.skipped),
        "write_mode": "ait_context_artifact",
        "content_sha256": hashlib.sha256(context_text.encode("utf-8")).hexdigest() if context_text else None,
    }
    return payload


def apply_context_trust_policy(repo_root: str | Path, recall: RelevantMemoryRecall) -> RelevantMemoryRecall:
    root = resolve_repo_root(repo_root)
    validation = validate_team_policy(root)
    if not validation.valid:
        raise TeamPolicyEnforcementError(
            {
                "schema": "ait.team_policy.enforcement",
                "schema_version": 1,
                "operation": "context_trust",
                "attempt_id": None,
                "status": "blocked",
                "checks": [
                    {
                        "name": "team_policy_valid",
                        "status": "blocked",
                        "message": "; ".join(validation.payload["errors"]),
                    }
                ],
                "policy_validation": validation.payload,
            }
        )
    policy_payload = validation.payload["policy"]
    selected: list[RelevantMemoryItem] = []
    skipped: list[dict[str, object]] = list(recall.skipped)
    for item in recall.selected:
        source_path = str(item.metadata.get("source_file_path") or item.metadata.get("path") or "")
        status = str(item.metadata.get("status") or "accepted")
        if status != "accepted":
            skipped.append(_skipped_from_item(item, reason="candidate_not_adopted" if status == "candidate" else "not_accepted"))
            continue
        if team_policy_blocks_path(policy_payload, source_path):
            skipped.append(_skipped_from_item(item, reason="policy_blocked"))
            continue
        selected.append(item)
    if tuple(selected) == recall.selected and tuple(skipped) == recall.skipped:
        return recall
    return RelevantMemoryRecall(
        query=recall.query,
        selected=tuple(selected),
        skipped=tuple(skipped),
        budget_chars=recall.budget_chars,
        rendered_chars=sum(len(item.text) for item in selected),
        compacted=recall.compacted,
        source_manifest=recall.source_manifest,
        write_mode=recall.write_mode,
        record_ref=recall.record_ref,
    )


def _selected_entry(item: RelevantMemoryItem) -> dict[str, object]:
    text = item.text or ""
    metadata = item.metadata
    return {
        "source_id": item.id,
        "source_type": _source_type(item.kind),
        "topic": item.topic,
        "status": str(metadata.get("status") or "accepted"),
        "trust_level": "trusted",
        "selected": True,
        "trusted_baseline": True,
        "included_in_context": True,
        "body_included": bool(text),
        "reason": "selected_trusted_memory",
        "source_ref": str(metadata.get("source_trace_ref") or metadata.get("source") or item.source),
        "source_path_redacted": _source_path(metadata),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        "bytes_included": len(text.encode("utf-8")),
    }


def _skipped_from_item(item: RelevantMemoryItem, *, reason: str) -> dict[str, object]:
    return {
        "id": item.id,
        "source_id": item.id,
        "kind": item.kind,
        "topic": item.topic,
        "reason": reason,
        "source": item.source,
    }


def _skipped_entry(item: dict[str, object]) -> dict[str, object] | None:
    source_id = str(item.get("id") or item.get("source_id") or "")
    if not source_id:
        return None
    reason = _normal_reason(str(item.get("reason") or "excluded"))
    return {
        "source_id": source_id,
        "source_type": _source_type(str(item.get("kind") or "memory")),
        "topic": str(item.get("topic") or ""),
        "status": _status_for_reason(reason),
        "trust_level": _trust_for_reason(reason),
        "selected": False,
        "trusted_baseline": False,
        "included_in_context": bool(item.get("included_in_context", False)),
        "body_included": bool(item.get("body_included", False)),
        "reason": reason,
        "source_ref": str(item.get("source") or ""),
        "source_path_redacted": None,
        "content_hash": None,
        "bytes_included": int(item.get("bytes_included", 0) or 0),
    }


def _memory_fact_entries(
    repo_root: Path,
    *,
    selected_ids: set[str],
    skipped_ids: set[str],
) -> list[dict[str, object]]:
    db_path = repo_root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return []
    policy = load_memory_policy(repo_root)
    conn = connect_db(db_path)
    try:
        facts = list_memory_facts(conn, include_superseded=True, limit=200)
    finally:
        conn.close()
    entries: list[dict[str, object]] = []
    for fact in facts:
        if fact.id in selected_ids or fact.id in skipped_ids:
            continue
        reason = _fact_reason(fact, policy)
        if reason == "not_selected_trusted_fact":
            trust_level = "trusted"
            status = fact.status
        else:
            trust_level = _trust_for_reason(reason)
            status = _status_for_fact(fact, reason)
        entries.append(
            {
                "source_id": fact.id,
                "source_type": "memory_fact",
                "topic": fact.topic,
                "status": status,
                "trust_level": trust_level,
                "selected": False,
                "trusted_baseline": False,
                "included_in_context": False,
                "body_included": False,
                "reason": reason,
                "source_ref": fact.source_trace_ref or "",
                "source_path_redacted": fact.source_file_path or None,
                "content_hash": None,
                "bytes_included": 0,
                **({"superseded_by": fact.superseded_by} if fact.superseded_by else {}),
            }
        )
    return entries


def _fact_reason(fact, policy) -> str:
    if fact.status != "accepted":
        if fact.status == "candidate":
            return "candidate_not_adopted"
        if fact.status == "superseded":
            return "superseded_fact"
        return "not_accepted"
    if fact.superseded_by:
        return "superseded_fact"
    if fact.valid_to and fact.valid_to <= utc_now():
        return "expired_fact"
    if fact.source_file_path and path_excluded(fact.source_file_path, policy):
        return "policy_blocked"
    if transcript_excluded(" ".join([fact.body, fact.summary]), policy):
        return "policy_blocked"
    return "not_selected_trusted_fact"


def _normal_reason(reason: str) -> str:
    lowered = reason.lower()
    if "candidate" in lowered or "status is candidate" in lowered:
        return "candidate_not_adopted"
    if "superseded" in lowered:
        return "superseded_fact"
    if "expired" in lowered or "stale" in lowered:
        return "expired_fact"
    if "policy" in lowered or "excluded" in lowered or "blocked" in lowered:
        return "policy_blocked"
    if "over selection limit" in lowered:
        return "not_selected"
    return reason.replace(" ", "_")


def _trust_for_reason(reason: str) -> str:
    if reason == "candidate_not_adopted":
        return "candidate"
    if reason in {"superseded_fact", "expired_fact"}:
        return "stale"
    if reason == "policy_blocked":
        return "policy_blocked"
    return "advisory"


def _status_for_reason(reason: str) -> str:
    if reason == "candidate_not_adopted":
        return "candidate"
    if reason == "superseded_fact":
        return "superseded"
    if reason == "expired_fact":
        return "stale"
    if reason == "policy_blocked":
        return "excluded"
    return "advisory"


def _status_for_fact(fact, reason: str) -> str:
    if reason == "expired_fact":
        return "stale"
    if reason == "policy_blocked":
        return "excluded"
    return str(fact.status)


def _source_type(kind: str) -> str:
    if kind == "fact":
        return "memory_fact"
    if kind == "live_source":
        return "live_memory_source"
    if kind == "note":
        return "memory_note"
    return kind or "memory"


def _source_path(metadata: dict[str, object]) -> str | None:
    value = str(metadata.get("source_file_path") or metadata.get("path") or "")
    return value or None


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_sidecar_manifest(context_path: Path, payload: dict[str, object]) -> None:
    try:
        sidecar = context_path.with_name(context_path.name + ".manifest.json")
        sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return


__all__ = [
    "CONTEXT_MANIFEST_SCHEMA",
    "CONTEXT_MANIFEST_SCHEMA_VERSION",
    "apply_context_trust_policy",
    "build_context_manifest_payload",
    "render_context_memory_trust_markdown",
    "write_context_manifest",
]
