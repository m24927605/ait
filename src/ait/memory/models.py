from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class MemoryNote:
    id: str
    topic: str | None
    body: str
    source: str
    created_at: str
    updated_at: str

@dataclass(frozen=True, slots=True)
class MemoryAttempt:
    intent_title: str
    intent_status: str
    attempt_id: str
    agent_id: str
    verified_status: str
    result_exit_code: int | None
    started_at: str
    changed_files: tuple[str, ...]
    commit_oids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    kind: str
    id: str
    score: float
    title: str
    text: str
    metadata: dict[str, object]

@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    kind: str
    topic: str
    body: str
    confidence: str
    status: str
    reason: str
    source_ref: str

@dataclass(frozen=True, slots=True)
class RelevantMemoryItem:
    kind: str
    id: str
    source: str
    topic: str
    score: float
    text: str
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

@dataclass(frozen=True, slots=True)
class RelevantMemoryRecall:
    query: str
    selected: tuple[RelevantMemoryItem, ...]
    skipped: tuple[dict[str, object], ...]
    budget_chars: int
    rendered_chars: int
    compacted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "selected": [item.to_dict() for item in self.selected],
            "skipped": list(self.skipped),
            "budget_chars": self.budget_chars,
            "rendered_chars": self.rendered_chars,
            "compacted": self.compacted,
        }

@dataclass(frozen=True, slots=True)
class RepoMemory:
    repo_root: str
    recent_attempts: tuple[MemoryAttempt, ...]
    hot_files: tuple[str, ...]
    notes: tuple[MemoryNote, ...]
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "recent_attempts": [asdict(attempt) for attempt in self.recent_attempts],
            "hot_files": list(self.hot_files),
            "notes": [asdict(note) for note in self.notes],
            "recommendations": list(self.recommendations),
        }

@dataclass(frozen=True, slots=True)
class MemoryImportResult:
    imported: tuple[MemoryNote, ...]
    skipped: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "imported": [asdict(note) for note in self.imported],
            "skipped": list(self.skipped),
        }

@dataclass(frozen=True, slots=True)
class AgentMemoryStatus:
    initialized: bool
    imported_sources: tuple[str, ...]
    candidate_paths: tuple[str, ...]
    pending_paths: tuple[str, ...]
    state_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "initialized": self.initialized,
            "imported_sources": list(self.imported_sources),
            "candidate_paths": list(self.candidate_paths),
            "pending_paths": list(self.pending_paths),
            "state_path": self.state_path,
        }

@dataclass(frozen=True, slots=True)
class MemoryLintIssue:
    code: str
    severity: str
    note_id: str
    source: str
    topic: str | None
    detail: str
    fixable: bool
    fixed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

@dataclass(frozen=True, slots=True)
class MemoryLintFix:
    note_id: str
    action: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

@dataclass(frozen=True, slots=True)
class MemoryLintResult:
    checked: int
    issues: tuple[MemoryLintIssue, ...]
    fixes: tuple[MemoryLintFix, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "checked": self.checked,
            "issue_count": len(self.issues),
            "fix_count": len(self.fixes),
            "issues": [issue.to_dict() for issue in self.issues],
            "fixes": [fix.to_dict() for fix in self.fixes],
        }

@dataclass(frozen=True, slots=True)
class MemoryHealth:
    status: str
    checked: int
    issue_count: int
    error_count: int
    warning_count: int
    info_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
