# AI VCS Protocol Appendix

## Purpose

This appendix defines the v1 daemon protocol details that are too operational for the main spec but required for consistent implementation.

## Transport

V1 uses:

- Unix domain socket
- newline-delimited JSON
- request messages sent from harness to daemon
- synchronous response messages for lifecycle-creating operations

Default socket path:

```text
.ait/daemon.sock
```

If the path is overridden, the override must be stored in local `.ait` config.

## Message Envelope

Every daemon message must use this outer shape:

```json
{
  "schema_version": 1,
  "event_id": "repo_id:01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "event_type": "tool_event",
  "sent_at": "2026-04-23T12:34:56Z",
  "attempt_id": "repo_id:01ARZ3NDEKTSV4RRFFQ69G5FAA",
  "ownership_token": "opaque-token",
  "payload": {}
}
```

Rules:

- `event_id` is the idempotency key
- duplicate `event_id` messages must be ignored
- `schema_version` applies to the message envelope, not only stored objects
- `ownership_token` is required on all lifecycle-mutating messages after attempt creation

## Lifecycle Creation Flow

### `ait attempt new`

`ait attempt new <intent-id>` must synchronously return:

- `attempt_id`
- `workspace_ref`
- `base_ref_oid`
- `ownership_token`

Example response:

```json
{
  "attempt_id": "repo_id:01ARZ3NDEKTSV4RRFFQ69G5FAA",
  "workspace_ref": "/repo/.ait/workspaces/attempt-01",
  "base_ref_oid": "abc123...",
  "ownership_token": "opaque-token"
}
```

The harness is responsible for retaining and replaying `ownership_token` in later messages.

## Event Types

### `attempt_started`

Payload:

```json
{
  "agent": {
    "agent_id": "claude-code:default",
    "model": "model-name",
    "harness": "claude-code",
    "harness_version": "1.2.3"
  }
}
```

### `attempt_heartbeat`

Payload:

```json
{}
```

Semantics:

- update `heartbeat_at = max(existing, sent_at)`

### `tool_event`

Payload:

```json
{
  "tool_name": "Read",
  "category": "read",
  "duration_ms": 42,
  "success": true,
  "files": [
    {
      "path": "src/auth.ts",
      "access": "read"
    }
  ],
  "payload_ref": ".ait/objects/ab/cdef..."
}
```

Rules:

- `files` is optional but strongly recommended
- each file entry must use `access` of:
  - `read`
  - `write`
- daemon derives:
  - `files_read` from any file with `access=read`
  - `files_touched` from any file with `access=write`
- `files_changed` is not derived from `tool_event`; it is derived from final commit diffs during verification

Category meanings:

- `read`: pure read operations
- `write`: file modification operations
- `command`: external command execution
- `other`: all remaining tools

Counter rules:

- increment `observed.tool_calls` for every `tool_event`
- increment `observed.file_reads` for every `tool_event` with `category=read`
- increment `observed.file_writes` for every `tool_event` with `category=write`
- increment `observed.commands_run` for every `tool_event` with `category=command`

### `attempt_finished`

Payload:

```json
{
  "exit_code": 0,
  "raw_trace_ref": ".ait/objects/ab/trace...",
  "logs_ref": ".ait/objects/cd/logs..."
}
```

Semantics:

- sets `reported_status=finished`
- stores refs needed for summarization and verification
- does not by itself set `verified_status=succeeded`

### `attempt_promoted`

Payload:

```json
{
  "promotion_ref": "refs/heads/fix/oauth-expiry",
  "commit_oids": [
    "abc123..."
  ]
}
```

Semantics:

- requests promotion verification
- daemon or verifier must confirm that `promotion_ref` points at a commit graph containing the declared commit set

### `attempt_discarded`

Payload:

```json
{
  "reason": "user-requested"
}
```

Semantics:

- sets `verified_status=discarded` if the attempt has not already been promoted

## Verification Rules

### `succeeded`

An attempt may become `verified_status=succeeded` when:

1. `reported_status=finished`
2. declared refs exist
3. raw trace and logs are readable if provided
4. commit metadata and evidence summary can be materialized consistently

### `promoted`

An attempt may become `verified_status=promoted` only when:

1. it already qualifies for `succeeded`
2. `promotion_ref` exists
3. the declared promoted commit set is reachable from `promotion_ref`

## Ordering And Idempotency

Rules:

1. events may arrive out of order
2. duplicate events must be deduplicated by `event_id`
3. `attempt_finished` may arrive after a later heartbeat
4. stale heartbeats must not move `heartbeat_at` backward
5. promotion verification is idempotent

## Ownership Rules

Rules:

1. only the holder of the current `ownership_token` may emit:
   - `attempt_started`
   - `attempt_heartbeat`
   - `tool_event`
   - `attempt_finished`
   - `attempt_promoted`
   - `attempt_discarded`
2. `ownership_token` is opaque in v1
3. token rotation is out of scope for v1

## Implementation Notes

The daemon should expose a small internal API surface:

- validate envelope
- dedupe by `event_id`
- validate `ownership_token`
- persist raw event log if desired
- update runtime objects
- enqueue verification jobs

This appendix defines protocol behavior, not the internal daemon architecture.
