from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "query":
        return _run_query_command(
            repo_root,
            subject=args.on,
            expression=args.expression,
            limit=args.limit,
            offset=args.offset,
            output_format=args.format,
        )
    if args.command == "blame":
        init_result = init_repo(repo_root)
        conn = connect_db(init_result.db_path)
        try:
            target = parse_blame_target(args.target)
            rows = blame_path(conn, target.path)
        finally:
            conn.close()
        print(_format_rows([row.__dict__ for row in rows], "table"))
        return 0
    if parser is not None:
        parser.print_help()
    return 1
