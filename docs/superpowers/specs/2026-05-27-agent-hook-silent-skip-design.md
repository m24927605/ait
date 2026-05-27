# Agent Hook Silent-Skip When Wrapper Missing

Date: 2026-05-27
Scope: robustness fix for `ait` agent-hook commands across claude-code, codex,
gemini adapters.

## Problem

The hook command written into `.claude/settings.json` (and the codex/gemini
equivalents) by `ait adapter setup ...` invokes Python directly against a path
inside `.ait/adapters/<adapter>/...`. If that wrapper file does not exist,
Python aborts with exit code 2:

```
can't open file '.../.ait/adapters/claude-code/claude_code_hook.py':
[Errno 2] No such file or directory
```

Claude Code treats a non-zero exit from a hook command as a blocking failure.
For `Stop` hooks this prevents the session from terminating cleanly: the user
sees the error on every PostToolUse / PostToolUseFailure / SessionStart /
SessionEnd / Stop event and must hand-edit `.claude/settings.json` to escape.

Common ways to land in this state:

- The repo was cloned but `ait adapter setup claude-code` was never run.
- The wrapper lives in a different repo, addressed by `AIT_WRAPPER_REPO`, but
  the env var is unset.
- `ait` was uninstalled but the hook block in `.claude/settings.json` was
  left behind.

The same template is used by the codex and gemini adapters, so they share the
same failure mode.

## Goal

Hook commands must exit 0 silently when the wrapper file does not exist,
regardless of how that happened, while preserving today's behavior when the
wrapper is present.

## Non-goals (this change)

- No `ait adapter uninstall` subcommand.
- No global launcher binary in pipx's bin directory.
- No self-healthcheck warnings.
- No documentation changes (the user-visible defect is silent failure → silent
  success; there is nothing new to document).

## Design

### Change surface

Three functions in `src/ait/adapter_resources.py` build the hook `command`
string:

- `_claude_code_settings()`
- `_codex_hooks_settings()`
- `_gemini_settings()`

Each currently produces a single shell command of the form:

```
{python} "${AIT_WRAPPER_REPO:-$<AGENT>_PROJECT_DIR}/.ait/adapters/<agent>/<hook>.py"
```

where `{python}` is `shlex.quote(sys.executable)` at generation time.

### New template

Replace each with a guarded form (claude-code shown; codex/gemini analogous):

```
HOOK="${AIT_WRAPPER_REPO:-$CLAUDE_PROJECT_DIR}/.ait/adapters/claude-code/claude_code_hook.py"; [ -f "$HOOK" ] || exit 0; exec {python} "$HOOK"
```

Semantics:

- Wrapper present (`[ -f "$HOOK" ]` true): `exec python "$HOOK"` replaces the
  shell with Python. stdin (the hook JSON payload) is forwarded unchanged.
  Behaviorally identical to today.
- Wrapper missing or unreadable: shell exits 0. Claude Code sees a successful
  hook.
- `AIT_WRAPPER_REPO` set but pointing nowhere useful: still resolves to a
  missing file → exit 0.
- Neither `AIT_WRAPPER_REPO` nor `CLAUDE_PROJECT_DIR` set: `$HOOK` becomes
  `/.ait/adapters/.../claude_code_hook.py`, which does not exist → exit 0.

The literal substrings `${AIT_WRAPPER_REPO:-$CLAUDE_PROJECT_DIR}` and
`.ait/adapters/claude-code/claude_code_hook.py` are preserved, so existing
assertions in `tests/test_cli_adapters.py` continue to pass.

### POSIX compatibility

`[ -f ... ]`, `||`, `;`, and `exec` are POSIX from day one. Claude Code's hook
runtime invokes hook commands via a shell on every supported platform.

### What does not change

- `src/ait/resources/claude-code/claude_code_hook.py` and the codex/gemini
  equivalents. They already handle their own exceptions and exit 0.
- `setup_adapter()` in `src/ait/adapter_setup.py`.
- The `_merge_settings()` merge semantics.
- Settings file paths and wrapper paths.

## Testing

New file `tests/test_adapter_resources.py`. For each of the three adapters,
parameterise these scenarios:

1. **Wrapper missing.** Use a tempdir as `<AGENT>_PROJECT_DIR`. Generate the
   command via the corresponding `_<adapter>_settings()` function, extract the
   first hook command from the returned dict, and run it with
   `subprocess.run(cmd, shell=True, env=..., input=b'{}', capture_output=True)`.
   Assert returncode 0, stdout empty, stderr empty.
2. **Wrapper exists.** Place a stub Python file at the expected path that
   reads stdin and prints its contents back to stdout, then exits 0. Run the
   command with a known JSON payload on stdin. Assert returncode 0 and that
   stdout contains the payload — this confirms both that the `exec` branch
   ran the Python and that stdin was forwarded across the `exec`.
3. **`AIT_WRAPPER_REPO` misconfigured.** Set `AIT_WRAPPER_REPO=/nonexistent`
   with no wrapper at that path. Same assertions as scenario 1.

Each scenario runs against all three adapters via parameterisation
(`subTest` is sufficient given the project uses stdlib `unittest`).

The full test suite (`PYTHONPATH=src python3 -m unittest discover -s tests`)
must remain green.

## Risk and rollback

- Risk: very low. The fix is a strict superset of current behavior on the happy
  path. The only new behavior is the missing-file branch, which today is the
  bug.
- Rollback: revert the single file change. The new tests would then fail,
  matching the pre-fix state.

## Spec alignment

This change touches `src/ait/adapter_resources.py`. That module is not listed
in `CLAUDE.md`'s "Spec Alignment Checklist", so no `docs/ai-vcs-mvp-spec.md`
or `docs/implementation-notes.md` update is required. The behavior change is
purely defensive at the agent-integration layer and does not affect the v1
spec surface.

## Acceptance criteria

1. In a repo with no wrapper file and no `AIT_WRAPPER_REPO`, starting Claude
   Code triggers no `file not found` blocking errors on PostToolUse,
   PostToolUseFailure, SessionStart, Stop, or SessionEnd.
2. With the wrapper present, hook behavior is unchanged: payloads are forwarded
   to Python, the existing `claude_code_hook.py` records attempts as before.
3. New `tests/test_adapter_resources.py` covers wrapper-present,
   wrapper-missing, and misconfigured-env scenarios for all three adapters and
   passes.
4. The full existing test suite remains green.
