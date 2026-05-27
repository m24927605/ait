# Agent Hook Silent-Skip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ait` agent-hook commands (claude-code, codex, gemini) exit 0 silently when the wrapper file is missing, instead of failing with Python's "No such file" error that blocks Claude Code's `Stop` hook.

**Architecture:** Three small functions in `src/ait/adapter_resources.py` generate the hook `command` string that lands in `.claude/settings.json` (and the codex/gemini equivalents). Replace each template with a POSIX shell guard that returns exit 0 when the wrapper path does not exist, otherwise `exec`s python on the wrapper exactly as before. Behavior is unchanged on the happy path; the missing-file branch becomes silent success instead of blocking failure.

**Tech Stack:** Python 3.14, stdlib `unittest`, POSIX `sh`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-27-agent-hook-silent-skip-design.md`

---

## File Structure

**Modify:**

- `src/ait/adapter_resources.py` — change the `command` template in three functions:
  - `_claude_code_settings()` (lines 38–56)
  - `_codex_hooks_settings()` (lines 59–77)
  - `_gemini_settings()` (lines 80–93)

**Create:**

- `tests/test_adapter_resources.py` — new test module covering the three scenarios per adapter.

No other files change.

---

## Task 1: Failing test — claude-code wrapper missing

**Files:**

- Create: `tests/test_adapter_resources.py`
- Reference: `src/ait/adapter_resources.py:38-56` (claude-code)

- [ ] **Step 1: Create the test file with a single failing test**

Create `tests/test_adapter_resources.py`:

```python
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ait.adapter_resources import (
    _claude_code_settings,
    _codex_hooks_settings,
    _gemini_settings,
)


def _claude_command() -> str:
    settings = _claude_code_settings()
    hooks = settings["hooks"]
    return hooks["SessionStart"][0]["hooks"][0]["command"]


def _codex_command() -> str:
    settings = _codex_hooks_settings()
    hooks = settings["hooks"]
    return hooks["SessionStart"][0]["hooks"][0]["command"]


def _gemini_command() -> str:
    settings = _gemini_settings()
    hooks = settings["hooks"]
    return hooks["SessionStart"][0]["hooks"][0]["command"]


def _run_hook(command: str, env_overrides: dict[str, str], payload: bytes = b"{}") -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        command,
        shell=True,
        env=env,
        input=payload,
        capture_output=True,
        timeout=10,
    )


class ClaudeCodeHookCommandTests(unittest.TestCase):
    def test_silent_exit_when_wrapper_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # No wrapper at $CLAUDE_PROJECT_DIR/.ait/adapters/claude-code/...
            result = _run_hook(
                _claude_command(),
                env_overrides={
                    "CLAUDE_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails against current code**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources -v`

Expected: `FAIL` — current command invokes Python on a nonexistent path, so the subprocess exits 2 and stderr contains `can't open file ...`.

- [ ] **Step 3: Do not commit yet — leaves a failing test in the suite. Move directly to Task 2.**

---

## Task 2: Fix `_claude_code_settings()`

**Files:**

- Modify: `src/ait/adapter_resources.py:38-56`

- [ ] **Step 1: Replace the command template**

Edit `src/ait/adapter_resources.py`. Find `_claude_code_settings()`:

```python
def _claude_code_settings() -> dict[str, object]:
    command = (
        f"{shlex.quote(sys.executable)} "
        '"${AIT_WRAPPER_REPO:-$CLAUDE_PROJECT_DIR}/.ait/adapters/claude-code/claude_code_hook.py"'
    )
```

Replace with:

```python
def _claude_code_settings() -> dict[str, object]:
    command = (
        'HOOK="${AIT_WRAPPER_REPO:-$CLAUDE_PROJECT_DIR}'
        '/.ait/adapters/claude-code/claude_code_hook.py"; '
        '[ -f "$HOOK" ] || exit 0; '
        f"exec {shlex.quote(sys.executable)} "
        '"$HOOK"'
    )
```

The rest of `_claude_code_settings()` is untouched.

- [ ] **Step 2: Run the new test — confirm it passes**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.ClaudeCodeHookCommandTests.test_silent_exit_when_wrapper_missing -v`

Expected: `OK`.

- [ ] **Step 3: Run the existing adapter-settings assertion — confirm it still passes**

Run: `PYTHONPATH=src python3 -m unittest tests.test_cli_adapters.CliAdapterTests.test_adapter_setup_print_outputs_claude_settings -v`

Expected: `OK`. The literal substrings `${AIT_WRAPPER_REPO:-$CLAUDE_PROJECT_DIR}` and `.ait/adapters/claude-code/claude_code_hook.py` are preserved by the new template, so the existing assertion is unaffected.

---

## Task 3: Add wrapper-exists test for claude-code

**Files:**

- Modify: `tests/test_adapter_resources.py`

- [ ] **Step 1: Add a stub-wrapper helper and the test**

Append to `ClaudeCodeHookCommandTests` in `tests/test_adapter_resources.py`:

```python
    def test_executes_wrapper_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / ".ait" / "adapters" / "claude-code" / "claude_code_hook.py"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "import sys\n"
                "data = sys.stdin.read()\n"
                "sys.stdout.write('ECHO:' + data)\n",
                encoding="utf-8",
            )
            result = _run_hook(
                _claude_command(),
                env_overrides={
                    "CLAUDE_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
                payload=b'{"hook_event_name":"SessionStart"}',
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertIn(b'ECHO:{"hook_event_name":"SessionStart"}', result.stdout)
```

- [ ] **Step 2: Run the new test**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.ClaudeCodeHookCommandTests.test_executes_wrapper_when_present -v`

Expected: `OK`. This confirms `exec` runs Python on the wrapper and that the hook payload on stdin is forwarded across the `exec`.

---

## Task 4: Add misconfigured-`AIT_WRAPPER_REPO` test for claude-code

**Files:**

- Modify: `tests/test_adapter_resources.py`

- [ ] **Step 1: Add the test**

Append to `ClaudeCodeHookCommandTests`:

```python
    def test_silent_exit_when_ait_wrapper_repo_points_nowhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bogus = Path(tmp) / "nonexistent-wrapper-repo"
            # bogus does not exist; AIT_WRAPPER_REPO is honoured over CLAUDE_PROJECT_DIR
            result = _run_hook(
                _claude_command(),
                env_overrides={
                    "CLAUDE_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": str(bogus),
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)
```

- [ ] **Step 2: Run the new test**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.ClaudeCodeHookCommandTests.test_silent_exit_when_ait_wrapper_repo_points_nowhere -v`

Expected: `OK`.

---

## Task 5: Codex — failing test for wrapper missing

**Files:**

- Modify: `tests/test_adapter_resources.py`

- [ ] **Step 1: Add a new test class with the wrapper-missing test**

Append to `tests/test_adapter_resources.py`:

```python
class CodexHookCommandTests(unittest.TestCase):
    def test_silent_exit_when_wrapper_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_hook(
                _codex_command(),
                env_overrides={
                    "CODEX_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)
```

- [ ] **Step 2: Run the new test and verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.CodexHookCommandTests.test_silent_exit_when_wrapper_missing -v`

Expected: `FAIL` — the codex template has not been fixed yet.

---

## Task 6: Fix `_codex_hooks_settings()`

**Files:**

- Modify: `src/ait/adapter_resources.py:59-77`

- [ ] **Step 1: Replace the command template**

Find `_codex_hooks_settings()`:

```python
def _codex_hooks_settings() -> dict[str, object]:
    command = (
        f"{shlex.quote(sys.executable)} "
        '"${AIT_WRAPPER_REPO:-$CODEX_PROJECT_DIR}/.ait/adapters/codex/codex_hook.py"'
    )
```

Replace with:

```python
def _codex_hooks_settings() -> dict[str, object]:
    command = (
        'HOOK="${AIT_WRAPPER_REPO:-$CODEX_PROJECT_DIR}'
        '/.ait/adapters/codex/codex_hook.py"; '
        '[ -f "$HOOK" ] || exit 0; '
        f"exec {shlex.quote(sys.executable)} "
        '"$HOOK"'
    )
```

- [ ] **Step 2: Run the codex wrapper-missing test — confirm pass**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.CodexHookCommandTests -v`

Expected: `OK` for `test_silent_exit_when_wrapper_missing`.

---

## Task 7: Codex — wrapper-exists and misconfigured-env tests

**Files:**

- Modify: `tests/test_adapter_resources.py`

- [ ] **Step 1: Append both tests to `CodexHookCommandTests`**

```python
    def test_executes_wrapper_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / ".ait" / "adapters" / "codex" / "codex_hook.py"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "import sys\n"
                "data = sys.stdin.read()\n"
                "sys.stdout.write('ECHO:' + data)\n",
                encoding="utf-8",
            )
            result = _run_hook(
                _codex_command(),
                env_overrides={
                    "CODEX_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
                payload=b'{"hook_event_name":"SessionStart"}',
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertIn(b'ECHO:{"hook_event_name":"SessionStart"}', result.stdout)

    def test_silent_exit_when_ait_wrapper_repo_points_nowhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bogus = Path(tmp) / "nonexistent-wrapper-repo"
            result = _run_hook(
                _codex_command(),
                env_overrides={
                    "CODEX_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": str(bogus),
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)
```

- [ ] **Step 2: Run all codex tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.CodexHookCommandTests -v`

Expected: 3 tests `OK`.

---

## Task 8: Gemini — failing test for wrapper missing

**Files:**

- Modify: `tests/test_adapter_resources.py`

- [ ] **Step 1: Add a new test class with the wrapper-missing test**

Append:

```python
class GeminiHookCommandTests(unittest.TestCase):
    def test_silent_exit_when_wrapper_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_hook(
                _gemini_command(),
                env_overrides={
                    "GEMINI_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)
```

- [ ] **Step 2: Run the new test and verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.GeminiHookCommandTests.test_silent_exit_when_wrapper_missing -v`

Expected: `FAIL`.

---

## Task 9: Fix `_gemini_settings()`

**Files:**

- Modify: `src/ait/adapter_resources.py:80-93`

- [ ] **Step 1: Replace the command template**

Find `_gemini_settings()`:

```python
def _gemini_settings() -> dict[str, object]:
    command = (
        f"{shlex.quote(sys.executable)} "
        '"${AIT_WRAPPER_REPO:-$GEMINI_PROJECT_DIR}/.ait/adapters/gemini/gemini_hook.py"'
    )
```

Replace with:

```python
def _gemini_settings() -> dict[str, object]:
    command = (
        'HOOK="${AIT_WRAPPER_REPO:-$GEMINI_PROJECT_DIR}'
        '/.ait/adapters/gemini/gemini_hook.py"; '
        '[ -f "$HOOK" ] || exit 0; '
        f"exec {shlex.quote(sys.executable)} "
        '"$HOOK"'
    )
```

- [ ] **Step 2: Run the gemini wrapper-missing test — confirm pass**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.GeminiHookCommandTests -v`

Expected: `OK` for `test_silent_exit_when_wrapper_missing`.

---

## Task 10: Gemini — wrapper-exists and misconfigured-env tests

**Files:**

- Modify: `tests/test_adapter_resources.py`

- [ ] **Step 1: Append both tests to `GeminiHookCommandTests`**

```python
    def test_executes_wrapper_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / ".ait" / "adapters" / "gemini" / "gemini_hook.py"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "import sys\n"
                "data = sys.stdin.read()\n"
                "sys.stdout.write('ECHO:' + data)\n",
                encoding="utf-8",
            )
            result = _run_hook(
                _gemini_command(),
                env_overrides={
                    "GEMINI_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
                payload=b'{"hook_event_name":"SessionStart"}',
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertIn(b'ECHO:{"hook_event_name":"SessionStart"}', result.stdout)

    def test_silent_exit_when_ait_wrapper_repo_points_nowhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bogus = Path(tmp) / "nonexistent-wrapper-repo"
            result = _run_hook(
                _gemini_command(),
                env_overrides={
                    "GEMINI_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": str(bogus),
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)
```

- [ ] **Step 2: Run all gemini tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_adapter_resources.GeminiHookCommandTests -v`

Expected: 3 tests `OK`.

---

## Task 11: Full suite green, then commit

**Files:**

- All previously modified.

- [ ] **Step 1: Run the full test suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests`

Expected: all tests pass. If anything fails, stop and investigate — do not commit.

- [ ] **Step 2: Three-pass code review (per CLAUDE.md)**

Open the diff (`git diff`) and review it three times against:
1. Spec — `docs/superpowers/specs/2026-05-27-agent-hook-silent-skip-design.md`. The wrapper-missing branch must exit 0 silently for all three adapters; the wrapper-present branch must `exec` Python with stdin intact.
2. Scope — only `src/ait/adapter_resources.py` and `tests/test_adapter_resources.py` are touched.
3. Style — three template strings have the same shape; quoting is correct (`"$HOOK"` and `shlex.quote(sys.executable)`); no unrelated edits.

- [ ] **Step 3: Commit**

```bash
git add src/ait/adapter_resources.py tests/test_adapter_resources.py
git commit -m "$(cat <<'EOF'
fix(adapters): silent-skip hook commands when wrapper missing

Wrap the generated hook command for claude-code, codex, and gemini in a
POSIX shell guard. When the wrapper file does not exist (repo cloned
without ait-vcs setup, AIT_WRAPPER_REPO mis-set, or stale hooks left
behind after uninstall), the hook exits 0 silently instead of failing
with Python's "No such file or directory" — which today blocks Claude
Code's Stop hook and traps the user in an error loop. When the wrapper
is present, exec keeps behavior bit-for-bit identical to today.

docs:docs/superpowers/specs/2026-05-27-agent-hook-silent-skip-design.md,docs/superpowers/plans/2026-05-27-agent-hook-silent-skip-plan.md
keyword:hooks,robustness,adapter-resources,claude-code,codex,gemini
EOF
)"
```

- [ ] **Step 4: Confirm clean tree**

Run: `git status`

Expected: `nothing to commit, working tree clean`.

---

## Out of scope (deferred)

These were called out in the bug report but excluded from this PR by user decision:

- `ait adapter uninstall` subcommand.
- Global launcher script under pipx bin.
- Self-healthcheck warnings.
- Stop-hook non-blocking option.

If those are needed later, file follow-up issues. The fix landed here removes the user-facing blocker on its own.

## Refactor note (informational)

`_claude_code_settings`, `_codex_hooks_settings`, and `_gemini_settings` are now near-identical: same shell-guard template, three different env vars and three different wrapper paths. After this PR lands, a follow-up could extract a single `_hook_command(env_var, wrapper_relpath)` helper. Out of scope for this change; not added to `docs/architecture-refactor-plan.md` because the duplication is contained and small.
