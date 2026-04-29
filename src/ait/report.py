from __future__ import annotations

from html import escape
from pathlib import Path
import sqlite3

from ait.db import connect_db, utc_now
from ait.repo import resolve_repo_root


def build_work_graph(repo_root: str | Path, *, limit: int = 20) -> dict[str, object]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    root = resolve_repo_root(repo_root)
    db_path = root / ".ait" / "state.sqlite3"
    graph: dict[str, object] = {
        "repo_root": str(root),
        "state_path": str(db_path),
        "generated_at": utc_now(),
        "initialized": db_path.exists(),
        "intent_count": 0,
        "attempt_count": 0,
        "memory_note_count": 0,
        "memory_topics": {},
        "intents": [],
    }
    if not db_path.exists():
        return graph

    conn = connect_db(db_path)
    try:
        intents = _query_intents(conn, limit=limit)
        for intent in intents:
            attempts = _query_attempts(conn, str(intent["id"]))
            for attempt in attempts:
                attempt["files"] = _query_files(conn, str(attempt["id"]))
                attempt["commits"] = _query_commits(conn, str(attempt["id"]))
            intent["attempts"] = attempts
        summary = _build_summary(intents)
        memory_topics = _query_memory_topics(conn)
        graph.update(
            {
                "intent_count": _count_rows(conn, "intents"),
                "attempt_count": _count_rows(conn, "attempts"),
                "memory_note_count": sum(memory_topics.values()),
                "memory_topics": memory_topics,
                "summary": summary,
                "intents": intents,
            }
        )
    finally:
        conn.close()
    return graph


def render_work_graph_text(graph: dict[str, object]) -> str:
    lines = [
        "AIT Work Graph",
        f"Repo: {graph.get('repo_root')}",
        f"State: {'initialized' if graph.get('initialized') else 'not initialized'}",
        (
            "Summary: "
            f"intents={graph.get('intent_count', 0)} "
            f"attempts={graph.get('attempt_count', 0)} "
            f"memory_notes={graph.get('memory_note_count', 0)}"
        ),
    ]
    memory_topics = graph.get("memory_topics", {})
    if isinstance(memory_topics, dict) and memory_topics:
        topics = ", ".join(f"{topic or 'general'}={count}" for topic, count in sorted(memory_topics.items()))
        lines.append(f"Memory topics: {topics}")
    lines.append("Tree:")
    intents = [item for item in graph.get("intents", []) if isinstance(item, dict)]
    if not intents:
        lines.append("`-- no intents recorded")
        return "\n".join(lines)
    for intent_index, intent in enumerate(intents):
        intent_last = intent_index == len(intents) - 1
        intent_prefix = "`-- " if intent_last else "|-- "
        child_prefix = "    " if intent_last else "|   "
        lines.append(
            intent_prefix
            + f"Intent {intent.get('short_id')}: {intent.get('title')} "
            + f"[status={intent.get('status')}]"
        )
        attempts = [item for item in intent.get("attempts", []) if isinstance(item, dict)]
        if not attempts:
            lines.append(child_prefix + "`-- attempts: none")
            continue
        for attempt_index, attempt in enumerate(attempts):
            attempt_last = attempt_index == len(attempts) - 1
            attempt_prefix = child_prefix + ("`-- " if attempt_last else "|-- ")
            detail_prefix = child_prefix + ("    " if attempt_last else "|   ")
            lines.append(
                attempt_prefix
                + f"Attempt {attempt.get('ordinal')} {attempt.get('short_id')} "
                + f"agent={attempt.get('agent_id')} "
                + f"status={attempt.get('verified_status')}/{attempt.get('reported_status')}"
            )
            files = attempt.get("files", {})
            changed = files.get("changed", []) if isinstance(files, dict) else []
            touched = files.get("touched", []) if isinstance(files, dict) else []
            file_list = changed or touched
            if file_list:
                lines.append(detail_prefix + "Files:")
                for file_path in file_list[:8]:
                    lines.append(detail_prefix + f"- {file_path}")
                if len(file_list) > 8:
                    lines.append(detail_prefix + f"- ... {len(file_list) - 8} more")
            commits = [item for item in attempt.get("commits", []) if isinstance(item, dict)]
            if commits:
                lines.append(detail_prefix + "Commits:")
                for commit in commits[:5]:
                    lines.append(detail_prefix + f"- {str(commit.get('commit_oid', ''))[:12]}")
                if len(commits) > 5:
                    lines.append(detail_prefix + f"- ... {len(commits) - 5} more")
    return "\n".join(lines)


def write_work_graph_html(graph: dict[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_work_graph_html(graph), encoding="utf-8")
    return path


def render_work_graph_html(graph: dict[str, object]) -> str:
    title = "AIT Work Graph"
    intents_html = "\n".join(
        _intent_html(intent, open_by_default=index < 3)
        for index, intent in enumerate(
            item for item in graph.get("intents", []) if isinstance(item, dict)
        )
    )
    if not intents_html:
        intents_html = "<li><span class=\"muted\">No intents recorded</span></li>"
    summary = graph.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    status_counts = summary.get("status_counts", {})
    agent_counts = summary.get("agent_counts", {})
    hot_files = summary.get("hot_files", [])
    status_html = _metric_list(status_counts if isinstance(status_counts, dict) else {})
    agent_html = _metric_list(agent_counts if isinstance(agent_counts, dict) else {})
    hot_file_html = "\n".join(
        f"<li><code>{escape(str(item.get('path', '')))}</code> <span class=\"muted\">{item.get('count', 0)}</span></li>"
        for item in hot_files
        if isinstance(item, dict)
    ) or "<li><span class=\"muted\">none</span></li>"
    memory_topics = graph.get("memory_topics", {})
    memory_html = _metric_list(memory_topics if isinstance(memory_topics, dict) else {})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; background: #ffffff; }}
    h1 {{ font-size: 24px; margin: 0 0 16px; }}
    h2 {{ font-size: 15px; margin: 0 0 8px; }}
    .meta {{ color: #4b5563; margin-bottom: 20px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 0 0 24px; }}
    .panel {{ border: 1px solid #d1d5db; border-radius: 6px; padding: 12px; background: #f9fafb; }}
    .panel ul {{ margin: 0; padding-left: 18px; }}
    .tree, .tree ul {{ list-style: none; margin: 0; padding-left: 22px; }}
    .tree li {{ margin: 8px 0; position: relative; }}
    .tree li::before {{ content: ""; position: absolute; left: -14px; top: 0; bottom: -8px; border-left: 1px solid #d1d5db; }}
    .tree li::after {{ content: ""; position: absolute; left: -14px; top: 12px; width: 10px; border-top: 1px solid #d1d5db; }}
    .tree > li::before, .tree > li::after {{ display: none; }}
    details > summary {{ cursor: pointer; }}
    .node {{ display: inline-block; padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 6px; background: #f9fafb; }}
    .muted {{ color: #6b7280; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="meta">
    <div>Repo: <code>{escape(str(graph.get("repo_root", "")))}</code></div>
    <div>Generated: <code>{escape(str(graph.get("generated_at", "")))}</code></div>
    <div>Summary: intents={graph.get("intent_count", 0)} attempts={graph.get("attempt_count", 0)} memory_notes={graph.get("memory_note_count", 0)}</div>
  </div>
  <section class="summary">
    <div class="panel"><h2>Attempt Status</h2><ul>{status_html}</ul></div>
    <div class="panel"><h2>Agents</h2><ul>{agent_html}</ul></div>
    <div class="panel"><h2>Hot Files</h2><ul>{hot_file_html}</ul></div>
    <div class="panel"><h2>Memory</h2><ul>{memory_html}</ul></div>
  </section>
  <ul class="tree">
    <li><details open><summary><span class="node">Repo</span></summary>
      <ul>
        {intents_html}
      </ul>
    </details></li>
  </ul>
</body>
</html>
"""

def _intent_html(intent: dict[str, object], *, open_by_default: bool) -> str:
    attempts = "\n".join(
        _attempt_html(attempt, open_by_default=open_by_default)
        for attempt in intent.get("attempts", [])
        if isinstance(attempt, dict)
    )
    if not attempts:
        attempts = "<li><span class=\"muted\">attempts: none</span></li>"
    open_attr = " open" if open_by_default else ""
    return (
        f"<li><details{open_attr}><summary><span class=\"node\">"
        f"Intent {escape(str(intent.get('short_id', '')))}: {escape(str(intent.get('title', '')))} "
        f"[{escape(str(intent.get('status', '')))}]"
        "</span></summary><ul>"
        f"{attempts}"
        "</ul></details></li>"
    )


def _attempt_html(attempt: dict[str, object], *, open_by_default: bool) -> str:
    children: list[str] = []
    files = attempt.get("files", {})
    changed = files.get("changed", []) if isinstance(files, dict) else []
    touched = files.get("touched", []) if isinstance(files, dict) else []
    for file_path in (changed or touched)[:8]:
        children.append(f"<li><span class=\"muted\">File</span> <code>{escape(str(file_path))}</code></li>")
    for commit in [item for item in attempt.get("commits", []) if isinstance(item, dict)][:5]:
        children.append(
            "<li><span class=\"muted\">Commit</span> "
            f"<code>{escape(str(commit.get('commit_oid', ''))[:12])}</code></li>"
        )
    child_html = "<ul>" + "\n".join(children) + "</ul>" if children else ""
    open_attr = " open" if open_by_default else ""
    return (
        f"<li><details{open_attr}><summary><span class=\"node\">"
        f"Attempt {attempt.get('ordinal')} {escape(str(attempt.get('short_id', '')))} "
        f"agent={escape(str(attempt.get('agent_id', '')))} "
        f"status={escape(str(attempt.get('verified_status', '')))}/{escape(str(attempt.get('reported_status', '')))}"
        "</span></summary>"
        f"{child_html}</details></li>"
    )


def _build_summary(intents: list[dict[str, object]]) -> dict[str, object]:
    status_counts: dict[str, int] = {}
    agent_counts: dict[str, int] = {}
    file_counts: dict[str, int] = {}
    for intent in intents:
        for attempt in [item for item in intent.get("attempts", []) if isinstance(item, dict)]:
            status = str(attempt.get("verified_status", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1
            agent = str(attempt.get("agent_id", "unknown"))
            agent_counts[agent] = agent_counts.get(agent, 0) + 1
            files = attempt.get("files", {})
            if not isinstance(files, dict):
                continue
            for file_path in files.get("changed", []) or files.get("touched", []):
                path = str(file_path)
                file_counts[path] = file_counts.get(path, 0) + 1
    hot_files = [
        {"path": path, "count": count}
        for path, count in sorted(file_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    return {
        "status_counts": dict(sorted(status_counts.items())),
        "agent_counts": dict(sorted(agent_counts.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "hot_files": hot_files,
    }


def _metric_list(values: dict[object, object]) -> str:
    if not values:
        return "<li><span class=\"muted\">none</span></li>"
    return "\n".join(
        f"<li>{escape(str(key))} <span class=\"muted\">{escape(str(value))}</span></li>"
        for key, value in sorted(values.items(), key=lambda item: str(item[0]))
    )


def _query_intents(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, title, kind, status, created_at
        FROM intents
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "short_id": _short_id(str(row["id"])),
            "title": str(row["title"]),
            "kind": row["kind"],
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def _query_attempts(conn: sqlite3.Connection, intent_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, ordinal, agent_id, started_at, ended_at, reported_status, verified_status
        FROM attempts
        WHERE intent_id = ?
        ORDER BY ordinal ASC
        """,
        (intent_id,),
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "short_id": _short_id(str(row["id"])),
            "ordinal": int(row["ordinal"]),
            "agent_id": str(row["agent_id"]),
            "started_at": str(row["started_at"]),
            "ended_at": row["ended_at"],
            "reported_status": str(row["reported_status"]),
            "verified_status": str(row["verified_status"]),
        }
        for row in rows
    ]


def _query_files(conn: sqlite3.Connection, attempt_id: str) -> dict[str, list[str]]:
    rows = conn.execute(
        """
        SELECT kind, file_path
        FROM evidence_files
        WHERE attempt_id = ?
        ORDER BY kind, file_path
        """,
        (attempt_id,),
    ).fetchall()
    files: dict[str, list[str]] = {}
    for row in rows:
        files.setdefault(str(row["kind"]), []).append(str(row["file_path"]))
    return files


def _query_commits(conn: sqlite3.Connection, attempt_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT commit_oid, insertions, deletions, touched_files_json
        FROM attempt_commits
        WHERE attempt_id = ?
        ORDER BY rowid ASC
        """,
        (attempt_id,),
    ).fetchall()
    return [
        {
            "commit_oid": str(row["commit_oid"]),
            "insertions": row["insertions"],
            "deletions": row["deletions"],
            "touched_files": row["touched_files_json"],
        }
        for row in rows
    ]


def _query_memory_topics(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT COALESCE(topic, 'general') AS topic, COUNT(*) AS count
        FROM memory_notes
        WHERE active = 1
        GROUP BY COALESCE(topic, 'general')
        ORDER BY topic
        """
    ).fetchall()
    return {str(row["topic"]): int(row["count"]) for row in rows}


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"])


def _short_id(value: str) -> str:
    return value.rsplit(":", 1)[-1][:8]
