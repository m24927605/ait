from __future__ import annotations

from dataclasses import dataclass
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
EXCLUDED_MARKER = "[EXCLUDED BY MEMORY POLICY]"


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    exclude_paths: tuple[str, ...] = DEFAULT_EXCLUDE_PATHS
    exclude_transcript_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_TRANSCRIPT_PATTERNS

    def to_dict(self) -> dict[str, object]:
        return {
            "exclude_paths": list(self.exclude_paths),
            "exclude_transcript_patterns": list(self.exclude_transcript_patterns),
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


def _policy_from_mapping(data: dict[str, Any], *, path: Path) -> MemoryPolicy:
    exclude_paths = _string_tuple(data.get("exclude_paths", DEFAULT_EXCLUDE_PATHS), path=path)
    patterns = _string_tuple(
        data.get("exclude_transcript_patterns", DEFAULT_EXCLUDE_TRANSCRIPT_PATTERNS),
        path=path,
    )
    return MemoryPolicy(
        exclude_paths=exclude_paths,
        exclude_transcript_patterns=patterns,
    )


def _string_tuple(value: object, *, path: Path) -> tuple[str, ...]:
    if not isinstance(value, list):
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
