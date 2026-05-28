# Bug-Report Feature Dogfood Notes — 2026-05-28

This document records the outcome of the six manual acceptance checks defined
in `docs/superpowers/specs/2026-05-28-bug-report-design.md` § "Manual
acceptance checks". It distinguishes what the automated test suite validates
from what requires a maintainer run against the real
`github.com/m24927605/ait/issues`.

---

## Check #1 — `gh` CLI happy path: auto-detected, issue opened

**Status: Requires maintainer run.**

This check needs a real `gh` session (authenticated, network access) and the
ability to open an issue at `github.com/m24927605/ait/issues`. It cannot be
fully validated in an offline CI environment. `tests/bug_report/test_submitter_gh.py`
validates the `gh`-subprocess invocation logic (argument construction,
stdout/stderr parsing, subprocess error handling) against a mocked `subprocess`.
A maintainer should run `pip install -e .`, force a daemon protocol error
(e.g., by starting an AIT daemon and sending a malformed socket frame), and
confirm that the prompt appears and `gh issue create` opens an issue on the real
repo.

## Check #2 — URL fallback when `gh` is not installed

**Status: Requires maintainer run.**

When `gh` is absent, `submitter.py` falls back to opening a pre-filled
`issues/new` URL via `webbrowser.open`. `tests/bug_report/test_submitter_url.py`
validates the URL-construction and `webbrowser.open` call via mocks. A
maintainer should uninstall `gh` (or temporarily remove it from `$PATH`),
repeat check #1, and confirm a browser opens with the pre-filled URL.

## Check #3 — 50 KB body → written to pending → `--replay --all` ships it

**Status: Validated by automated tests.**

`tests/bug_report/test_pending_queue.py` validates `enqueue`, `list_pending`,
`load_pending`, `remove`, `clear_pending`, and `prune_old` against a real
temp filesystem (no mocks for the file layer). The non-TTY flush path
(which enqueues without prompting) is validated end-to-end by
`tests/bug_report/test_end_to_end_flow.py::test_non_tty_flush_writes_pending`.
The `ait bug-report --replay --all` command path is validated at the CLI level
by `tests/bug_report/test_cli_bug_report.py`. The specific 50 KB body limit
that triggers pending rather than `gh` submission is validated by
`tests/bug_report/test_submitter_pending.py`.

## Check #4 — `AIT_BUG_REPORT=never` produces zero IO and no prompt

**Status: Validated by automated tests.**

`tests/bug_report/test_end_to_end_flow.py::test_env_never_disables_pipeline`
confirms that setting `AIT_BUG_REPORT=never` causes `report_internal_error` to
return before touching the collector; the collector remains empty and no pending
files are written. `tests/bug_report/test_config.py` validates `env_disabled()`
directly. The "zero IO / no imports" guarantee for mode=never is not
mechanically verified by `strace`, but the code path is a single early-return
check before any file-system or network operation.

## Check #5 — `mode=always`: first run auto-sends, subsequent runs are silent dedup

**Status: Partially validated; full validation needs real submission.**

`tests/bug_report/test_flush.py` validates the dedup decision logic: entries
already marked as submitted-open are `action="silent"`. The `mode=always` skip
of the per-session "send?" prompt is validated in
`tests/bug_report/test_prompt.py`. The three-run scenario (first auto-sends a
combined issue, next two are silent) cannot be fully validated without a real
`gh` session, because the dedup state from the first submission depends on a
real `issue_url` being returned and stored in `seen.json`. A maintainer should
run the three-run scenario against the live repo to confirm end-to-end dedup
behavior.

## Check #6 — `ait bug-report --attempt <id>` with literal-SEND confirmation

**Status: NOT IMPLEMENTED — deferred.**

The `--attempt` flag and the associated literal-`SEND` confirmation gate were
scoped out during T15 implementation. `cli/bug_report.py` has a placeholder
argument parser entry for `--attempt` that prints "not implemented" and
exits. The spec calls for the user to type the string `SEND` (not `y`) to
confirm submission of an attempt-attached report, functioning as a second-factor
against accidental submission. This behavior was not implemented in the v1
feature branch and should be addressed in a follow-up task.

---

## Non-functional checks

**Cold-start regression:** Not mechanically measured in CI. The `bug_report`
package uses no runtime imports at module load time (all heavy imports are
deferred to `flush_at_exit` callsite). When `mode == "never"` or
`AIT_BUG_REPORT=never`, `flush_at_exit` returns after one env-variable read
and one `load_prefs()` call. A maintainer can verify with
`time python -m ait.cli --help` before and after the feature branch merges.

**Zero-syscall fast path:** The collector is checked before any file or network
operation. When the collector is empty (no internal errors occurred),
`decide_prompt` returns `action="silent"` and `interactive_flush` returns
immediately. This is validated functionally by
`tests/bug_report/test_flush.py::test_empty_collector_is_silent` (or the
equivalent case in the flush tests). A strace snapshot in CI was not added in
this iteration.

---

## Summary table

| Check | Validated by automated tests | Needs maintainer run |
|-------|------------------------------|----------------------|
| #1 gh happy path | Partial (subprocess mock) | Yes — real gh + network |
| #2 URL fallback | Partial (webbrowser mock) | Yes — gh absent + browser |
| #3 pending queue + replay | Yes | No |
| #4 AIT_BUG_REPORT=never | Yes | No |
| #5 mode=always dedup | Partial (decision logic only) | Yes — real submission |
| #6 --attempt SEND gate | Not implemented | N/A (deferred) |
