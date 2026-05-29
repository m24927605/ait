# UX Friction P2 — Implementation Plan (target: 1.7.x patches)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the first-week experience per
`docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md` § P2 —
condense `ait status` default output (preserve dump as `--verbose`),
redesign `ait whereami` (5-line summary, exit 0 both states), and
add a shell-integration probe to `ait doctor`.

**Architecture:** Three independent commits. P2.1 splits the
existing 30+ line `_format_status` into a condensed default formatter
plus a `--verbose` legacy path. P2.2 rewrites
`_format_whereami` to emit the spec-blessed 5-line / 2-line
templates. P2.3 wires a shell-integration probe into the `doctor`
handler that reports + recommends but never auto-modifies rc.

**Tech Stack:** Python stdlib. No new runtime dependencies.

---

## Already shipped (do NOT redo)

Two P2 spec items are already on main from P0 / P1:

- **P2.4 — `.ait/config.json` `[review].auto_skip_globs` override**
  ships with P1 Task 2 (`docs/superpowers/plans/2026-05-30-ux-friction-p1-plan.md`).
  This plan does not touch it.

- **P2.5 — Install invariant docstring in `src/ait/shell_integration.py`**
  shipped with P0 commit `9103e38`. Already on main. This plan does
  not touch it.

Self-check before starting any task here: `git log --oneline | head -8`
should still show `9103e38 fix(shell): guard shell-integration helper
calls with command -v` and the P1 commits should be present. If P1
hasn't landed yet, ship P1 first — this plan assumes the P1 surface
(`Wrap behavior` block, `ait off` / `on` verbs) exists.

---

## Conventions (read before any task)

- Repo: `/Users/michael.chen/products/ait`
- Branch: cut 1.7.x patches from main as items land; work
  direct-on-main per established workflow.
- Python venv: `.venv/bin/python` (3.14.4)
- Test invocation:
  ```
  PYTHONPATH=src .venv/bin/python -m pytest tests/<module>.py -v
  ```
- Commit message footer (CLAUDE.md mandate) — every commit ends with:
  ```
  docs:<comma-separated-paths>
  keyword:<comma-separated-keywords>

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- HEREDOC for `git commit -m`.
- DO NOT `git push`, `gh release create`, or `gh workflow run` per
  `memory/feedback_no_github_cicd_runs.md`. Local-only verification.

---

## File inventory

| File | Touched by task |
|---|---|
| `src/ait/cli/status_helpers.py` (`_format_status` line ≈326) | T1 |
| `src/ait/cli_parser.py` (status_parser block) | T1 |
| `src/ait/cli/init.py` (status dispatch line ≈136) | T1 |
| `tests/test_status_condensed_format.py` (new) | T1 |
| `src/ait/cli/whereami.py` (`_format_whereami`, `handle` exit code) | T2 |
| `tests/test_whereami_format.py` (new) | T2 |
| `src/ait/cli/init.py` (doctor dispatch line ≈110) | T3 |
| `src/ait/cli/adapter_helpers.py` (or wherever doctor builds payload) | T3 |
| `tests/test_doctor_shell_probe.py` (new) | T3 |

---

## Task 1 — P2.1 `ait status` condensed default

`_format_status` (`src/ait/cli/status_helpers.py:326`) currently emits
30+ lines: a flat dump of every payload key (`Agent CLI: ...`,
`Adapter: ...`, `OK: ...`, etc). Per spec, the **default** output is
~13 lines grouped into named blocks (`Repo`, `Workspace`, `Wrap
behavior`). The 30+ line dump moves to `ait status --verbose`.

Spec output (inside attempt):

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

Spec output (outside attempt, primary checkout):

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

### Step 1: Add `--verbose` flag to `status` parser

In `src/ait/cli_parser.py`, locate the existing `status_parser` block
(grep for `"status"`):

```bash
grep -n "subparsers.add_parser.\"status\"" src/ait/cli_parser.py
```

Read the surrounding 10 lines. Add:

```python
    status_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="emit the full 30+ line dump (the pre-1.7 default)",
    )
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_status_condensed_format.py`:

```python
from __future__ import annotations

import unittest


class CondensedStatusFormatTests(unittest.TestCase):
    def _payload(self, **overrides) -> dict:
        base = {
            "adapter": "claude-code",
            "ok": True,
            "git_repo": True,
            "wrapper_installed": True,
            "path_wrapper_active": True,
            "wrapper_path": "/repo/.ait/bin/claude",
            "active_binary": None,
            "real_claude_binary": True,
            "real_agent_binary": True,
            "direnv_available": False,
            "direnv_loaded": False,
            "memory": {"initialized": True, "health": "ok",
                       "lint_issue_count": 0,
                       "lint_error_count": 0,
                       "lint_warning_count": 0,
                       "lint_info_count": 0},
            "daemon": {"running": True, "pid": 12345},
            "bypass_detection": {"status": "wrapped", "message": ""},
            "wrap_behavior": {
                "current": "wrapped (claude in this shell enters AIT)",
                "disable_once": "AIT_BYPASS=1 claude ...",
                "disable_shell": "ait off    (re-enable: ait on)",
            },
            "agent_cli_ready": True,
            "agent_cli_message": "ok",
            "ait_health": {"status": "ok"},
            "recovery": {"status": "ok"},
            "next_steps": [],
        }
        base.update(overrides)
        return base

    def test_condensed_default_is_under_18_lines(self) -> None:
        from ait.cli.status_helpers import _format_status_condensed
        out = _format_status_condensed(self._payload(), repo_root="/r/x")
        lines = out.splitlines()
        # Spec target is ~13 lines; allow some slack for installation
        # alerts. Hard ceiling is 18.
        self.assertLessEqual(len(lines), 18, f"too verbose:\n{out}")

    def test_condensed_contains_three_named_blocks(self) -> None:
        from ait.cli.status_helpers import _format_status_condensed
        out = _format_status_condensed(self._payload(), repo_root="/r/x")
        self.assertIn("Repo", out)
        self.assertIn("Workspace", out)
        self.assertIn("Wrap behavior", out)

    def test_condensed_ends_with_OK_on_healthy_state(self) -> None:
        from ait.cli.status_helpers import _format_status_condensed
        out = _format_status_condensed(self._payload(), repo_root="/r/x")
        self.assertTrue(
            out.rstrip().endswith("OK"),
            f"missing trailing OK:\n{out!r}",
        )

    def test_verbose_preserves_legacy_dump(self) -> None:
        # The pre-1.7 `_format_status` becomes the verbose path; it
        # must still be reachable and still produce the long output.
        from ait.cli.status_helpers import _format_status
        out = _format_status(self._payload(), debug=False)
        # Legacy dump emits 20+ lines for a fully populated payload.
        self.assertGreater(len(out.splitlines()), 15)
```

- [ ] **Step 3: Run, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_status_condensed_format.py -v
```

Expected: ImportError on `_format_status_condensed`; verbose test
passes (legacy formatter still exists).

- [ ] **Step 4: Add `_format_status_condensed` to status_helpers.py**

In `src/ait/cli/status_helpers.py`, add immediately above the
existing `_format_status` function (line 326):

```python
def _format_status_condensed(
    payload: dict[str, object],
    *,
    repo_root: str | Path,
) -> str:
    """Spec-blessed condensed status output (target ~13 lines).

    Three named blocks: Repo, Workspace, Wrap behavior. Trailing OK
    when the payload is healthy; otherwise show the failure reason
    and the first hint.

    See docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md
    § `ait status` redesigned output.
    """
    import sys

    lines: list[str] = []
    # Banner: AIT <version> · <install method> · <bin path>
    version = _ait_version()
    install_method = _detect_install_method()
    bin_path = sys.argv[0] if sys.argv and sys.argv[0] else "ait"
    lines.append(f"AIT {version} · {install_method} · {bin_path}")
    lines.append("")

    # Repo block
    lines.append(f"Repo {Path(repo_root).resolve()}")
    lines.append(_kv("initialized", "yes" if payload.get("git_repo") else "no"))
    daemon = payload.get("daemon") or {}
    if isinstance(daemon, dict) and daemon.get("running"):
        lines.append(_kv("daemon", f"running (pid {daemon.get('pid')})"))
    else:
        lines.append(_kv("daemon", "not running"))
    memory = payload.get("memory") or {}
    if isinstance(memory, dict):
        issues = memory.get("lint_issue_count", 0)
        lines.append(_kv("memory", f"{memory.get('health', 'unknown')} ({issues} lint issues)"))
    lines.append(_kv("attempts", _format_attempts_summary(payload.get("recovery"))))
    lines.append("")

    # Workspace block — content depends on in-attempt vs not
    workspace_line, workspace_details = _workspace_summary(payload)
    lines.append(workspace_line)
    lines.extend(workspace_details)
    lines.append("")

    # Wrap behavior block (block introduced in P1.1)
    wb = payload.get("wrap_behavior") or {}
    if isinstance(wb, dict) and wb:
        lines.append("Wrap behavior")
        lines.append(_kv("current", str(wb.get("current", "unknown"))))
        lines.append(_kv("disable once", str(wb.get("disable_once", ""))))
        lines.append(_kv("disable shell", str(wb.get("disable_shell", ""))))
        lines.append("")

    # Trailing status verdict
    if payload.get("ok") and payload.get("agent_cli_ready"):
        lines.append("OK")
    else:
        lines.append(f"NOT OK: {payload.get('agent_cli_message') or 'see --verbose'}")

    return "\n".join(lines)


def _kv(key: str, value: str) -> str:
    # Two-space indent, 14-char key column for the spec layout.
    return f"  {key:<14}{value}"


def _ait_version() -> str:
    try:
        return metadata.version("ait")
    except metadata.PackageNotFoundError:
        return "unknown"


def _detect_install_method() -> str:
    # pipx | brew | pip | dev — best-effort. Cheap heuristic on
    # the location of the executable. Authoritative source would be
    # `pipx list`, but that's a network round trip — keep it cheap.
    exe = Path(sys.argv[0]).resolve() if sys.argv else Path()
    parts = exe.parts
    if "pipx" in parts:
        return "pipx"
    if "Homebrew" in parts or "homebrew" in parts:
        return "brew"
    if exe.suffix == "" and ".venv" in parts:
        return "dev"
    return "pip"


def _format_attempts_summary(recovery: object) -> str:
    if not isinstance(recovery, dict):
        return "unknown"
    active = recovery.get("active_count", 0)
    archived = recovery.get("archived_count", 0)
    return f"{active} active, {archived} archived"


def _workspace_summary(payload: dict[str, object]) -> tuple[str, list[str]]:
    workspace_ctx = payload.get("workspace_context") or {}
    if isinstance(workspace_ctx, dict) and workspace_ctx.get("is_ait_workspace"):
        attempt_id = workspace_ctx.get("attempt_id", "?")
        short_id = str(attempt_id).split(":")[-1][:9]
        head = workspace_ctx.get("head", "detached")
        target = workspace_ctx.get("target", "unknown")
        dirty = workspace_ctx.get("dirty")
        dirty_str = "yes" if dirty else "no"
        return (
            f"Workspace ⟶  attempt {short_id} (you are here)",
            [
                _kv("target", str(target)),
                _kv("HEAD", str(head)),
                _kv("dirty", dirty_str),
            ],
        )
    return (
        "Workspace ⟶  primary checkout (no active attempt)",
        [_kv("next", "run `claude` to enter an attempt")],
    )
```

The `_workspace_summary` reads from a `workspace_context` key on the
payload. That key doesn't exist on the current payload — it needs to
be populated by `_status_payload`. Wire it in:

In `_status_payload` (around line 60-94), after the existing payload
dict is built, before the `bypass_detection` line, add:

```python
    from ait.agent_state import inspect_agent_state
    try:
        state = inspect_agent_state(_payload_repo_root_hint(payload))
        payload["workspace_context"] = state.detected_context.to_dict() if state.detected_context else {}
    except Exception:
        payload["workspace_context"] = {}
```

`_payload_repo_root_hint` is a helper that pulls the repo root from
elsewhere in the payload — if no such field exists, inline the
`Path.cwd()` fallback. (The existing `_format_status` doesn't take a
repo_root argument; the new condensed formatter does, so the
formatter call site has to pass it through.)

- [ ] **Step 5: Wire the condensed formatter into `init.handle`**

In `src/ait/cli/init.py` find the status dispatch (around line 136
per `grep -n "_format_status\b" src/ait/cli/init.py`):

```python
            output = _format_status(payload, debug=args.debug)
```

Replace with:

```python
            if getattr(args, "verbose", False):
                output = _format_status(payload, debug=args.debug)
            else:
                output = _format_status_condensed(payload, repo_root=repo_root)
```

…and add `_format_status_condensed` to the import at line 4:

```python
from ait.cli.status_helpers import _format_status, _format_status_condensed, _status_payload_with_recovery
```

- [ ] **Step 6: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_status_condensed_format.py -v
```

Expected: 4 passes.

- [ ] **Step 7: Manual smoke**

```bash
PYTHONPATH=src .venv/bin/python -m ait.cli status 2>&1 | wc -l
PYTHONPATH=src .venv/bin/python -m ait.cli status --verbose 2>&1 | wc -l
```

Expected: default ≤18 lines; --verbose ≥20 lines.

- [ ] **Step 8: Commit**

```bash
git add src/ait/cli/status_helpers.py src/ait/cli_parser.py src/ait/cli/init.py tests/test_status_condensed_format.py
git commit -m "$(cat <<'EOF'
feat(status): condensed default output, --verbose preserves legacy

`ait status` previously emitted a 30+ line flat dump that buried the
three things a user actually wants — repo health, current workspace,
and how to bypass. The condensed default (target ~13 lines) groups
under named blocks Repo / Workspace / Wrap behavior, trailing with
OK or a single-line failure verdict.

The legacy 30+ line dump is reachable as `ait status --verbose` (or
`-v`) for troubleshooting. `ait doctor` should continue to shell out
to verbose internally.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p2-plan.md
keyword:ux,status,condensed,verbose

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — P2.2 `ait whereami` redesigned

Current output (`src/ait/cli/whereami.py:24-37`) prints 9-10 flat
lines with verbose key names like `is_primary_worktree` and
`is_ait_workspace`. Per spec, **inside attempt** is a 6-line summary:

```
Inside AIT attempt 01HZX9TYE
  target     main
  HEAD       detached
  dirty      yes (1 file)
  workspace  .ait/workspaces/attempt-0001-01HZX9TYE
  repo       /Users/michael/products/<repo>
```

…and **outside attempt** is 2 lines:

```
Not in an AIT attempt.
  repo: /Users/michael/products/<repo> (primary checkout)
```

Exit code: **0 in both cases**. Today `handle()` returns 2 when
`current_state == "not_git_repository"` — change so the only non-zero
exit is when whereami itself fails (i.e., never; the function always
reports a fact).

### Step 1: Write the failing test

Create `tests/test_whereami_format.py`:

```python
from __future__ import annotations

import unittest


class WhereamiFormatTests(unittest.TestCase):
    def _payload_inside_attempt(self) -> dict:
        return {
            "current_state": "inside_attempt",
            "repo_root": "/repo/x",
            "detected_context": {
                "is_primary_worktree": False,
                "is_ait_workspace": True,
                "attempt_id": "repo:01HZX9TYE5K",
                "current_branch": None,
                "target_branch": "main",
                "ahead_by": 0,
                "dirty": True,
                "dirty_files_count": 1,
                "workspace_ref": ".ait/workspaces/attempt-0001-01hzx9tye5k",
            },
            "next_action": {},
        }

    def _payload_outside_attempt(self) -> dict:
        return {
            "current_state": "primary_checkout",
            "repo_root": "/repo/x",
            "detected_context": {
                "is_primary_worktree": True,
                "is_ait_workspace": False,
                "attempt_id": None,
                "current_branch": "main",
                "target_branch": None,
                "ahead_by": 0,
                "dirty": False,
                "dirty_files_count": 0,
                "workspace_ref": None,
            },
            "next_action": {},
        }

    def test_inside_attempt_is_six_lines(self) -> None:
        from ait.cli.whereami import _format_whereami
        out = _format_whereami(self._payload_inside_attempt())
        self.assertEqual(6, len(out.splitlines()), out)
        self.assertTrue(out.startswith("Inside AIT attempt"))
        self.assertIn("01HZX9TYE", out)
        self.assertIn("target", out)
        self.assertIn("HEAD", out)
        self.assertIn("dirty", out)
        self.assertIn("workspace", out)
        self.assertIn("repo", out)

    def test_outside_attempt_is_two_lines(self) -> None:
        from ait.cli.whereami import _format_whereami
        out = _format_whereami(self._payload_outside_attempt())
        self.assertEqual(2, len(out.splitlines()), out)
        self.assertTrue(out.startswith("Not in an AIT attempt"))
        self.assertIn("primary checkout", out)

    def test_does_not_emit_internal_keys(self) -> None:
        from ait.cli.whereami import _format_whereami
        out = _format_whereami(self._payload_inside_attempt())
        for noise in ("is_primary_worktree", "is_ait_workspace", "ahead_by"):
            self.assertNotIn(noise, out, f"leaked internal key {noise!r}")
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_whereami_format.py -v
```

Expected: 3 failures (current `_format_whereami` returns 9-10 lines
with internal keys).

- [ ] **Step 3: Rewrite `_format_whereami`**

In `src/ait/cli/whereami.py`, replace lines 21-37:

```python
def _format_whereami(payload: dict[str, object]) -> str:
    context = payload.get("detected_context") or {}
    context = context if isinstance(context, dict) else {}
    repo_root = payload.get("repo_root") or "<unknown>"

    if context.get("is_ait_workspace"):
        attempt_id = str(context.get("attempt_id", "?"))
        short_id = attempt_id.split(":")[-1][:9].upper()
        target = context.get("target_branch") or "unknown"
        head = context.get("current_branch") or "detached"
        dirty = context.get("dirty")
        dirty_count = context.get("dirty_files_count", 0)
        dirty_str = (
            f"yes ({dirty_count} file{'s' if dirty_count != 1 else ''})"
            if dirty else "no"
        )
        workspace_ref = context.get("workspace_ref") or "<unknown>"
        return "\n".join([
            f"Inside AIT attempt {short_id}",
            f"  target     {target}",
            f"  HEAD       {head}",
            f"  dirty      {dirty_str}",
            f"  workspace  {workspace_ref}",
            f"  repo       {repo_root}",
        ])

    # Outside attempt — primary checkout or other
    return "\n".join([
        "Not in an AIT attempt.",
        f"  repo: {repo_root} (primary checkout)",
    ])
```

- [ ] **Step 4: Change exit code to always 0**

In the same file, change `handle()` line 18:

```python
    return 0 if state.current_state != "not_git_repository" else 2
```

to:

```python
    # whereami reports a fact; not being in an attempt is not an
    # error. Exit 0 in both states. The only non-zero exit would be
    # an internal failure, which is signalled by an exception
    # bubbling up to main().
    return 0
```

- [ ] **Step 5: Run, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_whereami_format.py -v
```

Expected: 3 passes.

- [ ] **Step 6: Manual smoke**

From the repo root:

```bash
PYTHONPATH=src .venv/bin/python -m ait.cli whereami
echo "exit=$?"
```

Expected: 2-line output ending with `primary checkout`; exit 0.

If you have an attempt workspace handy:

```bash
cd .ait/workspaces/<first-attempt-dir>
PYTHONPATH=src .venv/bin/python -m ait.cli whereami
echo "exit=$?"
cd -
```

Expected: 6-line summary; exit 0.

- [ ] **Step 7: Commit**

```bash
git add src/ait/cli/whereami.py tests/test_whereami_format.py
git commit -m "$(cat <<'EOF'
feat(whereami): redesigned 6-line / 2-line output, exit 0 both states

`ait whereami` was emitting 9-10 flat lines with internal key names
(is_primary_worktree, is_ait_workspace, ahead_by). The redesigned
output is two spec-blessed templates:

- Inside attempt: six lines (attempt id, target, HEAD, dirty,
  workspace, repo)
- Outside attempt: two lines ("Not in an AIT attempt." + repo line)

Exit code is 0 in both states — whereami reports a fact; not being
in an attempt is not an error.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p2-plan.md
keyword:ux,whereami,exit-code,fact-not-error

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — P2.3 `ait doctor` shell-integration probe

When `ait` is on PATH but the wrapper is half-installed (rc edited
then truncated, partial source, post-upgrade drift), `ait doctor`
should report it cleanly with a copy-pasteable fix. **Never**
auto-modify rc files — probe and recommend; the user runs the fix.

Spec output block (added to existing doctor output):

```
Shell integration
  ait() wrapper:           defined
  _ait_continue_should_cd: MISSING ❌
  _ait_continue_reminder:  MISSING ❌
  fix: eval "$(ait shell init)"
       or: ait shell install --rc ~/.zshrc
```

When all helpers are present:

```
Shell integration
  ait() wrapper:           defined
  _ait_continue_should_cd: defined
  _ait_continue_reminder:  defined
```

### Step 1: Write the failing test

Create `tests/test_doctor_shell_probe.py`:

```python
from __future__ import annotations

import unittest
from unittest import mock


class ShellIntegrationProbeTests(unittest.TestCase):
    def test_probe_detects_all_helpers_present(self) -> None:
        from ait.cli.status_helpers import _shell_integration_probe
        with mock.patch.dict(
            "os.environ",
            {
                "AIT_SHELL_PROBE_AIT": "1",
                "AIT_SHELL_PROBE_CONTINUE_SHOULD_CD": "1",
                "AIT_SHELL_PROBE_CONTINUE_REMINDER": "1",
            },
        ):
            probe = _shell_integration_probe()
        self.assertEqual("defined", probe["ait_wrapper"])
        self.assertEqual("defined", probe["continue_should_cd"])
        self.assertEqual("defined", probe["continue_reminder"])
        self.assertFalse(probe["needs_fix"])

    def test_probe_flags_missing_helpers(self) -> None:
        from ait.cli.status_helpers import _shell_integration_probe
        with mock.patch.dict(
            "os.environ",
            {"AIT_SHELL_PROBE_AIT": "1"},
            clear=False,
        ):
            for noise in (
                "AIT_SHELL_PROBE_CONTINUE_SHOULD_CD",
                "AIT_SHELL_PROBE_CONTINUE_REMINDER",
            ):
                if noise in __import__("os").environ:
                    del __import__("os").environ[noise]
            probe = _shell_integration_probe()
        self.assertEqual("defined", probe["ait_wrapper"])
        self.assertEqual("MISSING", probe["continue_should_cd"])
        self.assertEqual("MISSING", probe["continue_reminder"])
        self.assertTrue(probe["needs_fix"])

    def test_format_probe_emits_fix_lines_when_broken(self) -> None:
        from ait.cli.status_helpers import _format_shell_integration_probe
        text = _format_shell_integration_probe({
            "ait_wrapper": "defined",
            "continue_should_cd": "MISSING",
            "continue_reminder": "MISSING",
            "needs_fix": True,
        })
        self.assertIn("Shell integration", text)
        self.assertIn("MISSING", text)
        self.assertIn('eval "$(ait shell init)"', text)
        self.assertIn("ait shell install", text)

    def test_format_probe_omits_fix_lines_when_clean(self) -> None:
        from ait.cli.status_helpers import _format_shell_integration_probe
        text = _format_shell_integration_probe({
            "ait_wrapper": "defined",
            "continue_should_cd": "defined",
            "continue_reminder": "defined",
            "needs_fix": False,
        })
        self.assertIn("Shell integration", text)
        self.assertNotIn("MISSING", text)
        self.assertNotIn("eval", text)
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_doctor_shell_probe.py -v
```

Expected: ImportError on `_shell_integration_probe` and
`_format_shell_integration_probe`.

- [ ] **Step 3: Add the probe helper to status_helpers.py**

The probe reads env vars set by a one-shot shell snippet the user
exports before invoking doctor. The shell snippet writes a 1 into
`$AIT_SHELL_PROBE_<HELPER_NAME>` for each helper currently defined.
This works because the helper functions live in the user's shell —
the Python process has no other way to see them.

In `src/ait/cli/status_helpers.py`, after the existing `_recovery_*`
helpers, add:

```python
def _shell_integration_probe() -> dict[str, object]:
    """Return a probe of which shell helpers the user's shell has.

    Relies on the shell snippet emitted by `ait shell probe-env` (see
    `src/ait/shell_integration.py`) having been eval'd before
    invoking `ait doctor`. When the snippet was not eval'd, this
    returns conservatively "MISSING" for every helper — the worst
    case is one false "missing" warning, never a false "defined".
    """
    def _check(env_var: str) -> str:
        return "defined" if os.environ.get(env_var) == "1" else "MISSING"

    ait_wrapper = _check("AIT_SHELL_PROBE_AIT")
    continue_should_cd = _check("AIT_SHELL_PROBE_CONTINUE_SHOULD_CD")
    continue_reminder = _check("AIT_SHELL_PROBE_CONTINUE_REMINDER")
    needs_fix = "MISSING" in (continue_should_cd, continue_reminder)
    return {
        "ait_wrapper": ait_wrapper,
        "continue_should_cd": continue_should_cd,
        "continue_reminder": continue_reminder,
        "needs_fix": needs_fix,
    }


def _format_shell_integration_probe(probe: dict[str, object]) -> str:
    lines = [
        "Shell integration",
        f"  ait() wrapper:           {probe['ait_wrapper']}",
        f"  _ait_continue_should_cd: {probe['continue_should_cd']}",
        f"  _ait_continue_reminder:  {probe['continue_reminder']}",
    ]
    if probe.get("needs_fix"):
        lines.extend([
            '  fix: eval "$(ait shell init)"',
            "       or: ait shell install --rc ~/.zshrc",
        ])
    return "\n".join(lines)
```

- [ ] **Step 4: Wire into the `doctor` path**

In `src/ait/cli/init.py` find the doctor dispatch (line ≈110 per the
inventory: `doctor_automation(args.name or "claude-code", repo_root)`).
The doctor command currently calls into the adapter system and prints
the doctor report. Append the shell probe to the printed output.

Search for the print site of the doctor output:

```bash
grep -n "doctor\b" src/ait/cli/init.py | head -20
```

After locating where doctor prints its output (likely a `print(...)`
of the result), append:

```python
            from ait.cli.status_helpers import (
                _shell_integration_probe,
                _format_shell_integration_probe,
            )
            print(_format_shell_integration_probe(_shell_integration_probe()))
```

The placement may be after the existing doctor output block. Read
the surrounding 15 lines to pick the right insertion point — the
probe should appear at the end of doctor's textual output, before
any final summary line.

- [ ] **Step 5: Add the `ait shell probe-env` subcommand (for the user-side snippet)**

The shell side needs a way to set `AIT_SHELL_PROBE_*` env vars in
the user's shell before doctor runs. Add to `src/ait/cli_parser.py`
after the existing `shell_parser` block (~line 701):

```python
    shell_probe = shell_subparsers.add_parser(
        "probe-env",
        help="emit a shell snippet that exports AIT_SHELL_PROBE_* env vars",
    )
```

(Adjust `shell_subparsers` based on how subcommands attach to
`shell_parser` — read lines 701-740 of cli_parser.py to confirm.)

In `src/ait/cli/shell.py`, add a `probe-env` action that prints:

```python
def _emit_probe_env() -> str:
    return (
        '[ "$(command -v ait)" ] '
        '&& AIT_SHELL_PROBE_AIT=1 && export AIT_SHELL_PROBE_AIT\n'
        'command -v _ait_continue_should_cd >/dev/null 2>&1 '
        '&& AIT_SHELL_PROBE_CONTINUE_SHOULD_CD=1 '
        '&& export AIT_SHELL_PROBE_CONTINUE_SHOULD_CD\n'
        'command -v _ait_continue_reminder >/dev/null 2>&1 '
        '&& AIT_SHELL_PROBE_CONTINUE_REMINDER=1 '
        '&& export AIT_SHELL_PROBE_CONTINUE_REMINDER\n'
    )
```

Hand-off to user: `ait doctor` documentation should add a one-liner
explaining that running `eval "$(ait shell probe-env)" && ait
doctor` is the canonical way to get an accurate shell-integration
report. When the user runs doctor cold (without the eval), the
report shows "MISSING" for helpers and the fix lines surface, which
is correct conservative behavior.

- [ ] **Step 6: Run, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_doctor_shell_probe.py -v
```

Expected: 4 passes.

- [ ] **Step 7: Manual smoke**

```bash
# Without eval — should report MISSING + fix lines
PYTHONPATH=src .venv/bin/python -m ait.cli doctor 2>&1 | tail -10

# With eval — should report defined for each helper
eval "$(PYTHONPATH=src .venv/bin/python -m ait.cli shell probe-env)" \
  && PYTHONPATH=src .venv/bin/python -m ait.cli doctor 2>&1 | tail -10
```

Expected: first run shows MISSING + fix; second shows all defined,
no fix lines.

- [ ] **Step 8: Commit**

```bash
git add src/ait/cli/status_helpers.py src/ait/cli/init.py src/ait/cli/shell.py src/ait/cli_parser.py tests/test_doctor_shell_probe.py
git commit -m "$(cat <<'EOF'
feat(doctor): shell-integration probe — never auto-modifies rc

When `ait` is on PATH but the wrapper is half-installed (partial
source, rc drift, post-upgrade scope loss), `ait doctor` now reports
the broken state cleanly with a copy-pasteable fix instead of
emitting confusing "command not found" warnings on every subsequent
invocation. The probe checks the ait() wrapper plus the two helpers
P0.1 added guards for (_ait_continue_should_cd, _ait_continue_reminder).

Probe consults AIT_SHELL_PROBE_* env vars set by the new
`ait shell probe-env` snippet. When the snippet was not eval'd
before doctor, the probe conservatively reports MISSING and surfaces
the fix lines — the worst case is one false "missing" report.

`ait doctor` never modifies the user's rc files. Reports + recommends
only.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p2-plan.md
keyword:ux,doctor,shell-integration,probe

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (no commit)

After all three tasks:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_status_condensed_format.py \
  tests/test_whereami_format.py \
  tests/test_doctor_shell_probe.py \
  tests/test_status_recovery_resolver.py \
  tests/test_banner.py \
  tests/test_shell_integration.py \
  -v 2>&1 | tail -10
```

Expected: P0 + P2 tests green (P1 tests may or may not be present
depending on whether P1 has landed).

Fast-path regression:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  -m "not (slow or daemon or subprocess or release)" -q 2>&1 | tail -5
```

Expected: no new failures vs the post-P1 baseline.

DO NOT `git push`. Patches roll up as the items land; maintainer
decides which items go in which 1.7.x patch.

---

# Self-review

**Spec coverage** (P2 section of `2026-05-30-ux-friction-fix-design.md`):

| Spec item | Plan task |
|---|---|
| P2.1 `ait status` condensed default (10-15 lines) | Task 1 |
| P2.1 `--verbose` preserves 30+ line dump | Task 1 Step 5 |
| P2.2 `ait whereami` 5-line workspace summary | Task 2 Step 3 |
| P2.2 exit 0 in/out | Task 2 Step 4 |
| P2.3 `ait doctor` shell-integration probe | Task 3 |
| P2.3 never auto-modifies rc | Task 3 Steps 4-5 (probe + emit shell snippet, no rc write) |
| P2.4 `[review].auto_skip_globs` | Shipped by P1 Task 2 (do-not-redo callout at top of plan) |
| P2.5 Install invariant docstring | Shipped by P0 (do-not-redo callout at top of plan) |

Each P2 release-note item maps directly to a commit message.

**Placeholder scan**: One annotated hand-off in Task 1 Step 4 says
"see line numbers below" and similar — those are concrete grep
instructions, not TBDs. Task 3 Step 5 says "Adjust `shell_subparsers`
based on how subcommands attach" — that's a grep-and-confirm
instruction since shell.py wasn't read in full during planning. No
"TBD", "TODO", "implement later" or "similar to".

**Type consistency**:

| Symbol | Defined in | Used in |
|---|---|---|
| `_format_status_condensed(payload, *, repo_root) -> str` | T1 Step 4 | T1 Step 5, T1 Step 2 |
| `_format_status(payload, *, debug=False) -> str` (legacy) | already exists, preserved | T1 Step 2 |
| `_format_whereami(payload) -> str` | rewritten T2 Step 3 | T2 Step 1 |
| `_shell_integration_probe() -> dict[str, object]` | T3 Step 3 | T3 Step 4, T3 Step 1 |
| `_format_shell_integration_probe(probe) -> str` | T3 Step 3 | T3 Step 4, T3 Step 1 |

All names consistent across tasks.

**Scope check**: P2 only. Three tasks, three commits, each ships in
its own 1.7.x patch (1.7.1 / 1.7.2 / 1.7.3) per spec's "spread
across point releases" guidance. No cross-task dependencies — they
can land in any order.

---

# Execution Handoff

Plan complete and saved to
`docs/superpowers/plans/2026-05-30-ux-friction-p2-plan.md`. Two
execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task,
   review between tasks. T1 touches the `_format_status` rewrite
   plus payload shape, so subagent isolation reduces context bleed.
2. **Inline Execution** — execute tasks in this session using
   `executing-plans`. Three tasks ≈ 4-6 hours.

P0 / P1 must already be on main before starting P2.
