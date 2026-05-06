# Contract: Public Daemon Surface

## Stable Imports

The following names must remain importable from `ait.daemon`:

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

## Stable Patch Semantics

- Patching `ait.daemon.run_accept_loop` must affect `serve_daemon()`.
- Patching `ait.daemon._handle_client` must affect `_handle_client_safely()`.
- Patching `ait.daemon._verify_attempt_in_background` must affect the accept
  loop imported from `ait.daemon`.
- Patching `ait.daemon.verify_attempt` must affect
  `_verify_attempt_in_background()`.

## Stable Behaviors

- `DaemonStatus` field names and truth semantics remain stable.
- Daemon CLI commands keep existing exit behavior and output payloads.
- Socket response payloads continue to contain `ok`, duplicate/event IDs, and
  error strings as before.
- Stale cleanup removes stale daemon-owned PID/socket state but not unrelated
  live PIDs.

## Verification Command

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
