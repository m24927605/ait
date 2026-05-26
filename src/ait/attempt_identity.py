from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from ait.db.records import (
    AttemptCommitRecord,
    AttemptRecord,
    EvidenceSummaryRecord,
    IntentRecord,
)


DESCRIPTION_SOURCE = "deterministic:v1"


@dataclass(frozen=True)
class AttemptDescription:
    display_title: str
    deterministic_description: str
    description_source: str
    description_fingerprint: str


def build_attempt_description(
    *,
    attempt: AttemptRecord,
    intent: IntentRecord | None,
    evidence_summary: EvidenceSummaryRecord | None,
    changed_files: tuple[str, ...],
    commits: tuple[AttemptCommitRecord, ...],
    integration_artifact: dict[str, object] | None = None,
) -> AttemptDescription:
    display_title = _display_title(attempt, intent)
    commit_files = _commit_files(commits)
    local_changed_files = tuple(sorted(set(changed_files or commit_files)))
    integration = _integration_facts(integration_artifact, intent)

    clauses: list[str] = []
    if integration:
        clauses.append(_integration_clause(integration))

    if local_changed_files:
        clauses.append(_changed_files_clause(local_changed_files))
    else:
        clauses.append(
            f"Attempt {_short_attempt_id(attempt.id)} has no indexed changed files yet"
        )

    stats = _commit_stats_clause(commits)
    if stats:
        clauses.append(stats)

    status = _status_label(attempt, integration)
    if status:
        clauses.append(f"status {status}")

    tests = _tests_clause(evidence_summary)
    if tests:
        clauses.append(tests)

    exit_code = _exit_code_clause(attempt)
    if exit_code:
        clauses.append(exit_code)

    description = "; ".join(clauses).rstrip(".") + "."
    fingerprint = _fingerprint(
        {
            "source": DESCRIPTION_SOURCE,
            "attempt": {
                "id": attempt.id,
                "reported_status": attempt.reported_status,
                "verified_status": attempt.verified_status,
                "result_exit_code": attempt.result_exit_code,
            },
            "intent": None
            if intent is None
            else {
                "title": intent.title,
                "description": intent.description,
                "kind": intent.kind,
            },
            "changed_files": local_changed_files,
            "commits": [
                {
                    "commit_oid": commit.commit_oid,
                    "insertions": commit.insertions,
                    "deletions": commit.deletions,
                    "touched_files": commit.touched_files,
                }
                for commit in commits
            ],
            "tests": None
            if evidence_summary is None
            else {
                "observed_tests_run": evidence_summary.observed_tests_run,
                "observed_tests_passed": evidence_summary.observed_tests_passed,
                "observed_tests_failed": evidence_summary.observed_tests_failed,
            },
            "integration": integration,
        }
    )
    return AttemptDescription(
        display_title=display_title,
        deterministic_description=description,
        description_source=DESCRIPTION_SOURCE,
        description_fingerprint=fingerprint,
    )


def load_integration_artifact(attempt: AttemptRecord) -> dict[str, object] | None:
    result_path = _integration_result_path(attempt)
    if result_path is None or not result_path.exists():
        return None
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != "integration":
        return None
    return payload


def _display_title(attempt: AttemptRecord, intent: IntentRecord | None) -> str:
    if intent is not None:
        if intent.title.strip():
            return intent.title.strip()
        if intent.description is not None and intent.description.strip():
            return intent.description.strip().splitlines()[0]
    return f"Attempt {_short_attempt_id(attempt.id)}"


def _changed_files_clause(paths: tuple[str, ...]) -> str:
    if len(paths) == 1:
        return f"changed {paths[0]}"
    if len(paths) == 2:
        return f"changed {paths[0]} and {paths[1]}"
    roots = _path_roots(paths)
    if roots:
        return f"{len(paths)} files changed across {_format_list(roots)}"
    return f"{len(paths)} files changed"


def _commit_stats_clause(commits: tuple[AttemptCommitRecord, ...]) -> str | None:
    insertions = sum(commit.insertions or 0 for commit in commits)
    deletions = sum(commit.deletions or 0 for commit in commits)
    if insertions <= 0 and deletions <= 0:
        return None
    return f"+{insertions}/-{deletions}"


def _status_label(
    attempt: AttemptRecord, integration: dict[str, object] | None
) -> str | None:
    if integration and attempt.verified_status == "pending":
        return "integration_created"
    if attempt.reported_status == "crashed":
        return "crashed"
    if attempt.verified_status != "pending":
        return attempt.verified_status
    if attempt.reported_status == "running":
        return "running"
    return "pending"


def _tests_clause(evidence: EvidenceSummaryRecord | None) -> str | None:
    if evidence is None:
        return None
    observed = (
        evidence.observed_tests_run,
        evidence.observed_tests_passed,
        evidence.observed_tests_failed,
    )
    if all(value <= 0 for value in observed):
        return None
    if evidence.observed_tests_failed > 0:
        return (
            f"tests observed {evidence.observed_tests_run} run, "
            f"{evidence.observed_tests_failed} failed"
        )
    if evidence.observed_tests_passed > 0:
        return (
            f"tests observed {evidence.observed_tests_run} run, "
            f"{evidence.observed_tests_passed} passed"
        )
    return f"tests observed {evidence.observed_tests_run} run"


def _exit_code_clause(attempt: AttemptRecord) -> str | None:
    if attempt.result_exit_code is None or attempt.result_exit_code == 0:
        return None
    return f"exit code {attempt.result_exit_code}"


def _commit_files(commits: tuple[AttemptCommitRecord, ...]) -> tuple[str, ...]:
    paths: set[str] = set()
    for commit in commits:
        paths.update(commit.touched_files)
    return tuple(sorted(paths))


def _integration_facts(
    artifact: dict[str, object] | None, intent: IntentRecord | None
) -> dict[str, object] | None:
    if artifact is not None:
        decision = artifact.get("decision_report")
        reason_code = None
        if isinstance(decision, dict):
            reasons = decision.get("reasons")
            if isinstance(reasons, list) and reasons:
                first = reasons[0]
                if isinstance(first, dict):
                    reason_code = first.get("code")
        return {
            "classification": _optional_str(artifact.get("classification")),
            "strategy": _optional_str(artifact.get("strategy")),
            "reason_code": _optional_str(reason_code),
        }
    if intent is not None and intent.kind == "integration":
        return {"classification": None, "strategy": None, "reason_code": None}
    return None


def _integration_clause(integration: dict[str, object]) -> str:
    classification = _optional_str(integration.get("classification"))
    strategy = _optional_str(integration.get("strategy"))
    if classification and strategy:
        return f"integration {classification} via {strategy}"
    if classification:
        return f"integration {classification}"
    return "integration attempt"


def _path_roots(paths: tuple[str, ...]) -> tuple[str, ...]:
    roots: list[str] = []
    for path in paths:
        if "/" not in path:
            continue
        root = path.split("/", 1)[0]
        if root not in roots:
            roots.append(root)
        if len(roots) == 2:
            break
    return tuple(roots)


def _format_list(values: tuple[str, ...]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _integration_result_path(attempt: AttemptRecord) -> Path | None:
    workspace = Path(attempt.workspace_ref)
    if workspace.parent.name != "workspaces":
        return None
    ait_dir = workspace.parent.parent
    return ait_dir / "results" / f"{_safe_attempt_filename(attempt.id)}.json"


def _safe_attempt_filename(attempt_id: str) -> str:
    suffix = attempt_id.rsplit(":", 1)[-1]
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in suffix)


def _short_attempt_id(attempt_id: str) -> str:
    suffix = attempt_id.rsplit(":", 1)[-1]
    return (suffix or attempt_id)[:12]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
