from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class BrainNode:
    id: str
    kind: str
    title: str
    text: str
    confidence: str
    metadata: dict[str, object]

@dataclass(frozen=True, slots=True)
class BrainEdge:
    source: str
    target: str
    kind: str
    confidence: str
    metadata: dict[str, object]

@dataclass(frozen=True, slots=True)
class RepoBrain:
    repo_root: str
    generated_at: str
    nodes: tuple[BrainNode, ...]
    edges: tuple[BrainEdge, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "generated_at": self.generated_at,
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }

@dataclass(frozen=True, slots=True)
class BrainQueryResult:
    node: BrainNode
    score: float
    neighbors: tuple[BrainNode, ...]
    edges: tuple[BrainEdge, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "node": asdict(self.node),
            "score": self.score,
            "neighbors": [asdict(node) for node in self.neighbors],
            "edges": [asdict(edge) for edge in self.edges],
        }

@dataclass(frozen=True, slots=True)
class BriefingQuerySource:
    source: str
    value: str

@dataclass(frozen=True, slots=True)
class AutoBriefingQuery:
    query: str
    sources: tuple[BriefingQuerySource, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "sources": [asdict(source) for source in self.sources],
        }

@dataclass(frozen=True, slots=True)
class RepoBrainBriefing:
    query: str
    generated_at: str
    results: tuple[BrainQueryResult, ...]
    sources: tuple[BriefingQuerySource, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "generated_at": self.generated_at,
            "sources": [asdict(source) for source in self.sources],
            "results": [result.to_dict() for result in self.results],
        }
