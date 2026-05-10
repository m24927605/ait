from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "reconcile":
        if getattr(args, "dry_run", False):
            from ait.agent_state import inspect_agent_state

            state = inspect_agent_state(repo_root)
            payload = {
                "schema_version": 1,
                "status": "planned",
                "dry_run": True,
                "detected_context": state.to_dict()["detected_context"],
                "operations": [
                    {
                        "kind": "ait",
                        "command": ["ait", "reconcile", "--json"],
                        "will_execute": False,
                    }
                ],
            }
            print(json.dumps(payload, indent=2))
            return 0
        result = reconcile_repo(repo_root)
        payload = asdict(result)
        payload["schema_version"] = 1
        if getattr(args, "format", "json") == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_reconcile_result(payload))
        return 0
    if parser is not None:
        parser.print_help()
    return 1


def _format_reconcile_result(payload: dict[str, object]) -> str:
    lines = [
        "AIT reconcile",
        f"Rewrite mappings: {payload.get('processed_mappings', 0)}",
        f"Synthetic result: {payload.get('synthetic_result_created', False)}",
    ]
    if payload.get("attempt_id"):
        lines.append(f"Attempt: {payload.get('attempt_id')}")
    if payload.get("changed_files"):
        lines.append(f"Changed: {len(payload.get('changed_files', []))} files")
    if payload.get("blocking_reason"):
        lines.append(f"Blocking: {payload.get('blocking_reason')}")
    return "\n".join(lines)
