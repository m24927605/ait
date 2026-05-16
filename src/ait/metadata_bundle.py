from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

from ait.db import (
    connect_db,
    list_attempt_reviews,
    list_attempts,
    list_memory_facts,
    list_review_findings,
    utc_now,
)
from ait.redaction import redact_text
from ait.repo import derive_repo_identity, resolve_repo_root

METADATA_BUNDLE_SCHEMA = "ait.metadata_bundle"
METADATA_BUNDLE_SCHEMA_VERSION = 1
METADATA_IMPORT_PLAN_SCHEMA = "ait.metadata_import_plan"
METADATA_IMPORT_PLAN_SCHEMA_VERSION = 1


def export_metadata_bundle(
    repo_root: str | Path,
    *,
    output: str | Path | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    root = resolve_repo_root(repo_root)
    contents = _read_local_metadata(root)
    output_ref = str(output) if output is not None else None
    bundle = {
        "schema": METADATA_BUNDLE_SCHEMA,
        "schema_version": METADATA_BUNDLE_SCHEMA_VERSION,
        "operation": "export",
        "dry_run": dry_run,
        "status": "planned" if dry_run else "written",
        "created_at": utc_now(),
        "repo": {
            "identity": derive_repo_identity(root),
            "name": root.name,
        },
        "object_counts": {
            "attempts": len(contents["attempts"]),
            "memory_facts": len(contents["memory_facts"]),
            "reviews": len(contents["reviews"]),
            "review_findings": len(contents["review_findings"]),
        },
        "contents": contents,
        "output": {
            "path": output_ref,
            "will_write": not dry_run and output_ref is not None,
            "written": False,
        },
        "redaction": {
            "absolute_paths": "omitted",
            "secrets": "redacted",
            "memory_bodies": "omitted",
            "review_finding_bodies": "omitted",
        },
        "limitations": [
            "local-only metadata bundle",
            "no remote sync",
            "no telemetry",
            "no automatic push",
            "no automatic merge",
        ],
    }
    bundle["content_sha256"] = _payload_hash(bundle)
    if not dry_run and output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        bundle["output"]["written"] = True
    return bundle


def import_metadata_bundle(
    repo_root: str | Path,
    *,
    input_path: str | Path,
    dry_run: bool = True,
) -> dict[str, Any]:
    if not dry_run:
        raise ValueError("metadata import only supports --dry-run in this version")
    root = resolve_repo_root(repo_root)
    path = Path(input_path)
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _import_plan(
            root,
            path,
            status="invalid",
            errors=[f"input is not a valid metadata bundle: {exc}"],
        )
    errors = _validate_bundle(bundle)
    warnings: list[str] = []
    repo = bundle.get("repo") if isinstance(bundle, dict) else None
    bundle_identity = repo.get("identity") if isinstance(repo, dict) else None
    current_identity = derive_repo_identity(root)
    if bundle_identity and bundle_identity != current_identity:
        warnings.append("bundle repo identity does not match current repo; dry-run only")
    return _import_plan(
        root,
        path,
        status="planned" if not errors else "invalid",
        errors=errors,
        warnings=warnings,
        bundle=bundle if isinstance(bundle, dict) else {},
    )


def _read_local_metadata(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    db_path = repo_root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return {
            "attempts": [],
            "memory_facts": [],
            "reviews": [],
            "review_findings": [],
        }
    conn = connect_db(db_path)
    try:
        attempts = [_attempt_payload(record) for record in list_attempts(conn)]
        memory_facts = [_memory_fact_payload(record) for record in list_memory_facts(conn)]
        reviews = [_review_payload(record) for record in list_attempt_reviews(conn)]
        review_findings = [_review_finding_payload(record) for record in list_review_findings(conn)]
    finally:
        conn.close()
    return {
        "attempts": attempts,
        "memory_facts": memory_facts,
        "reviews": reviews,
        "review_findings": review_findings,
    }


def _attempt_payload(record: Any) -> dict[str, Any]:
    data = asdict(record)
    return {
        "id": data["id"],
        "intent_id": data["intent_id"],
        "agent_id": data["agent_id"],
        "agent_model": data["agent_model"],
        "agent_harness": data["agent_harness"],
        "workspace_kind": data["workspace_kind"],
        "reported_status": data["reported_status"],
        "verified_status": data["verified_status"],
        "started_at": data["started_at"],
        "ended_at": data["ended_at"],
        "result_exit_code": data["result_exit_code"],
        "has_workspace_ref": bool(data["workspace_ref"]),
        "has_raw_trace_ref": bool(data["raw_trace_ref"]),
    }


def _memory_fact_payload(record: Any) -> dict[str, Any]:
    data = asdict(record)
    summary, redacted = redact_text(str(data["summary"]))
    return {
        "id": data["id"],
        "kind": data["kind"],
        "topic": data["topic"],
        "summary": summary,
        "summary_redacted": redacted,
        "status": data["status"],
        "confidence": data["confidence"],
        "valid_from": data["valid_from"],
        "valid_to": data["valid_to"],
        "superseded_by": data["superseded_by"],
        "human_review_state": data["human_review_state"],
        "provenance": data["provenance"],
    }


def _review_payload(record: Any) -> dict[str, Any]:
    data = asdict(record)
    return {
        "id": data["id"],
        "target_attempt_id": data["target_attempt_id"],
        "mode": data["mode"],
        "budget": data["budget"],
        "profiles": list(data["profiles"]),
        "reviewer_adapter": data["reviewer_adapter"],
        "risk_level": data["risk_level"],
        "risk_score": data["risk_score"],
        "status": data["status"],
        "blocking": data["blocking"],
        "created_at": data["created_at"],
        "completed_at": data["completed_at"],
    }


def _review_finding_payload(record: Any) -> dict[str, Any]:
    data = asdict(record)
    title, redacted = redact_text(str(data["title"]))
    return {
        "id": data["id"],
        "review_id": data["review_id"],
        "severity": data["severity"],
        "blocking": data["blocking"],
        "lifecycle_status": data["lifecycle_status"],
        "path": data["path"],
        "line": data["line"],
        "title": title,
        "title_redacted": redacted,
        "confidence": data["confidence"],
    }


def _validate_bundle(bundle: Any) -> list[str]:
    if not isinstance(bundle, dict):
        return ["bundle must be a JSON object"]
    errors: list[str] = []
    if bundle.get("schema") != METADATA_BUNDLE_SCHEMA:
        errors.append(f"schema must be {METADATA_BUNDLE_SCHEMA}")
    if bundle.get("schema_version") != METADATA_BUNDLE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {METADATA_BUNDLE_SCHEMA_VERSION}")
    object_counts = bundle.get("object_counts")
    if not isinstance(object_counts, dict):
        errors.append("object_counts must be an object")
    contents = bundle.get("contents")
    if not isinstance(contents, dict):
        errors.append("contents must be an object")
    return errors


def _import_plan(
    repo_root: Path,
    input_path: Path,
    *,
    status: str,
    errors: list[str],
    warnings: list[str] | None = None,
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    object_counts = bundle.get("object_counts", {}) if bundle else {}
    return {
        "schema": METADATA_IMPORT_PLAN_SCHEMA,
        "schema_version": METADATA_IMPORT_PLAN_SCHEMA_VERSION,
        "operation": "import",
        "dry_run": True,
        "status": status,
        "created_at": utc_now(),
        "repo": {
            "identity": derive_repo_identity(repo_root),
            "name": repo_root.name,
        },
        "input": {
            "path": str(input_path),
            "exists": input_path.exists(),
        },
        "object_counts": object_counts,
        "will_write": False,
        "errors": errors,
        "warnings": warnings or [],
        "limitations": [
            "dry-run only",
            "no remote sync",
            "no telemetry",
            "no automatic push",
            "no automatic merge",
        ],
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key != "content_sha256"}
    raw = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()
