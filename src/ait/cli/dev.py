from __future__ import annotations

import shlex

from ._shared import *

from ait.dev_server import (
    DEFAULT_DEV_PORTS,
    DevServerError,
    check_preview_url,
    guard_preview_port,
    inspect_port,
    list_dev_servers,
    require_current_ait_worktree,
    start_dev_server,
    stop_dev_server,
)


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command != "dev":
        if parser is not None:
            parser.print_help()
        return 1
    try:
        if args.dev_command == "status":
            ports = tuple(args.ports or DEFAULT_DEV_PORTS)
            try:
                require_current_ait_worktree(repo_root)
                guards = [guard_preview_port(repo_root, port) for port in ports]
            except DevServerError:
                guards = [
                    {
                        "ok": True,
                        "port": port,
                        "worktree_path": None,
                        "process": (
                            None if (process := inspect_port(port)) is None else asdict(process)
                        ),
                        "message": "",
                        "fix_commands": [],
                    }
                    for port in ports
                ]
            records = list_dev_servers(repo_root)
            payload = {
                "ports": [
                    item if isinstance(item, dict) else _guard_to_dict(item) for item in guards
                ],
                "servers": [asdict(item) for item in records],
            }
            if args.format == "json":
                print(json.dumps(payload, indent=2))
            else:
                print(_format_dev_status(payload))
            return (
                0
                if all(item["ok"] or item["process"] is None for item in payload["ports"])
                else 2
            )
        if args.dev_command == "preview":
            result = check_preview_url(repo_root, args.url, file_path=args.file)
            if args.format == "json":
                print(json.dumps(_preview_to_dict(result), indent=2))
            else:
                print(result.message)
                if not result.ok:
                    for command in result.port_guard.fix_commands:
                        print(f"  {command}")
            return 0 if result.ok else 2
        if args.dev_command == "run":
            command = _strip_separator(args.dev_run_command)
            records = start_dev_server(
                repo_root,
                tuple(command),
                ports=tuple(args.ports or DEFAULT_DEV_PORTS),
            )
            if args.format == "json":
                print(json.dumps([asdict(item) for item in records], indent=2))
            else:
                print(_format_started(records))
            return 0
        if args.dev_command == "stop":
            killed = stop_dev_server(repo_root, port=args.port, force=args.force)
            if args.format == "json":
                print(json.dumps({"killed_pids": list(killed)}, indent=2))
            else:
                stopped = ", ".join(str(pid) for pid in killed) or "none"
                print("Stopped dev server pids: " + stopped)
            return 0
    except DevServerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if parser is not None:
        parser.print_help()
    return 1


def _strip_separator(command: list[str]) -> list[str]:
    return command[1:] if command and command[0] == "--" else command


def _guard_to_dict(item) -> dict[str, object]:
    return {
        "ok": item.ok,
        "port": item.port,
        "worktree_path": item.worktree_path,
        "process": None if item.process is None else asdict(item.process),
        "message": item.message,
        "fix_commands": list(item.fix_commands),
    }


def _preview_to_dict(item) -> dict[str, object]:
    return {
        "ok": item.ok,
        "url": item.url,
        "file_path": item.file_path,
        "http_status": item.http_status,
        "message": item.message,
        "port_guard": _guard_to_dict(item.port_guard),
    }


def _format_dev_status(payload: dict[str, object]) -> str:
    lines = ["AIT dev server status"]
    servers = payload["servers"]
    if servers:
        lines.append("Managed servers:")
        for item in servers:
            lines.append(
                "  "
                f"port={item['port'] or '?'} "
                f"pid={item['pid']} "
                f"cwd={item['cwd']} "
                f"branch={item.get('branch') or '-'}"
            )
    else:
        lines.append("Managed servers: none")
    lines.append("Ports:")
    for item in payload["ports"]:
        process = item["process"]
        if process:
            lines.append(f"  {item['port']}: pid={process['pid']} cwd={process.get('cwd')}")
        else:
            lines.append(f"  {item['port']}: free")
        if not item["ok"] and process:
            lines.append("    " + str(item["message"]).replace("\n", "\n    "))
    return "\n".join(lines)


def _format_started(records) -> str:
    lines = ["Started AIT dev server"]
    for record in records:
        lines.append(f"  pid: {record.pid}")
        lines.append(f"  port: {record.port or 'unknown'}")
        lines.append(f"  cwd: {record.cwd}")
        lines.append(f"  command: {' '.join(shlex.quote(part) for part in record.command)}")
        if record.log_path:
            lines.append(f"  log: {record.log_path}")
    return "\n".join(lines)
