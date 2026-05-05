from __future__ import annotations

from pathlib import Path
import subprocess


def _semantic_exit_code(
    exit_code: int,
    *,
    transcript: str,
    workspace: Path,
    context_file: Path | None,
) -> int:
    if exit_code != 0:
        return exit_code
    if not _looks_like_agent_refusal(transcript):
        return exit_code
    if _has_workspace_changes(workspace, context_file=context_file):
        return exit_code
    return 3


def _looks_like_agent_refusal(transcript: str) -> bool:
    text = transcript.lower()
    refusal_markers = (
        "don't have permission",
        "do not have permission",
        "cannot make changes",
        "can't make changes",
        "cannot edit",
        "can't edit",
        "cannot write",
        "can't write",
        "permission denied",
        "operation not permitted",
        "refusing to",
        "i won't",
        "i cannot",
        "i can't",
        "unable to modify",
        "unable to write",
    )
    return any(marker in text for marker in refusal_markers)


def _has_workspace_changes(workspace: Path, *, context_file: Path | None) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    ignored = str(context_file.relative_to(workspace)) if context_file is not None else None
    for line in completed.stdout.splitlines():
        path = line[3:].strip()
        if ignored is not None and path == ignored:
            continue
        return True
    return False
