"""Smoke a built `ait` binary in a hermetic tmpdir.

Usage:
    python scripts/release-smoke/binary_smoke.py path/to/ait
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


class SmokeFailure(RuntimeError):
    pass


def smoke(binary_path: Path) -> int:
    """Return 0 on success; raise SmokeFailure on any check failure."""
    with tempfile.TemporaryDirectory() as td:
        env = {
            "HOME": td,
            "XDG_CONFIG_HOME": td,
            "XDG_STATE_HOME": td,
            "AIT_BUG_REPORT": "never",
            "PATH": os.environ.get("PATH", ""),
        }

        # 1. --version returns success
        r = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True, env=env, text=True, timeout=15,
        )
        if r.returncode != 0:
            raise SmokeFailure(
                f"--version failed: rc={r.returncode}\nstderr:\n{r.stderr}"
            )
        if "ait" not in (r.stdout or ""):
            raise SmokeFailure(f"--version output missing 'ait': {r.stdout!r}")

        # 2. bug-report list works
        r = subprocess.run(
            [str(binary_path), "bug-report", "list"],
            capture_output=True, env=env, text=True, timeout=15,
        )
        if r.returncode != 0:
            raise SmokeFailure(
                f"bug-report list failed: rc={r.returncode}\nstderr:\n{r.stderr}"
            )

        # 3. init in a fresh repo
        repo = Path(td) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), check=True,
                       capture_output=True)
        r = subprocess.run(
            [str(binary_path), "init"],
            cwd=str(repo), capture_output=True, env=env, text=True, timeout=15,
        )
        if r.returncode != 0:
            raise SmokeFailure(
                f"init failed: rc={r.returncode}\nstderr:\n{r.stderr}"
            )
        if not (repo / ".ait").exists():
            raise SmokeFailure(".ait directory not created by init")

    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: binary_smoke.py <binary_path>", file=sys.stderr)
        return 2
    try:
        return smoke(Path(sys.argv[1]))
    except SmokeFailure as exc:
        print(f"binary smoke FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
