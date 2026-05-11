from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ait.agent_state import AgentState, detected_context_payload, inspect_agent_state


NEXT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class NextAction:
    schema_version: int
    current_state: str
    detected_context: dict[str, object]
    safe_actions: tuple[str, ...]
    unsafe_actions: tuple[str, ...]
    recommended_command: str | None
    alternative_commands: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    recovery_commands: tuple[str, ...]
    explanation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "current_state": self.current_state,
            "detected_context": self.detected_context,
            "safe_actions": list(self.safe_actions),
            "unsafe_actions": list(self.unsafe_actions),
            "recommended_command": self.recommended_command,
            "alternative_commands": list(self.alternative_commands),
            "blocking_reasons": list(self.blocking_reasons),
            "recovery_commands": list(self.recovery_commands),
            "explanation": self.explanation,
        }


def plan_next_action(cwd: str | Path, *, target_branch: str | None = None) -> NextAction:
    state = inspect_agent_state(cwd, target_branch=target_branch)
    return next_action_for_state(state)


def next_action_for_state(state: AgentState) -> NextAction:
    context = detected_context_payload(state)
    target = state.target_branch or "main"
    safe: list[str] = ["ait whereami --json", "ait status --json", "ait next --json"]
    unsafe: list[str] = []
    alternatives: list[str] = []
    recommended: str | None = "ait status --json"
    explanation = "AIT is idle; no result or branch action is currently required."

    if state.current_state == "not_git_repository":
        recommended = "git status"
        safe = ["git status"]
        unsafe = ["ait merge --json", "ait apply --json"]
        explanation = "The current directory is not inside a Git repository, so AIT cannot inspect lineage."
    elif state.current_state == "dirty_worktree":
        recommended = "git status --short"
        safe.extend(["git status --short"])
        unsafe.extend(
            [
                f"ait merge --to {target} --push --json",
                "ait apply --json",
            ]
        )
        explanation = "AIT detected uncommitted or untracked files; merge/apply is blocked until the worktree is clean."
    elif state.current_state == "manual_commit_without_recorded_result":
        recommended = "ait reconcile --json"
        safe.extend(
            [
                "ait reconcile --json",
                f"ait merge --to {target} --dry-run --json",
            ]
        )
        alternatives.extend([f"ait merge --to {target} --dry-run --json"])
        unsafe.append(f"ait merge --to {target} --push --json")
        explanation = "Detected commits ahead of the attempt base branch but no AIT result metadata."
    elif state.current_state == "recorded_result_ready":
        recommended = f"ait merge --to {target} --dry-run --json"
        safe.extend(
            [
                "ait review attempt latest-reviewable --format json",
                "ait review report --format json",
                f"ait merge --to {target} --dry-run --json",
            ]
        )
        alternatives.extend(["ait apply --json", "ait review report --format markdown"])
        explanation = "Detected an AIT result with recorded commit metadata; dry-run merge can validate the landing plan."
    elif state.current_state == "branch_ahead_of_target":
        recommended = f"ait merge --to {target} --dry-run --json"
        safe.extend([f"ait merge --to {target} --dry-run --json"])
        alternatives.extend([f"ait merge --to {target} --mode ff-only --dry-run --json"])
        explanation = "Detected the current branch ahead of the target branch."
    elif state.current_state == "ait_workspace_idle":
        recommended = "ait status --json"
        safe.extend(["git status --short"])
        alternatives.extend(["ait run --help"])
        explanation = "This is an AIT workspace, but it has no committed result ahead of its base."

    if state.blocking_reasons:
        safe.extend(state.recovery_commands)

    return NextAction(
        schema_version=NEXT_SCHEMA_VERSION,
        current_state=state.current_state,
        detected_context=context,
        safe_actions=tuple(dict.fromkeys(safe)),
        unsafe_actions=tuple(dict.fromkeys(unsafe)),
        recommended_command=recommended,
        alternative_commands=tuple(dict.fromkeys(alternatives)),
        blocking_reasons=state.blocking_reasons,
        recovery_commands=state.recovery_commands,
        explanation=explanation,
    )


def format_next_action_text(next_action: NextAction, *, explain: bool = False) -> str:
    lines = [
        f"State: {next_action.current_state}",
        f"Recommended: {next_action.recommended_command or 'none'}",
    ]
    if next_action.blocking_reasons:
        lines.append("Blocking:")
        lines.extend(f"- {reason}" for reason in next_action.blocking_reasons)
    if next_action.safe_actions:
        lines.append("Safe actions:")
        lines.extend(f"- {command}" for command in next_action.safe_actions)
    if next_action.recovery_commands:
        lines.append("Recovery:")
        lines.extend(f"- {command}" for command in next_action.recovery_commands)
    if explain:
        lines.append(f"Explanation: {next_action.explanation}")
    return "\n".join(lines)
