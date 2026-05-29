# UX Friction P0 — Implementation Plan (target: 1.6.2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the three first-hour abandonment triggers from
`docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md` § P0 —
zsh helper-not-found warning, `ait status` reporting "not_initialized"
from inside an attempt, and the silent wrap that produces a wasted
half-conversation reconciling plain-git vs AIT mental model.

**Architecture:** Three small, independently revertable commits.
T1 hardens `src/ait/shell_integration.py` so the generated `ait()`
wrapper no longer references undefined helpers. T2 makes
`src/ait/repo.py:resolve_repo_root` worktree-aware so every reporter
(status, whereami, banner, doctor) gets the same correct AIT context.
T3 adds a 4-line stderr banner at the moment the wrapped agent is
about to exec.

**Tech Stack:** Python stdlib + stdlib `unittest`. No new runtime
dependencies. Shell snippets are still POSIX sh / zsh.

---

## Conventions (read before any task)

- Repo: `/Users/michael.chen/products/ait`
- Branch: create `fix/ux-friction-p0` from current `main` before starting
- Python venv: `.venv/bin/python` (3.14.4)
- Test invocation:
  ```
  PYTHONPATH=src:tests .venv/bin/python -m pytest tests/<module>.py -v
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
| `src/ait/shell_integration.py` | T1 |
| `tests/test_shell_integration.py` (new or extend) | T1 |
| `src/ait/repo.py` | T2 |
| `src/ait/cli/status_helpers.py` | T2 |
| `src/ait/cli/whereami.py` | T2 |
| `tests/test_repo_resolver.py` (new) | T2 |
| `src/ait/runner.py` (around line 242) | T3 |
| `src/ait/banner.py` (new) | T3 |
| `tests/test_banner.py` (new) | T3 |

---

## Task 1 — P0.1 zsh defensive guards (`command -v` invariant)

The `ait()` shell wrapper at `src/ait/shell_integration.py:133` calls
`_ait_continue_should_cd "$@"` unconditionally. When the helpers are
absent from the user's shell (sub-shell, partial source, post-upgrade
without re-source), zsh prints `ait:1: command not found:
_ait_continue_should_cd` before the wrapper falls through to
`command ait "$@"`.

**Files:**
- Modify: `src/ait/shell_integration.py` (function `_ait_command_function_lines`, lines ≈105-143)
- Modify: `src/ait/shell_integration.py` (module docstring at top of file — add the invariant)
- Create or extend: `tests/test_shell_integration.py`

- [ ] **Step 1: Read the current generator**

```bash
sed -n '105,145p' src/ait/shell_integration.py
```

Confirm the function emits the `ait()` wrapper containing the
unguarded `_ait_continue_should_cd "$@"` call.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_shell_integration.py` (create if absent — the test
should not require the project's pytest fixtures from conftest):

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.shell_integration import shell_snippet


class ShellHelperGuardTests(unittest.TestCase):
    def test_zsh_wrapper_guards_continue_helper_call(self):
        snippet = shell_snippet("zsh")
        # The ait() wrapper must check `command -v _ait_continue_should_cd`
        # before invoking it, so an environment with the wrapper defined
        # but the helper missing does not emit `command not found`.
        self.assertIn("command -v _ait_continue_should_cd", snippet)

    def test_bash_wrapper_guards_continue_helper_call(self):
        snippet = shell_snippet("bash")
        self.assertIn("command -v _ait_continue_should_cd", snippet)

    def test_invariant_documented_in_module_docstring(self):
        import ait.shell_integration as mod
        self.assertIsNotNone(mod.__doc__)
        self.assertIn("command -v", mod.__doc__)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test, verify failure**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/test_shell_integration.py -v
```

Expected: three failures. `command -v _ait_continue_should_cd` is not
in the generated snippet; module has no docstring with that token.

- [ ] **Step 4: Add module docstring (invariant)**

At the very top of `src/ait/shell_integration.py`, replace:

```python
from __future__ import annotations
```

with:

```python
"""ait shell integration.

INVARIANT: code emitted into the user's rc must never make an
unconditional call to a helper function it defines. Every call site
of a helper must be guarded with `command -v <helper> >/dev/null &&`
so a partial source, a sub-shell that lost function inheritance, or a
post-upgrade rc out of sync still leaves the wrapper functional —
falling through to `command ait` rather than printing a scary
`command not found` to stderr.

Reproduced 2026-05-29 in a new-user session; documented in
`docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md` § P0.1.
"""

from __future__ import annotations
```

- [ ] **Step 5: Guard the wrapper call**

In `src/ait/shell_integration.py:_ait_command_function_lines`, change
the `ait()` definition. Find:

```python
        "ait() {",
        '  if _ait_continue_should_cd "$@"; then',
        "    local ait_shell_script",
        '    if ait_shell_script="$(command ait continue "${@:2}" --shell-hook 2>/dev/null)" && [ -n "$ait_shell_script" ]; then',
        '      eval "$ait_shell_script"',
        "      return $?",
        "    fi",
        "  fi",
        '  command ait "$@"',
        "}",
```

Replace with:

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

`local` is zsh-specific; the bash version uses the same `ait()` body
since `_ait_command_function_lines()` is shared. `local` works in bash
inside functions too, so no further branching is needed.

- [ ] **Step 6: Run the test, verify pass**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/test_shell_integration.py -v
```

Expected: 3 passes.

- [ ] **Step 7: Smoke the generated snippet by eye**

```bash
PYTHONPATH=src .venv/bin/python -c \
  'from ait.shell_integration import shell_snippet; print(shell_snippet("zsh"))' \
  | grep -A 2 "^ait()"
```

Expected output includes the `command -v _ait_continue_should_cd >/dev/null 2>&1` line right after `ait()`.

- [ ] **Step 8: Commit**

```bash
git add src/ait/shell_integration.py tests/test_shell_integration.py
git commit -m "$(cat <<'EOF'
fix(shell): guard shell-integration helper calls with `command -v`

The ait() wrapper at src/ait/shell_integration.py emitted an
unguarded `_ait_continue_should_cd "$@"` call. When the helper was
missing from the user's shell — sub-shell scope, partial source,
post-upgrade rc drift — zsh printed `ait:1: command not found:
_ait_continue_should_cd` before every `ait` invocation. Inert but
trust-eroding; reproduced on a new-user session 2026-05-29.

Adds module docstring INVARIANT: emitted shell code must never
unconditionally call helpers it defines. Reproduced in
docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md § P0.1.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p0-plan.md
keyword:ux,shell-integration,defensive-guard,fix

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — P0.2 worktree-aware `resolve_repo_root`

`src/ait/cli/status_helpers.py` emits `"not_initialized"` when its
context-resolver does not see `.ait/`. From inside
`.ait/workspaces/attempt-*/`, the existing `resolve_repo_root` returns
the workspace path itself, not the host repo. `whereami` is already
correct (different code path); fix is to converge `status` onto the
same worktree-aware logic.

**Files:**
- Modify: `src/ait/repo.py:resolve_repo_root` (line ≈9)
- Modify: `src/ait/cli/status_helpers.py` (wherever it currently
  computes the context — locate via the existing `from ait.repo
  import resolve_repo_root` import at line 46)
- Create: `tests/test_repo_resolver.py`

- [ ] **Step 1: Read the current resolver**

```bash
sed -n '1,40p' src/ait/repo.py
```

Note that today `resolve_repo_root` likely just resolves and returns
the path as-is.

- [ ] **Step 2: Write the failing test**

Create `tests/test_repo_resolver.py`:

```python
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.repo import resolve_repo_root


class ResolveRepoRootTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.host_repo = Path(self._td.name) / "host"
        self.host_repo.mkdir()
        # A real git repo because resolve_repo_root inspects git state
        subprocess.run(["git", "init", "-q"], cwd=self.host_repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@example.com"],
            cwd=self.host_repo, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "test"],
            cwd=self.host_repo, check=True,
        )
        (self.host_repo / "README.md").write_text("seed\n")
        subprocess.run(["git", "add", "."], cwd=self.host_repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "seed"],
            cwd=self.host_repo, check=True,
        )
        (self.host_repo / ".ait").mkdir()
        # Mimic the workspace layout AIT uses
        self.workspace = self.host_repo / ".ait" / "workspaces" / "attempt-0001-01HZTEST"
        self.workspace.mkdir(parents=True)

    def test_resolves_host_repo_when_inside_attempt_workspace(self):
        result = resolve_repo_root(self.workspace)
        self.assertEqual(self.host_repo.resolve(), result.resolve())

    def test_resolves_path_as_is_when_outside_attempt(self):
        result = resolve_repo_root(self.host_repo)
        self.assertEqual(self.host_repo.resolve(), result.resolve())

    def test_resolves_when_cwd_is_subdir_of_attempt_workspace(self):
        subdir = self.workspace / "src" / "deep"
        subdir.mkdir(parents=True)
        result = resolve_repo_root(subdir)
        self.assertEqual(self.host_repo.resolve(), result.resolve())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test, verify failure**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/test_repo_resolver.py -v
```

Expected: 2 of 3 fail — the inside-attempt cases return the workspace
path instead of the host repo.

- [ ] **Step 4: Add the worktree-aware branch**

Open `src/ait/repo.py`. Replace `resolve_repo_root` with:

```python
def resolve_repo_root(repo_root: str | Path) -> Path:
    """Return the canonical host-repo root for `repo_root`.

    If `repo_root` is inside an AIT attempt workspace
    (`<host>/.ait/workspaces/attempt-*/...`), return `<host>` rather
    than the workspace path itself. This makes status, whereami, and
    other context-aware commands agree about which repo they are in
    when invoked from inside an attempt's detached worktree.

    Falls back to the input path resolved otherwise.
    """
    path = Path(repo_root).resolve()
    # Walk up looking for an `.ait/workspaces/attempt-*` ancestor.
    for ancestor in (path, *path.parents):
        # If `ancestor` is itself a workspace dir, its parents[1] is
        # `<host>/.ait`, and parents[2] is `<host>`.
        parent = ancestor.parent
        grandparent = parent.parent if parent != ancestor else None
        if (
            parent.name == "workspaces"
            and grandparent is not None
            and grandparent.name == ".ait"
        ):
            host = grandparent.parent
            if host.exists():
                return host.resolve()
    return path
```

This walks the ancestor chain looking for `.../.ait/workspaces/<attempt>`
shape. When found, the host root is the directory two levels above
`workspaces`. Falls back to the input path resolved when not inside an
attempt.

- [ ] **Step 5: Run the test, verify pass**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/test_repo_resolver.py -v
```

Expected: 3 passes.

- [ ] **Step 6: Confirm `status` no longer reports "not_initialized" when inside an attempt**

This is an integration check. From the project repo:

```bash
# Create a temp test fixture: a fake attempt workspace inside a real
# AIT-init'd repo. The simplest reproduction is to cd into one that
# exists right now if any are present:
ls .ait/workspaces/ 2>/dev/null | head -3
```

If `.ait/workspaces/` has an attempt directory:

```bash
cd .ait/workspaces/<attempt-name>
PYTHONPATH=src .venv/bin/python -m ait.cli status 2>&1 | head -10
cd -
```

Expected before fix: includes `"status": "not_initialized"` or
`Latest result: not_initialized`. Expected after fix: reports the
host repo's real init state (`status: "ok"` or equivalent).

If no attempt exists locally, this confirmation is satisfied by the
unit test alone.

- [ ] **Step 7: Verify `whereami` is unaffected**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/ -k "whereami" -v 2>&1 | tail -10
```

Expected: all existing whereami tests pass — the resolver change
should not regress whereami, which uses its own resolution path.

- [ ] **Step 8: Commit**

```bash
git add src/ait/repo.py tests/test_repo_resolver.py
git commit -m "$(cat <<'EOF'
fix(repo): resolve_repo_root is worktree-aware

`ait status` was reporting "not_initialized" when invoked from inside
an AIT attempt workspace because resolve_repo_root returned the
workspace path itself rather than the host repo root. From there the
status command could not find `.ait/` and gave up.

Adds an ancestor walk that detects the
`<host>/.ait/workspaces/<attempt>` shape and returns `<host>`. Both
status, whereami, banner, and doctor now agree on the AIT context
regardless of which sub-directory the user is invoking from.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p0-plan.md
keyword:ux,status,resolver,worktree,fix

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — P0.3 banner on attempt session entry

`src/ait/runner.py` calls `run_command_with_budget_and_timeout` at
line ≈242 to spawn the wrapped agent process. Right before that
spawn, the wrapper has provisioned the attempt and knows its id,
workspace path, HEAD state, and target ref. That is the place to
print a one-shot stderr banner.

Per spec, banner content is **four** lines (the fifth bypass line
lands in P1.3). Skip when `stderr` is not a TTY OR `AIT_NO_BANNER=1`.
Fixed width 60 chars; ANSI only when colour is appropriate.

**Files:**
- Create: `src/ait/banner.py`
- Modify: `src/ait/runner.py` (around line 242, just before the spawn)
- Create: `tests/test_banner.py`

- [ ] **Step 1: Write the failing test (banner renderer only)**

Create `tests/test_banner.py`:

```python
from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.banner import render_attempt_banner, print_attempt_banner


class RenderAttemptBannerTests(unittest.TestCase):
    def test_includes_attempt_id_workspace_head_apply_lines(self):
        text = render_attempt_banner(
            attempt_id="repo:01HZX9TYE",
            workspace_rel=".ait/workspaces/attempt-0001-01HZX9TYE",
            head="detached",
            target="main",
        )
        self.assertIn("01HZX9TYE", text)
        self.assertIn(".ait/workspaces/attempt-0001-01HZX9TYE", text)
        self.assertIn("HEAD: detached", text)
        self.assertIn("target: main", text)
        self.assertIn("ait apply", text)

    def test_each_line_no_longer_than_60_chars_visible(self):
        text = render_attempt_banner(
            attempt_id="repo:01HZX9TYE",
            workspace_rel=".ait/workspaces/attempt-0001-01HZX9TYE",
            head="detached",
            target="main",
        )
        for line in text.splitlines():
            # Strip ANSI escape sequences before counting width.
            import re
            visible = re.sub(r"\x1b\[[0-9;]*m", "", line)
            self.assertLessEqual(
                len(visible), 60,
                f"line wider than 60: {visible!r}",
            )

    def test_short_attempt_id_renders_full_when_below_9_chars(self):
        # ULIDs are 26 chars; spec said take first 9. Guard against an
        # off-by-one when the id is shorter than the slice budget.
        text = render_attempt_banner(
            attempt_id="01HZ",
            workspace_rel=".ait/workspaces/attempt-0001-01HZ",
            head="detached",
            target="main",
        )
        self.assertIn("01HZ", text)


class PrintAttemptBannerTests(unittest.TestCase):
    def _make_fake_tty(self):
        # Hand-rolled TTY-shaped object: a writable StringIO with
        # isatty() = True.
        class _FakeTTY(io.StringIO):
            def isatty(self):
                return True
        return _FakeTTY()

    def _make_fake_pipe(self):
        class _FakePipe(io.StringIO):
            def isatty(self):
                return False
        return _FakePipe()

    def test_prints_when_stderr_is_tty_and_env_unset(self):
        stream = self._make_fake_tty()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIT_NO_BANNER", None)
            print_attempt_banner(
                stream=stream,
                attempt_id="01HZX9TYE",
                workspace_rel=".ait/workspaces/attempt-0001-01HZX9TYE",
                head="detached",
                target="main",
            )
        out = stream.getvalue()
        self.assertIn("01HZX9TYE", out)

    def test_skips_when_stderr_not_tty(self):
        stream = self._make_fake_pipe()
        print_attempt_banner(
            stream=stream,
            attempt_id="01HZX9TYE",
            workspace_rel=".ait/workspaces/attempt-0001-01HZX9TYE",
            head="detached",
            target="main",
        )
        self.assertEqual("", stream.getvalue())

    def test_skips_when_ait_no_banner_env_set(self):
        stream = self._make_fake_tty()
        with mock.patch.dict(os.environ, {"AIT_NO_BANNER": "1"}):
            print_attempt_banner(
                stream=stream,
                attempt_id="01HZX9TYE",
                workspace_rel=".ait/workspaces/attempt-0001-01HZX9TYE",
                head="detached",
                target="main",
            )
        self.assertEqual("", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test, verify failure**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/test_banner.py -v
```

Expected: ImportError on `ait.banner`.

- [ ] **Step 3: Implement the banner renderer**

Create `src/ait/banner.py`:

```python
"""Attempt-entry banner printed to stderr at session start.

See docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md § P0.3.
Width fixed at 60 chars. Skip when stderr is not a TTY OR
AIT_NO_BANNER=1.
"""
from __future__ import annotations

import os
import sys
from typing import TextIO

_BOX_WIDTH = 60
_INNER = _BOX_WIDTH - 2  # account for │ … │ frame
_HORIZ = "─"


def _ansi(code: str, text: str, *, enable: bool) -> str:
    if not enable:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _truncate_visible(text: str, width: int) -> str:
    """Truncate to width with an ellipsis if needed (visible chars only)."""
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def render_attempt_banner(
    *,
    attempt_id: str,
    workspace_rel: str,
    head: str,
    target: str,
    use_color: bool = False,
) -> str:
    """Return the 4-line banner (with framing) as a single string.

    `attempt_id` may be a full ULID or shorter; the renderer truncates
    a long id to its first 9 visible characters.
    """
    short_id = attempt_id.split(":")[-1][:9]
    header_text = f" AIT attempt {short_id} "
    header_fill = max(0, _BOX_WIDTH - 2 - len(header_text))
    top = "┌─" + header_text + _HORIZ * header_fill + "┐"
    bottom = "└" + _HORIZ * (_BOX_WIDTH - 2) + "┘"

    body_lines = [
        f"workspace: {workspace_rel}",
        f"HEAD: {head} · target: {target}",
        f"Commits land on `{target}` only after you run `ait apply`.",
    ]

    rendered_body = []
    for line in body_lines:
        line = _truncate_visible(line, _INNER - 1)
        # Highlight 'detached' in yellow + `code` in bold when colour on.
        if use_color:
            line = line.replace(
                "detached", _ansi("33", "detached", enable=True)
            )
            # naive backtick → bold; only first occurrence per line is fine
            if "`" in line:
                pre, _, rest = line.partition("`")
                code, _, post = rest.partition("`")
                line = pre + _ansi("1", code, enable=True) + post
        rendered_body.append(f"│ {line}".ljust(_BOX_WIDTH - 1) + "│")

    return "\n".join([top, *rendered_body, bottom]) + "\n"


def print_attempt_banner(
    *,
    stream: TextIO | None = None,
    attempt_id: str,
    workspace_rel: str,
    head: str,
    target: str,
) -> None:
    """Print the banner to `stream` (default stderr) if conditions allow.

    Skip when the stream is not a TTY or when AIT_NO_BANNER=1 is set.
    """
    out = stream if stream is not None else sys.stderr
    try:
        is_tty = out.isatty()
    except (AttributeError, ValueError):
        is_tty = False
    if not is_tty:
        return
    if os.environ.get("AIT_NO_BANNER", "") not in ("", "0"):
        return
    text = render_attempt_banner(
        attempt_id=attempt_id,
        workspace_rel=workspace_rel,
        head=head,
        target=target,
        use_color=True,
    )
    out.write(text)
    out.flush()
```

The renderer separates pure-string `render_attempt_banner` (always
returns text, easy to test) from `print_attempt_banner` (handles
TTY/env skip and writes to stream). The tests in Step 1 exercise both
paths.

- [ ] **Step 4: Run banner tests, verify pass**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/test_banner.py -v
```

Expected: 6 passes.

- [ ] **Step 5: Wire the banner into the runner**

Open `src/ait/runner.py`. Find the call to
`run_command_with_budget_and_timeout` near line 242. The local scope
at that point has the attempt object (with id, workspace_ref) and the
target ref already known.

Locate the runner function (likely `run_attempt` or similar) by:

```bash
grep -n "run_command_with_budget_and_timeout\b" src/ait/runner.py
```

Take note of the surrounding 30 lines for the variable names that
hold attempt id, workspace path, HEAD state, and target. The exact
variable names depend on the function body; the spec is name-agnostic.

Just before the call to `run_command_with_budget_and_timeout`, add:

```python
        from ait.banner import print_attempt_banner
        try:
            head_label = (
                "detached" if attempt.target_head_oid else "no commits yet"
            )
            workspace_rel = os.path.relpath(
                str(attempt.workspace_ref), start=str(repo_root)
            )
            print_attempt_banner(
                attempt_id=attempt.attempt_id,
                workspace_rel=workspace_rel,
                head=head_label,
                target=attempt.base_ref_name or "main",
            )
        except Exception:
            # Never break the agent invocation on a banner failure.
            pass
```

Adjust attribute names to match the actual attempt object exposed in
that runner scope. If the function takes `target` as a separate
argument (not `attempt.base_ref_name`), prefer that argument.

Cosmetic detail: import at the top of the function or top of the file
— follow the file's existing import style.

- [ ] **Step 6: Smoke the integration by running an existing wrapper test**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/ \
  -k "runner or wrapper or attempt" -q 2>&1 | tail -5
```

Expected: no regressions. Banner emission goes to stderr in TTY
contexts only; the test environment is non-TTY so banner stays
silent.

- [ ] **Step 7: Visual smoke (manual, optional)**

If you have time, create an `ait init`'d test repo and run
`PYTHONPATH=src .venv/bin/python -m ait.cli run --adapter claude-code
--intent "hi" -- /bin/echo hello` (or similar that wraps a trivial
binary). Confirm the banner appears at stderr just before "hello".

- [ ] **Step 8: Commit**

```bash
git add src/ait/banner.py src/ait/runner.py tests/test_banner.py
git commit -m "$(cat <<'EOF'
feat(ui): print 4-line banner on attempt session entry

The wrapped agent session previously gave no visible signal that the
shell had been auto-wrapped into an AIT attempt workspace. A senior
engineer running `claude` on a plain-git handoff lost half a turn
reconciling two valid workflows. Adds a 60-char box-drawing banner to
stderr just before the wrapped binary execs, showing the attempt id,
workspace path, HEAD/target, and the `ait apply` path to land
commits.

Skip when stderr is not a TTY or AIT_NO_BANNER=1. ANSI colour only in
TTY contexts (box dim grey via default, `detached` yellow, backticked
code bold).

The 5th bypass line documenting `ait off` and AIT_BYPASS=1 lands in
P1.3 once those primitives exist.

docs:docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md,docs/superpowers/plans/2026-05-30-ux-friction-p0-plan.md
keyword:ux,banner,visibility,attempt-entry

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (no commit)

After all three tasks:

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest \
  tests/test_shell_integration.py \
  tests/test_repo_resolver.py \
  tests/test_banner.py \
  -v 2>&1 | tail -10
```

Expected: all P0 tests green.

Also confirm the existing fast-path suite is not regressed:

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest \
  -m "not (slow or daemon or subprocess or release)" -q 2>&1 | tail -5
```

Expected: same green count as before, plus the new tests above.

DO NOT `git push`. The branch ends in a local-ready state; the
maintainer decides when to push and when to cut 1.6.2.

---

# Self-review

**Spec coverage** (P0 section of `2026-05-30-ux-friction-fix-design.md`):

| Spec item | Plan task |
|---|---|
| P0.1 `command -v` guards | Task 1 |
| P0.1 invariant docstring | Task 1 Step 4 |
| P0.2 worktree-aware resolver | Task 2 |
| P0.2 status reads correct context | Task 2 (resolver fix propagates; no separate task needed) |
| P0.3 4-line banner content | Task 3 Step 1 + Step 3 |
| P0.3 stderr | Task 3 Step 3 (print_attempt_banner default) |
| P0.3 TTY skip | Task 3 Step 3 (isatty check) |
| P0.3 AIT_NO_BANNER=1 skip | Task 3 Step 3 |
| P0.3 60-char width | Task 3 Step 3 (`_BOX_WIDTH`) |
| P0.3 colour only on TTY | Task 3 Step 3 (`use_color=True` gated) |

Each P0 release-note one-liner from the spec maps directly to the
commit message of its task (T1 ↔ P0.1, T2 ↔ P0.2, T3 ↔ P0.3).

**Placeholder scan**: No "TBD", "TODO", "implement later", "Similar to
Task N", or "Add error handling" in plan text. Task 3 Step 5 deliberately
says "Adjust attribute names to match the actual attempt object" — that
is concrete guidance to grep the function body, not a TBD; the spec
cannot pre-know which attribute names the runner exposes without the
implementer reading 30 lines of `runner.py`.

**Type consistency**:

| Symbol | Defined in | Used in |
|---|---|---|
| `resolve_repo_root(path) -> Path` | Task 2 | already imported by status_helpers; no callers need updating |
| `render_attempt_banner(*, attempt_id, workspace_rel, head, target, use_color=False) -> str` | Task 3 Step 3 | Task 3 Step 1 tests |
| `print_attempt_banner(*, stream=None, attempt_id, workspace_rel, head, target) -> None` | Task 3 Step 3 | Task 3 Step 5 runner integration; Task 3 Step 1 tests |

All names and shapes consistent.

**Scope check**: P0 only. P1 and P2 follow in separate plans
(`2026-05-30-ux-friction-p1-plan.md`, `2026-05-30-ux-friction-p2-plan.md`)
so each can ship on its own release cadence without cross-PR coupling.

---

# Execution Handoff

Plan complete and saved to
`docs/superpowers/plans/2026-05-30-ux-friction-p0-plan.md`. Two
execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review
   between tasks, fast iteration. Three independent commits map
   cleanly to three subagent dispatches.
2. **Inline Execution** — execute tasks in this session using
   `executing-plans`, batch execution with checkpoints. Three small
   tasks are also a reasonable fit for inline.
