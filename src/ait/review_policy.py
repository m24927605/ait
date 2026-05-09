from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import sqlite3

from ait.db import (
    get_attempt,
    get_evidence_summary,
    list_attempt_commits,
    list_attempt_review_findings,
    list_attempt_review_overrides,
    list_attempt_reviews,
)
from ait.memory_policy import load_memory_policy
from ait.policy import repo_policy


REVIEW_DEFAULT_MODES = {"never", "risk-based", "light", "adversarial", "multi"}
RUN_REVIEW_MODES = {"never", "risk-based", "light", "adversarial"}
PROFILE_VALUES = {"security", "regression", "maintainability", "release"}
DEFAULT_REQUIRED_PROFILES = {
    "auth/**": ("security", "regression"),
    "**/auth/**": ("security", "regression"),
    ".github/workflows/**": ("security",),
    "migrations/**": ("regression", "release"),
    "**/migrations/**": ("regression", "release"),
}


@dataclass(frozen=True, slots=True)
class RiskReason:
    code: str
    message: str
    paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    risk_level: str
    risk_score: int
    risk_reasons: tuple[RiskReason, ...]
    review_required: bool
    suggested_mode: str


@dataclass(frozen=True, slots=True)
class ReviewBaselinePolicy:
    require_approved_facts: bool = True
    allow_candidate_memory: bool = False
    include_prior_failed_attempts: bool = True
    include_prior_review_findings: bool = True


@dataclass(frozen=True, slots=True)
class ReviewAdapterPolicy:
    command: str
    args: tuple[str, ...] = ()
    timeout_seconds: int = 300
    env_allowlist: tuple[str, ...] = ()
    cwd: str | None = None
    output: str = "json"


@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    default_mode: str = "never"
    auto_apply_requires_review: bool = False
    allow_override: bool = True
    sensitive_paths: tuple[str, ...] = ()
    required_profiles: dict[str, tuple[str, ...]] | None = None
    baseline: ReviewBaselinePolicy = ReviewBaselinePolicy()
    adapters: dict[str, ReviewAdapterPolicy] | None = None


@dataclass(frozen=True, slots=True)
class ReviewGateDecision:
    required: bool
    allowed: bool
    status: str
    reason: str
    review_id: str | None = None
    override_id: str | None = None

    @property
    def blocking(self) -> bool:
        return self.required and not self.allowed

    def metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "required": self.required,
            "allowed": self.allowed,
            "status": self.status,
            "reason": self.reason,
        }
        if self.review_id is not None:
            payload["review_id"] = self.review_id
        if self.override_id is not None:
            payload["override_id"] = self.override_id
        return payload


@dataclass(frozen=True, slots=True)
class ReviewFreshness:
    fresh: bool
    status: str
    reason: str

    def metadata(self) -> dict[str, object]:
        return {
            "fresh": self.fresh,
            "status": self.status,
            "reason": self.reason,
        }


def assess_review_risk(
    *,
    changed_files: tuple[str, ...],
    observed_tests_run: int = 0,
) -> RiskAssessment:
    score = 0
    reasons: list[RiskReason] = []

    if len(changed_files) >= 30:
        score += 35
        reasons.append(
            RiskReason(
                "very_large_diff",
                "attempt changed at least 30 files",
                changed_files,
            )
        )
    elif len(changed_files) >= 10:
        score += 20
        reasons.append(
            RiskReason("large_diff", "attempt changed at least 10 files", changed_files)
        )

    sensitive_paths = tuple(path for path in changed_files if _sensitive_path(path))
    if sensitive_paths:
        score += 30
        reasons.append(
            RiskReason(
                "sensitive_path",
                "changed path matches a sensitive review area",
                sensitive_paths,
            )
        )

    dependency_paths = tuple(path for path in changed_files if _dependency_path(path))
    if dependency_paths:
        score += 25
        reasons.append(
            RiskReason(
                "dependency_change",
                "changed dependency or lockfile metadata",
                dependency_paths,
            )
        )

    binary_or_generated_paths = tuple(
        path for path in changed_files if _binary_or_generated_path(path)
    )
    if binary_or_generated_paths:
        score += 15
        reasons.append(
            RiskReason(
                "binary_or_generated",
                "changed likely binary or generated files",
                binary_or_generated_paths,
            )
        )

    if changed_files and observed_tests_run <= 0:
        score += 20
        reasons.append(
            RiskReason(
                "missing_test_evidence",
                "attempt changed files but no test evidence was observed",
                (),
            )
        )

    capped_score = min(score, 100)
    risk_level = _risk_level(capped_score)
    return RiskAssessment(
        risk_level=risk_level,
        risk_score=capped_score,
        risk_reasons=tuple(reasons),
        review_required=False,
        suggested_mode=_suggested_mode(risk_level),
    )


def risk_reason_payload(reason: RiskReason) -> dict[str, object]:
    return {
        "code": reason.code,
        "message": reason.message,
        "paths": list(reason.paths),
    }


def load_review_policy(repo_root: str | Path) -> ReviewPolicy:
    review = repo_policy(repo_root).get("review")
    if not isinstance(review, dict):
        return ReviewPolicy()
    baseline = review.get("baseline")
    baseline_payload = baseline if isinstance(baseline, dict) else {}
    default_mode = str(review.get("default_mode", "never")).strip().lower()
    if default_mode not in REVIEW_DEFAULT_MODES:
        default_mode = "never"
    return ReviewPolicy(
        default_mode=default_mode,
        auto_apply_requires_review=_strict_bool(
            review.get("auto_apply_requires_review"), False
        ),
        allow_override=_strict_bool(review.get("allow_override"), True),
        sensitive_paths=_string_tuple(review.get("sensitive_paths")),
        required_profiles=_required_profiles(review.get("required_profiles")),
        baseline=ReviewBaselinePolicy(
            require_approved_facts=_strict_bool(
                baseline_payload.get("require_approved_facts"), True
            ),
            allow_candidate_memory=_strict_bool(
                baseline_payload.get("allow_candidate_memory"), False
            ),
            include_prior_failed_attempts=_strict_bool(
                baseline_payload.get("include_prior_failed_attempts"), True
            ),
            include_prior_review_findings=_strict_bool(
                baseline_payload.get("include_prior_review_findings"), True
            ),
        ),
        adapters=_adapter_policies(review.get("adapters")),
    )


def run_review_policy(repo_root: str | Path, explicit: str | None = None) -> str:
    if explicit is not None:
        return explicit
    policy = load_review_policy(repo_root)
    mode = policy.default_mode
    return mode if mode in RUN_REVIEW_MODES else "never"


def resolve_review_adapter_policy(
    repo_root: str | Path,
    adapter: str,
) -> ReviewAdapterPolicy | None:
    policy = load_review_policy(repo_root)
    adapters = policy.adapters or {}
    key = adapter.strip()
    if key in adapters:
        return adapters[key]
    if key == "default" and "default" in adapters:
        return adapters["default"]
    return None


def review_policy_requires_escalation(
    repo_root: str | Path,
    *,
    changed_files: tuple[str, ...],
    risk_level: str,
) -> bool:
    if risk_level in {"high", "critical"}:
        return True
    policy = load_review_policy(repo_root)
    if policy.default_mode == "never":
        return False
    return any(_matches_any(path, policy.sensitive_paths) for path in changed_files)


def required_review_profiles(
    repo_root: str | Path,
    *,
    changed_files: tuple[str, ...],
    risk_level: str,
) -> tuple[str, ...]:
    policy = load_review_policy(repo_root)
    profile_map = policy.required_profiles or DEFAULT_REQUIRED_PROFILES
    profiles: list[str] = []
    for path in changed_files:
        for pattern, required in profile_map.items():
            if fnmatch(_normalize(path), pattern):
                profiles.extend(required)
    if profiles:
        return _dedupe_profiles(profiles)
    if risk_level in {"high", "critical"}:
        return ("regression",)
    return ()


def evaluate_apply_review_gate(
    repo_root: str | Path,
    conn: sqlite3.Connection,
    *,
    target_attempt_id: str,
    required: bool = False,
) -> ReviewGateDecision:
    policy = load_review_policy(repo_root)
    if not required and not policy.auto_apply_requires_review:
        return ReviewGateDecision(
            required=False,
            allowed=True,
            status="not_required",
            reason="review gate is not required by repo policy",
        )

    reviews = list_attempt_reviews(conn, target_attempt_id=target_attempt_id)
    if not reviews:
        return ReviewGateDecision(
            required=True,
            allowed=False,
            status="missing",
            reason="required review is missing",
        )

    latest = reviews[-1]

    overrides = list_attempt_review_overrides(conn, latest.id)
    if latest.status == "overridden" and policy.allow_override:
        return ReviewGateDecision(
            required=True,
            allowed=True,
            status="overridden",
            reason="required review was overridden",
            review_id=latest.id,
            override_id=overrides[-1].id if overrides else None,
        )

    if overrides and policy.allow_override:
        return ReviewGateDecision(
            required=True,
            allowed=True,
            status="overridden",
            reason="required review was overridden",
            review_id=latest.id,
            override_id=overrides[-1].id,
        )

    if latest.status in {"queued", "running"}:
        return ReviewGateDecision(
            required=True,
            allowed=False,
            status=latest.status,
            reason=f"required review is {latest.status}",
            review_id=latest.id,
        )

    if latest.status in {"blocked", "failed"}:
        return ReviewGateDecision(
            required=True,
            allowed=False,
            status=latest.status,
            reason=f"required review is {latest.status}",
            review_id=latest.id,
        )

    freshness = evaluate_review_freshness(repo_root, conn, latest)
    if not freshness.fresh:
        return ReviewGateDecision(
            required=True,
            allowed=False,
            status="stale",
            reason=f"required review is stale: {freshness.reason}",
            review_id=latest.id,
        )

    missing_profiles = missing_required_profiles(repo_root, conn, latest)
    if missing_profiles:
        return ReviewGateDecision(
            required=True,
            allowed=False,
            status="missing_profile",
            reason="required review is missing profile(s): " + ", ".join(missing_profiles),
            review_id=latest.id,
        )

    blocking_findings = open_high_or_critical_findings(conn, latest.id)
    if blocking_findings:
        return ReviewGateDecision(
            required=True,
            allowed=False,
            status="blocked",
            reason="required review has open high/critical blocking finding(s)",
            review_id=latest.id,
        )

    if sensitive_path_missing_tests(repo_root, conn, latest.target_attempt_id, latest.risk_reasons):
        return ReviewGateDecision(
            required=True,
            allowed=False,
            status="missing_test_evidence",
            reason="required review touches sensitive paths without test evidence",
            review_id=latest.id,
        )

    if latest.status == "passed" and not latest.blocking:
        return ReviewGateDecision(
            required=True,
            allowed=True,
            status="passed",
            reason="required review passed",
            review_id=latest.id,
        )

    return ReviewGateDecision(
        required=True,
        allowed=False,
        status=latest.status,
        reason="required review is not passing",
        review_id=latest.id,
    )


def review_policy_hash(
    repo_root: str | Path,
    *,
    mode: str,
    budget: str,
    profiles: tuple[str, ...],
    adapter: str | None,
) -> str:
    policy = load_review_policy(repo_root)
    payload = {
        "default_mode": policy.default_mode,
        "auto_apply_requires_review": policy.auto_apply_requires_review,
        "allow_override": policy.allow_override,
        "sensitive_paths": list(policy.sensitive_paths),
        "required_profiles": {
            key: list(value)
            for key, value in sorted((policy.required_profiles or {}).items())
        },
        "baseline": {
            "require_approved_facts": policy.baseline.require_approved_facts,
            "allow_candidate_memory": policy.baseline.allow_candidate_memory,
            "include_prior_failed_attempts": policy.baseline.include_prior_failed_attempts,
            "include_prior_review_findings": policy.baseline.include_prior_review_findings,
        },
        "adapters": {
            name: {
                "command": config.command,
                "args": list(config.args),
                "timeout_seconds": config.timeout_seconds,
                "env_allowlist": list(config.env_allowlist),
                "cwd": config.cwd,
                "output": config.output,
            }
            for name, config in sorted((policy.adapters or {}).items())
        },
        "review": {
            "mode": mode,
            "budget": budget,
            "profiles": list(profiles),
            "adapter": adapter,
        },
    }
    return "review-policy:" + _stable_hash(payload)


def current_baseline_policy_hash(repo_root: str | Path) -> str:
    return _stable_hash(load_memory_policy(repo_root).to_dict())


def evaluate_review_freshness(
    repo_root: str | Path,
    conn: sqlite3.Connection,
    review,
) -> ReviewFreshness:
    attempt = get_attempt(conn, review.target_attempt_id)
    if attempt is None:
        return ReviewFreshness(False, "stale", "target attempt is missing")
    current_head_oid = latest_attempt_head_oid(conn, review.target_attempt_id)
    if not review.target_head_oid:
        return ReviewFreshness(False, "stale", "review is missing target head oid")
    if current_head_oid != review.target_head_oid:
        return ReviewFreshness(False, "stale", "target attempt commits changed")
    if not review.base_ref_oid:
        return ReviewFreshness(False, "stale", "review is missing base ref oid")
    if attempt.base_ref_oid != review.base_ref_oid:
        return ReviewFreshness(False, "stale", "base ref oid changed")
    expected_policy_hash = review_policy_hash(
        repo_root,
        mode=review.mode,
        budget=review.budget,
        profiles=review.profiles,
        adapter=review.reviewer_adapter,
    )
    if review.policy_hash != expected_policy_hash:
        return ReviewFreshness(False, "stale", "review policy changed")
    if review.baseline_policy_hash != current_baseline_policy_hash(repo_root):
        return ReviewFreshness(False, "stale", "baseline policy changed")
    for finding in list_attempt_review_findings(conn, review.id):
        if finding.lifecycle_status in {"fixed", "superseded"}:
            return ReviewFreshness(False, "stale", "review finding lifecycle changed")
    return ReviewFreshness(True, "fresh", "review metadata matches current target")


def latest_attempt_head_oid(conn: sqlite3.Connection, attempt_id: str) -> str | None:
    commits = list_attempt_commits(conn, attempt_id)
    if not commits:
        return None
    return commits[-1].commit_oid


def missing_required_profiles(
    repo_root: str | Path,
    conn: sqlite3.Connection,
    review,
) -> tuple[str, ...]:
    changed_files = tuple(
        sorted(
            {
                file_path
                for commit in list_attempt_commits(conn, review.target_attempt_id)
                for file_path in commit.touched_files
            }
        )
    )
    required = required_review_profiles(
        repo_root,
        changed_files=changed_files,
        risk_level=review.risk_level,
    )
    return tuple(profile for profile in required if profile not in review.profiles)


def open_high_or_critical_findings(conn: sqlite3.Connection, review_id: str):
    return tuple(
        finding
        for finding in list_attempt_review_findings(conn, review_id)
        if finding.lifecycle_status == "open"
        and finding.blocking
        and finding.severity in {"critical", "high"}
    )


def sensitive_path_missing_tests(
    repo_root: str | Path,
    conn: sqlite3.Connection,
    attempt_id: str,
    risk_reasons: tuple[dict[str, object], ...],
) -> bool:
    sensitive = any(reason.get("code") == "sensitive_path" for reason in risk_reasons)
    if not sensitive:
        return False
    evidence = get_evidence_summary(conn, attempt_id)
    return evidence is None or evidence.observed_tests_run <= 0


def _risk_level(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def _suggested_mode(risk_level: str) -> str:
    if risk_level == "low":
        return "none"
    if risk_level == "medium":
        return "light"
    return "adversarial"


def _sensitive_path(path: str) -> bool:
    normalized = _normalize(path)
    parts = PurePosixPath(normalized).parts
    joined = "/".join(parts)
    if joined.startswith(".github/workflows/"):
        return True
    markers = {
        "auth",
        "authentication",
        "authorization",
        "security",
        "payment",
        "payments",
        "billing",
        "deploy",
        "deployment",
        "ci",
        "migrations",
        "migration",
    }
    return any(part.lower() in markers for part in parts)


def _dependency_path(path: str) -> bool:
    name = PurePosixPath(_normalize(path)).name.lower()
    return name in {
        "pyproject.toml",
        "uv.lock",
        "poetry.lock",
        "requirements.txt",
        "requirements-dev.txt",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "cargo.lock",
        "go.mod",
        "go.sum",
        "gemfile.lock",
    }


def _binary_or_generated_path(path: str) -> bool:
    normalized = _normalize(path)
    lowered = normalized.lower()
    if "/generated/" in lowered or lowered.endswith(".generated.py"):
        return True
    return PurePosixPath(lowered).suffix in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".pdf",
        ".zip",
        ".gz",
        ".bin",
        ".wasm",
    }


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _strict_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return default


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = _normalize(path)
    return any(fnmatch(normalized, pattern) for pattern in patterns)


def _required_profiles(value: object) -> dict[str, tuple[str, ...]] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for pattern, raw_profiles in value.items():
        profiles = _profile_tuple(raw_profiles)
        if profiles:
            result[str(pattern)] = profiles
    return result


def _adapter_policies(value: object) -> dict[str, ReviewAdapterPolicy] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return {}
    result: dict[str, ReviewAdapterPolicy] = {}
    for name, raw_config in value.items():
        if not isinstance(raw_config, dict):
            continue
        command = str(raw_config.get("command", "")).strip()
        if not command:
            continue
        args = raw_config.get("args")
        env_allowlist = raw_config.get("env_allowlist")
        timeout = raw_config.get("timeout_seconds", 300)
        cwd = raw_config.get("cwd")
        output = str(raw_config.get("output", "json")).strip().lower() or "json"
        result[str(name)] = ReviewAdapterPolicy(
            command=command,
            args=tuple(str(item) for item in args) if isinstance(args, list) else (),
            timeout_seconds=timeout if isinstance(timeout, int) and timeout > 0 else 300,
            env_allowlist=tuple(str(item) for item in env_allowlist)
            if isinstance(env_allowlist, list)
            else (),
            cwd=None if cwd is None else str(cwd),
            output=output,
        )
    return result


def _profile_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return _dedupe_profiles(str(item).strip() for item in value if str(item).strip() in PROFILE_VALUES)


def _dedupe_profiles(values) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in PROFILE_VALUES and text not in seen:
            result.append(text)
            seen.add(text)
    return tuple(result)


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
