from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DecisionReason:
    code: str
    message: str
    paths: tuple[str, ...] = ()
    debug: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DecisionNextStep:
    command: str
    description: str
    kind: str = "daily"


@dataclass(frozen=True, slots=True)
class DecisionReport:
    schema_version: int
    subject: str
    subject_id: str | None
    decision: str
    safety_level: str
    reasons: tuple[DecisionReason, ...]
    next_steps: tuple[DecisionNextStep, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def decision_report(
    *,
    subject: str,
    subject_id: str | None,
    decision: str,
    safety_level: str,
    reason_code: str,
    reason_message: str,
    paths: tuple[str, ...] = (),
    debug: dict[str, Any] | None = None,
    next_steps: tuple[DecisionNextStep, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> DecisionReport:
    return DecisionReport(
        schema_version=1,
        subject=subject,
        subject_id=subject_id,
        decision=decision,
        safety_level=safety_level,
        reasons=(DecisionReason(reason_code, reason_message, paths=paths, debug=debug or {}),),
        next_steps=next_steps,
        metadata=metadata or {},
    )


def daily_step(command: str, description: str) -> DecisionNextStep:
    return DecisionNextStep(command=command, description=description)


def debug_step(command: str, description: str) -> DecisionNextStep:
    return DecisionNextStep(command=command, description=description, kind="debug")


def decision_payload(report: DecisionReport) -> dict[str, Any]:
    return asdict(report)
