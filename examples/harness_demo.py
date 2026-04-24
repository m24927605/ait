"""Minimal example showing how to drive the ait daemon from a harness.

Usage (after `ait init` in a repo and `ait daemon start`):

    $ ait intent new "Demo intent" --kind chore        # prints intent_id
    $ ait attempt new <intent-id-or-suffix>            # prints attempt_id,
                                                       # workspace_ref,
                                                       # ownership_token
    $ python examples/harness_demo.py \
        <attempt-id> <ownership-token> .ait/daemon.sock

The demo opens the daemon socket, sends `attempt_started`, streams a few
`tool_event` calls (one per simulated file read / write / command), and
finishes. After it exits you can observe the counters with::

    $ ait attempt show <attempt-id>

You should see `observed_tool_calls = 3`, `observed_file_reads = 1`,
`observed_file_writes = 1`, `observed_commands_run = 1`, and the file
paths reported under `files.read` / `files.touched`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ait.harness import AitHarness


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            "usage: harness_demo.py <attempt-id> <ownership-token> <socket-path>",
            file=sys.stderr,
        )
        return 2

    attempt_id, token, socket_path = argv[1], argv[2], argv[3]

    with AitHarness.open(
        attempt_id=attempt_id,
        ownership_token=token,
        socket_path=Path(socket_path),
        agent={
            "agent_id": "demo:harness",
            "harness": "ait-example",
            "harness_version": "0.1.0",
        },
    ) as harness:
        harness.record_tool(
            tool_name="Read",
            category="read",
            duration_ms=3,
            success=True,
            files=[{"path": "src/example.py", "access": "read"}],
        )
        harness.record_tool(
            tool_name="Write",
            category="write",
            duration_ms=7,
            success=True,
            files=[{"path": "src/example.py", "access": "write"}],
        )
        harness.record_tool(
            tool_name="Bash",
            category="command",
            duration_ms=120,
            success=True,
        )
        # finish handled automatically on context exit
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
