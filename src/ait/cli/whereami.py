from __future__ import annotations

from ._shared import *

from ait.agent_state import inspect_agent_state


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    state = inspect_agent_state(repo_root, target_branch=getattr(args, "to", None))
    payload = state.to_dict()
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(_format_whereami(payload))
    return 0 if state.current_state != "not_git_repository" else 2


def _format_whereami(payload: dict[str, object]) -> str:
    context = payload.get("detected_context", {})
    context = context if isinstance(context, dict) else {}
    lines = [
        f"State: {payload.get('current_state')}",
        f"Repo: {payload.get('repo_root')}",
        f"Worktree: {context.get('workspace_ref') or payload.get('worktree', {}).get('path') if isinstance(payload.get('worktree'), dict) else ''}",
        f"Primary: {context.get('is_primary_worktree')}",
        f"AIT workspace: {context.get('is_ait_workspace')}",
        f"Attempt: {context.get('attempt_id') or 'none'}",
        f"Branch: {context.get('current_branch') or 'detached'}",
        f"Target: {context.get('target_branch') or 'unknown'}",
        f"Ahead: {context.get('ahead_by', 0)}",
    ]
    if context.get("dirty"):
        lines.append("Dirty: true")
    return "\n".join(lines)
