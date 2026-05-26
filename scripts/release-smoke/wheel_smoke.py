from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", default="dist")
    parser.add_argument("--wheel")
    args = parser.parse_args(argv)
    wheel = Path(args.wheel).resolve() if args.wheel else _latest_wheel(Path(args.dist_dir))
    if wheel is None:
        print(f"release wheel smoke error: no wheel found in {args.dist_dir}", file=sys.stderr)
        return 1
    if shutil.which("git") is None:
        print("release wheel smoke error: git is required", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="ait-wheel-smoke-") as tmp:
        root = Path(tmp)
        venv_dir = root / "venv"
        repo = root / "repo"
        home = root / "home"
        home.mkdir()
        repo.mkdir()
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = _venv_bin(venv_dir, "python")
        ait = _venv_bin(venv_dir, "ait")
        env = _isolated_env(home=home, state_dir=root / "ait-state")
        _run([str(python), "-m", "pip", "install", "--no-cache-dir", str(wheel)], env=env)
        _run(["git", "config", "--global", "user.email", "release-smoke@ait.test"], env=env)
        _run(["git", "config", "--global", "user.name", "AIT Release Smoke"], env=env)
        _run([str(ait), "--version"], cwd=repo, env=env)
        init = _run_json([str(ait), "init", "--no-shell-install", "--format", "json"], cwd=repo, env=env)
        if not init.get("git_initialized"):
            raise RuntimeError(f"ait init did not initialize a fresh git repo: {init}")
        _run([str(ait), "status", "--no-interactive"], cwd=repo, env=env)
        _run_json(
            [
                str(ait),
                "run",
                "--adapter",
                "shell",
                "--intent",
                "Release wheel smoke",
                "--commit-message",
                "release smoke",
                "--stdin",
                "none",
                "--format",
                "json",
                "--",
                str(python),
                "-c",
                "from pathlib import Path; Path('release-smoke.txt').write_text('ok\\n')",
            ],
            cwd=repo,
            env=env,
        )
        apply_payload = _run_json(
            [str(ait), "apply", "latest", "--no-interactive", "--format", "json"],
            cwd=repo,
            env=env,
        )
        if apply_payload.get("status") not in {"applied", "already_applied"}:
            raise RuntimeError(f"ait apply latest did not apply the smoke result: {apply_payload}")
        if (repo / "release-smoke.txt").read_text(encoding="utf-8") != "ok\n":
            raise RuntimeError("ait apply latest did not land release-smoke.txt")
    print("release wheel smoke ok")
    return 0


def _latest_wheel(dist_dir: Path) -> Path | None:
    wheels = sorted(dist_dir.glob("ait_vcs-*.whl"), key=lambda path: path.stat().st_mtime)
    return wheels[-1].resolve() if wheels else None


def _venv_bin(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        suffix = ".exe" if name in {"python", "ait"} else ""
        return venv_dir / "Scripts" / f"{name}{suffix}"
    return venv_dir / "bin" / name


def _isolated_env(*, home: Path, state_dir: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"}
    }
    env["HOME"] = str(home)
    env["AIT_STATE_DIR"] = str(state_dir)
    return env


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"{command[0]} failed with exit code {result.returncode}")
    return result


def _run_json(command: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, object]:
    result = _run(command, cwd=cwd, env=env)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{command[0]} did not output JSON: {result.stdout}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{command[0]} JSON output was not an object: {payload!r}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
