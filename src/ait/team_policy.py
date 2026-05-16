from __future__ import annotations

import json
from dataclasses import dataclass
import fnmatch
from pathlib import Path
from typing import Any

TEAM_POLICY_SCHEMA = "ait.team_policy"
TEAM_POLICY_SCHEMA_VERSION = 1
TEAM_POLICY_VALIDATION_SCHEMA = "ait.team_policy.validation"
TEAM_POLICY_VALIDATION_SCHEMA_VERSION = 1
TEAM_POLICY_ENFORCEMENT_SCHEMA = "ait.team_policy.enforcement"
TEAM_POLICY_ENFORCEMENT_SCHEMA_VERSION = 1
TEAM_POLICY_PATH = ".ait/policy.json"

REVIEW_DEFAULT_MODE_VALUES = {"never", "light", "risk-based", "adversarial", "multi"}
REVIEW_SEVERITY_VALUES = {"critical", "high", "medium", "low", "info"}
TRUSTED_MEMORY_STATUS_VALUES = {"accepted"}
EXCLUDED_MEMORY_STATUS_VALUES = {
    "candidate",
    "rejected",
    "superseded",
    "stale",
    "policy-blocked",
}


@dataclass(frozen=True, slots=True)
class TeamPolicyValidation:
    payload: dict[str, Any]
    valid: bool


class TeamPolicyEnforcementError(ValueError):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        message = "; ".join(str(item.get("message") or item.get("name")) for item in payload.get("checks", []))
        super().__init__(message or "team policy blocked operation")


def team_policy_path(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / TEAM_POLICY_PATH


def default_team_policy() -> dict[str, Any]:
    return {
        "schema": TEAM_POLICY_SCHEMA,
        "schema_version": TEAM_POLICY_SCHEMA_VERSION,
        "review": {
            "default_mode": "risk-based",
            "blocking_severities": ["critical", "high"],
            "require_clearance_for_apply": True,
        },
        "memory": {
            "trusted_statuses": ["accepted"],
            "excluded_statuses": [
                "candidate",
                "rejected",
                "superseded",
                "stale",
                "policy-blocked",
            ],
            "block_paths": [],
        },
        "apply": {
            "allow_dirty_root": False,
            "require_review_clearance": True,
        },
        "console": {
            "actions_enabled": True,
            "mutation_ui_enabled": False,
        },
        "metadata": {
            "allow_export": True,
            "allow_import": False,
            "redact_absolute_paths": True,
        },
        "redaction": {
            "exclude_env_patterns": [
                "*TOKEN*",
                "*SECRET*",
                "*KEY*",
                "*PASSWORD*",
            ],
        },
    }


def validate_team_policy(repo_root: str | Path) -> TeamPolicyValidation:
    root = Path(repo_root).resolve()
    path = team_policy_path(root)
    errors: list[str] = []
    warnings: list[str] = []
    source = "repo"

    if path.exists():
        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raw_payload = {}
            errors.append(f"{TEAM_POLICY_PATH} is not valid JSON: {exc}")
    else:
        raw_payload = default_team_policy()
        source = "default"

    if not isinstance(raw_payload, dict):
        errors.append(f"{TEAM_POLICY_PATH} must contain a JSON object")
        raw_payload = {}

    policy = _merge_with_defaults(raw_payload)
    errors.extend(validate_team_policy_payload(policy))

    payload = {
        "schema": TEAM_POLICY_VALIDATION_SCHEMA,
        "schema_version": TEAM_POLICY_VALIDATION_SCHEMA_VERSION,
        "status": "valid" if not errors else "invalid",
        "source": source,
        "policy_path": TEAM_POLICY_PATH,
        "policy": policy,
        "errors": errors,
        "warnings": warnings,
    }
    return TeamPolicyValidation(payload=payload, valid=not errors)


def enforce_team_policy(
    repo_root: str | Path,
    *,
    operation: str,
    attempt_id: str | None = None,
    review_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validate_team_policy(repo_root)
    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "team_policy_valid",
            "status": "passed" if validation.valid else "blocked",
            "message": "policy valid" if validation.valid else "; ".join(validation.payload["errors"]),
        }
    )
    policy = validation.payload.get("policy") if isinstance(validation.payload, dict) else {}
    if isinstance(policy, dict):
        if operation == "console_action":
            console = policy.get("console")
            enabled = isinstance(console, dict) and console.get("actions_enabled") is True
            checks.append(
                {
                    "name": "console_actions_enabled",
                    "status": "passed" if enabled else "blocked",
                    "message": "console actions enabled" if enabled else "console.actions_enabled is false",
                }
            )
        if operation == "apply":
            apply = policy.get("apply")
            require_review = (
                validation.payload.get("source") == "repo"
                and isinstance(apply, dict)
                and apply.get("require_review_clearance") is True
            )
            if require_review:
                clear = _review_summary_clear(review_summary)
                checks.append(
                    {
                        "name": "apply_review_clearance",
                        "status": "passed" if clear else "blocked",
                        "message": "latest review is clear" if clear else "apply.require_review_clearance requires a clear latest review",
                        "attempt_id": attempt_id,
                        "review_status": None if review_summary is None else review_summary.get("status"),
                    }
                )
            else:
                checks.append(
                    {
                        "name": "apply_review_clearance",
                        "status": "passed",
                        "message": (
                            "apply.require_review_clearance is false"
                            if validation.payload.get("source") == "repo"
                            else "no repo team policy; existing apply review gate remains authoritative"
                        ),
                        "attempt_id": attempt_id,
                    }
                )
        if operation == "review":
            review = policy.get("review")
            enabled = not (isinstance(review, dict) and review.get("default_mode") == "never")
            checks.append(
                {
                    "name": "review_policy_available",
                    "status": "passed" if enabled else "blocked",
                    "message": "review policy allows review" if enabled else "review.default_mode is never",
                }
            )
    payload = {
        "schema": TEAM_POLICY_ENFORCEMENT_SCHEMA,
        "schema_version": TEAM_POLICY_ENFORCEMENT_SCHEMA_VERSION,
        "operation": operation,
        "attempt_id": attempt_id,
        "status": "passed" if all(item["status"] == "passed" for item in checks) else "blocked",
        "checks": checks,
        "policy_validation": validation.payload,
    }
    if payload["status"] != "passed":
        raise TeamPolicyEnforcementError(payload)
    return payload


def team_policy_blocks_path(policy_payload: dict[str, Any], path: str | None) -> bool:
    if not path:
        return False
    memory = policy_payload.get("memory")
    patterns = memory.get("block_paths") if isinstance(memory, dict) else []
    if not isinstance(patterns, list):
        return False
    normalized = str(path).lstrip("./")
    return any(isinstance(pattern, str) and fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def validate_team_policy_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != TEAM_POLICY_SCHEMA:
        errors.append(f"schema must be {TEAM_POLICY_SCHEMA}")
    if payload.get("schema_version") != TEAM_POLICY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {TEAM_POLICY_SCHEMA_VERSION}")

    review = _dict_section(payload, "review", errors)
    default_mode = review.get("default_mode")
    if default_mode not in REVIEW_DEFAULT_MODE_VALUES:
        errors.append("review.default_mode must be one of " + ", ".join(sorted(REVIEW_DEFAULT_MODE_VALUES)))
    _validate_string_set(
        review,
        "blocking_severities",
        REVIEW_SEVERITY_VALUES,
        errors,
        "review.blocking_severities",
    )
    _validate_bool(review, "require_clearance_for_apply", errors, "review.require_clearance_for_apply")

    memory = _dict_section(payload, "memory", errors)
    trusted_statuses = _validate_string_set(
        memory,
        "trusted_statuses",
        TRUSTED_MEMORY_STATUS_VALUES,
        errors,
        "memory.trusted_statuses",
    )
    if trusted_statuses and set(trusted_statuses) != {"accepted"}:
        errors.append("memory.trusted_statuses may only trust accepted memory")
    _validate_string_set(
        memory,
        "excluded_statuses",
        EXCLUDED_MEMORY_STATUS_VALUES,
        errors,
        "memory.excluded_statuses",
    )
    _validate_string_list(memory, "block_paths", errors, "memory.block_paths")

    apply = _dict_section(payload, "apply", errors)
    _validate_bool(apply, "allow_dirty_root", errors, "apply.allow_dirty_root")
    _validate_bool(apply, "require_review_clearance", errors, "apply.require_review_clearance")

    console = _dict_section(payload, "console", errors)
    _validate_bool(console, "actions_enabled", errors, "console.actions_enabled")
    _validate_bool(console, "mutation_ui_enabled", errors, "console.mutation_ui_enabled")
    if console.get("mutation_ui_enabled") is True:
        errors.append("console.mutation_ui_enabled must remain false until browser mutation recovery is implemented")

    metadata = _dict_section(payload, "metadata", errors)
    _validate_bool(metadata, "allow_export", errors, "metadata.allow_export")
    _validate_bool(metadata, "allow_import", errors, "metadata.allow_import")
    _validate_bool(metadata, "redact_absolute_paths", errors, "metadata.redact_absolute_paths")
    if metadata.get("allow_import") is True:
        errors.append("metadata.allow_import must remain false while only dry-run import is implemented")

    redaction = _dict_section(payload, "redaction", errors)
    _validate_string_list(
        redaction,
        "exclude_env_patterns",
        errors,
        "redaction.exclude_env_patterns",
    )
    return errors


def _merge_with_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    default = default_team_policy()
    merged: dict[str, Any] = {}
    for key, value in default.items():
        if isinstance(value, dict):
            supplied = payload.get(key)
            merged[key] = {**value, **supplied} if isinstance(supplied, dict) else dict(value)
        else:
            merged[key] = payload.get(key, value)
    for key, value in payload.items():
        if key not in merged:
            merged[key] = value
    return merged


def _dict_section(payload: dict[str, Any], name: str, errors: list[str]) -> dict[str, Any]:
    section = payload.get(name)
    if not isinstance(section, dict):
        errors.append(f"{name} must be an object")
        return {}
    return section


def _validate_bool(section: dict[str, Any], key: str, errors: list[str], display: str) -> None:
    if not isinstance(section.get(key), bool):
        errors.append(f"{display} must be a boolean")


def _validate_string_list(
    section: dict[str, Any],
    key: str,
    errors: list[str],
    display: str,
) -> list[str]:
    value = section.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{display} must be a list of strings")
        return []
    return list(value)


def _validate_string_set(
    section: dict[str, Any],
    key: str,
    allowed: set[str],
    errors: list[str],
    display: str,
) -> list[str]:
    values = _validate_string_list(section, key, errors, display)
    invalid = sorted(set(values) - allowed)
    if invalid:
        errors.append(f"{display} contains invalid values: {', '.join(invalid)}")
    return values


def _review_summary_clear(review_summary: dict[str, Any] | None) -> bool:
    if not review_summary:
        return False
    status = review_summary.get("status")
    if status in {"blocked", "failed", "queued", "running"}:
        return False
    if review_summary.get("blocking"):
        return False
    return status in {"passed", "warning"}
