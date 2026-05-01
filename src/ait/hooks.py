from __future__ import annotations

from pathlib import Path
import subprocess

HOOK_MARKER_START = "# >>> ait post-rewrite hook >>>"
HOOK_MARKER_END = "# <<< ait post-rewrite hook <<<"

HOOK_SNIPPET = """# >>> ait post-rewrite hook >>>
if [ -x "$(command -v python3)" ]; then
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
  if [ -n "$REPO_ROOT" ]; then
    mkdir -p "$REPO_ROOT/.ait"
    cat >> "$REPO_ROOT/.ait/post-rewrite.last"
    : > "$REPO_ROOT/.ait/manual-reconcile-required"
  fi
fi
# <<< ait post-rewrite hook <<<
"""


def install_post_rewrite_hook(repo_root: str | Path) -> Path:
    root = Path(repo_root).resolve()
    hooks_dir = _resolve_hooks_dir(root)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "post-rewrite"

    existing = hook_path.read_text(encoding="utf-8") if hook_path.exists() else ""
    if HOOK_MARKER_START in existing and HOOK_MARKER_END in existing:
        return hook_path

    content = existing
    if content and not content.endswith("\n"):
        content += "\n"
    if not content.startswith("#!"):
        content = "#!/bin/sh\n" + content
    content += HOOK_SNIPPET
    hook_path.write_text(content, encoding="utf-8")
    hook_path.chmod(0o755)
    return hook_path


def _resolve_hooks_dir(repo_root: Path) -> Path:
    # Honour core.hooksPath when explicitly configured.
    configured = _git_config_get(repo_root, "core.hooksPath")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = repo_root / path
        return path.resolve()

    # Fall back to the shared git-common-dir so this works in both normal
    # checkouts and worktrees. In a worktree `.git` is a file, so the naive
    # `<repo_root>/.git/hooks` path does not exist; git-common-dir points at
    # the main repository's `.git/` which is shared across all worktrees.
    common = _git_rev_parse(repo_root, "--git-common-dir")
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (repo_root / common_path).resolve()
    return common_path / "hooks"


def _git_config_get(repo_root: Path, key: str) -> str:
    result = subprocess.run(
        ["git", "config", "--get", key],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _git_rev_parse(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
