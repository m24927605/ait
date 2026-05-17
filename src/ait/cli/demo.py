from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ait.app import create_attempt, create_commit_for_attempt, create_intent
from ait.review import create_fake_reviewer_review
from ait.review_policy import open_high_or_critical_findings

DEMO_DIR_PREFIX = "ait-demo-"


def _scenario_path() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "demo" / "scenario.json"


def _load_scenario() -> dict:
    return json.loads(_scenario_path().read_text(encoding="utf-8"))


def handle(args, repo_root, parser=None) -> int:
    if args.command != "demo":
        if parser is not None:
            parser.print_help()
        return 1
    if getattr(args, "clean", False):
        return _handle_clean(args)
    return _run_demo(args)


def _handle_clean(args) -> int:
    tmp_root = Path(tempfile.gettempdir())
    removed = 0
    for entry in tmp_root.iterdir():
        if entry.is_dir() and entry.name.startswith(DEMO_DIR_PREFIX):
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    if getattr(args, "format", "text") == "json":
        print(json.dumps({"removed": removed, "scope": str(tmp_root)}, indent=2))
    else:
        noun = "directory" if removed == 1 else "directories"
        print(f"Removed {removed} ait demo {noun} from {tmp_root}.")
    return 0


def _run_demo(args) -> int:
    scenario = _load_scenario()
    quiet = getattr(args, "quiet", False)
    json_output = getattr(args, "format", "text") == "json"

    started = time.monotonic()
    demo_root = Path(tempfile.mkdtemp(prefix=DEMO_DIR_PREFIX))

    try:
        _bootstrap_demo_repo(demo_root)

        if not quiet and not json_output:
            print(f"[ait] Creating demo repo at {demo_root}/")
            print("[ait] Initialising ait + git (in-process, no daemon)")
            print()

        intent = create_intent(
            demo_root,
            title=scenario["intent"]["title"],
            description=scenario["intent"].get("description"),
            kind=scenario["intent"].get("kind"),
        )

        implementer = scenario["implementer"]
        attempt = create_attempt(
            demo_root,
            intent_id=intent.intent_id,
            agent_id=implementer["agent_id"],
        )

        if not quiet and not json_output:
            print(f'[ait] Intent  : "{scenario["intent"]["title"]}"')
            print(f"[ait] Attempt : {attempt.attempt_id}  agent={implementer['agent_id']}")
            print()

        workspace_path = Path(attempt.workspace_ref)
        for file_spec in implementer["files"]:
            target = workspace_path / file_spec["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file_spec["content"], encoding="utf-8")
            _git_demo(workspace_path, "add", file_spec["path"])
            if not quiet and not json_output:
                print(f"      written: {file_spec['path']}")
                for line in file_spec["content"].splitlines():
                    print(f"        {line}")
                print()

        create_commit_for_attempt(
            demo_root,
            attempt_id=attempt.attempt_id,
            message=scenario["intent"]["title"],
        )

        reviewer = scenario["reviewer"]
        review_result = create_fake_reviewer_review(
            demo_root,
            attempt.attempt_id,
            fake_adapter=reviewer["fake_adapter"],
            budget=reviewer.get("budget", "standard"),
        )

        db_path = demo_root / ".ait" / "state.sqlite3"
        review_row, findings_rows, counts = _read_ledger(db_path, review_result.review.id)

        if not quiet and not json_output:
            print(f"[ait] Review  : agent={reviewer['fake_adapter']}")
            for f in findings_rows:
                print(f"      finding : {f['title']}")
                print(f"      severity: {f['severity']}")
                if f["path"]:
                    location = f["path"] + (f":{f['line']}" if f["line"] is not None else "")
                    print(f"      file    : {location}")
            print()

        with contextlib.closing(sqlite3.connect(str(db_path))) as conn:
            conn.row_factory = sqlite3.Row
            blockers = open_high_or_critical_findings(conn, review_result.review.id)
        apply_blocked = bool(blockers)

        if not quiet and not json_output:
            if apply_blocked:
                print(
                    f"[ait] Apply gate: review found {len(blockers)} blocking finding(s) -> apply skipped."
                )
            else:
                print("[ait] Apply gate: no blocking findings -> apply would proceed (not applied in demo).")
            print()

        duration = time.monotonic() - started

        if json_output:
            print(
                json.dumps(
                    {
                        "demo_dir": str(demo_root),
                        "intent_id": intent.intent_id,
                        "attempt_id": attempt.attempt_id,
                        "review_id": review_result.review.id,
                        "apply_blocked": apply_blocked,
                        "duration_seconds": round(duration, 3),
                        "intents": counts["intents"],
                        "attempts": counts["attempts"],
                        "reviews": counts["reviews"],
                    },
                    indent=2,
                )
            )
        elif not quiet:
            print("[ait] Ledger state (read live from SQLite):")
            print(
                f"      intents: {counts['intents']}   attempts: {counts['attempts']}"
                f"   reviews: {counts['reviews']}"
            )
            print()
            print("[ait] What just happened")
            print("  - ait wrapped a coding task as an isolated attempt with full provenance")
            print("  - a second agent reviewed the result before any code reached your tree")
            if apply_blocked:
                print("  - the reviewer caught a blocking issue, so 'ait apply' was held back automatically")
            else:
                print("  - the reviewer raised non-blocking findings; 'ait apply' would proceed in a real run")
            print(f"  - everything above lives in {demo_root}/.ait/state.sqlite3")
            print()
            print("[ait] Try the same with your real agents:")
            print("      cd your-repo")
            print("      ait init")
            print('      ait run --adapter claude-code --intent "fix the flaky queue test"')
            print()
            if not getattr(args, "keep", False):
                print(f"[ait] Demo repo kept at {demo_root}/  (remove all with 'ait demo --clean')")
            print(f"[ait] Done in {duration:.1f}s")

        return 0

    except Exception as exc:
        print(f"[ait] demo failed at {demo_root}: {exc}", file=sys.stderr)
        return 2


def _bootstrap_demo_repo(demo_root: Path) -> None:
    env = _demo_git_env()
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=demo_root,
        check=True,
        capture_output=True,
        env=env,
    )
    readme = demo_root / "README.md"
    readme.write_text("# ait demo repo\n\nThrowaway repo created by `ait demo`.\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=demo_root,
        check=True,
        capture_output=True,
        env=env,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial demo commit"],
        cwd=demo_root,
        check=True,
        capture_output=True,
        env=env,
    )


def _demo_git_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "ait demo",
        "GIT_AUTHOR_EMAIL": "demo@ait.local",
        "GIT_COMMITTER_NAME": "ait demo",
        "GIT_COMMITTER_EMAIL": "demo@ait.local",
    }


def _git_demo(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=_demo_git_env(),
    )


def _read_ledger(db_path: Path, review_id: str):
    with contextlib.closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        review_row = conn.execute(
            "SELECT id, status, blocking, risk_level, summary FROM attempt_reviews WHERE id = ?",
            (review_id,),
        ).fetchone()
        findings_rows = conn.execute(
            "SELECT id, severity, blocking, title, path, line FROM attempt_review_findings "
            "WHERE review_id = ? ORDER BY id",
            (review_id,),
        ).fetchall()
        counts = {
            "intents": conn.execute("SELECT COUNT(*) AS n FROM intents").fetchone()["n"],
            "attempts": conn.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"],
            "reviews": conn.execute("SELECT COUNT(*) AS n FROM attempt_reviews").fetchone()["n"],
        }
    return review_row, findings_rows, counts
