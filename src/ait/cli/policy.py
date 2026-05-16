from __future__ import annotations

from ._shared import *

from ait.team_policy import validate_team_policy


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    if args.policy_command not in {"show", "validate"}:
        return 1
    result = validate_team_policy(repo_root)
    if args.format == "json":
        print(json.dumps(result.payload, indent=2, sort_keys=True))
    else:
        print(_format_policy(result.payload))
    return 0 if result.valid else 2


def _format_policy(payload: dict[str, object]) -> str:
    lines = ["AIT Team Policy", f"status: {payload.get('status')}"]
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines)
