from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "graph":
        try:
            graph = build_work_graph(
                repo_root,
                limit=args.limit,
                agent=args.agent,
                status=args.status,
                file_path=args.file_path,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.html:
            output_path = Path(args.output) if args.output else Path(graph["repo_root"]) / ".ait" / "report" / "graph.html"
            path = write_work_graph_html(graph, output_path)
            if args.format == "json":
                payload = dict(graph)
                payload["html_path"] = str(path)
                print(json.dumps(payload, indent=2))
            else:
                print(f"wrote {path}")
            return 0
        if args.format == "json":
            print(json.dumps(graph, indent=2))
        else:
            print(render_work_graph_text(graph))
        return 0
    if parser is not None:
        parser.print_help()
    return 1
