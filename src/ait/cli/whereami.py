from __future__ import annotations

from ._shared import *

from ait.agent_state import inspect_agent_state
from ait.next_action import next_action_for_state


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    state = inspect_agent_state(repo_root, target_branch=getattr(args, "to", None))
    payload = state.to_dict()
    payload["next_action"] = next_action_for_state(state).to_dict()
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(_format_whereami(payload))
    # whereami reports a fact; not being in an attempt is not an
    # error. Exit 0 in both states. Internal failures bubble up to
    # main() as exceptions, never as a non-zero whereami exit.
    return 0


def _format_whereami(payload: dict[str, object]) -> str:
    context = payload.get("detected_context") or {}
    if not isinstance(context, dict):
        context = {}
    repo_root = payload.get("repo_root") or "<unknown>"

    if context.get("is_ait_workspace"):
        attempt_id = str(context.get("attempt_id") or "?")
        short_id = attempt_id.split(":")[-1][:9].upper()
        target = context.get("target_branch") or "unknown"
        head = context.get("current_branch") or "detached"
        dirty = bool(context.get("dirty"))
        dirty_files = context.get("dirty_tracked_files") or []
        dirty_count = len(dirty_files) if isinstance(dirty_files, list) else 0
        if dirty:
            dirty_str = (
                f"yes ({dirty_count} file{'s' if dirty_count != 1 else ''})"
                if dirty_count
                else "yes"
            )
        else:
            dirty_str = "no"
        workspace_ref = context.get("workspace_ref") or "<unknown>"
        return "\n".join([
            f"Inside AIT attempt {short_id}",
            f"  target     {target}",
            f"  HEAD       {head}",
            f"  dirty      {dirty_str}",
            f"  workspace  {workspace_ref}",
            f"  repo       {repo_root}",
        ])

    return "\n".join([
        "Not in an AIT attempt.",
        f"  repo: {repo_root} (primary checkout)",
    ])
