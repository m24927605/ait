# Dogfood Session 1

Date: 2026-04-24

Goal: exercise the full v1 lifecycle (`init` → `intent new` → `attempt new` →
edit in worktree → `attempt commit` → `attempt promote` → `intent show` →
`blame`) on a real small change, and capture every friction point.

The change used as the vehicle: document `intent_edges.edge_type` enum values
in `docs/implementation-notes.md` (the Finding #11 doc fix from
`docs/ai-vcs-mvp-spec.md` round-3 review).

## What Worked

- `ait init` created `.ait/`, config, SQLite state, `.gitignore` entry, and
  installed the `post-rewrite` hook. One command, clean output.
- `ait intent new` persisted the intent and returned a JSON object with a
  stable `intent_id`.
- `ait attempt new <intent-id>` provisioned a detached worktree under
  `.ait/workspaces/attempt-0001-<slug>/` and returned `attempt_id`,
  `workspace_ref`, `base_ref_oid`, `ownership_token`.
- Edits made in the worktree stayed isolated from the main working tree.
- `ait attempt commit -m "..."` created a git commit with correctly-formatted
  trailers:
  ```
  Intent-Id: <intent-id>
  Attempt-Id: <attempt-id>
  ```
- `ait attempt promote --to main` updated `refs/heads/main` to the worktree
  HEAD and moved `verified_status` to `promoted`.
- Intent status auto-advanced to `finished` via forward-only refresh.
- `ait blame docs/implementation-notes.md` returned the attempt and commit
  that last touched the file, joined through indexed metadata (no full git
  log scan).
- `ait intent show <intent-id>` returned a useful aggregate: intent, attempts,
  evidence summary stub, changed files, linked commits.

## Real Bugs Found

### Bug A (high): `ait` invoked from within a worktree crashes

Reproduction: run any `ait` command with `cwd` inside
`.ait/workspaces/attempt-*/`. Example traceback:

```
File ".../src/ait/hooks.py", line 25, in install_post_rewrite_hook
    hooks_dir.mkdir(parents=True, exist_ok=True)
NotADirectoryError: [Errno 20] Not a directory:
'.ait/workspaces/attempt-0001-.../.git/hooks'
```

Root cause: inside a git worktree, `.git` is a file (pointing to
`<main>/.git/worktrees/<name>`), not a directory. `_resolve_hooks_dir` in
`src/ait/hooks.py:56` falls back to `repo_root / ".git" / "hooks"`, which is
an invalid path in a worktree.

Impact: any harness that invokes `ait` from inside the attempt workspace
(which is the natural place for an agent to run) will hard-fail on the first
call. This is a day-one blocker for the agent-integration story.

Fix direction: use `git rev-parse --git-path hooks` to get the correct hooks
directory in both a normal checkout and a worktree. Falls back to
`<main>/.git/hooks` for worktrees without customisation.

### Bug B (medium): `attempt promote --to <currently-checked-out-branch>` leaves working tree out of sync

Reproduction: promote an attempt to the branch that is currently checked
out in the main repo. `git update-ref` moves the branch head forward, but
the working tree and index are not touched.

After the promote:

```
$ git status
On branch main
Changes to be committed:
    modified: docs/implementation-notes.md  # diff shows the inverse of the new commit
```

This is the classic symptom of a branch ref that jumped forward while the
working tree stayed behind.

Fix direction, in order of preference:

1. Detect when `target_ref` matches `HEAD` and run `git reset --keep` (or
   `merge --ff-only`) so the working tree follows forward.
2. Refuse to promote onto the currently-checked-out branch and require the
   user to switch to another branch first.
3. Print a clear warning suggesting `git reset --hard <ref>` and document the
   limitation in `implementation-notes.md`.

### Friction C (medium): 100-character object IDs are painful

The fully-qualified intent/attempt ID is `<root_commit_oid>:<install_nonce>:<ulid>`
= 40 + 32 + 26 + 2 separators = 100 characters. Copy-pasting this by hand is
unworkable. For this session, every command after `intent new` required
careful ID handling.

Fix direction: allow a short-form suffix (last 8–12 characters of the ULID)
as input to any command that takes an intent_id / attempt_id. The repo_id
prefix is implied by the current repo. Disambiguate on collision.

### Bug D (high): ait spawns a split-brain `.ait/` store when invoked from inside a worktree

**Surfaced** while verifying the Bug A fix: after the hook installer
was fixed, running `ait intent new ...` from inside the attempt
worktree created an intent with a fresh `repo_id` (new `install_nonce`)
rather than using the main repo's existing store.

**Root cause:** `resolve_repo_root` (`src/ait/repo.py`) used
`git rev-parse --show-toplevel`, which returns the worktree path, not
the main repo. Every `ait` invocation from a worktree therefore spun
up a parallel `.ait/` store inside the worktree, split-brain with the
canonical one.

**Resolution:** switched to `git rev-parse --path-format=absolute
--git-common-dir` and took the parent of that directory. Works
identically for a normal checkout (`--git-common-dir` returns `.git`)
and a worktree (returns `<main>/.git/`). Landed in commit `709af54`.

### Bug E (medium): `ait intent list` with no filter crashes on empty query

**Surfaced** while verifying the Bug D fix: `ait intent list` (no
`--status` / `--kind` / `--tag` flags) raised
`QueryError("query expression must not be empty")`.

**Root cause:** `list_shortcut_expression` in `src/ait/query.py`
returns `""` when none of the filter flags are set, and
`compile_query` fed that to the parser, which rejects empty input.

**Resolution:** `compile_query` now treats `None` / empty / whitespace
expressions as "no filter" and emits `SELECT ... WHERE 1=1 ...`. The
DSL parser still rejects malformed non-empty expressions. Landed in
commit `312bd5d`.

### Friction D (low): no `ait` binary on Homebrew Python

`pip install -e .` on Homebrew's Python fails with PEP 668
"externally-managed-environment". For this session the CLI was invoked via
`PYTHONPATH=src python3 -m ait.cli <args>`, which is fine for tests but not
for user-facing adoption.

Fix direction: add a short README section on creating a venv
(`python3 -m venv .venv && .venv/bin/pip install -e .`), or provide a
`bin/ait` wrapper script that prepends `PYTHONPATH` automatically.

## Observations That Are Not Bugs But Are Interesting

- The daemon was not needed for this session because the flow used only
  lifecycle CLI calls. `tool_event` ingestion (the real agent path) was not
  exercised. That is the natural next target.
- `evidence_summary.observed.*` counters are all zero after a CLI-only flow.
  This is expected: no `tool_event` was emitted. But it means intent-level
  metrics like `ait query 'observed.tool_calls>0'` return nothing for
  CLI-driven work. If we want this metric to cover CLI-only work too, the
  `ait attempt commit` path could synthesise a minimal `tool_event`
  equivalent from its own actions.
- `agent_id` was recorded as `codex:main` (the hard-coded default from
  `src/ait/app.py`). This matches review Finding #10 and is still unfixed.
- `workspace_ref` is an absolute path. Portable across invocations on the
  same machine, but not portable across machines or container bind mounts.
  Not a v1 concern but worth flagging for v2 cross-machine sync.

## Next Targets

Ranked by what unblocks the next dogfood pass.

1. **Fix Bug A** (`.git` file vs. directory in worktrees). Small change in
   `src/ait/hooks.py`, probably 5 lines plus a regression test. Without
   this, an AI agent running inside the attempt workspace cannot call any
   `ait` command.
2. **Add a thin `bin/ait` launcher** so the CLI is usable without venv
   gymnastics. Even without PEP 668 fix, a shell stub that does
   `PYTHONPATH=<ait>/src exec python3 -m ait.cli "$@"` is enough.
3. **Short-form ID resolution** for `intent_id` / `attempt_id` arguments in
   the CLI. Every other dogfood cycle will trip over this otherwise.
4. **Dogfood cycle 2 — with the daemon and a real `tool_event` stream.**
   Write a minimal Python harness that opens the daemon socket, sends
   `attempt_started`, streams `tool_event` for each file read/write, then
   `attempt_finished`. Run it against a real small fix. This exercises the
   still-untested high-frequency code path.
5. **Document the working-tree-stale behaviour after promote** in
   `implementation-notes.md` even before the proper fix ships, so users are
   not surprised.

Decision on which of the above to do next will be driven by the user, but
the ordering reflects the blast radius: Bug A is the only thing that is
strictly a blocker for the dogfood loop itself.
