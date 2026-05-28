from __future__ import annotations

import sys
from pathlib import Path

from ait.bug_report.pending_queue import (
    clear_pending,
    list_pending,
    load_pending,
    remove,
)

SCOPE_LINE = (
    "Reports bugs in AIT itself. For issues with your code or your "
    "agent's behavior, this is not the right tool."
)


def run_list() -> int:
    fps = sorted(list_pending())
    if not fps:
        print("no pending bug reports.")
        return 0
    print(f"{len(fps)} pending bug report(s):")
    for fp in fps:
        report = load_pending(fp)
        if report is None:
            continue
        print(f"  {fp}  [{report.category}]  created={report.created_at}")
    return 0


def run_show(fingerprint: str) -> int:
    report = load_pending(fingerprint)
    if report is None:
        print(f"no pending report with fingerprint {fingerprint}",
              file=sys.stderr)
        return 1
    print(f"Title: {report.title}")
    print()
    print(report.body)
    return 0


def run_clear(*, all_flag: bool, fingerprint: str | None) -> int:
    if all_flag:
        n = clear_pending()
        print(f"cleared {n} pending report(s).")
        return 0
    if fingerprint is None:
        print("specify a fingerprint or use --all", file=sys.stderr)
        return 2
    ok = remove(fingerprint)
    if not ok:
        print(f"no pending report with fingerprint {fingerprint}",
              file=sys.stderr)
        return 1
    print(f"removed {fingerprint}.")
    return 0


def run_replay(*, all_flag: bool, fingerprint: str | None) -> int:
    from ait.bug_report.submitter import submit

    targets: list[str]
    if all_flag:
        targets = sorted(list_pending())
    elif fingerprint:
        targets = [fingerprint]
    else:
        print("specify a fingerprint or use --all", file=sys.stderr)
        return 2

    if not targets:
        print("nothing to replay.")
        return 0

    for fp in targets:
        report = load_pending(fp)
        if report is None:
            print(f"skip: {fp} (not found)", file=sys.stderr)
            continue
        result = submit(title=report.title, body=report.body)
        if result.status == "ok":
            remove(fp)
            print(f"sent: {fp} via {result.method} → {result.issue_url or 'browser'}")
        else:
            print(f"defer: {fp} ({result.reason})", file=sys.stderr)
    return 0


def handle(args, repo_root: Path, parser=None) -> int:
    del repo_root, parser
    cmd = getattr(args, "bug_report_cmd", None)
    if cmd == "list":
        return run_list()
    if cmd == "show":
        return run_show(args.fingerprint)
    if cmd == "clear":
        return run_clear(all_flag=args.all_flag, fingerprint=args.fingerprint)
    if cmd == "replay":
        return run_replay(all_flag=args.all_flag, fingerprint=args.fingerprint)
    # No subcommand → scope line + wizard placeholder.
    print(SCOPE_LINE)
    print("(interactive wizard is implemented in a follow-up task; "
          "use `ait bug-report list|show|clear|replay` for now.)")
    return 0
