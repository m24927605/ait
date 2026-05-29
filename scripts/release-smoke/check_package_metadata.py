from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    errors = _metadata_errors(REPO_ROOT)
    if errors:
        for error in errors:
            print(f"release metadata error: {error}", file=sys.stderr)
        return 1
    print("release metadata ok")
    return 0


def _metadata_errors(repo_root: Path) -> list[str]:
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((repo_root / "npm" / "ait-vcs" / "package.json").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    errors: list[str] = []
    if project.get("name") != package.get("name"):
        errors.append(f"project.name {project.get('name')!r} != npm name {package.get('name')!r}")
    if project.get("version") != package.get("version"):
        errors.append(f"project.version {project.get('version')!r} != npm version {package.get('version')!r}")
    if project.get("description") != package.get("description"):
        errors.append("pyproject and npm descriptions differ")
    if project.get("requires-python") != ">=3.11":
        errors.append("pyproject requires-python must remain honest as >=3.11 for this slice")
    if package.get("bin", {}).get("ait") != "bin/ait.js":
        errors.append("npm package must expose ait via bin/ait.js")
    package_files = set(package.get("files", []))
    for expected in {"bin/", "scripts/", "README.md"}:
        if expected not in package_files:
            errors.append(f"npm package files missing {expected}")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    if ref_type == "tag" and ref_name:
        tag_version = ref_name.removeprefix("v")
        if tag_version != project.get("version"):
            errors.append(f"git tag {ref_name!r} does not match package version {project.get('version')!r}")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
