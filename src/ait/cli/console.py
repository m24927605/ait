from __future__ import annotations

from ._shared import *

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import tempfile

from ait.console_actions import run_console_action
from ait.report import DAILY_CONSOLE_SCHEMA, DAILY_CONSOLE_SCHEMA_VERSION, build_work_graph, write_daily_console_html


def handle(args, repo_root: Path, parser=None) -> int:
    if getattr(args, "console_command", None) == "action":
        return _handle_console_action(args, repo_root)
    host = str(args.host or "127.0.0.1")
    if args.serve_local and not _loopback_host(host):
        return _console_error(args.format, f"console host must be loopback-only, got {host!r}", exit_code=2)
    try:
        graph = build_work_graph(
            repo_root,
            limit=args.limit,
            agent=args.agent,
            status=args.status,
            file_path=args.file_path,
        )
    except ValueError as exc:
        return _console_error(args.format, str(exc), exit_code=2)

    output_path = Path(args.output) if args.output else Path(tempfile.mkdtemp(prefix="ait-console-")) / "index.html"
    path = write_daily_console_html(graph, output_path)
    payload = {
        "schema": DAILY_CONSOLE_SCHEMA,
        "schema_version": DAILY_CONSOLE_SCHEMA_VERSION,
        "status": "ready" if args.serve_local else "written",
        "read_only": True,
        "output": str(path),
        "repo_root": str(graph.get("repo_root", repo_root)),
        "graph_schema": graph.get("schema"),
        "graph_schema_version": graph.get("schema_version"),
        "served": False,
        "host": host,
        "port": int(args.port),
    }
    if not args.serve_local:
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(f"wrote read-only console {path}")
        return 0

    server = ThreadingHTTPServer((host, int(args.port)), _handler_for(path.parent))
    actual_host, actual_port = server.server_address[:2]
    payload.update({"served": True, "host": str(actual_host), "port": int(actual_port), "url": f"http://{actual_host}:{actual_port}/{path.name}"})
    if args.format == "json":
        print(json.dumps(payload, indent=2), flush=True)
    else:
        print(f"serving read-only console at {payload['url']}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


def _handle_console_action(args, repo_root: Path) -> int:
    action_map = {
        "apply": "apply_attempt",
        "recover": "recover_attempt",
        "discard": "discard_attempt",
    }
    action = action_map.get(str(getattr(args, "console_action", "") or ""))
    if action is None:
        return _console_error(getattr(args, "format", "json"), "console action is required", exit_code=2)
    payload = run_console_action(
        repo_root,
        action=action,
        attempt_id=str(args.attempt),
        dry_run=bool(args.dry_run),
        actor_label=str(args.actor_label),
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(f"{payload['status']}: {payload['action']} {payload['target']['attempt_id']}")
    return 0 if payload["status"] == "planned" else 1


def _console_error(output_format: str, message: str, *, exit_code: int) -> int:
    if output_format == "json":
        print(json.dumps({"schema_version": 1, "status": "error", "error": message}, indent=2))
    else:
        print(f"error: {message}", file=sys.stderr)
    return exit_code


def _loopback_host(host: str) -> bool:
    if host in {"localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _handler_for(directory: Path):
    class ConsoleHandler(SimpleHTTPRequestHandler):
        def __init__(self, *handler_args, **handler_kwargs):
            super().__init__(*handler_args, directory=str(directory), **handler_kwargs)

        def log_message(self, format, *args):  # noqa: A002
            return

    return ConsoleHandler
