# Dogfood Session 2

Date: 2026-04-24

Goal: prove the high-frequency path. Session 1 exercised only the lifecycle
CLI. Session 2 stands up the daemon, writes a minimal harness client, and
streams real `tool_event`s against a live attempt while independently
verifying `observed.*` counters and `evidence_files` population.

## What Worked

- `ait daemon start` spawned a background process and the socket path
  reported by `ait daemon status` was immediately usable.
- Fresh attempt created under intent `01KPYYR8DQXFF10A7HBR8P26D5` (short
  id resolution via the Friction C fix, no need to paste the full
  100-char form).
- Harness (`ait.harness.AitHarness`) successfully:
  - opened a unix socket connection to the daemon
  - sent `attempt_started` with agent descriptor
  - streamed four `tool_event` messages (2 reads, 1 write, 1 command)
  - sent one `attempt_heartbeat`
  - sent `attempt_finished` with `exit_code=0`
- Daemon accumulated counters exactly as expected:
  ```
  observed_tool_calls  = 4
  observed_file_reads  = 2
  observed_file_writes = 1
  observed_commands_run = 1
  observed_duration_ms = 445     # 8 + 5 + 12 + 420
  ```
- `evidence_files` indexed correctly into `files.read` (two paths) and
  `files.touched` (one path).
- Verifier auto-advanced the attempt to `verified_status=succeeded` on
  receipt of `attempt_finished`.
- `ait attempt commit` on the worktree wrote a commit with correct
  `Intent-Id` / `Attempt-Id` trailers on top of the attempt's base.

## Real Bugs Found And Fixed

### Bug F (medium): daemon does not accept short id fragments

**Symptom:** sending events with a ULID suffix as `attempt_id` failed
with `attempt not found: 01KPYYRC...`.

**Root cause:** the idresolver fix from Friction C lives in the app layer
(`src/ait/app.py`); the daemon event handlers (`src/ait/events.py`) call
`get_attempt(conn, attempt_id)` directly, which is exact-match only.

**Resolution:** explicitly **not** fixed in this session. The harness
receives the full `attempt_id` from `ait attempt new` stdout and passes
it through verbatim; CLI accepts short ids for human convenience. This
is the right split — only humans need fuzzy id resolution. Documented
here so the next harness author does not hunt for it.

### Bug G (medium): tool_event without `files` is rejected

**Symptom:** `daemon rejected tool_event: tool_event files must be a list`
when sending a `category=command` event with no per-file records.

**Root cause:** `handle_tool_event` defaulted `payload.get('files', ())`
to an empty tuple and then validated `isinstance(files, list)`, which
rejected the default `()`.

**Resolution:** changed the default to `None` so the early return
covers both "key absent" and "explicit null" cases. Regression test
added (`tests/test_events.py::test_tool_event_without_files_only_updates_counters`).
Fix landed in commit `e65f6a4`.

### Bug B (verified in practice): promote refuses when main is dirty

The Bug B fix (`bf6bb5b`) intentionally refuses `ait attempt promote --to
<head-branch>` when the main working tree has uncommitted tracked changes.
This session hit that path for real: after fixing Bug G locally but
before committing it, promoting the dogfood attempt to `main` failed.
That is the correct, desired behaviour — the alternative is silently
clobbering in-flight work — but it means harness authors need to plan
around it. Two reasonable patterns:

1. Promote to a side branch (e.g. `dogfood/cycle-2`) that is not
   currently checked out. The main working tree is untouched.
2. Require a clean main tree before promote; treat the refusal as a
   signal to commit or stash first.

This session used pattern 2: committed Bug G fix and harness module via
plain `git` (outside the attempt) and then landed the harness demo and
this log separately. The attempt-2 record remains with
`verified_status=succeeded` as a historical artifact.

## Observations That Are Not Bugs But Interesting

- **Daemon restart is required after source changes.** The daemon is a
  long-lived Python process; module reload is not automatic. Every time
  an event handler (or any imported module) changes, `ait daemon stop &&
  ait daemon start` is needed. For iterative development this is real
  friction but acceptable for v1.
- **The ownership token is opaque and regenerated per attempt.** Good:
  no way to accidentally use a stale token. Cost: if you lose the token
  after `attempt new` returns, you cannot recover it — the attempt is
  effectively orphaned. Recommendation: persist the JSON output of
  `attempt new` to a file before using it.
- **`ait.harness` round-tripped `agent_id=dogfood:session-2`** into
  `attempt.agent_id` correctly, replacing the CLI placeholder
  `codex:main`. The agent identity lifecycle is: initial row set by
  `create_attempt` (CLI default), overwritten by the first
  `attempt_started` event from the harness. That is the right shape but
  the placeholder is still odd when the harness never sends
  `attempt_started`.
- **Base ref divergence.** The attempt started from commit
  `10f9285` (pre-Bug-G). By the time I wanted to promote, main had
  advanced past that point via plain git commits. In a longer-running
  harness session this will happen routinely — a rebase / reconcile
  story is needed, though v1 can ship without it.

## Next Targets

Ranked by expected blast radius on a real agent integration:

1. **Decide the agent_id placeholder story** — either accept
   `--agent-id` on `ait attempt new`, or make it `NULL` until the first
   `attempt_started` event arrives. Current `"codex:main"` default is
   misleading for non-codex harnesses.
2. **Add a `--promote-to-branch` flag variant that errors louder** when
   the target would be the current HEAD and the tree is dirty — current
   error message is accurate but users will hit it blind.
3. **Sort out base ref drift** — attempts that outlive several main
   commits should have a cheap way to rebase onto current main before
   promote. Today this means manual `git rebase` inside the worktree.
4. **Claude Code hook config** that auto-wraps a session in an ait
   attempt + stream. This converts the manual harness into automatic
   provenance and is the next logical step once the friction above is
   addressed.

## Evidence Artifacts

- Test attempt: `01KPYYXS6VGGX295D8H5NR712B`
  - reported_status=finished, verified_status=succeeded
  - 4 tool_events accumulated correctly
  - evidence_files: 2 read, 1 touched
  - Commit `b2cb25e1b320d31445c203dcdef01c456f05d3b0` landed via
    `ait attempt commit` with trailers.
- Harness module: `src/ait/harness.py` (commit `d398319`)
- Bug G fix: `src/ait/events.py` (commit `e65f6a4`)
- Demo: `examples/harness_demo.py` (this commit)
