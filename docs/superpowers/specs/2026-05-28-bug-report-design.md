# AIT Bug Report Feature Design

Date: 2026-05-28
Scope: opt-in feature that lets AIT users report bugs **in AIT itself** to
`github.com/m24927605/ait/issues`, triggered automatically on internal failures
or manually via `ait bug-report`.

## Scope Statement

This feature reports **bugs in AIT (the tool) itself** — daemon protocol
errors, DB failures, hook install failures, reconcile errors, verifier
crashes, and so on.

It is **not** for:

- Bugs in the user's own codebase.
- Unexpected output from AI agents that AIT runs.
- Feedback about AI-agent quality.

The scope statement is repeated verbatim at every user-facing entry point
(crash prompt, `ait bug-report` wizard, `ait config bug-report --help`) so the
user cannot misunderstand what they are submitting.

## Problem

When AIT crashes or hits an internal error, the user sees a Python traceback
or a swallowed `print(..., file=sys.stderr)` warning. There is no path from
that observation to a GitHub issue except manual copy-paste, which depends on
the user being motivated, knowing the repo URL, and having a GitHub account
configured. As a result, real AIT bugs are systematically under-reported,
especially the ones that are caught and silenced internally.

## Goal

A single, opt-in mechanism that:

1. Detects AIT internal failures (both uncaught and known-caught).
2. With user consent, packages a redacted, reviewable report.
3. Submits to `github.com/m24927605/ait/issues` either via the GitHub CLI
   (`gh`) or by opening a pre-filled `issues/new` URL in the user's browser.
4. Deduplicates so users are not spammed across repeated runs of the same bug.
5. Survives offline / submission failures by queueing for later replay.
6. Never blocks or breaks the main CLI flow if anything inside the bug-report
   path itself fails.

## Non-goals (this change)

- Hosting an AIT-operated backend, telemetry server, or proxy.
- Bundling a GitHub PAT inside the AIT distribution.
- Reporting bugs in the user's project or in AI agents' outputs.
- Crash analytics dashboards, aggregation, or anonymous metrics.
- Auto-submission without per-report user review (every send requires
  explicit confirmation of contents).

## Design

### Architecture and file layout

A new `bug_report/` package under `src/ait/`, plus a `cli/bug_report.py`
subcommand entry point:

```
src/ait/
  bug_report/
    __init__.py
    api.py             # public surface: install_excepthook, report_internal_error, flush_at_exit
    config.py          # global XDG preference read/write
    collector.py       # process-local error accumulator
    fingerprint.py     # SHA256-based error fingerprint
    redactor.py        # thin layer atop existing src/ait/redaction.py
    builder.py         # issue title/body composition
    submitter.py       # gh-CLI detection, URL fallback, pending queue
    excepthook.py      # sys.excepthook chain installer
    seen_store.py      # ~/.local/state/ait/bug_reports/seen.json read/write
    pending_queue.py   # ~/.local/state/ait/bug_reports/pending/* read/write
  cli/
    bug_report.py      # `ait bug-report` subcommand
```

Public API consumed by the rest of AIT:

```python
from ait.bug_report.api import (
    install_excepthook,    # cli/main.py startup, once
    report_internal_error, # Layer-2 instrumented sites
    flush_at_exit,         # cli/main.py atexit registration
)
```

`bug_report` depends on stdlib only (`urllib.request`, `subprocess`,
`hashlib`, `json`, `pathlib`, `os`, `sys`, `atexit`, `webbrowser`). No new
runtime dependencies (CLAUDE.md mandate).

### Storage layout (XDG-compliant)

```
~/.config/ait/config.json                              # preferences
~/.local/state/ait/bug_reports/seen.json               # fingerprint dedup state
~/.local/state/ait/bug_reports/pending/<fp>.json       # unsent drafts
~/.local/state/ait/bug_reports/internal_errors.log     # bug_report's own faults
```

Paths honor `XDG_CONFIG_HOME` and `XDG_STATE_HOME` env overrides. All disk
writes use atomic write (sibling of `config._write_text_atomic`).

### Global preference schema

`~/.config/ait/config.json`:

```json
{
  "schema_version": 1,
  "bug_report": {
    "mode": "unset",
    "first_setup_at": null,
    "last_prompted_at": null,
    "include_tier2": true,
    "include_tier3": false
  }
}
```

`mode` states:

| Value      | Behavior                                                                                   |
|------------|--------------------------------------------------------------------------------------------|
| `unset`    | Never asked. Next crash triggers the first-time setup dialog before any reporting flow.    |
| `ask`      | Default after first-time setup. Each (deduplicated) error triggers a prompt.               |
| `always`   | Skip the "report?" prompt, but still require explicit confirmation of contents.            |
| `never`    | Feature fully disabled. `install_excepthook` becomes a no-op.                              |

Escape hatches:

- `AIT_BUG_REPORT=never` env var forces disable regardless of stored mode
  (intended for CI and enterprise environments).
- `ait config bug-report <mode>` flips the stored mode any time.

### Trigger surface

**Layer 1 — `sys.excepthook` catch-all.**

`install_excepthook` is called as the first line of `ait.cli.main.main()`.
It chains: save the previous hook, install a new hook that calls
`collector.record(...)` then delegates to the previous hook so the existing
traceback output is preserved bit-for-bit.

Skip list (never recorded):

- `KeyboardInterrupt`
- `SystemExit`
- `BrokenPipeError`
- Any exception whose `__module__` does not start with `ait.` (covers
  third-party crashes from agents AIT spawned)

If `mode == "never"` (incl. env override), `install_excepthook` is a no-op
and skips the `ait.bug_report.*` imports entirely to keep cold-start cost
near zero.

**Layer 2 — explicit instrumentation.**

```python
def report_internal_error(
    *,
    category: str,
    exc: BaseException,
    context: dict | None = None,
    user_facing: str | None = None,
) -> None:
    """Accumulate to the process-local collector. Never raises, never blocks."""
```

Initial instrumented sites (8):

| # | Location                            | Category                       |
|---|-------------------------------------|--------------------------------|
| 1 | `daemon_transport.py:36`            | `daemon.protocol.transport`    |
| 2 | `daemon.py:197`                     | `daemon.protocol.main`         |
| 3 | `db/core.py:52`                     | `db.operational`               |
| 4 | `events.py:455`                     | `events.txn_rollback`          |
| 5 | `runner.py:477`                     | `memory.note_write`            |
| 6 | `hooks.py` (hook install failure)   | `hooks.install`                |
| 7 | `reconcile.py` (post-rewrite fail)  | `reconcile.post_rewrite`       |
| 8 | `verifier.py` (verification crash)  | `verifier.crash`               |

Each call site uses the existing `except` block; we add one call and leave
the surrounding behavior (swallow, log, re-raise) unchanged.

**Collector.**

A module-level single instance in `collector.py`:

- Stores up to 20 entries per process. Excess entries are dropped (FIFO),
  with a single internal marker recorded so the report says "+N more
  truncated".
- Each entry: `(category, exc_type, exc_message, traceback_frames,
  context, fingerprint, recorded_at)`.
- Same fingerprint counted as a single "occurrence" with a `count` field.

### Consent model: two tiers

**Tier A — global preference (`mode`)** decides whether the user is even
asked. See the preference schema above.

**Tier B — per-report review** is mandatory regardless of `mode`. Even
`mode == "always"` only suppresses the "would you like to report?" question;
it does **not** suppress the "here is the exact content, send it?" review
screen. There is no path that sends data without an explicit user keystroke
on the review screen.

### Data tiers

Tier 1 (always included):

- AIT version (`ait --version`)
- Python version, OS, architecture
- Stack traces, redacted with `$HOME → ~`
- The `argv` of the running `ait` command, with values for `--api-key`,
  `--token`, `--password` stripped
- ISO-8601 timestamp of the crash

Tier 2 (default on, opt-out via `--no-include-tier2` or config):

- `install_nonce` (random per-install identifier, not user identity)
- Daemon log tail (last 20 lines) passed through the redactor
- Daemon state (running / down / unreachable)
- Current AIT sub-command and phase

Tier 3 (opt-in via review-screen checkbox, default off):

- Environment-variable whitelist: `PATH`, `EDITOR`, and any `AIT_*` var
  (other env vars are never included)

Explicit-flag only (NOT in any menu or checkbox):

- **Transcripts / attempt prompts** — only via `ait bug-report --attempt <id>`.
  When `--attempt` is passed, the review screen shows a red-banner warning
  and requires a **second** explicit confirmation keystroke beyond the
  normal `[s] send`.
- **`repo_id`** — only via `ait bug-report --include-repo-id`. Same
  double-confirm flow.

Rationale: transcripts and `repo_id` reveal the user's project rather than
AIT internals. They are useful for a narrow class of AIT bugs but pose
disproportionate privacy risk. Moving them out of the default checklist
prevents accidental inclusion via casual checkbox selection.

### Redaction

Calls into existing `src/ait/redaction.py`, then layers four additional
substitutions:

1. `$HOME` → `~`
2. Token-like strings matching `gh[ps]_[A-Za-z0-9]{30,}`, `sk-[A-Za-z0-9]{20,}`,
   `ghp_[A-Za-z0-9]{30,}` → `[REDACTED_TOKEN]`
3. Email addresses → `[REDACTED_EMAIL]`
4. `argv` values after `--api-key`, `--token`, `--password` (both
   space-separated `--api-key foo` and `=`-joined `--api-key=foo` forms) →
   `[REDACTED]`

The redactor is **best-effort**, not a guarantee. The mandatory review
screen is the final defense against leaks.

### Submission flow

```python
def submit(title, body) -> SubmitResult:
    # 1. Prefer `gh` if installed and authenticated
    if which("gh") and gh_auth_ok():
        try:
            r = subprocess.run(
                ["gh", "issue", "create",
                 "--repo", "m24927605/ait",
                 "--title", title,
                 "--body-file", "-"],
                input=body, capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                return SubmitResult.ok(method="gh", issue_url=r.stdout.strip())
        except (subprocess.TimeoutExpired, OSError):
            pass

    # 2. Open a pre-filled URL in the browser
    url = build_prefill_url(title, body)
    if len(url) <= 7000 and open_browser(url):
        return SubmitResult.ok(method="url", issue_url=None)

    # 3. Defer to pending queue
    return SubmitResult.deferred(reason="body_too_long_or_no_browser")
```

`gh_auth_ok()` runs `gh auth status` and checks exit code 0 **and** absence
of "not logged in" in stderr.

If the body exceeds the practical URL ceiling (~7KB), the report is written
to `~/.local/state/ait/bug_reports/pending/<fp>.json` and the user is told
how to send it later (`ait bug-report --replay <fp>` or open the file
manually).

### Fingerprinting

```python
def fingerprint(exc_type: str, traceback_frames: list[Frame]) -> str:
    # Take top-3 frames (deepest call site first).
    # Per frame: (basename(file), function_name) — no line numbers.
    parts = [exc_type]
    for f in traceback_frames[:3]:
        parts.append(f"{os.path.basename(f.filename)}:{f.function}")
    return "fp:" + hashlib.sha256("\n".join(parts).encode()).hexdigest()[:8]
```

Deliberately excludes:

- AIT version — same bug across versions stays one fingerprint
- Line numbers — minor code edits don't shatter dedup

### Dedup decision table

| State                                                    | Behavior                                                      |
|----------------------------------------------------------|---------------------------------------------------------------|
| fp not in `seen.json`                                    | Prompt (mode=ask) / auto-review (mode=always)                 |
| fp seen, not submitted, last_seen < 7d ago               | Silent. Update `count` and `last_seen_at` only                |
| fp seen, not submitted, last_seen ≥ 7d ago               | Re-prompt: "Saw this last week, ready to send now?"           |
| fp submitted, issue state = open                         | Silent. Update `count`                                        |
| fp submitted, issue state = closed/locked                | Prompt: "Reported before but issue is closed — regression?"   |
| fp submitted, issue state unknown (`gh` unavailable)     | Silent (conservative: assume still open)                      |

Issue-state lookups via `gh issue view <num> --json state,locked` are cached
for 24 hours in `seen.json` (`last_status_check_at`) to avoid GitHub API
rate limits.

### Per-process hard cap

- Collector keeps at most 20 entries.
- `flush_at_exit` triggers at most **one** user prompt per process,
  regardless of how many distinct fingerprints accumulated.
- `mode=always` auto-sends at most one combined report per process (merging
  all fingerprints into a single issue body).

### TTY / non-interactive behavior

When `sys.stdin` or `sys.stdout` is not a TTY:

- Auto-crash flow: do **not** prompt. Persist collector contents to
  `pending/` and emit one stderr line:

  ```
  ait: 2 internal errors saved to ~/.local/state/ait/bug_reports/pending/
       Run `ait bug-report --replay --all` to send.
  ```

- Manual `ait bug-report` without `--message`: exit with an instructive
  error directing the user to either run in a TTY or pass `--message`.

### CLI surface

`ait bug-report [SUBCOMMAND] [OPTIONS]`:

```
SUBCOMMANDS:
  (none)                      Interactive bug-report wizard
  list                        List pending and recently-seen reports
  replay [FP|--all]           Re-send pending reports
  show <FP>                   Print a pending report body to stdout
  clear [FP|--all]            Delete pending reports without sending

OPTIONS:
  --include-tier2 / --no-include-tier2   Override config for this run
  --include-tier3 / --no-include-tier3   Override config for this run
  --message "<text>"          Free-form user description
  --attempt <id>              Include an attempt's transcript (high-risk)
  --include-repo-id           Include repo_id in the body (high-risk)
  --dry-run                   Build and print the report, don't submit
  --json                      Machine-readable output for agents
```

`ait config bug-report`:

```
ait config bug-report                 Show current settings
ait config bug-report <mode>          ask | always | never
ait config bug-report tier2 on|off    Toggle Tier 2 default
ait config bug-report tier3 on|off    Toggle Tier 3 default
```

### Issue body template

```markdown
> Automatically generated by `ait` v{version}. Reviewed and submitted by the user.
> Reports a bug in **AIT itself** — not the user's code or AI-agent output.

## Summary
{category}: {short error message}

## Environment
- AIT: {version}
- Python: {python_version}
- OS: {os}/{arch}

## Command
```
{argv_redacted}
```

## Stack Trace
```
{traceback_redacted}
```

## Internal Errors (Layer 2)
- [db.operational] disk I/O error  (×3)
- [daemon.protocol.main] invalid envelope  (×1)

## Context  <!-- Tier 2 -->
- Install ID: {install_nonce_short}
- Daemon: running, socket reachable
- Sub-command: `ait run --intent foo`
- Phase: workspace_provision

## Daemon Log Tail (last 20 lines, redacted)  <!-- Tier 2 -->
```
{daemon_log_tail}
```

## Environment Variables  <!-- Tier 3, opt-in -->
- PATH: ...
- EDITOR: vim
- AIT_*: ...

---
Fingerprint: `fp:a1b2c3d4`
```

Title: `[crash] {category} — {short_msg} [fp:a1b2c3d4]`

### Self-safety

Every public function in `ait.bug_report.api` is wrapped:

```python
def _safe(fn):
    @functools.wraps(fn)
    def wrapped(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as exc:
            _log_internal_error(exc)   # writes to internal_errors.log
            return None                # NEVER calls report_internal_error itself
    return wrapped
```

This ensures no failure inside the bug-report path can break the main CLI
flow. `_log_internal_error` deliberately does not call back into the
collector to avoid recursion.

### Review-screen UI

Standard flow (no `--attempt`, no `--include-repo-id`):

```
ait encountered 1 internal error during this run.

  • db.operational  (×3)  [fp:a1b2c3d4]

Send a bug report to help improve AIT?
  [y] yes, review and send
  [n] not now
  [s] not now, and stop asking         (sets mode=never)
  [a] always ask for next time too     (keeps mode=ask)

Choice [y]:

----- Review -----
Title: [crash] db.operational — disk I/O error [fp:a1b2c3d4]
Body:
  ...(full body shown)...
------------------

Extras opt-in:
  [ ] Include Tier 3 (env vars whitelist)

[s] send  [e] edit body in $EDITOR  [x] cancel
Choice [s]:
```

High-risk attachments flow (`--attempt` or `--include-repo-id`):

```
⚠️  This report includes high-risk content:
    • Attempt transcript for 01HZ...
    • Repository ID

    Transcripts contain your project's prompts and outputs.
    Only include if directly relevant to the AIT bug.

Type SEND to confirm (anything else cancels): SEND
```

The literal-string match (`SEND`) is intentional: a single keystroke is too
easy to fat-finger when shipping user code.

## Testing

stdlib `unittest`, files under `tests/bug_report/`:

```
test_fingerprint.py        Same/different trace → same/different fp; <3 frames OK
test_redactor.py           HOME / tokens / emails / argv values all redacted
test_builder.py            Title/body composition; tier inclusion gates
test_config.py             XDG path resolution; schema migration; env override
test_collector.py          20-entry cap; same-fp merge; skip-list (KeyboardInterrupt etc.)
test_submitter_url.py      URL encoding; 7KB threshold; browser injection
test_submitter_gh.py       gh missing / unauth'd / timeout / non-zero exit
test_excepthook.py         Chain preservation; non-ait modules skipped
test_seen_store.py         Decision-table coverage; 7-day re-prompt; 24h status cache
test_pending_queue.py      Round-trip; replay; 30-day cleanup
test_cli_bug_report.py     argparse; manual wizard with injected stdin
test_cli_config_bug_report.py
test_end_to_end_flow.py    record → flush → submit (all subprocess + browser mocked)
test_self_safety.py        Forcing exceptions inside bug_report does not break main flow
```

All tests inject:

- `XDG_CONFIG_HOME` and `XDG_STATE_HOME` pointing into `tmpdir`
- A fake `subprocess.run` so `gh` is never actually called
- A fake `browser_opener` callable so no browser opens
- A fake clock for deterministic timestamps
- `sys.stdin` via `io.StringIO` for prompt scripting

### Manual acceptance checks

1. `pip install -e .` then `ait init`. Force a daemon protocol error.
   Confirm the prompt appears, type `y`, confirm `gh` opens an issue at
   `github.com/m24927605/ait/issues`.
2. Uninstall `gh`. Repeat (1). Confirm a browser opens with a pre-filled
   `issues/new` URL.
3. Force a 50 KB report body. Confirm the report lands in
   `~/.local/state/ait/bug_reports/pending/` and `ait bug-report --replay --all`
   ships it once `gh` is reinstalled.
4. `AIT_BUG_REPORT=never ait run ...`. Force an error. Confirm no prompt,
   no IO, no `bug_report` imports loaded.
5. `mode=always`. Force three identical crashes. Confirm first auto-sends
   one combined issue, next two are silent dedup updates.
6. `ait bug-report --attempt 01HZ...`. Confirm the `SEND` literal-string
   confirmation gate fires and cancelling on any other input does not
   submit.

### Non-functional checks

- `time python -m ait.cli --help` cold-start regression: ≤ 5 ms increase
  with `bug_report` package present, ≤ 0 ms when `mode == "never"`.
- Zero-error fast path: `flush_at_exit` triggers zero syscalls when the
  collector is empty (assert via `strace -c` snapshot in CI on a
  representative `ait status` run).

## Rollout

1. Land the package and tests with `mode=unset` as the global default.
   First-time setup is shown only when the first internal error happens.
2. Hold Layer 2 instrumentation to the 8 sites for the first release. Add
   more in follow-up patches as we learn which silenced-error sites
   actually generate useful reports.
3. After two weeks of dogfooding, audit `internal_errors.log` from
   contributor machines and prune any self-safety failures.

## Open Questions

None at design freeze. The 8 instrumentation sites, default tier inclusions,
and dedup windows are deliberately conservative starting points that can be
relaxed once production data exists.

## References

- `src/ait/redaction.py` — base redaction primitives reused here
- `src/ait/config.py` — `_write_text_atomic` and config-file conventions
- `src/ait/agent_errors.py` — structured error code precedent (`emit_agent_error`)
- `pyproject.toml` — canonical AIT repository URL
- `CLAUDE.md` — stdlib-only mandate; commit checklist
- `docs/ai-vcs-mvp-spec.md` — non-goal context (this is outside spec surface)
