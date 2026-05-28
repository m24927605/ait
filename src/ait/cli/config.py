from __future__ import annotations

import sys
from ._shared import *

from ait.policy import effective_policy
from ait.bug_report.config import load_prefs, save_prefs


def run_bug_report_config(*, args: list[str]) -> int:
    prefs = load_prefs()
    if not args:
        print(f"mode: {prefs.mode}")
        print(f"include_tier2: {prefs.include_tier2}")
        print(f"include_tier3: {prefs.include_tier3}")
        return 0
    head, *rest = args
    if head in ("ask", "always", "never"):
        prefs.mode = head
        save_prefs(prefs)
        print(f"mode set to {head}.")
        return 0
    if head in ("tier2", "tier3") and rest and rest[0] in ("on", "off"):
        val = rest[0] == "on"
        if head == "tier2":
            prefs.include_tier2 = val
        else:
            prefs.include_tier3 = val
        save_prefs(prefs)
        print(f"{head} = {'on' if val else 'off'}.")
        return 0
    print(f"unknown bug-report config: {' '.join(args)}", file=sys.stderr)
    return 2


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    if args.config_command == "bug-report":
        remaining = getattr(args, "bug_report_config_args", []) or []
        return run_bug_report_config(args=remaining)
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
