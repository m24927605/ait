# Quickstart: Split Daemon Module

## 1. Baseline Daemon Behavior

```bash
uv run pytest tests/test_daemon_lifecycle.py tests/test_daemon_reaper.py tests/test_daemon_concurrency.py tests/test_daemon_verifier_threads.py tests/test_daemon_e2e.py
```

## 2. Targeted Daemon Consumers

```bash
uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py tests/test_runner.py tests/test_claude_code_hook.py tests/test_codex_hook.py tests/test_gemini_hook.py
```

## 3. Public Import Contract

```bash
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
```

## 4. Architecture Gate

```bash
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

## 5. Full Verification

```bash
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```
