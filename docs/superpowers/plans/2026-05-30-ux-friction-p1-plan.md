# UX Friction P1 — Implementation Plan (target: 1.7.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the three first-day "AIT is broken" issue triggers from
`docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md` § P1 —
the phantom-verb contract break (no clear bypass), reviewer running
on docs-only changes, and an entry banner that doesn't tell users
how to bypass.

**Architecture:** Three independent commits. T1 adds two bypass
entries (`AIT_BYPASS=1` env + `ait off` / `ait on` shell verbs) and a
`Wrap behavior` block in `ait status`. T2 adds a `auto`/`always`
mode to `--review` plus a docs-only changed-files detector and
`auto_skip_globs` config. T3 extends the P0 banner with a 5th line
documenting bypass — depends on T1's `ait off` existing.

**Tech Stack:** Python stdlib, `fnmatch` (already imported in
`review_policy.py`). No new runtime dependencies.

---

## Conventions (read before any task)

- Repo: `/Users/michael.chen/products/ait`
- Branch: maintainer cuts 1.7.0 from main once P1 lands; work
  direct-on-main per established workflow (P0 precedent commits
  `9103e38`, `dd0b8de`, `74258f2`)
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
| `src/ait/adapter_wrapper.py` (line ≈159) | T1 |
| `src/ait/cli_parser.py` (after line ≈460) | T1, T2 |
| `src/ait/cli/main.py` (`_HANDLERS` near line ≈80) | T1 |
| `src/ait/cli/off_on.py` (new) | T1 |
| `src/ait/shell_integration.py` (`_ait_command_function_lines`) | T1 |
| `src/ait/cli/status_helpers.py` (`_status_payload`, formatter) | T1 |
| `tests/test_bypass_primitives.py` (new) | T1 |
| `tests/test_shell_integration.py` (extend) | T1 |
| `src/ait/review_policy.py` (`ReviewPolicy`, loader) | T2 |
| `src/ait/cli/run.py` (line ≈74) | T2 |
| `src/ait/cli/apply.py` | T2 |
| `tests/test_review_auto_skip.py` (new) | T2 |
| `src/ait/banner.py` (`render_attempt_banner` body lines) | T3 |
| `src/ait/runner.py` (banner call site) | T3 |
| `tests/test_banner.py` (extend) | T3 |

---

## Task 1 — P1.1 bypass primitives + status wrap-behavior block

Two user-visible entries to bypass the auto-wrap:

1. **Per-invocation** — `AIT_BYPASS=1 claude "quick question"` — env
   var consulted by the wrapper script.
2. **Per-shell session** — `ait off` / `ait on` — verbs that the
   `ait()` shell function intercepts and `eval`s to mutate the
   caller's shell env.

Plus a `Wrap behavior` block in `ait status` so the discoverability
gap from O4 closes.

The wrapper today already checks `AIT_WRAPPER_BYPASS=1` (see
`src/ait/adapter_wrapper.py:159`). The user-facing name per spec is
`AIT_BYPASS`. Keep both — the wrapper accepts either name; legacy
`AIT_WRAPPER_BYPASS` continues to work; new docs and verbs use
`AIT_BYPASS`.

### Step 1: Write the failing tests

Create `tests/test_bypass_primitives.py`:

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from ait.adapter_wrapper import _adapter_wrapper_script
from ait.adapters import get_adapter
from ait.shell_integration import shell_snippet


class WrapperBypassTests(unittest.TestCase):
    def test_wrapper_script_honours_ait_bypass_env(self) -> None:
        adapter = get_adapter("claude-code")
        script = _adapter_wrapper_script(adapter, real_binary="/usr/bin/true")
        # Must check both the legacy AIT_WRAPPER_BYPASS *and* the new
        # spec-blessed AIT_BYPASS name. Legacy stays for backward
        # compatibility; AIT_BYPASS is the documented entry-point.
        self.assertIn("AIT_BYPASS", script)
        self.assertIn("AIT_WRAPPER_BYPASS", script)


class ShellOffOnInterceptTests(unittest.TestCase):
    def test_zsh_wrapper_intercepts_off_and_on(self) -> None:
        snippet = shell_snippet("zsh")
        # The ait() shell function must intercept `ait off` and
        # `ait on` like it does `ait continue`, eval'ing the script
        # the binary prints so AIT_BYPASS can be set/unset in the
        # parent shell.
        self.assertIn("off|on", snippet)

    def test_bash_wrapper_intercepts_off_and_on(self) -> None:
        snippet = shell_snippet("bash")
        self.assertIn("off|on", snippet)


class OffOnCommandTests(unittest.TestCase):
    def test_off_emits_export_ait_bypass(self) -> None:
        from ait.cli.off_on import build_off_script
        self.assertIn("export AIT_BYPASS=1", build_off_script())

    def test_on_emits_unset_ait_bypass(self) -> None:
        from ait.cli.off_on import build_on_script
        self.assertIn("unset AIT_BYPASS", build_on_script())

    def test_off_includes_acknowledgement_line(self) -> None:
        from ait.cli.off_on import build_off_script
        self.assertIn("AIT auto-wrap disabled", build_off_script())


class WrapBehaviorStatusTests(unittest.TestCase):
    def test_status_payload_includes_wrap_behavior_block(self) -> None:
        # Reuse the existing _status_payload helper. The check
        # cares only that the new block surface exists — its detailed
        # population is exercised by status integration tests.
        from ait.adapters import doctor_automation
        from ait.cli.status_helpers import _status_payload
        from pathlib import Path as _Path

        result = doctor_automation("claude-code", _Path.cwd())
        payload = _status_payload(result)
        self.assertIn("wrap_behavior", payload)
        wb = payload["wrap_behavior"]
        self.assertIn("current", wb)
        self.assertIn("disable_once", wb)
        self.assertIn("disable_shell", wb)


if __name__ == "__main__":
    unittest.main()
```

Extend `tests/test_shell_integration.py` `ShellHelperGuardTests`:

```python
    def test_off_on_intercept_guarded_by_command_v(self) -> None:
        # The same invariant from P0.1 applies: any helper the
        # snippet defines and calls must be `command -v`-guarded.
        snippet = shell_snippet("zsh")
        # The intercept is implemented as a case inside the existing
        # ait() function, which already has its guard. Verify the
        # ait() function body itself still starts with the guard
        # after off/on integration.
        self.assertIn("command -v _ait_continue_should_cd", snippet)
```

- [ ] **Step 2: Run the tests, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_bypass_primitives.py tests/test_shell_integration.py -v
```

Expected: 4 new failures (the four `test_*` methods in the new file)
plus 0 failures in extended `test_shell_integration.py` (the new
intercept-guarded test already passes since P0.1).

- [ ] **Step 3: Wrapper accepts `AIT_BYPASS` as alias for `AIT_WRAPPER_BYPASS`**

In `src/ait/adapter_wrapper.py` find the `ait_wrapper_should_passthrough()` function block (line ≈158). Change:

```python
        'ait_wrapper_should_passthrough() {\n'
        '  if [ "${AIT_WRAPPER_BYPASS:-}" = "1" ] || [ "${AIT_WRAPPER_BYPASS:-}" = "true" ]; then\n'
        "    return 0\n"
        "  fi\n"
```

to:

```python
        'ait_wrapper_should_passthrough() {\n'
        '  if [ "${AIT_BYPASS:-}" = "1" ] || [ "${AIT_BYPASS:-}" = "true" ]; then\n'
        "    return 0\n"
        "  fi\n"
        '  if [ "${AIT_WRAPPER_BYPASS:-}" = "1" ] || [ "${AIT_WRAPPER_BYPASS:-}" = "true" ]; then\n'
        "    return 0\n"
        "  fi\n"
```

- [ ] **Step 4: Create `src/ait/cli/off_on.py`**

```python
"""Shell-eval'able scripts for `ait off` and `ait on`.

The binary cannot mutate its parent shell's environment, so these
commands print a shell snippet that the `ait()` function intercepts
and eval's. Pattern mirrors `ait continue --shell-hook`.
"""
from __future__ import annotations


def build_off_script() -> str:
    return (
        "export AIT_BYPASS=1\n"
        'printf "%s\\n" "AIT auto-wrap disabled for this shell." >&2\n'
        'printf "%s\\n" "Run \\`ait on\\` to re-enable." >&2\n'
    )


def build_on_script() -> str:
    return (
        "unset AIT_BYPASS\n"
        'printf "%s\\n" "AIT auto-wrap re-enabled for this shell." >&2\n'
    )


def handle(args, repo_root, parser=None) -> int:
    import sys
    if args.command == "off":
        sys.stdout.write(build_off_script())
        return 0
    if args.command == "on":
        sys.stdout.write(build_on_script())
        return 0
    return 1
```

- [ ] **Step 5: Register `off` and `on` in `cli_parser.py` and `cli/main.py`**

In `src/ait/cli_parser.py`, after the existing `continue_parser` block (around line 357), add:

```python
    off_parser = subparsers.add_parser("off", help="disable AIT auto-wrap for this shell (sets AIT_BYPASS=1)")
    on_parser = subparsers.add_parser("on", help="re-enable AIT auto-wrap for this shell (unsets AIT_BYPASS)")
```

In `src/ait/cli/main.py` add to `_HANDLERS`:

```python
    "off": off_on.handle,
    "on": off_on.handle,
```

…and the corresponding import:

```python
from ait.cli import off_on
```

- [ ] **Step 6: Intercept `ait off|on` in the shell wrapper**

In `src/ait/shell_integration.py:_ait_command_function_lines`, after the existing `ait()` function body, extend the wrapper to intercept off/on. Replace:

```python
        "ait() {",
        '  if command -v _ait_continue_should_cd >/dev/null 2>&1 \\',
        '     && _ait_continue_should_cd "$@"; then',
        "    local ait_shell_script",
        '    if ait_shell_script="$(command ait continue "${@:2}" --shell-hook 2>/dev/null)" && [ -n "$ait_shell_script" ]; then',
        '      eval "$ait_shell_script"',
        "      return $?",
        "    fi",
        "  fi",
        '  command ait "$@"',
        "}",
```

with:

```python
        "ait() {",
        '  case "${1:-}" in',
        "    off|on)",
        "      local ait_shell_script",
        '      if ait_shell_script="$(command ait "$1" 2>/dev/null)" && [ -n "$ait_shell_script" ]; then',
        '        eval "$ait_shell_script"',
        "        return $?",
        "      fi",
        '      command ait "$@"',
        "      return $?",
        "      ;;",
        "  esac",
        '  if command -v _ait_continue_should_cd >/dev/null 2>&1 \\',
        '     && _ait_continue_should_cd "$@"; then',
        "    local ait_shell_script",
        '    if ait_shell_script="$(command ait continue "${@:2}" --shell-hook 2>/dev/null)" && [ -n "$ait_shell_script" ]; then',
        '      eval "$ait_shell_script"',
        "      return $?",
        "    fi",
        "  fi",
        '  command ait "$@"',
        "}",
```

- [ ] **Step 7: Add `wrap_behavior` block to `_status_payload`**

In `src/ait/cli/status_helpers.py:_status_payload`, after the existing `payload["bypass_detection"] = ...` line (around line 93), add:

```python
    payload["wrap_behavior"] = _wrap_behavior_payload(payload)
```

…and define the helper above `_status_payload`:

```python
def _wrap_behavior_payload(payload: dict[str, object]) -> dict[str, str]:
    adapter = str(payload.get("adapter", "claude-code"))
    command = _agent_command_name(adapter)
    if payload.get("path_wrapper_active"):
        current = f"wrapped ({command} in this shell enters AIT)"
    elif payload.get("wrapper_installed"):
        current = f"unwrapped ({command} not on PATH ahead of .ait/bin)"
    else:
        current = "not configured"
    return {
        "current": current,
        "disable_once": f"AIT_BYPASS=1 {command} ...",
        "disable_shell": "ait off    (re-enable: ait on)",
    }
```

The corresponding formatter that turns `wrap_behavior` into the
text block (3 lines under a `Wrap behavior` header) is added in the
same file, modelled after existing block formatters. Locate the
function that renders payload sections (search for the heading
`Repo` formatting) and add the new block in the natural reading
order — after `Workspace`, before `OK`.

- [ ] **Step 8: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_bypass_primitives.py tests/test_shell_integration.py -v
```

Expected: all green.

- [ ] **Step 9: Smoke `ait off` and `ait on` manually (optional)**

```bash
# In a fresh terminal where shell integration is installed
PYTHONPATH=src .venv/bin/python -m ait.cli off
PYTHONPATH=src .venv/bin/python -m ait.cli on
```

Expected: `off` prints `export AIT_BYPASS=1\n` plus two echoes; `on`
prints `unset AIT_BYPASS\n` plus one echo.

- [ ] **Step 10: Commit**

```bash
git add src/ait/adapter_wrapper.py src/ait/cli_parser.py src/ait/cli/main.py src/ait/cli/off_on.py src/ait/shell_integration.py src/ait/cli/status_helpers.py tests/test_bypass_primitives.py tests/test_shell_integration.py
git commit -m "$(cat <<'EOF'
feat(bypass): two bypass entries + Wrap behavior in `ait status`

Closes the phantom-verb contract break from
docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md § O4
and P1.1. Adds two first-class bypass mechanisms:

- AIT_BYPASS=1 (per-invocation) — the adapter wrapper accepts this
  alongside the legacy AIT_WRAPPER_BYPASS name; AIT_BYPASS is now the
  documented entry-point.
- `ait off` / `ait on` (per-shell session) — verbs that print an
  eval-able shell snippet. The ait() shell function intercepts them
  like it does `ait continue --shell-hook`, so the parent shell's
  AIT_BYPASS env is mutated.

Adds a Wrap behavior block to `ait status` payload + formatter, so
the bypass entries are discoverable in-product.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p1-plan.md
keyword:ux,bypass,ait-off,ait-on,status

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — P1.2 right-size review (docs-only auto-skip)

The reviewer currently runs against README changes and similar
documentation-only diffs. That makes AIT feel like a broken tool on
the first PR a new user tries. Add a `--review auto` mode (becomes
the new default) that skips review when 100% of changed files match
a docs-glob set. Default globs from the spec; override via
`.ait/config.json` `[review].auto_skip_globs`.

Extend the existing `--review` choices in `cli_parser.py:460` rather
than redefining the flag — backward compatible. Existing modes
(`never`, `light`, `adversarial`, `risk-based`) remain unchanged.
Two new modes: `auto` and `always`.

| Mode | Behavior |
|---|---|
| `auto` (new default when policy default mode is non-`never`) | Docs-only? skip. Else use the policy's default profile. |
| `never` | Skip review unconditionally. (unchanged) |
| `always` | Force the policy's default profile regardless of file mix. |
| `light` / `adversarial` / `risk-based` | Force-select a specific profile, ignore docs-skip. (unchanged) |

### Step 1: Write the failing test

Create `tests/test_review_auto_skip.py`:

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from ait.review_policy import (
    DEFAULT_AUTO_SKIP_GLOBS,
    is_docs_only_change,
    load_review_policy,
)


class IsDocsOnlyChangeTests(unittest.TestCase):
    def test_returns_true_for_pure_markdown_change(self) -> None:
        self.assertTrue(
            is_docs_only_change(
                changed_files=("README.md", "docs/intro.md"),
                globs=DEFAULT_AUTO_SKIP_GLOBS,
            )
        )

    def test_returns_false_when_any_code_file_changed(self) -> None:
        self.assertFalse(
            is_docs_only_change(
                changed_files=("README.md", "src/ait/cli.py"),
                globs=DEFAULT_AUTO_SKIP_GLOBS,
            )
        )

    def test_returns_false_for_empty_change_set(self) -> None:
        # No changes → no review to skip, but auto-skip should NOT
        # claim docs-only on an empty set; let the upstream decide.
        self.assertFalse(
            is_docs_only_change(
                changed_files=(),
                globs=DEFAULT_AUTO_SKIP_GLOBS,
            )
        )

    def test_default_globs_cover_spec_set(self) -> None:
        for pattern in ("**/*.md", "docs/**", "LICENSE*", "CHANGELOG*", "README*"):
            self.assertIn(pattern, DEFAULT_AUTO_SKIP_GLOBS)


class PolicyAutoSkipOverrideTests(unittest.TestCase):
    def test_config_can_override_auto_skip_globs(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".ait").mkdir()
            (root / ".ait" / "config.json").write_text(
                json.dumps({
                    "review": {"auto_skip_globs": ["custom/**"]}
                })
            )
            policy = load_review_policy(root)
            self.assertEqual(("custom/**",), policy.auto_skip_globs)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_review_auto_skip.py -v
```

Expected: ImportError for `DEFAULT_AUTO_SKIP_GLOBS` and
`is_docs_only_change`.

- [ ] **Step 3: Add `DEFAULT_AUTO_SKIP_GLOBS` + helper in `review_policy.py`**

Near the top of `src/ait/review_policy.py` (after the
`RUN_REVIEW_MODES` constant at line 24), add:

```python
DEFAULT_AUTO_SKIP_GLOBS: tuple[str, ...] = (
    "**/*.md",
    "**/*.rst",
    "**/*.txt",
    "docs/**",
    "site-docs/**",
    "LICENSE*",
    "CHANGELOG*",
    "README*",
)


def is_docs_only_change(
    *,
    changed_files: tuple[str, ...],
    globs: tuple[str, ...],
) -> bool:
    """Return True iff `changed_files` is non-empty and every path
    matches at least one pattern in `globs`."""
    if not changed_files:
        return False
    return all(_matches_any(path, globs) for path in changed_files)
```

(`_matches_any` already lives at line 660 of the same file.)

- [ ] **Step 4: Extend `ReviewPolicy` dataclass with `auto_skip_globs`**

Find the `ReviewPolicy` dataclass (around line 60-75 — the one with
`default_mode`, `sensitive_paths`, etc.). Add a field:

```python
    auto_skip_globs: tuple[str, ...] = DEFAULT_AUTO_SKIP_GLOBS
```

In the `load_review_policy` function (around line 208-246), parse
the optional override:

```python
    raw_globs = review.get("auto_skip_globs") if isinstance(review, dict) else None
    if isinstance(raw_globs, list) and all(isinstance(p, str) for p in raw_globs):
        auto_skip_globs = tuple(raw_globs)
    else:
        auto_skip_globs = DEFAULT_AUTO_SKIP_GLOBS
```

…and pass it into the returned `ReviewPolicy(...)` constructor.

- [ ] **Step 5: Extend `--review` choices in cli_parser.py**

Change line 460:

```python
    run_parser.add_argument("--review", choices=("never", "light", "adversarial", "risk-based"))
```

to:

```python
    run_parser.add_argument("--review", choices=("auto", "never", "always", "light", "adversarial", "risk-based"))
```

Same change for `apply_parser` if it has a `--review` flag (grep
`cli_parser.py` for `apply_parser.add_argument("--review"`).

- [ ] **Step 6: Wire docs-skip into `run.py`**

Open `src/ait/cli/run.py`. Find line 74:

```python
        run_review = run_review_policy(repo_root, args.review)
```

After this, before the `if run_review != "never":` block, add:

```python
        if args.review == "auto" or args.review is None:
            from ait.review_policy import is_docs_only_change, load_review_policy
            policy = load_review_policy(repo_root)
            changed_files = _changed_files_for_attempt(...)  # see note below
            if is_docs_only_change(
                changed_files=changed_files,
                globs=policy.auto_skip_globs,
            ):
                run_review = "never"
        elif args.review == "always":
            policy = load_review_policy(repo_root)
            run_review = policy.default_mode if policy.default_mode != "never" else "light"
```

`_changed_files_for_attempt` should walk the attempt's diff vs base
ref. Look for an existing helper in `run.py` / `app.py` /
`workspace.py` — the codebase already needs this for review's
`changed_files=` argument. If there's no helper, the simplest path
is to inline a `git diff --name-only <base_ref_oid>..HEAD` call in
the attempt workspace.

- [ ] **Step 7: Re-run, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_review_auto_skip.py tests/test_review_adapter_config.py -v
```

Expected: new tests pass; existing review-adapter-config tests
unregressed.

- [ ] **Step 8: Smoke `--review auto` (optional, manual)**

In a sandbox repo, change only `README.md`, run `ait run --review
auto claude-code -- /bin/echo`. Expected log: "review skipped:
docs-only change matched globs" (or similar concise message).

- [ ] **Step 9: Commit**

```bash
git add src/ait/review_policy.py src/ait/cli_parser.py src/ait/cli/run.py src/ait/cli/apply.py tests/test_review_auto_skip.py
git commit -m "$(cat <<'EOF'
feat(review): docs-only auto-skip via `--review auto`

Reviewer used to run against README-only changes, making AIT feel
broken to new users on their first doc-typo fix. Adds two new
review modes:

- `--review auto` (new default when policy default isn't 'never'):
  skip review if 100% of changed files match the docs glob set,
  else fall through to the policy's default profile.
- `--review always`: force the policy's default profile regardless
  of file mix.

Existing modes (never / light / adversarial / risk-based) unchanged.

Default globs cover *.md, *.rst, *.txt, docs/**, site-docs/**,
LICENSE*, CHANGELOG*, README*. Override per-repo via
.ait/config.json `[review].auto_skip_globs`.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p1-plan.md
keyword:ux,review,auto-skip,docs-glob

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — P1.3 banner gains 5th bypass line

P0.3 banner shipped with 4 body lines. P1.3 adds a 5th explaining
how to bypass. Depends on T1 (the `ait off` verb must exist before
the banner can mention it).

### Step 1: Extend the banner test

Add to `tests/test_banner.py:RenderAttemptBannerTests`:

```python
    def test_banner_mentions_ait_off_and_ait_bypass(self) -> None:
        text = render_attempt_banner(
            attempt_id="repo:01HZX9TYE",
            workspace_rel=".ait/workspaces/attempt-0001-01hzx9tye",
            head="detached",
            target="main",
        )
        self.assertIn("ait off", text)
        self.assertIn("AIT_BYPASS=1", text)

    def test_banner_5th_line_still_fits_60_chars(self) -> None:
        import re
        text = render_attempt_banner(
            attempt_id="repo:01HZX9TYE",
            workspace_rel=".ait/workspaces/attempt-0001-01hzx9tye",
            head="detached",
            target="main",
            use_color=True,
        )
        ansi = re.compile(r"\x1b\[[0-9;]*m")
        for line in text.splitlines():
            visible = ansi.sub("", line)
            self.assertLessEqual(len(visible), 60, f"too wide: {visible!r}")
```

- [ ] **Step 2: Run, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_banner.py -v
```

Expected: 1 failure (mention test); width test passes (still 4
lines).

- [ ] **Step 3: Add 5th body line to `render_attempt_banner`**

Open `src/ait/banner.py`. Locate the `body_lines` list inside
`render_attempt_banner`:

```python
    body_lines = [
        f"workspace: {workspace_rel}",
        f"HEAD: {head} · target: {target}",
        f"Commits land on `{target}` only after you run `ait apply`.",
    ]
```

Replace with two-line bypass tail. The spec wording is:

```
Not wrapped? Exit, then `ait off` (this shell) or
`AIT_BYPASS=1 claude …` (one-shot).
```

That's 49 + 39 = two lines. Pick the shorter wording that fits
within 56 visible chars per body line (the box uses 1+1=2 framing
chars + 1 pad column on the right):

```python
    body_lines = [
        f"workspace: {workspace_rel}",
        f"HEAD: {head} · target: {target}",
        f"Commits land on `{target}` only after `ait apply`.",
        "Bypass once: AIT_BYPASS=1 <agent> …",
        "Bypass shell: `ait off`  ·  re-enable: `ait on`",
    ]
```

(Shortened "you run `ait apply`" → "`ait apply`" to keep the line
under 56 visible chars given the longer target names some users may
have. Verify with the width test.)

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_banner.py -v
```

Expected: 8 passes (6 original + 2 new).

- [ ] **Step 5: Visual smoke**

```bash
PYTHONPATH=src .venv/bin/python -c '
from ait.banner import render_attempt_banner
print(render_attempt_banner(
    attempt_id="01HZX9TYE5K2NRMW6QV",
    workspace_rel=".ait/workspaces/attempt-0001-01hzx9tye5k2nrmw6qv",
    head="detached",
    target="main",
))'
```

Expected: 5-line body banner, all lines fit 60 chars including the
two bypass lines.

- [ ] **Step 6: Commit**

```bash
git add src/ait/banner.py tests/test_banner.py
git commit -m "$(cat <<'EOF'
feat(ui): banner gains 5th line documenting bypass

Composes P0.3 + P1.1 into one complete entry-time signal. The
attempt-entry banner now shows the AIT_BYPASS=1 (one-shot) and
`ait off` (per-shell) escape hatches added in P1.1, so a new user
who realises they don't want the auto-wrap can exit cleanly without
filing an issue.

Width stays 60 chars; the body grows from 3 to 5 lines.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p1-plan.md
keyword:ux,banner,bypass,visibility

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (no commit)

After all three tasks:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_bypass_primitives.py \
  tests/test_shell_integration.py \
  tests/test_review_auto_skip.py \
  tests/test_banner.py \
  tests/test_status_recovery_resolver.py \
  -v 2>&1 | tail -10
```

Expected: all P0 + P1 tests green.

Fast-path regression:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  -m "not (slow or daemon or subprocess or release)" -q 2>&1 | tail -5
```

Expected: no new failures vs the post-P0 baseline (252 passing).

DO NOT `git push`. Maintainer cuts 1.7.0 when ready.

---

# Self-review

**Spec coverage** (P1 section of `2026-05-30-ux-friction-fix-design.md`):

| Spec item | Plan task |
|---|---|
| P1.1 `AIT_BYPASS=1` env var (one-shot) | Task 1 Step 3 |
| P1.1 `ait off` / `ait on` verbs | Task 1 Steps 4-6 |
| P1.1 `ait --help` first-class for off/on | Task 1 Step 5 (`subparsers.add_parser` exposes them) |
| P1.1 `Wrap behavior` section in `ait status` | Task 1 Step 7 |
| P1.2 `--review auto` mode (docs-skip) | Task 2 Steps 5-6 |
| P1.2 `--review never` (preserved) | unchanged — already in cli_parser.py |
| P1.2 `--review always` mode | Task 2 Steps 5-6 |
| P1.2 default docs glob set | Task 2 Step 3 (`DEFAULT_AUTO_SKIP_GLOBS`) |
| P1.2 `.ait/config.json` `[review].auto_skip_globs` override | Task 2 Step 4 |
| P1.3 banner 5th line | Task 3 Step 3 |

Each P1 release-note item maps directly to a commit message.

**Placeholder scan**: One annotated hand-off in Task 2 Step 6 says
"see note below" — that's the existing-helper-or-inline-git-diff
guidance and is explicit, not a placeholder. No "TBD", "TODO",
"implement later", or "similar to" elsewhere.

**Type consistency**:

| Symbol | Defined in | Used in |
|---|---|---|
| `DEFAULT_AUTO_SKIP_GLOBS: tuple[str, ...]` | T2 Step 3 | T2 Step 4 (default), T2 Step 1 (tests) |
| `is_docs_only_change(*, changed_files, globs) -> bool` | T2 Step 3 | T2 Step 6, T2 Step 1 |
| `ReviewPolicy.auto_skip_globs: tuple[str, ...]` | T2 Step 4 | T2 Step 1 |
| `build_off_script() / build_on_script() -> str` | T1 Step 4 | T1 Step 1 |
| `render_attempt_banner(*, attempt_id, workspace_rel, head, target, use_color=False) -> str` | P0 (unchanged signature) | T3 |

All names and shapes consistent.

**Scope check**: P1 only. P2 ships separately. Each task is one
commit, three independent commits per `1.7.0` release.

**Ordering**: T1 must land before T3 (T3 banner mentions `ait off`).
T2 is independent. Recommended execution order: T1 → T2 → T3.

---

# Execution Handoff

Plan complete and saved to
`docs/superpowers/plans/2026-05-30-ux-friction-p1-plan.md`. Two
execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task,
   review between tasks. T1 touches 7 files including the shell
   wrapper, so subagent isolation reduces context bleed.
2. **Inline Execution** — execute tasks in this session using
   `executing-plans`. Feasible since each task ends in tests; just
   plan for ~3-5h vs P0's ~1-2h.
