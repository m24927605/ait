# Implementation Plan: Split Daemon Module

**Branch**: `005-split-daemon-module` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/005-split-daemon-module/spec.md`

## Summary

Reduce coupling in `src/ait/daemon.py` by extracting daemon lifecycle/status,
path/config/process state helpers, and reaper behavior into focused modules.
Keep `ait.daemon` as the public API and monkey-patch surface for server loop,
client handler, verifier/summarizer background work, and existing tests.

## Technical Context

**Language/Version**: Python 3.14+
**Primary Dependencies**: Python standard library only; no new runtime dependencies
**Storage**: Existing `.ait/state.sqlite3`, `.ait/daemon.pid`, configured daemon socket path, `.ait/transcripts/`
**Testing**: `pytest` and `unittest` over existing tests
**Target Platform**: Local POSIX CLI environments with Git and UNIX sockets
**Project Type**: Python CLI/library package
**Performance Goals**: Preserve current daemon startup wait, accept-loop concurrency, reaper interval behavior, and shutdown timing
**Constraints**: Preserve `ait.daemon` imports and patch points; no daemon protocol, SQLite schema, CLI, hook, or worktree behavior changes
**Scale/Scope**: Daemon module extraction only

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Kit Traceability**: PASS. Active feature is recorded in
  `.specify/feature.json` and artifacts live under `specs/005-split-daemon-module/`.
- **Low Coupling, High Cohesion**: PASS. Lifecycle/status, low-level state,
  and reaper responsibilities have explicit modules; `daemon.py` keeps server
  protocol handling and patch-sensitive orchestration.
- **Stable Public Behavior**: PASS. The plan preserves public daemon functions,
  `DaemonStatus`, server-loop helpers, socket protocol responses, and patch
  surfaces used by existing tests.
- **Local Safety And Data Integrity**: PASS. Writes remain bounded to existing
  AIT-owned daemon PID/socket paths and SQLite behavior is unchanged.
- **Verification Before Completion**: PASS. Targeted daemon tests, consumer
  tests, full suites, public import/patch contract, architecture gates, and
  `git diff --check` are required.

## Project Structure

### Documentation (this feature)

```text
specs/005-split-daemon-module/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── public-daemon-surface.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/ait/
├── daemon.py             # public API, serve loop, client patch surface
├── daemon_lifecycle.py   # start/stop/prune/status lifecycle commands
├── daemon_models.py      # DaemonStatus dataclass
├── daemon_reaper.py      # timed stale attempt recovery and transcript pruning
└── daemon_state.py       # paths, config, stale cleanup, process inspection

tests/
├── test_daemon_lifecycle.py
├── test_daemon_reaper.py
├── test_daemon_concurrency.py
├── test_daemon_verifier_threads.py
├── test_daemon_e2e.py
├── test_cli_adapters.py
├── test_cli_run.py
└── test_runner.py
```

**Structure Decision**: Keep `src/ait/daemon.py` as a module, not a package, to
preserve direct imports and monkey-patch behavior. Move cohesive helper groups
that do not need `ait.daemon` patch semantics behind `daemon_*.py` modules.

### Dependency Direction

Allowed direction:

```text
daemon.py -> daemon_lifecycle.py
daemon.py -> daemon_models.py
daemon.py -> daemon_reaper.py
daemon.py -> daemon_state.py

daemon_lifecycle.py -> daemon_models.py
daemon_lifecycle.py -> daemon_state.py
daemon_reaper.py -> daemon_state.py
daemon_state.py -> daemon_models.py
```

Helper modules must not import `ait.daemon`. `daemon.py` may import helper
functions as module-level names so public imports and direct tests continue to
work.

### Public Compatibility Surface

- `DaemonStatus`
- `start_daemon`
- `stop_daemon`
- `prune_daemon`
- `daemon_status`
- `serve_daemon`
- `run_reaper_loop`
- `run_accept_loop`
- `_handle_client_safely`
- `_handle_client`
- `_write_response`
- `_verify_attempt_in_background`
- `_summarize_attempt_in_background`
- `_join_verifier_threads`
- `_socket_path`
- `_pid_file`
- `_write_pid_file`
- `_cleanup_stale_daemon_state`
- `_daemon_stale_reason`
- `_socket_connectable`
- `_pid_matches_ait_daemon`
- `_pid_command`
- `_pythonpath_with_src`
- `_reaper_ttl`
- `_daemon_idle_timeout`
- Patch points: `run_accept_loop`, `_handle_client`,
  `_verify_attempt_in_background`, `verify_attempt`,
  `summarize_attempt_transcript`, `process_event`

### Verification Plan

```bash
uv run pytest tests/test_daemon_lifecycle.py tests/test_daemon_reaper.py tests/test_daemon_concurrency.py tests/test_daemon_verifier_threads.py tests/test_daemon_e2e.py
uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py tests/test_runner.py tests/test_claude_code_hook.py tests/test_codex_hook.py tests/test_gemini_hook.py
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
PYTHONPATH=src python3 - <<'PY'
from ait.daemon import (
    DaemonStatus, _cleanup_stale_daemon_state, _daemon_idle_timeout,
    _daemon_stale_reason, _handle_client, _handle_client_safely,
    _join_verifier_threads, _pid_command, _pid_file,
    _pid_matches_ait_daemon, _pythonpath_with_src, _reaper_ttl,
    _socket_connectable, _socket_path, _summarize_attempt_in_background,
    _verify_attempt_in_background, _write_pid_file, _write_response,
    daemon_status, prune_daemon, run_accept_loop, run_reaper_loop,
    serve_daemon, start_daemon, stop_daemon,
)
print("ait.daemon public imports ok")
PY
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
import re
limits = {"src/ait/daemon.py": 420}
for path in Path("src/ait").glob("daemon_*.py"):
    limits[str(path)] = 400
failures = []
facade_import = re.compile(r"(^|\n)\s*(from\s+ait\.daemon\s+import|import\s+ait\.daemon(\s|$))")
for path, limit in sorted(limits.items()):
    lines = Path(path).read_text(encoding="utf-8").count("\n") + 1
    print(f"{lines:4d} {path}")
    if lines > limit:
        failures.append(f"{path} has {lines} lines > {limit}")
for path in Path("src/ait").glob("daemon_*.py"):
    text = path.read_text(encoding="utf-8")
    if facade_import.search(text):
        failures.append(f"{path} imports ait.daemon")
if failures:
    raise SystemExit("\n".join(failures))
print("daemon architecture gate ok")
PY
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Keep `daemon.py` as patch surface | Existing tests patch module-level daemon names | Package conversion or moving patch-sensitive client/background functions would break compatibility without changing behavior |
