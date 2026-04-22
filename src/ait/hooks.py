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
    cat > "$REPO_ROOT/.ait/post-rewrite.last"
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
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        configured = Path(result.stdout.strip())
        if not configured.is_absolute():
            configured = repo_root / configured
        return configured.resolve()
    return repo_root / ".git" / "hooks"
