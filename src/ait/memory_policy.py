from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import json
from pathlib import Path
from typing import Any

from ait.repo import resolve_repo_root


DEFAULT_EXCLUDE_PATHS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "secrets/",
    "secrets/**",
)
DEFAULT_EXCLUDE_TRANSCRIPT_PATTERNS = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)
DEFAULT_RECALL_SOURCE_ALLOW = (
    "manual",
    "manual:*",
    "attempt-memory:*",
    "agent-memory:*",
    "durable-memory:*",
    "transcript-summary:*",
)
DEFAULT_RECALL_SOURCE_BLOCK: tuple[str, ...] = ()
DEFAULT_RECALL_LINT_BLOCK_SEVERITIES = ("error",)
DEFAULT_TRANSCRIPT_RETAIN_DAYS = 90
DEFAULT_TRANSCRIPT_MAX_TOTAL_BYTES = 500 * 1024 * 1024  # 500 MB
DEFAULT_SUMMARIZER_KIND = "heuristic"
DEFAULT_SUMMARIZER_LLM_PROVIDER = "anthropic"
DEFAULT_SUMMARIZER_LLM_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_SUMMARIZER_LLM_API_KEY_ENV = "ANTHROPIC_API_KEY"
DEFAULT_SUMMARIZER_LLM_MAX_CHARS = 600
DEFAULT_SUMMARIZER_LLM_TIMEOUT_SECONDS = 30
SUMMARIZER_KINDS = frozenset({"heuristic", "llm"})
SUMMARIZER_LLM_PROVIDERS = frozenset({"anthropic", "openai-compat"})
EXCLUDED_MARKER = "[EXCLUDED BY MEMORY POLICY]"


@dataclass(frozen=True, slots=True)
class SummarizerLLMConfig:
    provider: str = DEFAULT_SUMMARIZER_LLM_PROVIDER
    model: str = DEFAULT_SUMMARIZER_LLM_MODEL
    api_key_env: str = DEFAULT_SUMMARIZER_LLM_API_KEY_ENV
    max_chars: int = DEFAULT_SUMMARIZER_LLM_MAX_CHARS
    base_url: str | None = None
    timeout_seconds: int = DEFAULT_SUMMARIZER_LLM_TIMEOUT_SECONDS

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "max_chars": self.max_chars,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class SummarizerConfig:
    kind: str = DEFAULT_SUMMARIZER_KIND
    llm: SummarizerLLMConfig = field(default_factory=SummarizerLLMConfig)

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "llm": self.llm.to_dict()}


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    exclude_paths: tuple[str, ...] = DEFAULT_EXCLUDE_PATHS
    exclude_transcript_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_TRANSCRIPT_PATTERNS
    recall_source_allow: tuple[str, ...] = DEFAULT_RECALL_SOURCE_ALLOW
    recall_source_block: tuple[str, ...] = DEFAULT_RECALL_SOURCE_BLOCK
    recall_lint_block_severities: tuple[str, ...] = DEFAULT_RECALL_LINT_BLOCK_SEVERITIES
    transcript_retain_days: int = DEFAULT_TRANSCRIPT_RETAIN_DAYS
    transcript_max_total_bytes: int = DEFAULT_TRANSCRIPT_MAX_TOTAL_BYTES
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig)

    def to_dict(self) -> dict[str, object]:
        return {
            "exclude_paths": list(self.exclude_paths),
            "exclude_transcript_patterns": list(self.exclude_transcript_patterns),
            "recall_source_allow": list(self.recall_source_allow),
            "recall_source_block": list(self.recall_source_block),
            "recall_lint_block_severities": list(self.recall_lint_block_severities),
            "transcripts": {
                "retain_days": self.transcript_retain_days,
                "max_total_bytes": self.transcript_max_total_bytes,
            },
            "summarizer": self.summarizer.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MemoryPolicyInitResult:
    path: str
    created: bool
    policy: MemoryPolicy

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "created": self.created,
            "policy": self.policy.to_dict(),
        }


def default_memory_policy() -> MemoryPolicy:
    return MemoryPolicy()


def memory_policy_path(repo_root: str | Path) -> Path:
    return resolve_repo_root(repo_root) / ".ait" / "memory-policy.json"


def load_memory_policy(repo_root: str | Path) -> MemoryPolicy:
    path = memory_policy_path(repo_root)
    if not path.exists():
        return default_memory_policy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid memory policy JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid memory policy JSON at {path}: expected object")
    return _policy_from_mapping(data, path=path)


def init_memory_policy(repo_root: str | Path, *, overwrite: bool = False) -> MemoryPolicyInitResult:
    path = memory_policy_path(repo_root)
    created = overwrite or not path.exists()
    if created:
        path.parent.mkdir(parents=True, exist_ok=True)
        policy = default_memory_policy()
        path.write_text(json.dumps(policy.to_dict(), indent=2) + "\n", encoding="utf-8")
    else:
        policy = load_memory_policy(repo_root)
    return MemoryPolicyInitResult(path=str(path), created=created, policy=policy)


def path_excluded(path: str | Path, policy: MemoryPolicy) -> bool:
    normalized = _normalize_path(path)
    basename = Path(normalized).name
    for pattern in policy.exclude_paths:
        normalized_pattern = _normalize_path(pattern)
        if not normalized_pattern:
            continue
        if normalized_pattern.endswith("/"):
            prefix = normalized_pattern
            if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
                return True
        if (
            fnmatch.fnmatch(normalized, normalized_pattern)
            or fnmatch.fnmatch(basename, normalized_pattern)
        ):
            return True
    return False


def transcript_excluded(text: str, policy: MemoryPolicy) -> bool:
    haystack = text.casefold()
    return any(pattern.casefold() in haystack for pattern in policy.exclude_transcript_patterns if pattern)


def recall_source_blocked(source: str, policy: MemoryPolicy) -> bool:
    return _matches_any(source, policy.recall_source_block)


def recall_source_allowed(source: str, policy: MemoryPolicy) -> bool:
    return _matches_any(source, policy.recall_source_allow)


def _policy_from_mapping(data: dict[str, Any], *, path: Path) -> MemoryPolicy:
    exclude_paths = _string_tuple(data.get("exclude_paths", DEFAULT_EXCLUDE_PATHS), path=path)
    patterns = _string_tuple(
        data.get("exclude_transcript_patterns", DEFAULT_EXCLUDE_TRANSCRIPT_PATTERNS),
        path=path,
    )
    recall_source_allow = _string_tuple(
        data.get("recall_source_allow", DEFAULT_RECALL_SOURCE_ALLOW),
        path=path,
    )
    recall_source_block = _string_tuple(
        data.get("recall_source_block", DEFAULT_RECALL_SOURCE_BLOCK),
        path=path,
    )
    recall_lint_block_severities = _string_tuple(
        data.get("recall_lint_block_severities", DEFAULT_RECALL_LINT_BLOCK_SEVERITIES),
        path=path,
    )
    invalid_severities = sorted(
        severity
        for severity in recall_lint_block_severities
        if severity not in {"error", "warning", "info"}
    )
    if invalid_severities:
        raise ValueError(
            f"invalid memory policy JSON at {path}: invalid recall lint severities "
            + ", ".join(invalid_severities)
        )
    transcript_retain_days, transcript_max_total_bytes = _transcript_retention_from_mapping(
        data.get("transcripts"),
        path=path,
    )
    summarizer = _summarizer_from_mapping(data.get("summarizer"), path=path)
    return MemoryPolicy(
        exclude_paths=exclude_paths,
        exclude_transcript_patterns=patterns,
        recall_source_allow=recall_source_allow,
        recall_source_block=recall_source_block,
        recall_lint_block_severities=recall_lint_block_severities,
        transcript_retain_days=transcript_retain_days,
        transcript_max_total_bytes=transcript_max_total_bytes,
        summarizer=summarizer,
    )


def _summarizer_from_mapping(value: object, *, path: Path) -> SummarizerConfig:
    if value is None:
        return SummarizerConfig()
    if not isinstance(value, dict):
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer must be an object"
        )
    kind = value.get("kind", DEFAULT_SUMMARIZER_KIND)
    if not isinstance(kind, str) or kind not in SUMMARIZER_KINDS:
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer.kind must be one of "
            f"{sorted(SUMMARIZER_KINDS)}"
        )
    llm_data = value.get("llm")
    if llm_data is None:
        llm = SummarizerLLMConfig()
    elif not isinstance(llm_data, dict):
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer.llm must be an object"
        )
    else:
        llm = _summarizer_llm_from_mapping(llm_data, path=path)
    return SummarizerConfig(kind=kind, llm=llm)


def _summarizer_llm_from_mapping(
    data: dict[str, Any], *, path: Path
) -> SummarizerLLMConfig:
    provider = data.get("provider", DEFAULT_SUMMARIZER_LLM_PROVIDER)
    if not isinstance(provider, str) or provider not in SUMMARIZER_LLM_PROVIDERS:
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer.llm.provider must be "
            f"one of {sorted(SUMMARIZER_LLM_PROVIDERS)}"
        )
    model = data.get("model", DEFAULT_SUMMARIZER_LLM_MODEL)
    if not isinstance(model, str) or not model:
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer.llm.model must be a non-empty string"
        )
    api_key_env = data.get("api_key_env", DEFAULT_SUMMARIZER_LLM_API_KEY_ENV)
    if not isinstance(api_key_env, str) or not api_key_env:
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer.llm.api_key_env must be a non-empty string"
        )
    max_chars = data.get("max_chars", DEFAULT_SUMMARIZER_LLM_MAX_CHARS)
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars <= 0:
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer.llm.max_chars must be a positive integer"
        )
    timeout_seconds = data.get("timeout_seconds", DEFAULT_SUMMARIZER_LLM_TIMEOUT_SECONDS)
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer.llm.timeout_seconds must be a positive integer"
        )
    base_url = data.get("base_url")
    if base_url is not None and (not isinstance(base_url, str) or not base_url):
        raise ValueError(
            f"invalid memory policy JSON at {path}: summarizer.llm.base_url must be a non-empty string when set"
        )
    return SummarizerLLMConfig(
        provider=provider,
        model=model,
        api_key_env=api_key_env,
        max_chars=max_chars,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _transcript_retention_from_mapping(
    value: object, *, path: Path
) -> tuple[int, int]:
    if value is None:
        return DEFAULT_TRANSCRIPT_RETAIN_DAYS, DEFAULT_TRANSCRIPT_MAX_TOTAL_BYTES
    if not isinstance(value, dict):
        raise ValueError(
            f"invalid memory policy JSON at {path}: transcripts must be an object"
        )
    retain = value.get("retain_days", DEFAULT_TRANSCRIPT_RETAIN_DAYS)
    cap = value.get("max_total_bytes", DEFAULT_TRANSCRIPT_MAX_TOTAL_BYTES)
    if not isinstance(retain, int) or isinstance(retain, bool) or retain < 0:
        raise ValueError(
            f"invalid memory policy JSON at {path}: transcripts.retain_days must be a non-negative integer"
        )
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        raise ValueError(
            f"invalid memory policy JSON at {path}: transcripts.max_total_bytes must be a non-negative integer"
        )
    return retain, cap


def _string_tuple(value: object, *, path: Path) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"invalid memory policy JSON at {path}: expected list")
    result = tuple(str(item) for item in value if str(item).strip())
    if len(result) != len(value):
        raise ValueError(f"invalid memory policy JSON at {path}: empty patterns are not allowed")
    return result


def _normalize_path(path: str | Path) -> str:
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)
