"""ait shell integration.

INVARIANT: code emitted into the user's rc must never make an
unconditional call to a helper function it defines. Every call site
of a helper must be guarded with `command -v <helper> >/dev/null &&`
so a partial source, a sub-shell that lost function inheritance, or
a post-upgrade rc out of sync still leaves the wrapper functional —
falling through to `command ait` rather than printing a scary
`command not found` to stderr.

Reproduced 2026-05-29 in a new-user session; documented in
`docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md` § P0.1.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


class ShellIntegrationError(ValueError):
    pass


START_MARKER = "# >>> ait shell integration >>>"
END_MARKER = "# <<< ait shell integration <<<"


@dataclass(frozen=True, slots=True)
class ShellIntegrationResult:
    shell: str
    rc_path: str
    changed: bool
    snippet: str


def shell_snippet(shell: str) -> str:
    shell_name = _normalize_shell(shell)
    if shell_name not in {"zsh", "bash"}:
        raise ShellIntegrationError(f"unsupported shell: {shell}")
    body = _zsh_body() if shell_name == "zsh" else _bash_body()
    return "\n".join([START_MARKER, body, END_MARKER, ""])


def _zsh_body() -> str:
    return "\n".join(
        [
            "_ait_auto_path() {",
            '  if [[ -n "${AIT_ACTIVE_BIN:-}" ]]; then',
            '    path=("${path[@]:#$AIT_ACTIVE_BIN}")',
            "  fi",
            '  local candidate="$PWD/.ait/bin"',
            '  path=("${path[@]:#$candidate}")',
            '  if [[ -d "$candidate" ]]; then',
            '    AIT_ACTIVE_BIN="$candidate"',
            '    path=("$AIT_ACTIVE_BIN" "${path[@]}")',
            "  else",
            '    AIT_ACTIVE_BIN=""',
            "  fi",
            "  export AIT_ACTIVE_BIN PATH",
            "}",
            "",
            "_ait_auto_path",
            "autoload -Uz add-zsh-hook 2>/dev/null || true",
            "add-zsh-hook -d chpwd _ait_auto_path 2>/dev/null || true",
            "add-zsh-hook chpwd _ait_auto_path 2>/dev/null || true",
            "",
            *_ait_command_function_lines(),
            "",
            "_ait_continue_reminder",
        ]
    )


def _bash_body() -> str:
    return "\n".join(
        [
            "_ait_remove_path_entry() {",
            '  local remove="$1" part new_path',
            '  local old_ifs="$IFS"',
            '  IFS=":"',
            "  for part in $PATH; do",
            '    [ "$part" = "$remove" ] && continue',
            '    new_path="${new_path:+$new_path:}$part"',
            "  done",
            '  IFS="$old_ifs"',
            '  PATH="$new_path"',
            "}",
            "",
            "_ait_auto_path() {",
            '  if [ -n "${AIT_ACTIVE_BIN:-}" ]; then',
            '    _ait_remove_path_entry "$AIT_ACTIVE_BIN"',
            "  fi",
            '  local candidate="$PWD/.ait/bin"',
            '  _ait_remove_path_entry "$candidate"',
            '  if [ -d "$candidate" ]; then',
            '    AIT_ACTIVE_BIN="$candidate"',
            '    PATH="$AIT_ACTIVE_BIN:$PATH"',
            "  else",
            '    AIT_ACTIVE_BIN=""',
            "  fi",
            "  export AIT_ACTIVE_BIN PATH",
            "}",
            "",
            "_ait_auto_path",
            'case ";${PROMPT_COMMAND:-};" in',
            '  *";_ait_auto_path;"*) ;;',
            '  *) PROMPT_COMMAND="_ait_auto_path${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;',
            "esac",
            "",
            *_ait_command_function_lines(),
            "",
            "_ait_continue_reminder",
        ]
    )


def _ait_command_function_lines() -> list[str]:
    return [
        "_ait_continue_should_cd() {",
        '  [ "${AIT_CONTINUE_AUTO_CD:-1}" = "0" ] && return 1',
        '  [ "${1:-}" = "continue" ] || return 1',
        "  shift",
        "  for ait_arg in \"$@\"; do",
        '    case "$ait_arg" in',
        "      --format|--format=*|--json|--no-interactive|--shell-hook|--help|-h)",
        "        return 1",
        "        ;;",
        "    esac",
        "  done",
        "  return 0",
        "}",
        "",
        "_ait_continue_reminder() {",
        '  [ "${AIT_CONTINUE_REMINDER:-1}" = "0" ] && return 0',
        '  [ -n "${AIT_CONTINUE_REMINDER_SHOWN:-}" ] && return 0',
        '  case "$-" in',
        "    *i*) ;;",
        "    *) return 0 ;;",
        "  esac",
        "  AIT_CONTINUE_REMINDER_SHOWN=1",
        "  export AIT_CONTINUE_REMINDER_SHOWN",
        "  command ait continue --shell-reminder 2>/dev/null || true",
        "}",
        "",
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
    ]


def install_shell_integration(
    *,
    shell: str | None = None,
    rc_path: str | Path | None = None,
) -> ShellIntegrationResult:
    shell_name = _normalize_shell(shell or os.environ.get("SHELL", ""))
    path = _resolve_rc_path(shell_name, rc_path)
    snippet = shell_snippet(shell_name)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if START_MARKER in existing and END_MARKER in existing:
        start = existing.find(START_MARKER)
        end = existing.find(END_MARKER)
        if end > start:
            end += len(END_MARKER)
            if end < len(existing) and existing[end] == "\n":
                end += 1
            current = existing[start:end]
            if current == snippet:
                return ShellIntegrationResult(shell=shell_name, rc_path=str(path), changed=False, snippet=snippet)
            updated = existing[:start] + snippet + existing[end:]
            path.write_text(updated, encoding="utf-8")
            return ShellIntegrationResult(shell=shell_name, rc_path=str(path), changed=True, snippet=snippet)
        return ShellIntegrationResult(shell=shell_name, rc_path=str(path), changed=False, snippet=snippet)
    path.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not existing or existing.endswith("\n") else "\n"
    path.write_text(f"{existing}{separator}{snippet}", encoding="utf-8")
    return ShellIntegrationResult(shell=shell_name, rc_path=str(path), changed=True, snippet=snippet)


def uninstall_shell_integration(
    *,
    shell: str | None = None,
    rc_path: str | Path | None = None,
) -> ShellIntegrationResult:
    shell_name = _normalize_shell(shell or os.environ.get("SHELL", ""))
    path = _resolve_rc_path(shell_name, rc_path)
    snippet = shell_snippet(shell_name)
    if not path.exists():
        return ShellIntegrationResult(shell=shell_name, rc_path=str(path), changed=False, snippet=snippet)
    existing = path.read_text(encoding="utf-8")
    start = existing.find(START_MARKER)
    end = existing.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        return ShellIntegrationResult(shell=shell_name, rc_path=str(path), changed=False, snippet=snippet)
    end += len(END_MARKER)
    if end < len(existing) and existing[end] == "\n":
        end += 1
    updated = existing[:start] + existing[end:]
    path.write_text(updated, encoding="utf-8")
    return ShellIntegrationResult(shell=shell_name, rc_path=str(path), changed=True, snippet=snippet)


def detect_user_shell() -> str | None:
    """Best-effort detection of the user's interactive shell name.

    Returns "zsh" or "bash" when recognised, otherwise None. Reads
    `$SHELL` from the environment without raising on unsupported values.
    """
    raw = os.environ.get("SHELL", "")
    name = Path(raw).name if raw else ""
    if name in {"zsh", "bash"}:
        return name
    return None


def is_shell_integration_installed(
    shell: str | None = None,
    *,
    rc_path: str | Path | None = None,
) -> bool:
    """Return True if the ait shell hook block is present in the rc file."""
    try:
        shell_name = _normalize_shell(shell or os.environ.get("SHELL", ""))
        path = _resolve_rc_path(shell_name, rc_path)
    except ShellIntegrationError:
        return False
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return START_MARKER in text and END_MARKER in text


def _resolve_rc_path(shell: str, rc_path: str | Path | None) -> Path:
    if rc_path is not None:
        return Path(rc_path).expanduser()
    if shell == "zsh":
        return _home_path() / ".zshrc"
    if shell == "bash":
        return _home_path() / ".bashrc"
    raise ShellIntegrationError(f"unsupported shell: {shell}")


def _home_path() -> Path:
    home = os.environ.get("HOME")
    if home:
        return Path(home).expanduser()
    return Path.home()


def _normalize_shell(shell: str) -> str:
    name = Path(shell).name
    if name in {"zsh", "bash"}:
        return name
    raise ShellIntegrationError(f"unsupported shell: {shell or '<unknown>'}")
