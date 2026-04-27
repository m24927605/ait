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
        ]
    )


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


def _resolve_rc_path(shell: str, rc_path: str | Path | None) -> Path:
    if rc_path is not None:
        return Path(rc_path).expanduser()
    if shell == "zsh":
        return Path.home() / ".zshrc"
    if shell == "bash":
        return Path.home() / ".bashrc"
    raise ShellIntegrationError(f"unsupported shell: {shell}")


def _normalize_shell(shell: str) -> str:
    name = Path(shell).name
    if name in {"zsh", "bash"}:
        return name
    raise ShellIntegrationError(f"unsupported shell: {shell or '<unknown>'}")
