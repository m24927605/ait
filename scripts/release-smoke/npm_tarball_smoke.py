from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", default="npm/ait-vcs")
    parser.add_argument("--dist-dir", default="dist")
    parser.add_argument("--wheel")
    args = parser.parse_args(argv)
    package_dir = Path(args.package_dir).resolve()
    wheel = Path(args.wheel).resolve() if args.wheel else _latest_wheel(Path(args.dist_dir))
    if wheel is None:
        print(f"npm tarball smoke error: no wheel found in {args.dist_dir}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="ait-npm-smoke-") as tmp:
        root = Path(tmp)
        pack_dir = root / "pack"
        prefix = root / "prefix"
        home = root / "home"
        pack_dir.mkdir()
        prefix.mkdir()
        home.mkdir()
        pack_payload = _run_json(
            ["npm", "pack", "--json", "--pack-destination", str(pack_dir)],
            cwd=package_dir,
        )
        if not pack_payload:
            raise RuntimeError("npm pack did not report a tarball")
        tarball = pack_dir / str(pack_payload[0]["filename"])
        env = {
            **os.environ,
            "HOME": str(home),
            "AIT_NPM_PIP_SPEC": str(wheel),
            "AIT_NPM_SKIP_PIP_UPGRADE": "1",
        }
        _run(["npm", "install", "--global", "--prefix", str(prefix), str(tarball)], env=env)
        ait = prefix / ("ait.cmd" if os.name == "nt" else "bin/ait")
        if os.name == "nt":
            ait = prefix / "ait.cmd"
        _run([str(ait), "--version"], env={**env, "AIT_STATE_DIR": str(root / "ait-state")})
    print("npm tarball smoke ok")
    return 0


def _latest_wheel(dist_dir: Path) -> Path | None:
    wheels = sorted(dist_dir.glob("ait_vcs-*.whl"), key=lambda path: path.stat().st_mtime)
    return wheels[-1].resolve() if wheels else None


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


def _run_json(command: list[str], *, cwd: Path) -> list[dict[str, object]]:
    result = _run(command, cwd=cwd)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{command[0]} did not output JSON: {result.stdout}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"{command[0]} JSON output was not a list: {payload!r}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
