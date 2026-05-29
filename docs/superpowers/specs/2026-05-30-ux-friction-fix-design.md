# UX Friction Fix — First-Hour Abandonment

Date: 2026-05-30
Scope: address the first-hour UX collapse observed when a senior engineer
ran `claude` against a multi-month handoff and AIT silently auto-wrapped
the shell. Seven mission points; three P0 fixes for 1.6.2, three P1 fixes
for 1.7.0, five P2 polish items.

## Diagnosis (root cause at design-philosophy level)

**AIT does the right thing (auto-wrap a `claude` invocation into an
attempt workspace for high-stakes work) but refuses to explain itself.**

Auto-wrap is correct for AIT's named value-proposition use cases (see
§ Use-case classes). The friction is not the wrap. The friction is that
every UI affordance that should install the matching mental model for a
first-time user is broken:

| Observation | Design-philosophy failure |
|---|---|
| **O1 — Silent wrap collision** | No visible signal on session entry. User keeps their plain-git mental model (handoff said `git checkout -b design/foo`), tries it inside an attempt workspace's detached HEAD, stops half a turn to reconcile. |
| **O2 — `status` vs `whereami` contradict** | Two reporters of the same state give two different facts. User cannot trust the tool to know its own state. First-impression interpretation: "I should re-init." |
| **O3 — `command not found: _ait_continue_should_cd`** | A pre-command zsh warning on every `ait` invocation. Functionally inert; emotionally fatal. First-time user infers "broken install" and closes the tab. |
| **O4 — Phantom bypass verb** | `ait status` reports `Bypass detection: wrapped` — implying an alternative state exists. No `ait --help`, `ait status --help`, or README documents a bypass mechanism. Contract broken. |

The pattern: **magic that won't explain itself.** AIT decides to wrap,
then either lies about it (O2), prints a scary error on top of it (O3),
hides the escape (O4), or doesn't acknowledge it (O1). This is the most
costly anti-pattern for first-time users.

## Use-case classes (committed)

The wrap is the right delivery mechanism **only** for the classes below.
For the rest, wrap is pure overhead and must be cheap to opt out of.

### Wrap-required (attempt isolation + reviewer pass pay off)

| Class | Trigger |
|---|---|
| **A1. Slice implementation** | ≥5 files OR cross-module refactor / new feature |
| **A2. Schema / data migration** | DB schema change, migration, production data shape |
| **A3. Security-sensitive change** | auth / crypto / secret handling / payment / RBAC |
| **A4. Performance-critical change** | hot path / inner loop / perf-budget-tested code |
| **A5. API surface change** | public API / RPC contract / persisted format |

Common: subtle wrong has severe consequences; cross-file coherence is
hard to eyeball; reviewer adds value beyond eyeball; multi-attempt
comparison matters.

### Wrap-overhead (pure tax)

| Class | Trigger |
|---|---|
| **B1. Doc / prose writing** | README / design notes / CHANGELOG / inline comments |
| **B2. Exploration / Q&A** | "show me X", "how does Y work", read-mostly |
| **B3. Single-file isolated fix** | typo / one-line bugfix in non-critical path |
| **B4. Config / scaffolding tweak** | dependency bump / CI config / formatter rules |
| **B5. One-off scratch** | throwaway script / benchmark code / experiment |

Common: obvious wrong is eyeball-visible; reversible via `git revert`;
reviewer offers no value beyond a senior engineer's own first pass.

### Mapping to CLI actions

```
A1–A5  (high stakes)       → just `claude ...` — auto-wrap, attempt, review
B1     (docs)              → `claude ...` — auto-wrap, but review auto-skipped (§6)
                             OR `ait off` for full bypass
B2 / B5 (explore / scratch) → `ait off`  OR  `AIT_BYPASS=1 claude ...`
B3 / B4 (single-fix / config) → user judgement; wrap default stays for safety
```

## Wrapper attachment model (decision)

**Keep auto-wrap as default. Add visibility + first-class bypass.**

Rejected alternatives:

| Option | Rejected because |
|---|---|
| Explicit `ait run …` only | High friction for power users; loses the IDE-alias magic that makes AIT work without conscious activation |
| Mode toggle (`ait mode on/off`) without auto-wrap | Same as above, plus an extra concept to learn |
| Per-session interactive prompt at entry | Hostile to users who *want* the wrap; doubles input cost |
| Auto-detect by work type | Heuristic-driven default behavior is brittle and surprising. Better to wrap and let users opt out per-task |

Position: silent wrap was the worst of both worlds (invisible *and*
unavoidable). The fix is to keep wrap-by-default, but make it
**impossible to miss** (banner) and **trivial to escape per-task**
(`ait off` / `AIT_BYPASS=1`).

## Unified state model

A single resolver feeds all four state surfaces (banner, `status`,
`whereami`, `doctor`):

```
┌─────────────────────────────────────────────────────────────┐
│              resolve_ait_context(cwd) → AitContext          │
│                      worktree-aware                         │
│                                                             │
│   ┌──────────┐    ┌──────────┐    ┌────────────────┐        │
│   │ Install  │    │   Repo   │    │   Workspace    │        │
│   │ ait on   │    │ .ait/    │    │ inside         │        │
│   │ PATH?    │    │ init'd?  │    │ attempt-XXX?   │        │
│   │ version  │    │ daemon?  │    │ attempt id     │        │
│   │ wrapper  │    │ memory   │    │ HEAD/target    │        │
│   │ helpers  │    │ attempts │    │ dirty?         │        │
│   └────┬─────┘    └────┬─────┘    └───────┬────────┘        │
│        └──────────┬────┴──────────────────┘                 │
│                   ↓                                         │
│        ┌──────────┴───────────┐                             │
│        │                      │                             │
│   ait status              ait whereami                      │
│   (3-layer condensed)     (workspace only,                  │
│                            cross-ref status                 │
│                            in one line)                     │
└─────────────────────────────────────────────────────────────┘
```

Worktree-aware means: when `cwd` is inside `.ait/workspaces/attempt-X/`,
the resolver finds the host repo at the parent and reports the AIT
context from the host's perspective. **No more "not_initialized" from
inside an attempt.**

## Install invariant

```
INVARIANT: the ait binary must never make an unconditional call to a
           shell helper function. Every call site must `command -v
           <helper>` guard.
```

Documented in the module docstring of `src/ait/shell_integration.py`.
First violation reproduced in O3.

## Right-size review

`ait run` and `ait apply` both get a `--review` flag with three modes:

```
ait run [OPTIONS] <agent>

  --review MODE   auto    (default) skip when 100% of changed files
                          match the docs glob set, else run review
                  never   skip review unconditionally
                  always  force review even for docs-only changes
```

Default docs glob set (override via `.ait/config.json` `[review]
auto_skip_globs`):

```
**/*.md
**/*.rst
**/*.txt
docs/**
site-docs/**
LICENSE*
CHANGELOG*
README*
```

Rejected: `ait apply --mode design` as a new verb. Its three implied
semantics ("no review, no isolation tax, just land") are an incoherent
bundle — "no isolation" + "apply" contradict each other. Compose
existing primitives instead:

```
# Doc-writing, full bypass
$ ait off
$ claude ...                        # direct, no AIT involvement

# Attempt flow but skip review for this run
$ ait run --review never claude ...

# Apply an existing attempt without running reviewer
$ ait apply latest --review never
```

## Banner (concrete output)

Printed to stderr at attempt session entry, before exec'ing the wrapped
agent binary. Skip when stderr is not a TTY OR `AIT_NO_BANNER=1`.

```
┌─ AIT attempt 01HZX9TYE ──────────────────────────────
│ workspace: .ait/workspaces/attempt-0001-01HZX9TYE
│ HEAD: detached · target: main
│ Commits land on `main` only after you run `ait apply`.
│ Not wrapped? Exit, then `ait off` (this shell) or
│ `AIT_BYPASS=1 claude …` (one-shot).
└──────────────────────────────────────────────────────
```

Width fixed at 60 chars. Box drawing characters; no emoji. Colour only
when `isatty(stderr)` — box dim grey, `detached` yellow, backticked
code bold. ANSI absent in pipes / CI.

## Bypass mechanisms

Two entries, no more:

```
# Per-invocation (one-shot)
$ AIT_BYPASS=1 claude "quick question"

# Per-shell session (verb)
$ ait off
AIT auto-wrap disabled for this shell.
Run `ait on` to re-enable.

$ ait on
AIT auto-wrap re-enabled for this shell.
```

`ait off` is essentially `export AIT_BYPASS=1` plus the acknowledgement
line. `ait on` is `unset AIT_BYPASS`. Both must be `eval`'d by the
caller's shell — the binary alone cannot mutate parent shell state, so
the `ait` shell function (see `shell_integration.py`) intercepts these
verbs and emits the eval-able script.

Permanent per-repo or per-machine disable (use cases C/D from the
discussion) is **out of scope** for this spec — covered separately by
`ait uninstall` and `ait disable` if ever designed.

## `ait status` redesigned output

### Inside attempt (after fix)

```
AIT 1.6.0 · pipx · /Users/michael/.local/bin/ait

Repo /Users/michael/products/<repo>
  initialized   yes
  daemon        running (pid 12345)
  memory        ok (0 lint issues)
  attempts      3 active, 12 archived

Workspace ⟶  attempt 01HZX9TYE (you are here)
  target        main
  HEAD          detached
  dirty         yes (.ait-context.md.manifest.json)

Wrap behavior
  current        wrapped (claude in this shell enters AIT)
  disable once   AIT_BYPASS=1 claude ...
  disable shell  ait off    (re-enable: ait on)

OK
```

### Outside attempt (primary checkout)

```
AIT 1.6.0 · pipx · /Users/michael/.local/bin/ait

Repo /Users/michael/products/<repo>
  initialized   yes
  daemon        running (pid 12345)
  memory        ok (0 lint issues)
  attempts      3 active, 12 archived

Workspace ⟶  primary checkout (no active attempt)
  next          run `claude` to enter an attempt

Wrap behavior
  current        wrapped (claude in this shell enters AIT)
  disable once   AIT_BYPASS=1 claude ...
  disable shell  ait off    (re-enable: ait on)

OK
```

### `--verbose`

Existing 30+ line dump preserved as `ait status --verbose` (alias `-v`)
for troubleshooting. `ait doctor` shells out to verbose status by
default.

## `ait whereami` redesigned output

### Inside attempt

```
Inside AIT attempt 01HZX9TYE
  target     main
  HEAD       detached
  dirty      yes (1 file)
  workspace  .ait/workspaces/attempt-0001-01HZX9TYE
  repo       /Users/michael/products/<repo>
```

### Outside attempt

```
Not in an AIT attempt.
  repo: /Users/michael/products/<repo> (primary checkout)
```

Exit code is **0** in both cases. `whereami` reports a fact; not being
in an attempt is not an error.

## `ait doctor` shell-integration probe

When `ait` is on PATH but the wrapper is half-installed:

```
Shell integration
  ait() wrapper:           defined
  _ait_continue_should_cd: MISSING ❌
  _ait_continue_reminder:  MISSING ❌
  fix: eval "$(ait shell init)"
       or: ait shell install --rc ~/.zshrc
```

`ait doctor` **never** auto-modifies the user's rc files. Probe and
recommend; the user runs the fix.

## Prioritization

Decision criterion: **what stops a new user from abandoning AIT in the
first hour and from filing an issue saying it's broken.**

### P0 — first-hour abandonment fixes (shipped: 1.7.0)

| # | Item | Why P0 | Effort | Shipped |
|---|---|---|---|---|
| P0.1 | `command -v` guards around shell-integration helper calls (O3) | Most direct "broken install" signal a new user can see | ~1h | ✅ `9103e38` |
| P0.2 | Worktree-aware root resolver wired into `ait status` (O2) | Second-largest "I should re-init" misdirection | ~half day | ✅ `dd0b8de` |
| P0.3 | Banner on attempt session entry (O1) | Closes the half-conversation reconciliation cost | ~half day | ✅ `74258f2` |

**Total**: ~1.5 engineering days. Rolled into 1.7.0 instead of a
standalone 1.6.2 patch.

#### Release-note one-liners (per item)

```
P0.1  fix(shell): guard shell-integration helper calls with `command -v`;
      no more `_ait_continue_should_cd: command not found` warning on
      every `ait` invocation.

P0.2  fix(status): `ait status` is now worktree-aware. From inside
      `.ait/workspaces/attempt-*` it correctly reports the host repo's
      AIT state instead of "not_initialized".

P0.3  feat(ui): print a 4-line box-drawing banner on attempt session
      entry (stderr, TTY-only) showing attempt id, workspace path,
      HEAD/target, and the `ait apply` path to land commits.
```

### P1 — first-day issue-filing fixes (shipped: 1.7.0)

| # | Item | Why P1 | Shipped |
|---|---|---|---|
| P1.1 | Two bypass entries: `AIT_BYPASS=1` env + `ait off`/`on` verbs; `ait --help` first-class; `Wrap behavior` section in `ait status` (O4) | Closes the phantom-verb contract break | ✅ `577f339` |
| P1.2 | Docs-only auto-skip review + `--review` flag on `run` (§6) | Stops reviewer running on README changes — would otherwise feel like a broken tool | ✅ `bf82e90` (apply-side flag deferred — apply doesn't trigger review) |
| P1.3 | Banner gains 5th line documenting `ait off` and `AIT_BYPASS=1` | Composes P0.3 + P1.1 into one complete entry-time signal | ✅ `3377800` |

**Total**: ~1 engineering day.

### P2 — first-week polish (shipped: 1.7.0)

| # | Item | Shipped |
|---|---|---|
| P2.1 | `ait status` condensed default (~17 lines); `--verbose` preserves 30+ line dump | ✅ `fb71870` |
| P2.2 | `ait whereami` redesigned (6-line / 2-line, exit 0 in/out) | ✅ `e707aa2` |
| P2.3 | `ait doctor` shell-integration probe; reports + recommends, never auto-modifies rc | ✅ `62397aa` |
| P2.4 | `.ait/config.json` `[review].auto_skip_globs` override | ✅ shipped as part of `bf82e90` (P1.2) |
| P2.5 | Install invariant documented in `src/ait/shell_integration.py` module docstring | ✅ shipped as part of `9103e38` (P0.1) |

**Total**: ~1-2 engineering days, batched into 1.7.0.

## Non-goals (this spec)

- Removing or changing auto-wrap default behavior (the value
  proposition validation in § Use-case classes commits to keeping it).
- Per-repo or per-machine permanent disable (use cases C/D from the
  discussion). Separate work.
- Auto-detection of work type to switch wrap default. Heuristic-driven
  defaults are brittle; explicit opt-out is the right primitive.
- Replacing `ait continue` shell auto-cd integration. The defensive
  guard (P0.1) makes the existing integration robust; whether the
  integration is worth keeping is a separate decision.
- Windows shell-integration parity (current scope: zsh + bash).

## References

- `src/ait/shell_integration.py` — site of P0.1 guard + invariant docstring
- `src/ait/cli/status.py` (or wherever `ait status` lives) — site of P0.2 resolver wiring
- `src/ait/cli/run.py`, `src/ait/cli/apply.py` — `--review` flag wiring (P1.2)
- `src/ait/review_policy.py` — docs-glob detector (P1.2)
- `tests/conftest.py` — `AIT_BUG_REPORT=never` precedent for `AIT_NO_BANNER`
  and `AIT_BYPASS` env handling
- `memory/feedback_no_github_cicd_runs.md` — interacts with the release
  cadence below
- `docs/release-checklist.md` — must learn about the new `--review`
  flags and banner before tagging 1.6.2 / 1.7.0
