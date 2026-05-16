from __future__ import annotations

from html import escape
from pathlib import Path


DAILY_CONSOLE_SCHEMA = "ait.daily_console"
DAILY_CONSOLE_SCHEMA_VERSION = 1


def write_daily_console_html(graph: dict[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_daily_console_html(graph), encoding="utf-8")
    return path


def render_daily_console_html(graph: dict[str, object]) -> str:
    intents = [item for item in graph.get("intents", []) if isinstance(item, dict)]
    attempts = _attempts(intents)
    latest_html = _attempt_list(attempts[:8], empty="No attempts recorded.")
    blocked_html = _attempt_list(
        [attempt for attempt in attempts if _review_status(attempt) in {"blocked", "failed", "queued", "running"}],
        empty="No blocked or pending reviews.",
    )
    apply_ready_html = _attempt_list(
        [
            attempt
            for attempt in attempts
            if str(attempt.get("verified_status") or "") in {"succeeded", "promoted"}
            and _review_status(attempt) not in {"blocked", "failed", "queued", "running"}
        ],
        empty="No apply-ready attempts.",
    )
    memory_html = _memory_topics_html(graph.get("memory_topics", {}))
    hot_file_html = _hot_files_html(graph.get("summary", {}))
    summary = graph.get("summary", {})
    status_counts = summary.get("status_counts", {}) if isinstance(summary, dict) else {}
    outcome_counts = summary.get("outcome_counts", {}) if isinstance(summary, dict) else {}
    agent_counts = summary.get("agent_counts", {}) if isinstance(summary, dict) else {}
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIT Daily Console</title>
  <style>
    :root {{ color-scheme: light; --border: #d7dde5; --ink: #1d2733; --muted: #667085; --surface: #f7f9fb; --accent: #166c7d; --ok: #177245; --warn: #8a5a00; --bad: #b42318; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: #fff; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
    header {{ display: grid; gap: 6px; margin-bottom: 18px; }}
    h1 {{ margin: 0; font-size: 24px; }}
    h2 {{ margin: 0 0 10px; font-size: 15px; }}
    .meta, .muted {{ color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .wide {{ grid-column: 1 / -1; }}
    section {{ border: 1px solid var(--border); border-radius: 6px; padding: 14px; background: var(--surface); min-width: 0; }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 7px 0; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    .attempt {{ display: grid; gap: 4px; padding: 10px; border: 1px solid var(--border); border-radius: 6px; background: #fff; }}
    .attempt + .attempt {{ margin-top: 8px; }}
    .title {{ font-weight: 650; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 5px; }}
    .badge {{ display: inline-flex; min-height: 22px; align-items: center; border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px; background: #fff; font-size: 12px; }}
    .ok {{ color: var(--ok); border-color: #9bd3b2; background: #f0fbf4; }}
    .warn {{ color: var(--warn); border-color: #e5c372; background: #fff8e5; }}
    .bad {{ color: var(--bad); border-color: #f1a7a1; background: #fff1f0; }}
    .read-only {{ color: var(--accent); font-weight: 650; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>AIT Daily Console</h1>
      <div class="meta">
        <span class="read-only">Read-only</span> · repo <code>{escape(str(graph.get("repo_root", "")))}</code> · generated <code>{escape(str(graph.get("generated_at", "")))}</code>
      </div>
      <div class="meta">Schema <code>{escape(str(graph.get("schema", "")))}</code> v<code>{escape(str(graph.get("schema_version", "")))}</code>. This page does not mutate Git, <code>.ait/</code>, or attempt worktrees.</div>
    </header>
    <div class="grid">
      <section><h2>Attempt Status</h2>{_metric_html(status_counts if isinstance(status_counts, dict) else {})}</section>
      <section><h2>Outcomes</h2>{_metric_html(outcome_counts if isinstance(outcome_counts, dict) else {})}</section>
      <section><h2>Agents</h2>{_metric_html(agent_counts if isinstance(agent_counts, dict) else {})}</section>
      <section><h2>Hot Files</h2>{hot_file_html}</section>
      <section><h2>Memory Topics</h2>{memory_html}</section>
      <section><h2>Review Queue</h2>{blocked_html}</section>
      <section class="wide"><h2>Latest Attempts</h2>{latest_html}</section>
      <section class="wide"><h2>Apply-ready Attempts</h2>{apply_ready_html}</section>
    </div>
  </main>
</body>
</html>
"""


def _attempts(intents: list[dict[str, object]]) -> list[dict[str, object]]:
    attempts: list[dict[str, object]] = []
    for intent in intents:
        title = str(intent.get("title") or "")
        for attempt in intent.get("attempts", []):
            if isinstance(attempt, dict):
                attempts.append({**attempt, "intent_title": title})
    return attempts


def _attempt_list(attempts: list[dict[str, object]], *, empty: str) -> str:
    if not attempts:
        return f"<div class=\"muted\">{escape(empty)}</div>"
    return "\n".join(_attempt_html(attempt) for attempt in attempts)


def _attempt_html(attempt: dict[str, object]) -> str:
    files = attempt.get("files", {})
    changed = files.get("changed", []) if isinstance(files, dict) else []
    changed_text = ", ".join(str(item) for item in changed[:4]) if changed else "no changed files"
    return (
        "<div class=\"attempt\">"
        f"<div class=\"title\">{escape(str(attempt.get('intent_title') or 'Untitled intent'))}</div>"
        f"<div><code>{escape(str(attempt.get('short_id') or attempt.get('id') or ''))}</code> · {escape(str(attempt.get('agent_id') or 'unknown'))}</div>"
        "<div class=\"badges\">"
        f"{_badge(str(attempt.get('verified_status') or 'unknown'), _status_class(str(attempt.get('verified_status') or '')))}"
        f"{_badge(str(attempt.get('outcome_class') or 'unclassified'), 'warn' if str(attempt.get('outcome_class') or '').startswith('failed') else '')}"
        f"{_badge(_review_status(attempt) or 'review:none', 'bad' if _review_status(attempt) in {'blocked', 'failed'} else '')}"
        "</div>"
        f"<div class=\"muted\">{escape(changed_text)}</div>"
        "</div>"
    )


def _review_status(attempt: dict[str, object]) -> str:
    review = attempt.get("review", {})
    return str(review.get("status") or "") if isinstance(review, dict) else ""


def _metric_html(values: dict[object, object]) -> str:
    if not values:
        return "<div class=\"muted\">none</div>"
    items = "\n".join(
        f"<li><code>{escape(str(key))}</code> <span class=\"muted\">{escape(str(value))}</span></li>"
        for key, value in sorted(values.items(), key=lambda item: str(item[0]))
    )
    return f"<ul>{items}</ul>"


def _hot_files_html(summary: object) -> str:
    hot_files = summary.get("hot_files", []) if isinstance(summary, dict) else []
    if not isinstance(hot_files, list) or not hot_files:
        return "<div class=\"muted\">none</div>"
    items = "\n".join(
        f"<li><code>{escape(str(item.get('path', '')))}</code> <span class=\"muted\">{escape(str(item.get('count', 0)))}</span></li>"
        for item in hot_files
        if isinstance(item, dict)
    )
    return f"<ul>{items}</ul>"


def _memory_topics_html(topics: object) -> str:
    return _metric_html(topics if isinstance(topics, dict) else {})


def _badge(text: str, css_class: str = "") -> str:
    return f"<span class=\"badge {escape(css_class, quote=True)}\">{escape(text)}</span>"


def _status_class(status: str) -> str:
    if status in {"succeeded", "promoted"}:
        return "ok"
    if status in {"failed", "discarded"}:
        return "bad"
    return "warn" if status else ""
