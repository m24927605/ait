# Code Review: `ait continue`

Date: 2026-05-20

Scope:

- `src/ait/continue_flow.py`
- `src/ait/cli/continue_cmd.py`
- `src/ait/cli_parser.py`
- `src/ait/cli/main.py`
- `tests/test_cli_continue.py`
- `docs/ait-continue-recovery-design-zh.md`

## Findings

No blocking issues found.

## Review Notes

- `ait continue` is implemented as a router, not as a replacement for `ait session attach` or `ait resume`.
- JSON and non-interactive modes only print a plan. They do not start PTYs or shells.
- Interactive mode delegates to the existing primitives:
  - `run_foreground_attach()` for `session_attach`.
  - `launch_resume_shell()` for `attempt_resume`.
- `latest` selection compares session `updated_at` against attempt `started_at`, `ended_at`, and `heartbeat_at`, using the newest attempt timestamp.
- Agent-native resume commands are presented as hints only. AIT's guarantee remains limited to its own session metadata and worktrees.
- Codex native resume extraction is local-only and best-effort; missing traces fall back to `ait resume`.

## Residual Risk

- Agent CLI native resume commands can change across versions. This is acceptable because the commands are displayed as hints, not treated as authoritative recovery.
- Foreground PTY detach/resume is still bounded by the existing foreground ownership model. If the OS process is killed, AIT cannot resurrect it.

## Verification

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_cli_continue.py tests/test_cli_resume.py -q
PYTHONPATH=src .venv/bin/python -m compileall -q src/ait/continue_flow.py src/ait/cli/continue_cmd.py
git diff --check
```

Result:

```text
9 passed
compileall passed
git diff --check passed
```
