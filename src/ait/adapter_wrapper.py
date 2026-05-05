from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import sys

from ait.adapter_models import AdapterDoctorCheck, AdapterError, AgentAdapter


def _merge_envrc(path: Path) -> None:
    marker = "# ait: add repo-local adapter wrappers"
    path_line = "PATH_add .ait/bin"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if path_line in text.splitlines():
            return
        if text and not text.endswith("\n"):
            text += "\n"
    else:
        text = ""
    path.write_text(f"{text}{marker}\n{path_line}\n", encoding="utf-8")


def _envrc_has_wrapper_path(path: Path) -> bool:
    if not path.exists():
        return False
    return "PATH_add .ait/bin" in path.read_text(encoding="utf-8").splitlines()


def _real_claude_check(wrapper_path: Path) -> AdapterDoctorCheck:
    try:
        real_claude = _find_real_binary("claude", wrapper_path)
    except AdapterError as exc:
        return AdapterDoctorCheck("real_claude_binary", False, str(exc))
    return AdapterDoctorCheck("real_claude_binary", True, real_claude)


def _real_agent_binary_check(adapter: AgentAdapter, wrapper_path: Path) -> AdapterDoctorCheck:
    try:
        real_binary = _find_real_binary(adapter.command_name, wrapper_path)
    except AdapterError as exc:
        return AdapterDoctorCheck("real_agent_binary", False, str(exc))
    return AdapterDoctorCheck("real_agent_binary", True, real_binary)


def _find_real_binary(command_name: str, wrapper_path: Path) -> str:
    wrapper = wrapper_path
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / command_name
        if _same_file(candidate, wrapper):
            continue
        resolved = candidate.resolve()
        if _same_file(resolved, wrapper):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    found = shutil.which(command_name)
    if found is None:
        raise AdapterError(f"could not find {command_name} on PATH")
    if _same_file(Path(found), wrapper_path):
        raise AdapterError(f"could not find real {command_name} on PATH")
    return found


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return left.resolve(strict=False) == right.resolve(strict=False)


def _adapter_wrapper_script(adapter: AgentAdapter, real_binary: str) -> str:
    ait_executable = Path(sys.executable).with_name("ait")
    ait_command = str(ait_executable) if ait_executable.exists() else "ait"
    intent = {
        "claude-code": "Claude Code session",
        "aider": "Aider session",
        "codex": "Codex session",
    }.get(adapter.name, f"{adapter.name} session")
    commit_message = {
        "claude-code": "claude code changes",
        "aider": "aider changes",
        "codex": "codex changes",
    }.get(adapter.name, f"{adapter.name} changes")
    real_command = adapter.command_name
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        f"AIT_WRAPPER_ADAPTER={shlex.quote(adapter.name)}\n"
        f"AIT_WRAPPER_COMMAND={shlex.quote(real_command)}\n"
        f"AIT_WRAPPER_REAL_BINARY={shlex.quote(real_binary)}\n"
        f"AIT_WRAPPER_AIT_COMMAND={shlex.quote(ait_command)}\n"
        'AIT_WRAPPER_PATH="${0}"\n'
        'AIT_WRAPPER_REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"\n'
        "export AIT_WRAPPER_ADAPTER AIT_WRAPPER_COMMAND AIT_WRAPPER_REAL_BINARY AIT_WRAPPER_PATH AIT_WRAPPER_REPO\n"
        'if [ ! -x "$AIT_WRAPPER_REAL_BINARY" ]; then\n'
        '  printf "%s\\n" "ait wrapper failed: real ${AIT_WRAPPER_COMMAND} binary not found or not executable" >&2\n'
        '  printf "%s\\n" "adapter: ${AIT_WRAPPER_ADAPTER}" >&2\n'
        '  printf "%s\\n" "repo: ${AIT_WRAPPER_REPO}" >&2\n'
        '  printf "%s\\n" "wrapper: ${AIT_WRAPPER_PATH}" >&2\n'
        '  printf "%s\\n" "real_binary: ${AIT_WRAPPER_REAL_BINARY}" >&2\n'
        '  printf "%s\\n" "next: run ait status ${AIT_WRAPPER_ADAPTER}" >&2\n'
        "  exit 127\n"
        "fi\n"
        'if [ "$AIT_WRAPPER_REAL_BINARY" = "$AIT_WRAPPER_PATH" ]; then\n'
        '  printf "%s\\n" "ait wrapper failed: wrapper recursion detected" >&2\n'
        '  printf "%s\\n" "adapter: ${AIT_WRAPPER_ADAPTER}" >&2\n'
        '  printf "%s\\n" "repo: ${AIT_WRAPPER_REPO}" >&2\n'
        '  printf "%s\\n" "wrapper: ${AIT_WRAPPER_PATH}" >&2\n'
        '  printf "%s\\n" "real_binary: ${AIT_WRAPPER_REAL_BINARY}" >&2\n'
        '  printf "%s\\n" "next: run ait init --adapter ${AIT_WRAPPER_ADAPTER} --shell" >&2\n'
        "  exit 126\n"
        "fi\n"
        f': "${{AIT_INTENT:={intent}}}"\n'
        f': "${{AIT_COMMIT_MESSAGE:={commit_message}}}"\n'
        'if [ -t 0 ] && [ -t 1 ]; then\n'
        '  AIT_WRAPPER_FORMAT=text\n'
        "else\n"
        '  AIT_WRAPPER_FORMAT=json\n'
        "fi\n"
        'exec "$AIT_WRAPPER_AIT_COMMAND" '
        f"run --adapter {shlex.quote(adapter.name)} --format \"$AIT_WRAPPER_FORMAT\" "
        '--intent "$AIT_INTENT" --commit-message "$AIT_COMMIT_MESSAGE" -- '
        '"$AIT_WRAPPER_REAL_BINARY" "$@"\n'
    )
