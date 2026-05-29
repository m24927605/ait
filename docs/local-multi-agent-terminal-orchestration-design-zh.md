# AIT Local Multi-Agent Terminal Orchestration 設計

Status: Phase 5a/5b foreground MVP implemented; daemon-owned PTY detach/resume scaffold pending
Owner: AIT Staff+ Product, Platform Architecture, DevRel, Security/Trust,
Docs, Open Source Maintainer, and Senior Python Engineering Team
Scope: interactive terminal / PTY orchestration for AIT Local Multi-Agent
Session Room.

本文延伸
[`local-multi-agent-session-room-design-zh.md`](local-multi-agent-session-room-design-zh.md)。
目前 session room 已有 repo-local session store、real adapter / fake /
local command fan-out、Role Mode attempt/review linkage、context manifest、
participant lifecycle、split implementation、adaptive allocation dry-run。
本文專門定義尚未完成的
互動式 terminal / streaming UX。

Implementation note:

- `ait session attach latest` now starts foreground-owned local PTYs for active
  participants, writes per-PTY state under `.ait/sessions/<session-id>/ptys/`,
  appends attributed streaming events to
  `.ait/sessions/<session-id>/streams/events.jsonl`, and persists raw plus
  redacted terminal transcripts per response.
- `ait session attach latest --format json` is plan-only and does not start a
  PTY.
- `ait session panes/send/kill/replay` exist. `panes` and `replay` are
  machine-readable; `send` and resumable `kill` report blocking reasons while
  daemon-owned PTY ownership remains pending.
- Foreground input routing supports `/to`, `/all`, `/kill`, and `/detach`.
  Detach refuses active foreground PTYs unless `--terminate-on-detach` is used
  or AIT performs cleanup for non-interactive stdin.
- Advisory PTYs run in session-local directories. Implementer PTYs run in
  isolated AIT attempt workspaces with `AIT_WORKSPACE_REF`; reviewer PTYs use a
  separate session-local reviewer workspace. Terminal commands do not apply
  changes.

## 1. Product Positioning

AIT terminal orchestration 的定位是：

> AIT owns the local terminal room. Each interactive agent gets its own PTY,
> transcript, context manifest, lifecycle, and responsibility boundary. The user
> routes input explicitly; AIT records and gates outcomes before repo mutation.

繁中：

> AIT 提供本機 multi-agent terminal room：Claude Code、Codex、Aider 等互動式
> CLI 可以同時掛在同一個 AIT session 裡，但每個 agent 的 terminal、輸入、輸出、
> evidence、attempt 與責任歸屬仍然分開。

這不是：

- 不是 SaaS chat。
- 不是遠端 terminal sharing。
- 不是 tmux replacement。
- 不是讓 agents 自由互相私聊。
- 不是 multi-agent consensus auto-apply。
- 不是把 Claude/Codex/Aider 的 provider network 行為藏到 AIT 裡。

這是：

- 本機 PTY coordinator。
- 使用者可 attach/detach/resume 的 session UI。
- 每個 agent 一個 isolated PTY process。
- 每個 output event 都有 participant attribution。
- 每個 input route 都有 user/audit provenance。
- 任何 repo mutation 仍走 existing isolated attempt + review/apply gate。

## 2. User Experience

### Primary Commands

```bash
ait session attach latest
ait session attach latest --layout stacked
ait session attach latest --agent claude-code
ait session attach latest --read-only
ait session detach latest
ait session panes latest --format json
ait session send latest --to claude-code --message "review the latest finding"
ait session send latest --all --message "what risks do you see?"
ait session kill latest --agent codex
ait session replay latest --turn latest
```

### Interactive Screen Draft

```text
AIT Session: Refactor auth retry · ses_01...
Mode: attached · Input route: /to claude-code

┌─ claude-code · active · rsp_01... ───────────────────────────────┐
│ Claude streaming output...                                        │
│ changed files are still isolated in attempt att_01...             │
└───────────────────────────────────────────────────────────────────┘

┌─ codex · active · rsp_02... ──────────────────────────────────────┐
│ Codex streaming output...                                         │
│ review evidence: rev_01...                                        │
└───────────────────────────────────────────────────────────────────┘

input> /to claude-code implement retry policy
input> /to codex review attempt att_01...
input> /all list unresolved risks
input> /detach
```

### Input Routing

Supported routes:

- `/to <agent-or-participant-id> <text>` routes input to one participant.
- `/all <text>` routes the same user input to all active participants.
- `/mode panel|role|council|sequential` changes future dispatch mode.
- `/pause <agent>` stops future input to one participant.
- `/resume <agent>` resumes input routing.
- `/kill <agent>` terminates the PTY process and records cancellation.
- `/detach` exits the UI but leaves eligible PTYs running.
- `/help` shows local commands.

Rules:

- Default route should be explicit. If omitted, AIT should use the selected
  participant and render that state visibly.
- Input routed to multiple agents is copied as separate input events, one per
  participant.
- Agent output is never pasted into another agent's stdin automatically.
- Cross-agent communication must go through AIT summaries, accepted decisions,
  review findings, or explicitly routed user messages.

## 3. Architecture

### Existing Baseline

Current code already has:

- `src/ait/runner_pty.py`: single-command PTY transcript capture.
- `src/ait/session_room.py`: session artifacts, participants, context manifests,
  local command/fake fan-out, role attempts, reviewer evidence.
- `src/ait/daemon_transport.py`: Unix socket transport primitives.
- `.ait/sessions/<session-id>/`: session-local transcript/provenance artifacts.

Gap:

- There is no long-running multi-PTY attach loop.
- There is no streaming session event store.
- There is no pane renderer/input router.
- There is no detach/resume process registry for interactive participants.

### Proposed Components

```text
src/ait/session_terminal.py
  PTY process lifecycle, resize, input write, output read

src/ait/session_events.py
  append-only streaming event store and replay cursor

src/ait/session_attach.py
  terminal UI loop, layout, input routing, detach/resume

src/ait/cli/session.py
  attach/detach/panes/send/kill/replay command handlers
```

### PTY Per Agent

Each attached participant owns:

- `pty_id`
- `participant_id`
- `response_id`
- `pid`
- `master_fd`
- `command`
- `cwd`
- `env`
- `context_ref`
- `context_manifest_ref`
- `started_at`
- `last_output_at`
- `state`

PTY state transitions:

```text
created -> starting -> running
running -> detached
detached -> attached
running -> cancelling -> cancelled
running -> exited
running -> crashed
```

### Process Ownership

AIT should not place multiple agents in one PTY. A participant can be restarted,
but restart creates a new response id and links `retry_of_response_id`.

Long-running PTYs need one of two ownership models:

1. Foreground attach owns child processes. Detach either refuses while processes
   are active or moves them under a local session daemon.
2. Local session daemon owns child PTYs. `ait session attach` is a client that
   renders and routes input.

Recommendation:

- Phase 5a: foreground attach, no detach while PTYs are running unless
  `--terminate-on-detach`.
- Phase 5b: daemon-owned PTYs with detach/resume.

This reduces first implementation risk and avoids orphaned terminal processes.

## 4. Streaming Event Store

### Storage Layout

```text
.ait/sessions/<session-id>/
  streams/
    events.jsonl
    cursors/
      attach-<pid>.json
  ptys/
    <pty-id>.json
  transcripts/
    <response-id>.terminal.raw
    <response-id>.terminal.redacted.md
```

### Event Schema

```json
{
  "schema_version": 1,
  "event_id": "evt_01...",
  "session_id": "ses_01...",
  "turn_id": "turn_0004",
  "participant_id": "part_001_claude",
  "response_id": "rsp_01...",
  "pty_id": "pty_01...",
  "seq": 42,
  "kind": "pty_output",
  "created_at": "2026-05-15T08:00:00Z",
  "payload_ref": ".ait/sessions/ses_01.../streams/payloads/evt_01....bin",
  "payload_sha256": "...",
  "redacted": false,
  "byte_count": 512
}
```

Event kinds:

- `pty_started`
- `pty_output`
- `pty_input`
- `pty_resize`
- `pty_exited`
- `pty_cancelled`
- `attach_started`
- `attach_detached`
- `route_changed`
- `summary_written`

Rules:

- Events are append-only.
- `seq` is monotonic per session.
- Output payload can be binary-safe, but replay/export uses UTF-8 replacement
  plus redaction.
- Raw payloads are local-only.
- Redacted transcript is the default export source.

## 5. Context And Memory

Before starting each interactive PTY, AIT writes:

```text
.ait/sessions/<session-id>/contexts/<turn-id>-<participant-id>.md
.ait/sessions/<session-id>/contexts/<turn-id>-<participant-id>-manifest.json
```

Environment:

```text
AIT_SESSION_ID
AIT_TURN_ID
AIT_PARTICIPANT_ID
AIT_RESPONSE_ID
AIT_CONTEXT_FILE
AIT_CONTEXT_HINT
AIT_WORKSPACE_REF        # only if attached to an isolated attempt
```

Context rules:

- Same-round peer output is not injected automatically.
- Prior peer output can appear only as attributed advisory context.
- Accepted decisions can appear as trusted session decisions.
- Policy-blocked memory must not enter context.
- Raw terminal output must pass redaction before summary/export reuse.

## 6. Attempt And Review Integration

Interactive PTY can be advisory or mutation-capable.

Advisory participant:

- CWD is a session-local run directory.
- Cannot mutate root checkout through AIT.
- Output is advisory response evidence.

Implementer participant:

- Must run inside an AIT isolated attempt workspace.
- `AIT_WORKSPACE_REF` is set.
- Any commits/diffs link to the response id.
- Root checkout remains untouched.

Reviewer participant:

- Receives target attempt diff/evidence through reviewer context.
- Does not write implementer workspace.
- Review findings link to target attempt and response id.

Apply:

- No terminal session command applies changes.
- `ait apply <attempt-id>` remains explicit.

## 7. Safety And Trust

Blocking rules:

- A PTY participant must not run in root checkout if role can mutate files.
- AIT must not route one agent's raw output into another agent's stdin
  automatically.
- Hidden network calls by AIT are forbidden. Provider network belongs to the
  invoked local CLI and must be visible in command provenance.
- Terminal escape sequences must be sanitized for transcript/export.
- Raw terminal payloads are local-only.
- Redaction must run before summaries, replay export, and context reuse.
- Detach must not leave untracked orphan processes without a visible recovery
  handle.
- Resize/input/cancel events must be attributable to user or AIT actor.

Prompt injection considerations:

- Agent output is untrusted text.
- If a user routes output-derived text to another agent, AIT records it as a
  user route event or AIT summary event.
- Summary-generated context must preserve source response ids.

## 8. CLI/API JSON

`ait session attach --format json` should not start an interactive UI. It should
return a plan:

```json
{
  "schema_version": 1,
  "kind": "session_attach_plan",
  "session_id": "ses_01...",
  "participants": [
    {
      "participant_id": "part_001_claude",
      "agent_id": "claude-code",
      "state": "ready",
      "command": "claude",
      "context_manifest_ref": ".ait/sessions/.../contexts/..."
    }
  ],
  "safe_actions": ["ait session attach latest"],
  "unsafe_actions": [
    {
      "command": "ait apply latest",
      "reason": "attach does not select or apply attempts"
    }
  ],
  "blocking_reasons": [],
  "provenance_refs": [".ait/sessions/ses_01.../streams/events.jsonl"]
}
```

`ait session panes --format json` returns live PTY state:

```json
{
  "schema_version": 1,
  "kind": "session_panes",
  "session_id": "ses_01...",
  "panes": [
    {
      "pty_id": "pty_01...",
      "participant_id": "part_001_claude",
      "response_id": "rsp_01...",
      "pid": 12345,
      "state": "running",
      "last_output_at": "2026-05-15T08:00:00Z"
    }
  ]
}
```

## 9. Implementation Plan

### Phase 5a: Foreground Attach MVP

Files likely touched:

- `src/ait/session_terminal.py`
- `src/ait/session_events.py`
- `src/ait/session_attach.py`
- `src/ait/cli/session.py`
- `src/ait/cli_parser.py`
- `tests/test_session_terminal.py`
- `tests/test_cli_session_attach.py`

Scope:

- One PTY per participant.
- Foreground attach owns PTYs.
- No daemon detach/resume yet.
- Prefix or stacked layout, not full curses UI.
- Explicit `/to`, `/all`, `/kill`, `/detach`.
- Redacted transcript assembly on exit.

Implemented acceptance:

- Two fake PTY commands stream with separate attribution.
- Input routed to one participant does not appear in another participant stdin.
- `/all` creates separate input events per participant.
- Terminal output events are deterministic and replayable.
- Ctrl-C/cancel records partial output.
- Root checkout remains untouched for advisory participants.

### Phase 5b: Session Panes, Send, Kill, Replay

Scope:

- `ait session panes`, `send`, `kill`, `replay`.
- Stale PTY recovery and orphan process handling.

Implemented acceptance:

- `panes --format json` lists PTY state, pid, participant, response,
  `last_output_at`, and provenance refs.
- `replay` deterministically rebuilds attributed output from the stream event
  store with terminal escape stripping and redaction.
- `send` reports explicit blocking reasons until daemon-owned PTY ownership is
  enabled.
- `kill` can mark stale or externally killable pane metadata without affecting
  siblings; foreground `/kill` cancels only the selected participant.
- Stale process detection marks response crashed/cancelled.

### Phase 5c: Daemon-Owned PTYs And Resume

Scope:

- Local Unix-socket session terminal daemon.
- Detach/resume active PTYs.

Current status:

- Scaffolded as explicit `daemon_ownership` metadata in attach, panes, send,
  kill, and replay payloads.
- Pending implementation. Foreground attach refuses active detach unless
  termination is explicit, so AIT does not leave orphan PTYs without recovery
  metadata.

Acceptance:

- Detach leaves visible recovery handles.
- Resume replays missed events and continues streaming.

### Phase 5c: Rich Terminal UI

Scope:

- Pane layout with resize support.
- Scrollback and focus.
- Optional compact status bar.
- Search/replay from event stream.

Acceptance:

- Resize event updates child PTY size.
- Long output does not mix attribution.
- Export remains deterministic and redacted.

## 10. Testing Matrix

| Area | Test | Acceptance |
| --- | --- | --- |
| PTY isolation | Two fake PTY agents run | Separate `pty_id`, `response_id`, output refs. |
| Input route | `/to claude hi` | Only Claude stdin receives `hi`. |
| Broadcast | `/all status?` | Each participant gets separate input event. |
| Attribution | Interleaved output | Renderer and event store keep participant ids. |
| Cancel | `/kill codex` | Codex response cancelled, Claude continues. |
| Detach MVP | `/detach` with running PTYs in Phase 5a | Either refuses with reason or terminates per explicit policy. |
| Resume | Phase 5b detach/resume | Missed events replay before live stream. |
| Redaction | Agent prints token fixture | Export/replay redacts secret. |
| Escape safety | Agent emits terminal escape sequence | Export sanitizes or escapes control chars. |
| Root safety | Advisory attach | Root `git status --short` unchanged except ignored `.ait/`. |
| Attempt safety | Implementer attach | Writes happen in isolated attempt workspace. |
| JSON | `panes --format json` | Machine-actionable state and provenance refs. |

## 11. Code Review Blocking Standards

Blocking findings:

- Interactive agent runs in root checkout with mutation permission.
- Output from different agents is stored without attribution.
- One agent can write another agent's PTY/input stream.
- Detach leaves orphaned processes without recovery metadata.
- Raw terminal output is reused as context without redaction and attribution.
- `ait session attach` or `send` applies changes directly.
- Hidden SaaS/network dependency in AIT orchestration.
- Missing tests for input routing, cancellation, redaction, and root safety.

## 12. Open Questions

- Should Phase 5a allow detach only after all PTYs exit, or terminate on detach
  by default?
- Should the rich UI use simple ANSI rendering first or depend on a TUI library?
- How should provider-specific interactive startup prompts be detected without
  brittle scraping?
- Should `ait session attach` require explicit `--agent-command` for real
  Claude/Codex/Aider, or infer from adapter registry?
- What is the retention policy for raw PTY payloads versus redacted replay?
