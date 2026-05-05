from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from ait.repo import resolve_repo_root

DEFAULT_DEV_PORTS = (8003, 8004, 8010, 8030)


class DevServerError(RuntimeError):
    """Raised when a dev server action is unsafe or cannot be completed."""


@dataclass(frozen=True, slots=True)
class PortProcess:
    port: int
    pid: int
    cwd: str | None
    command: str | None = None


@dataclass(frozen=True, slots=True)
class DevServerRecord:
    port: int
    pid: int
    command: tuple[str, ...]
    cwd: str
    branch: str | None
    worktree_path: str
    started_at: str
    log_path: str | None = None


@dataclass(frozen=True, slots=True)
class PortGuardResult:
    ok: bool
    port: int
    worktree_path: str
    process: PortProcess | None
    message: str
    fix_commands: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreviewCheckResult:
    ok: bool
    url: str
    file_path: str | None
    port_guard: PortGuardResult
    http_status: int | None
    message: str


PortInspector = Callable[[int], PortProcess | None]


def current_git_toplevel(cwd: str | Path) -> Path:
    completed = _run_git(Path(cwd).resolve(), "rev-parse", "--show-toplevel")
    return Path(completed).resolve()


def current_branch(cwd: str | Path) -> str | None:
    branch = _run_git(Path(cwd).resolve(), "branch", "--show-current", allow_failure=True)
    return branch or None


def require_current_ait_worktree(cwd: str | Path) -> Path:
    root = resolve_repo_root(cwd)
    worktree = current_git_toplevel(cwd)
    workspaces_root = (root / ".ait" / "workspaces").resolve()
    try:
        worktree.relative_to(workspaces_root)
    except ValueError as exc:
        raise DevServerError(
            "AIT dev server commands must be run from an AIT attempt worktree.\n"
            f"Current checkout is: {worktree}\n"
            f"AIT workspaces live under: {workspaces_root}\n"
            f"Open the worktree in VS Code with: code <ait-worktree-path>"
        ) from exc
    return worktree


def inspect_port(port: int) -> PortProcess | None:
    pids = _pids_for_port(port)
    if not pids:
        return None
    pid = pids[0]
    return PortProcess(
        port=port,
        pid=pid,
        cwd=_cwd_for_pid(pid),
        command=_command_for_pid(pid),
    )


def guard_preview_port(
    cwd: str | Path,
    port: int,
    *,
    inspector: PortInspector = inspect_port,
) -> PortGuardResult:
    worktree = require_current_ait_worktree(cwd)
    process = inspector(port)
    if process is None:
        return PortGuardResult(
            ok=False,
            port=port,
            worktree_path=str(worktree),
            process=None,
            message=(
                f"Port {port} is not serving anything. Start the dev server from the AIT "
                f"worktree first: cd {shlex.quote(str(worktree))} "
                f"&& ait run --port {port} -- <command>"
            ),
            fix_commands=(
                f"cd {shlex.quote(str(worktree))} && ait run --port {port} -- <command>",
            ),
        )
    process_cwd = Path(process.cwd).resolve() if process.cwd else None
    if process_cwd is not None and _path_is_inside(process_cwd, worktree):
        return PortGuardResult(
            ok=True,
            port=port,
            worktree_path=str(worktree),
            process=process,
            message=f"Port {port} is serving from the current AIT worktree: {worktree}",
            fix_commands=(),
        )
    return PortGuardResult(
        ok=False,
        port=port,
        worktree_path=str(worktree),
        process=process,
        message=(
            f"Port {port} is serving from:\n"
            f"  {process.cwd or '<unknown cwd>'}\n"
            f"Current AIT worktree is:\n"
            f"  {worktree}\n"
            "This preview will not include your AIT changes."
        ),
        fix_commands=(
            f"ait dev stop --port {port} --force",
            f"cd {shlex.quote(str(worktree))} && ait run --port {port} -- <command>",
            f"code {shlex.quote(str(worktree))}",
        ),
    )


def check_preview_url(
    cwd: str | Path,
    url: str,
    *,
    file_path: str | None = None,
    inspector: PortInspector = inspect_port,
    fetch: Callable[[str], int] | None = None,
) -> PreviewCheckResult:
    port = _port_from_url(url)
    guard = guard_preview_port(cwd, port, inspector=inspector)
    worktree = Path(guard.worktree_path)
    if file_path is not None and not (worktree / file_path).exists():
        return PreviewCheckResult(
            ok=False,
            url=url,
            file_path=file_path,
            port_guard=guard,
            http_status=None,
            message=f"Preview file does not exist in the AIT worktree: {worktree / file_path}",
        )
    if not guard.ok:
        return PreviewCheckResult(
            ok=False,
            url=url,
            file_path=file_path,
            port_guard=guard,
            http_status=None,
            message=guard.message,
        )
    status = (fetch or _fetch_status)(url)
    if status == 404:
        return PreviewCheckResult(
            ok=False,
            url=url,
            file_path=file_path,
            port_guard=guard,
            http_status=status,
            message=(
                f"{url} returned 404 even though port {port} is serving from the current worktree. "
                "Check the app static route and server configuration."
            ),
        )
    return PreviewCheckResult(
        ok=200 <= status < 400,
        url=url,
        file_path=file_path,
        port_guard=guard,
        http_status=status,
        message=f"{url} returned HTTP {status} from the current AIT worktree.",
    )


def start_dev_server(
    cwd: str | Path,
    command: tuple[str, ...],
    *,
    ports: tuple[int, ...] = DEFAULT_DEV_PORTS,
    inspector: PortInspector = inspect_port,
) -> tuple[DevServerRecord, ...]:
    if not command:
        raise DevServerError("dev server command must not be empty")
    worktree = require_current_ait_worktree(cwd)
    conflicts = [guard_preview_port(worktree, port, inspector=inspector) for port in ports]
    occupied = [item for item in conflicts if item.process is not None]
    if occupied:
        messages: list[str] = []
        fixes: list[str] = []
        for item in occupied:
            if item.ok:
                pid = item.process.pid if item.process is not None else "?"
                messages.append(
                    f"Port {item.port} is already serving from the current AIT worktree "
                    f"(pid {pid})."
                )
            else:
                messages.append(item.message)
                fixes.extend(item.fix_commands)
        fix_text = "\n".join(f"  {command}" for command in fixes)
        suffix = f"\n\nFix commands:\n{fix_text}" if fix_text else ""
        raise DevServerError("\n\n".join(messages) + suffix)

    repo_root = resolve_repo_root(worktree)
    log_dir = repo_root / ".ait" / "dev-servers"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"{worktree.name}-{stamp}.log"
    log_file = log_path.open("ab")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=worktree,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_file.close()

    time.sleep(1.0)
    if process.poll() is not None:
        raise DevServerError(
            f"dev server command exited with code {process.returncode}; see log: {log_path}"
        )

    started_at = datetime.now(UTC).isoformat()
    records: list[DevServerRecord] = []
    for port in ports:
        owner = inspector(port)
        if owner is None:
            continue
        owner_cwd = Path(owner.cwd).resolve() if owner.cwd else None
        if owner.pid != process.pid and (
            owner_cwd is None or not _path_is_inside(owner_cwd, worktree)
        ):
            continue
        records.append(
            DevServerRecord(
                port=port,
                pid=owner.pid,
                command=command,
                cwd=str(worktree),
                branch=current_branch(worktree),
                worktree_path=str(worktree),
                started_at=started_at,
                log_path=str(log_path),
            )
        )
    if not records:
        records.append(
            DevServerRecord(
                port=0,
                pid=process.pid,
                command=command,
                cwd=str(worktree),
                branch=current_branch(worktree),
                worktree_path=str(worktree),
                started_at=started_at,
                log_path=str(log_path),
            )
        )
    _upsert_records(repo_root, tuple(records))
    return tuple(records)


def list_dev_servers(repo_root: str | Path) -> tuple[DevServerRecord, ...]:
    return tuple(_load_records(resolve_repo_root(repo_root)))


def stop_dev_server(
    repo_root: str | Path,
    *,
    port: int | None = None,
    force: bool = False,
    inspector: PortInspector = inspect_port,
) -> tuple[int, ...]:
    root = resolve_repo_root(repo_root)
    records = _load_records(root)
    targets = [record for record in records if port is None or record.port == port]
    killed: list[int] = []
    for record in targets:
        if _terminate_pid(record.pid):
            killed.append(record.pid)
    if port is not None and force:
        owner = inspector(port)
        if owner is not None and owner.pid not in killed:
            if _terminate_pid(owner.pid, process_group=False):
                killed.append(owner.pid)
    remaining = [record for record in records if record.pid not in set(killed)]
    _write_records(root, remaining)
    return tuple(killed)


def cleanup_dev_servers_for_worktree(worktree_path: str | Path) -> tuple[int, ...]:
    worktree = Path(worktree_path).resolve()
    root = resolve_repo_root(worktree)
    records = [
        record for record in _load_records(root) if Path(record.worktree_path).resolve() == worktree
    ]
    killed: list[int] = []
    for record in records:
        if _terminate_pid(record.pid):
            killed.append(record.pid)
    remaining = [
        record for record in _load_records(root) if Path(record.worktree_path).resolve() != worktree
    ]
    _write_records(root, remaining)
    return tuple(killed)


def _records_path(repo_root: Path) -> Path:
    return repo_root / ".ait" / "dev-servers.json"


def _load_records(repo_root: Path) -> list[DevServerRecord]:
    path = _records_path(repo_root)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    records: list[DevServerRecord] = []
    for item in data.get("servers", []):
        records.append(
            DevServerRecord(
                port=int(item.get("port", 0)),
                pid=int(item["pid"]),
                command=tuple(str(part) for part in item.get("command", [])),
                cwd=str(item["cwd"]),
                branch=str(item["branch"]) if item.get("branch") is not None else None,
                worktree_path=str(item["worktree_path"]),
                started_at=str(item["started_at"]),
                log_path=str(item["log_path"]) if item.get("log_path") is not None else None,
            )
        )
    return records


def _write_records(repo_root: Path, records: list[DevServerRecord]) -> None:
    path = _records_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "servers": [asdict(record) for record in records]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _upsert_records(repo_root: Path, records: tuple[DevServerRecord, ...]) -> None:
    existing = [
        record
        for record in _load_records(repo_root)
        if (record.pid, record.port) not in {(item.pid, item.port) for item in records}
    ]
    existing.extend(records)
    _write_records(repo_root, existing)


def _pids_for_port(port: int) -> list[int]:
    result = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _cwd_for_pid(pid: int) -> str | None:
    result = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def _command_for_pid(pid: int) -> str | None:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_pid(pid: int, *, process_group: bool = True) -> bool:
    if not _pid_alive(pid):
        return False
    try:
        if process_group:
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except PermissionError:
        raise
    except OSError:
        os.kill(pid, signal.SIGTERM)
    return True


def _path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _run_git(cwd: Path, *args: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if allow_failure:
            return ""
        raise DevServerError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _port_from_url(url: str) -> int:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    raise DevServerError(f"preview URL must include http or https scheme: {url}")


def _fetch_status(url: str) -> int:
    try:
        with urlopen(url, timeout=5.0) as response:  # nosec B310 - user-provided local preview URL.
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
    except URLError as exc:
        raise DevServerError(f"unable to fetch preview URL {url}: {exc}") from exc
