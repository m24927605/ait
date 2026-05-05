from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
from typing import Any


class PythonEnvError(RuntimeError):
    """Raised when Python project environment provisioning fails."""


@dataclass(frozen=True, slots=True)
class LocalPathDependency:
    name: str
    path: str
    source: str


@dataclass(frozen=True, slots=True)
class SymlinkRecord:
    link: str
    target: str
    dependency: str


@dataclass(frozen=True, slots=True)
class PythonEnvironmentResult:
    is_python_project: bool
    is_poetry_project: bool
    path_dependencies: tuple[LocalPathDependency, ...]
    symlinks: tuple[SymlinkRecord, ...]
    interpreter_path: str | None
    metadata_path: Path | None


LOCAL_EXCLUDE_ENTRIES = (
    ".venv/",
    ".vscode/",
    "poetry.toml",
)


def prepare_python_project_environment(
    repo_root: str | Path,
    worktree_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
) -> PythonEnvironmentResult:
    root = Path(repo_root).resolve()
    workspace = Path(worktree_path).resolve()
    pyproject = workspace / "pyproject.toml"
    if not pyproject.exists():
        return PythonEnvironmentResult(False, False, (), (), None, None)

    data = _read_pyproject(pyproject)
    path_dependencies = tuple(_iter_poetry_path_dependencies(data))
    is_poetry_project = _is_poetry_project(data)
    _ensure_git_local_excludes(workspace)
    symlinks = _repair_local_path_dependencies(root, workspace, path_dependencies)

    record_path = Path(metadata_path).resolve() if metadata_path is not None else None
    interpreter_path: str | None = None
    try:
        if is_poetry_project and os.environ.get("AIT_SKIP_PYTHON_ENV_SETUP") != "1":
            interpreter_path = _prepare_poetry_environment(workspace)
        elif is_poetry_project:
            interpreter_path = _poetry_in_project_python(workspace)

        if interpreter_path:
            _write_vscode_settings(workspace, interpreter_path)

        if record_path is not None:
            record_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": 1,
                "worktree_path": str(workspace),
                "is_python_project": True,
                "is_poetry_project": is_poetry_project,
                "path_dependencies": [asdict(dep) for dep in path_dependencies],
                "symlinks": [asdict(link) for link in symlinks],
                "interpreter_path": interpreter_path,
            }
            record_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        for link in symlinks:
            link_path = Path(link.link)
            if link_path.is_symlink():
                link_path.unlink()
        if record_path is not None:
            record_path.unlink(missing_ok=True)
        raise

    return PythonEnvironmentResult(
        is_python_project=True,
        is_poetry_project=is_poetry_project,
        path_dependencies=path_dependencies,
        symlinks=symlinks,
        interpreter_path=interpreter_path,
        metadata_path=record_path,
    )


def cleanup_python_project_environment(metadata_path: str | Path) -> None:
    path = Path(metadata_path)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return
    for item in data.get("symlinks", []):
        link = Path(str(item.get("link", "")))
        if link.is_symlink():
            link.unlink()
            _remove_empty_parents(link.parent, stop=path.parent)
    path.unlink(missing_ok=True)


def determine_vscode_interpreter(worktree_path: str | Path) -> str | None:
    workspace = Path(worktree_path).resolve()
    in_project = _poetry_in_project_python(workspace)
    if Path(in_project).exists():
        return in_project
    poetry = shutil.which("poetry")
    if not poetry:
        return None
    completed = _run(
        [poetry, "env", "info", "--path"],
        cwd=workspace,
        check=False,
    )
    if completed.returncode != 0:
        return None
    env_path = completed.stdout.strip()
    if not env_path:
        return None
    candidate = Path(env_path) / _python_executable_relative()
    return str(candidate) if candidate.exists() else None


def _read_pyproject(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PythonEnvError(f"invalid pyproject.toml in {path}: {exc}") from exc


def _is_poetry_project(data: dict[str, Any]) -> bool:
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return False
    poetry = tool.get("poetry")
    return isinstance(poetry, dict)


def _iter_poetry_path_dependencies(data: dict[str, Any]) -> list[LocalPathDependency]:
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return []
    poetry = tool.get("poetry")
    if not isinstance(poetry, dict):
        return []

    dependencies: list[LocalPathDependency] = []
    dependencies.extend(_path_dependencies_from_table(poetry.get("dependencies"), "tool.poetry.dependencies"))
    dependencies.extend(
        _path_dependencies_from_table(poetry.get("dev-dependencies"), "tool.poetry.dev-dependencies")
    )
    groups = poetry.get("group")
    if isinstance(groups, dict):
        for group_name, group in groups.items():
            if isinstance(group, dict):
                dependencies.extend(
                    _path_dependencies_from_table(
                        group.get("dependencies"),
                        f"tool.poetry.group.{group_name}.dependencies",
                    )
                )
    return dependencies


def _path_dependencies_from_table(value: object, source: str) -> list[LocalPathDependency]:
    if not isinstance(value, dict):
        return []
    dependencies: list[LocalPathDependency] = []
    for name, spec in value.items():
        if not isinstance(spec, dict):
            continue
        path_value = spec.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            continue
        dep_path = path_value.strip()
        if Path(dep_path).is_absolute():
            continue
        dependencies.append(LocalPathDependency(name=str(name), path=dep_path, source=source))
    return dependencies


def _repair_local_path_dependencies(
    repo_root: Path,
    worktree_path: Path,
    dependencies: tuple[LocalPathDependency, ...],
) -> tuple[SymlinkRecord, ...]:
    symlinks: list[SymlinkRecord] = []
    for dependency in dependencies:
        expected_in_worktree = (worktree_path / dependency.path).resolve(strict=False)
        if expected_in_worktree.exists():
            continue
        source_layout_target = (repo_root / dependency.path).resolve(strict=False)
        if not source_layout_target.exists():
            raise PythonEnvError(
                "local path dependency cannot be resolved: "
                f"{dependency.name} path={dependency.path!r}; "
                f"missing in worktree at {expected_in_worktree} and missing in source layout at {source_layout_target}"
            )
        expected_in_worktree.parent.mkdir(parents=True, exist_ok=True)
        if expected_in_worktree.exists() or expected_in_worktree.is_symlink():
            raise PythonEnvError(f"cannot repair path dependency over existing path: {expected_in_worktree}")
        expected_in_worktree.symlink_to(source_layout_target, target_is_directory=source_layout_target.is_dir())
        symlinks.append(
            SymlinkRecord(
                link=str(expected_in_worktree),
                target=str(source_layout_target),
                dependency=dependency.name,
            )
        )
    return tuple(symlinks)


def _prepare_poetry_environment(worktree_path: Path) -> str:
    poetry = shutil.which("poetry")
    if not poetry:
        raise PythonEnvError("Poetry project detected, but 'poetry' was not found on PATH.")

    # A root checkout venv can contain editable installs pointing at the root,
    # so AIT uses a worktree-local venv for attempt isolation.
    _run_checked([poetry, "config", "virtualenvs.in-project", "true", "--local"], cwd=worktree_path)
    _run_checked([poetry, "check"], cwd=worktree_path)
    _run_checked([poetry, "install"], cwd=worktree_path)

    interpreter = determine_vscode_interpreter(worktree_path)
    if interpreter is None:
        env_path = _run_checked([poetry, "env", "info", "--path"], cwd=worktree_path).stdout.strip()
        raise PythonEnvError(f"Poetry environment was created but no Python interpreter was found under {env_path!r}.")
    return interpreter


def _write_vscode_settings(worktree_path: Path, interpreter_path: str) -> None:
    settings_path = worktree_path / ".vscode" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    else:
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    settings["python.defaultInterpreterPath"] = interpreter_path
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _ensure_git_local_excludes(worktree_path: Path) -> None:
    completed = _run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=worktree_path, check=True)
    exclude_path = Path(completed.stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = worktree_path / exclude_path
    existing = exclude_path.read_text(encoding="utf-8").splitlines() if exclude_path.exists() else []
    additions = [entry for entry in LOCAL_EXCLUDE_ENTRIES if entry not in {line.strip() for line in existing}]
    if not additions:
        return
    lines = list(existing)
    if lines and lines[-1] != "":
        lines.append("")
    lines.extend(additions)
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    exclude_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _poetry_in_project_python(worktree_path: Path) -> str:
    return str(worktree_path / ".venv" / _python_executable_relative())


def _python_executable_relative() -> Path:
    return Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")


def _run_checked(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    completed = _run(args, cwd=cwd, check=False)
    if completed.returncode != 0:
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        raise PythonEnvError(f"command failed in {cwd}: {' '.join(args)}\n{output}")
    return completed


def _run(
    args: list[str],
    *,
    cwd: Path,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        output = "\n".join(part for part in ((exc.stdout or "").strip(), (exc.stderr or "").strip()) if part)
        raise PythonEnvError(f"command failed in {cwd}: {' '.join(args)}\n{output}") from exc


def _remove_empty_parents(path: Path, *, stop: Path) -> None:
    current = path
    stop_resolved = stop.resolve()
    while current != stop_resolved and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
