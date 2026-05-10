from __future__ import annotations

import json
import sys


AGENT_ERROR_SCHEMA_VERSION = 1


def agent_error_payload(
    *,
    error_code: str,
    message: str,
    detected_state: dict[str, object] | None = None,
    user_data_safe: bool = True,
    blocking_reason: str | None = None,
    recommended_commands: list[str] | tuple[str, ...] = (),
    docs_reference: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": AGENT_ERROR_SCHEMA_VERSION,
        "status": "error",
        "error_code": error_code,
        "message": message,
        "detected_state": detected_state or {},
        "user_data_safe": user_data_safe,
        "blocking_reason": blocking_reason or message,
        "recommended_commands": list(recommended_commands),
        "docs_reference": docs_reference or "docs/agent-command-contract.md",
    }
    return payload


def emit_agent_error(
    output_format: str,
    *,
    error_code: str,
    message: str,
    detected_state: dict[str, object] | None = None,
    user_data_safe: bool = True,
    blocking_reason: str | None = None,
    recommended_commands: list[str] | tuple[str, ...] = (),
    docs_reference: str | None = None,
) -> None:
    payload = agent_error_payload(
        error_code=error_code,
        message=message,
        detected_state=detected_state,
        user_data_safe=user_data_safe,
        blocking_reason=blocking_reason,
        recommended_commands=recommended_commands,
        docs_reference=docs_reference,
    )
    if output_format == "json":
        print(json.dumps(payload, indent=2))
        return
    print(f"error: {message}", file=sys.stderr)
    if recommended_commands:
        print("Recommended:", file=sys.stderr)
        for command in recommended_commands:
            print(f"- {command}", file=sys.stderr)
