# Data Model: Split Daemon Module

## DaemonStatus

Public state snapshot returned by daemon lifecycle commands.

Fields:

- `socket_path`
- `pid_file`
- `running`
- `pid`
- `pid_running`
- `pid_matches`
- `socket_connectable`
- `stale_reason`

## Daemon Lifecycle Command

Start, stop, prune, status, and serve behavior exposed through `ait.daemon`.

Rules:

- Start cleans stale state before spawning a daemon.
- Stop only terminates matching AIT daemon PIDs.
- Prune cleans stale state without starting a daemon.
- Status reports stale reasons without trusting unrelated live PIDs.

## Daemon Socket Server

UNIX socket accept loop that starts one worker thread per client.

Rules:

- Client workers share one SQLite connection protected by `db_lock`.
- Idle timeout stops the server only when no active clients remain.
- Shutdown joins client workers for a bounded time.

## Client Handler

NDJSON protocol event reader and response writer.

Rules:

- Protocol errors return `{ok: false, error: ...}` responses.
- Successful non-duplicate finish/promote events schedule background work
  after the SQLite lock is released.
- Per-client unexpected errors are logged and do not crash the daemon.

## Background Task Thread

Verifier or summarizer thread tracked for clean shutdown.

Rules:

- Threads are tracked until completion.
- Join waits until all tracked threads finish or timeout expires.
- Failures are logged as warnings and do not poison attempt lifecycle records.

## Reaper Loop

Timer-based stale attempt recovery and transcript pruning.

Rules:

- Startup grace can delay the first reap cycle.
- Reaper errors and transcript prune errors are warning-only.
- Stop event exits promptly.

## Daemon State Paths

Socket path, PID file, and temporary PID file locations.

Validation:

- Socket path honors local config and relative paths resolve under repo root.
- PID file replacement is atomic.
- Stale cleanup removes only AIT-owned stale socket/file/symlink paths.

## Process Inspection

PID command lookup and AIT daemon validation.

Validation:

- Current process and invalid PIDs never match.
- `/proc/<pid>/cmdline` is preferred when available.
- `ps` fallback is bounded by a timeout.
