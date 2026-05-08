from __future__ import annotations

from ._shared import *

from ait.policy import effective_policy


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    if args.config_command != "show":
        return 1
    result = effective_policy(repo_root)
    payload = {
        "policy": result.policy,
        "warnings": list(result.warnings),
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(_format_config_policy(payload))
    return 0


def _format_config_policy(payload: dict[str, object]) -> str:
    policy = payload.get("policy", {})
    warnings = payload.get("warnings", [])
    lines = ["AIT Config"]
    if isinstance(policy, dict):
        for section_name in ("run", "apply", "integration"):
            section = policy.get(section_name)
            if not isinstance(section, dict):
                continue
            lines.append(f"{section_name}:")
            for key, value in section.items():
                lines.append(f"  {key}: {value}")
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)
