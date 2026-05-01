from __future__ import annotations



from html import escape

from pathlib import Path



from ait.report.shared import _css_token, _json_list, _search_blob

def write_work_graph_html(graph: dict[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_work_graph_html(graph), encoding="utf-8")
    return path

def render_work_graph_html(graph: dict[str, object]) -> str:
    title = "AIT Work Graph"
    visual_graph_html = _visual_graph_html(graph)
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
    health_html = _health_panel_html(graph.get("report_status", {}))
    filters = graph.get("filters", {})
    filters_html = ""
    if isinstance(filters, dict) and filters:
        filters_html = (
            "<div>Filters: "
            + ", ".join(
                f"{escape(str(key))}=<code>{escape(str(value))}</code>"
                for key, value in sorted(filters.items())
            )
            + "</div>"
        )
    outcome_counts = summary.get("outcome_counts", {})
    outcome_html = _metric_list(outcome_counts if isinstance(outcome_counts, dict) else {})
    agent_options = _filter_options(agent_counts if isinstance(agent_counts, dict) else {})
    status_options = _filter_options(status_counts if isinstance(status_counts, dict) else {})
    outcome_options = _filter_options(outcome_counts if isinstance(outcome_counts, dict) else {})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; --border: #d7dde5; --ink: #1d2733; --muted: #667085; --surface: #f7f9fb; --accent: #166c7d; --ok: #177245; --warn: #8a5a00; --bad: #b42318; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: var(--ink); background: #ffffff; }}
    main {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 24px; margin: 0 0 10px; }}
    h2 {{ font-size: 14px; margin: 0 0 8px; }}
    .meta {{ color: var(--muted); margin-bottom: 16px; line-height: 1.45; }}
    .toolbar {{ display: grid; grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(150px, 220px)); gap: 10px; align-items: end; padding: 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); margin: 0 0 16px; }}
    label {{ display: grid; gap: 4px; font-size: 12px; color: var(--muted); }}
    input, select {{ width: 100%; height: 34px; border: 1px solid var(--border); border-radius: 6px; background: #fff; color: var(--ink); padding: 0 10px; font: inherit; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin: 0 0 18px; }}
    .panel {{ border: 1px solid var(--border); border-radius: 6px; padding: 12px; background: var(--surface); }}
    .panel ul {{ margin: 0; padding-left: 18px; }}
    .visual-graph {{ margin: 0 0 18px; border: 1px solid var(--border); border-radius: 6px; background: #fff; overflow: auto; }}
    .visual-inner {{ min-width: 920px; padding: 16px; }}
    .graph-row {{ display: grid; grid-template-columns: 160px minmax(230px, 1fr) minmax(280px, 2fr); gap: 18px; align-items: stretch; position: relative; }}
    .graph-row + .graph-row {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); }}
    .graph-column {{ display: grid; align-content: start; gap: 8px; min-width: 0; }}
    .graph-column-label {{ font-size: 11px; text-transform: uppercase; color: var(--muted); letter-spacing: .04em; }}
    .graph-card {{ display: grid; gap: 6px; min-width: 0; padding: 9px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); position: relative; }}
    .graph-card::after {{ content: ""; position: absolute; top: 50%; right: -19px; width: 18px; border-top: 1px solid var(--border); }}
    .graph-column:last-child .graph-card::after {{ display: none; }}
    .graph-title {{ font-weight: 650; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .graph-subtitle {{ color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .graph-attempts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 8px; }}
    .graph-attempt {{ border-left: 4px solid var(--border); }}
    .graph-attempt.outcome-succeeded, .graph-attempt.outcome-promoted {{ border-left-color: var(--ok); }}
    .graph-attempt.outcome-succeeded_noop, .graph-attempt.outcome-needs_review, .graph-attempt.outcome-failed_with_evidence {{ border-left-color: var(--warn); }}
    .graph-attempt.outcome-failed, .graph-attempt.outcome-failed_no_evidence {{ border-left-color: var(--bad); }}
    .graph-facts {{ display: flex; flex-wrap: wrap; gap: 5px; }}
    .graph-artifacts {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }}
    .artifact {{ min-width: 0; padding: 8px; border: 1px solid var(--border); border-radius: 6px; background: #fff; }}
    .artifact strong {{ display: block; margin-bottom: 4px; font-size: 12px; }}
    .artifact code {{ display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .tree, .tree ul {{ list-style: none; margin: 0; padding-left: 22px; }}
    .tree li {{ margin: 8px 0; position: relative; }}
    .tree li::before {{ content: ""; position: absolute; left: -14px; top: 0; bottom: -8px; border-left: 1px solid var(--border); }}
    .tree li::after {{ content: ""; position: absolute; left: -14px; top: 13px; width: 10px; border-top: 1px solid var(--border); }}
    .tree > li::before, .tree > li::after {{ display: none; }}
    details > summary {{ cursor: pointer; }}
    .node {{ display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }}
    .intent-title {{ font-weight: 600; }}
    .attempt-body {{ margin-top: 8px; display: grid; gap: 8px; }}
    .facts {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .badge {{ display: inline-flex; align-items: center; min-height: 22px; border-radius: 999px; border: 1px solid var(--border); padding: 2px 8px; font-size: 12px; background: #fff; color: var(--ink); }}
    .badge-ok {{ color: var(--ok); border-color: #9bd3b2; background: #f0fbf4; }}
    .badge-warn {{ color: var(--warn); border-color: #e5c372; background: #fff8e5; }}
    .badge-bad {{ color: var(--bad); border-color: #f1a7a1; background: #fff1f0; }}
    .muted {{ color: var(--muted); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    .mini-list {{ margin: 0; padding-left: 18px; }}
    .memory-note {{ border: 1px solid var(--border); border-radius: 6px; padding: 8px; background: #fff; }}
    .memory-note pre {{ margin: 6px 0 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; }}
    pre.transcript {{ max-height: 420px; overflow: auto; white-space: pre-wrap; word-break: break-word; padding: 10px; border: 1px solid #222b36; border-radius: 6px; background: #111827; color: #f9fafb; font-size: 12px; line-height: 1.45; }}
    .trace-ref {{ margin: 8px 0; }}
    .hidden-by-filter {{ display: none !important; }}
    .empty-state {{ display: none; padding: 18px; border: 1px dashed var(--border); border-radius: 6px; color: var(--muted); }}
    .empty-state.visible {{ display: block; }}
    @media (max-width: 780px) {{ main {{ padding: 16px; }} .toolbar {{ grid-template-columns: 1fr; }} .visual-inner {{ min-width: 760px; }} .tree, .tree ul {{ padding-left: 14px; }} }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <div class="meta">
      <div>Repo: <code>{escape(str(graph.get("repo_root", "")))}</code></div>
      <div>Generated: <code>{escape(str(graph.get("generated_at", "")))}</code></div>
      <div>Summary: intents={graph.get("intent_count", 0)} attempts={graph.get("attempt_count", 0)} matched_intents={graph.get("matched_intent_count", len(graph.get("intents", [])))} matched_attempts={graph.get("matched_attempt_count", 0)} memory_notes={graph.get("memory_note_count", 0)}</div>
      {filters_html}
    </div>
    <section class="toolbar" aria-label="Graph filters">
      <label>Search<input id="filterText" type="search" placeholder="intent, transcript, file, memory"></label>
      <label>Agent<select id="filterAgent"><option value="">All agents</option>{agent_options}</select></label>
      <label>Status<select id="filterStatus"><option value="">All statuses</option>{status_options}</select></label>
      <label>Outcome<select id="filterOutcome"><option value="">All outcomes</option>{outcome_options}</select></label>
    </section>
    <section class="summary">
      {health_html}
      <div class="panel"><h2>Attempt Status</h2><ul>{status_html}</ul></div>
      <div class="panel"><h2>Outcomes</h2><ul>{outcome_html}</ul></div>
      <div class="panel"><h2>Agents</h2><ul>{agent_html}</ul></div>
      <div class="panel"><h2>Hot Files</h2><ul>{hot_file_html}</ul></div>
      <div class="panel"><h2>Memory</h2><ul>{memory_html}</ul></div>
    </section>
    {visual_graph_html}
    <div id="emptyState" class="empty-state">No attempts match the current filters.</div>
    <ul class="tree" id="workGraph">
      <li><details open><summary><span class="node">Repo</span></summary>
        <ul>
          {intents_html}
        </ul>
      </details></li>
    </ul>
  </main>
  <script>
    const controls = {{
      text: document.getElementById('filterText'),
      agent: document.getElementById('filterAgent'),
      status: document.getElementById('filterStatus'),
      outcome: document.getElementById('filterOutcome'),
      empty: document.getElementById('emptyState')
    }};
    function applyFilters() {{
      const query = controls.text.value.trim().toLowerCase();
      const agent = controls.agent.value;
      const status = controls.status.value;
      const outcome = controls.outcome.value;
      let visibleAttempts = 0;
      document.querySelectorAll('[data-attempt-node]').forEach((node) => {{
        const haystack = node.dataset.search || '';
        const statuses = node.dataset.statuses || '';
        const visible = (!query || haystack.includes(query))
          && (!agent || node.dataset.agent === agent)
          && (!status || statuses.split(' ').includes(status))
          && (!outcome || node.dataset.outcome === outcome);
        node.classList.toggle('hidden-by-filter', !visible);
        if (visible) visibleAttempts += 1;
      }});
      document.querySelectorAll('[data-visual-attempt]').forEach((node) => {{
        const haystack = node.dataset.search || '';
        const statuses = node.dataset.statuses || '';
        const visible = (!query || haystack.includes(query))
          && (!agent || node.dataset.agent === agent)
          && (!status || statuses.split(' ').includes(status))
          && (!outcome || node.dataset.outcome === outcome);
        node.classList.toggle('hidden-by-filter', !visible);
      }});
      document.querySelectorAll('[data-visual-intent]').forEach((node) => {{
        const hasVisibleAttempt = Boolean(node.querySelector('[data-visual-attempt]:not(.hidden-by-filter)'));
        const hasAttempts = Boolean(node.querySelector('[data-visual-attempt]'));
        node.classList.toggle('hidden-by-filter', hasAttempts && !hasVisibleAttempt);
      }});
      document.querySelectorAll('[data-intent-node]').forEach((node) => {{
        const hasVisibleAttempt = Boolean(node.querySelector('[data-attempt-node]:not(.hidden-by-filter)'));
        const hasAttempts = Boolean(node.querySelector('[data-attempt-node]'));
        node.classList.toggle('hidden-by-filter', hasAttempts && !hasVisibleAttempt);
        const details = node.querySelector(':scope > details');
        if (details && hasVisibleAttempt && (query || agent || status || outcome)) details.open = true;
      }});
      controls.empty.classList.toggle('visible', visibleAttempts === 0);
    }}
    Object.values(controls).forEach((control) => {{
      if (control && control !== controls.empty) control.addEventListener('input', applyFilters);
    }});
  </script>
</body>
</html>
"""

def _visual_graph_html(graph: dict[str, object]) -> str:
    intents = [item for item in graph.get("intents", []) if isinstance(item, dict)]
    if not intents:
        return (
            "<section class=\"visual-graph\" aria-label=\"Visual work graph\">"
            "<div class=\"visual-inner\"><span class=\"muted\">No visual graph data</span></div>"
            "</section>"
        )
    rows = "\n".join(_visual_intent_row(intent) for intent in intents)
    return (
        "<section class=\"visual-graph\" aria-label=\"Visual work graph\">"
        "<div class=\"visual-inner\">"
        "<div class=\"graph-column-label\">Visual Tree Graph</div>"
        f"{rows}"
        "</div>"
        "</section>"
    )

def _visual_intent_row(intent: dict[str, object]) -> str:
    attempts = [item for item in intent.get("attempts", []) if isinstance(item, dict)]
    attempt_cards = "\n".join(_visual_attempt_card(attempt) for attempt in attempts)
    artifact_cards = "\n".join(_visual_artifact_card(attempt) for attempt in attempts)
    if not attempt_cards:
        attempt_cards = "<div class=\"graph-card\"><div class=\"graph-title muted\">No attempts</div></div>"
    if not artifact_cards:
        artifact_cards = "<div class=\"artifact\"><strong>Artifacts</strong><span class=\"muted\">none</span></div>"
    search_text = _search_blob(
        str(intent.get("short_id", "")),
        str(intent.get("title", "")),
        str(intent.get("status", "")),
        *(str(attempt.get("agent_id", "")) for attempt in attempts),
    )
    return (
        f"<div class=\"graph-row\" data-visual-intent data-search=\"{escape(search_text, quote=True)}\">"
        "<div class=\"graph-column\">"
        "<div class=\"graph-column-label\">Intent</div>"
        "<div class=\"graph-card\">"
        f"<div class=\"graph-title\">{escape(str(intent.get('title', '')))}</div>"
        f"<div class=\"graph-subtitle\">{escape(str(intent.get('short_id', '')))} · {escape(str(intent.get('kind', '')))}</div>"
        f"<div class=\"graph-facts\">{_badge(str(intent.get('status', '')), kind='neutral')}</div>"
        "</div></div>"
        "<div class=\"graph-column\">"
        "<div class=\"graph-column-label\">Attempts</div>"
        f"<div class=\"graph-attempts\">{attempt_cards}</div>"
        "</div>"
        "<div class=\"graph-column\">"
        "<div class=\"graph-column-label\">Evidence</div>"
        f"<div class=\"graph-artifacts\">{artifact_cards}</div>"
        "</div>"
        "</div>"
    )

def _visual_attempt_card(attempt: dict[str, object]) -> str:
    verified_status = str(attempt.get("verified_status", ""))
    reported_status = str(attempt.get("reported_status", ""))
    outcome = str(attempt.get("outcome_class") or "unclassified")
    agent = str(attempt.get("agent_id", ""))
    files = attempt.get("files", {})
    changed = files.get("changed", []) if isinstance(files, dict) else []
    touched = files.get("touched", []) if isinstance(files, dict) else []
    file_list = changed or touched
    memory_notes = [item for item in attempt.get("memory_notes", []) if isinstance(item, dict)]
    memory_facts = [item for item in attempt.get("memory_facts", []) if isinstance(item, dict)]
    search_text = _search_blob(
        str(attempt.get("short_id", "")),
        agent,
        verified_status,
        reported_status,
        outcome,
        *(str(path) for path in file_list),
        *(str(note.get("body", "")) for note in memory_notes),
        *(str(fact.get("body", "")) for fact in memory_facts),
    )
    css_outcome = _css_token(outcome)
    return (
        f"<div class=\"graph-card graph-attempt outcome-{css_outcome}\" data-visual-attempt "
        f"data-agent=\"{escape(agent, quote=True)}\" "
        f"data-statuses=\"{escape(_search_blob(verified_status, reported_status), quote=True)}\" "
        f"data-outcome=\"{escape(outcome, quote=True)}\" "
        f"data-search=\"{escape(search_text, quote=True)}\">"
        f"<div class=\"graph-title\">Attempt {attempt.get('ordinal')} {escape(str(attempt.get('short_id', '')))}</div>"
        f"<div class=\"graph-subtitle\">{escape(agent)}</div>"
        f"<div class=\"graph-facts\">{_badge(verified_status, kind='status')}{_badge(outcome, kind='outcome')}</div>"
        "</div>"
    )

def _visual_artifact_card(attempt: dict[str, object]) -> str:
    files = attempt.get("files", {})
    changed = files.get("changed", []) if isinstance(files, dict) else []
    touched = files.get("touched", []) if isinstance(files, dict) else []
    file_list = changed or touched
    commits = [item for item in attempt.get("commits", []) if isinstance(item, dict)]
    memory_notes = [item for item in attempt.get("memory_notes", []) if isinstance(item, dict)]
    memory_facts = [item for item in attempt.get("memory_facts", []) if isinstance(item, dict)]
    transcript_mode = str(attempt.get("transcript_mode") or "none")
    file_text = escape(str(file_list[0])) if file_list else "none"
    commit_text = escape(str(commits[0].get("commit_oid", ""))[:12]) if commits else "none"
    memory_text = str(len(memory_notes) + len(memory_facts))
    transcript_text = escape(transcript_mode)
    return (
        "<div class=\"artifact\">"
        f"<strong>Files</strong><code>{file_text}</code>"
        f"<span class=\"muted\">{len(file_list)}</span>"
        "</div>"
        "<div class=\"artifact\">"
        f"<strong>Commits</strong><code>{commit_text}</code>"
        f"<span class=\"muted\">{len(commits)}</span>"
        "</div>"
        "<div class=\"artifact\">"
        f"<strong>Memory</strong><code>{memory_text}</code>"
        "</div>"
        "<div class=\"artifact\">"
        f"<strong>Transcript</strong><code>{transcript_text}</code>"
        "</div>"
    )

def _intent_html(intent: dict[str, object], *, open_by_default: bool) -> str:
    attempts = "\n".join(
        _attempt_html(attempt, open_by_default=open_by_default)
        for attempt in intent.get("attempts", [])
        if isinstance(attempt, dict)
    )
    if not attempts:
        attempts = "<li><span class=\"muted\">attempts: none</span></li>"
    open_attr = " open" if open_by_default else ""
    search_text = _search_blob(
        str(intent.get("short_id", "")),
        str(intent.get("title", "")),
        str(intent.get("status", "")),
        str(intent.get("kind", "")),
    )
    return (
        f"<li data-intent-node data-search=\"{escape(search_text, quote=True)}\"><details{open_attr}>"
        f"<summary><span class=\"node\">"
        f"<span class=\"intent-title\">Intent {escape(str(intent.get('short_id', '')))}: {escape(str(intent.get('title', '')))}</span> "
        f"{_badge(str(intent.get('status', '')), kind='neutral')}"
        "</span></summary><ul>"
        f"{attempts}"
        "</ul></details></li>"
    )

def _attempt_html(attempt: dict[str, object], *, open_by_default: bool) -> str:
    children: list[str] = []
    files = attempt.get("files", {})
    changed = files.get("changed", []) if isinstance(files, dict) else []
    touched = files.get("touched", []) if isinstance(files, dict) else []
    file_list = changed or touched
    if file_list:
        children.append(_files_html(file_list))
    commits = [item for item in attempt.get("commits", []) if isinstance(item, dict)]
    if commits:
        children.append(_commits_html(commits))
    outcome_reasons = _json_list(str(attempt.get("outcome_reasons_json") or "[]"))
    if outcome_reasons:
        children.append(_reasons_html(outcome_reasons))
    memory_notes = [item for item in attempt.get("memory_notes", []) if isinstance(item, dict)]
    memory_facts = [item for item in attempt.get("memory_facts", []) if isinstance(item, dict)]
    memory_retrievals = [item for item in attempt.get("memory_retrievals", []) if isinstance(item, dict)]
    memory_eval = attempt.get("memory_eval", {})
    if isinstance(memory_eval, dict) and int(memory_eval.get("event_count", 0) or 0):
        children.append(_memory_eval_html(memory_eval))
    if memory_retrievals:
        children.append(_memory_retrievals_html(memory_retrievals))
    if memory_facts:
        children.append(_memory_facts_html(memory_facts))
    if memory_notes:
        children.append(_memory_notes_html(memory_notes))
    transcript_html = _transcript_html(attempt)
    if transcript_html:
        children.append(transcript_html)
    child_html = "<div class=\"attempt-body\">" + "\n".join(children) + "</div>" if children else ""
    open_attr = " open" if open_by_default else ""
    verified_status = str(attempt.get("verified_status", ""))
    reported_status = str(attempt.get("reported_status", ""))
    outcome = str(attempt.get("outcome_class") or "unclassified")
    agent = str(attempt.get("agent_id", ""))
    search_text = _search_blob(
        str(attempt.get("short_id", "")),
        agent,
        verified_status,
        reported_status,
        outcome,
        str(attempt.get("transcript", "")),
        *(str(path) for path in file_list),
        *(str(note.get("body", "")) for note in memory_notes),
        *(str(fact.get("body", "")) for fact in memory_facts),
        *(str(retrieval.get("query", "")) for retrieval in memory_retrievals),
        str(memory_eval.get("status", "")) if isinstance(memory_eval, dict) else "",
        *(
            str(issue)
            for event in memory_eval.get("events", [])
            for issue in event.get("issues", [])
            if isinstance(memory_eval, dict) and isinstance(event, dict)
        ),
        *(
            str(warning)
            for event in memory_eval.get("events", [])
            for warning in event.get("warnings", [])
            if isinstance(memory_eval, dict) and isinstance(event, dict)
        ),
        *(
            str(fact.get("body", ""))
            for retrieval in memory_retrievals
            for fact in retrieval.get("selected_facts", [])
            if isinstance(fact, dict)
        ),
    )
    return (
        f"<li data-attempt-node data-agent=\"{escape(agent, quote=True)}\" "
        f"data-statuses=\"{escape(_search_blob(verified_status, reported_status), quote=True)}\" "
        f"data-outcome=\"{escape(outcome, quote=True)}\" data-search=\"{escape(search_text, quote=True)}\">"
        f"<details{open_attr}><summary><span class=\"node\">"
        f"<span>Attempt {attempt.get('ordinal')} {escape(str(attempt.get('short_id', '')))}</span>"
        f"{_badge(agent, kind='agent')}"
        f"{_badge(verified_status, kind='status')}"
        f"{_badge(reported_status, kind='neutral')}"
        f"{_badge(outcome, kind='outcome')}"
        "</span></summary>"
        f"{child_html}</details></li>"
    )

def _transcript_html(attempt: dict[str, object]) -> str:
    raw_trace_ref = str(attempt.get("raw_trace_ref") or "")
    if not raw_trace_ref:
        return ""
    transcript = str(attempt.get("transcript") or "")
    transcript_mode = str(attempt.get("transcript_mode") or "raw")
    if not transcript:
        return (
            "<details><summary>Transcript</summary>"
            f"<div class=\"trace-ref muted\">Trace: <code>{escape(raw_trace_ref)}</code> unavailable</div>"
            "</details>"
        )
    return (
        "<details><summary>Transcript</summary>"
        f"<div class=\"trace-ref muted\">Trace: <code>{escape(raw_trace_ref)}</code> mode=<code>{escape(transcript_mode)}</code></div>"
        f"<pre class=\"transcript\">{escape(transcript)}</pre>"
        "</details>"
    )

def _files_html(file_paths: list[object]) -> str:
    items = "\n".join(
        f"<li><code>{escape(str(file_path))}</code></li>"
        for file_path in file_paths[:16]
    )
    if len(file_paths) > 16:
        items += f"<li><span class=\"muted\">... {len(file_paths) - 16} more</span></li>"
    return f"<details open><summary>Files <span class=\"muted\">{len(file_paths)}</span></summary><ul class=\"mini-list\">{items}</ul></details>"

def _commits_html(commits: list[dict[str, object]]) -> str:
    items = "\n".join(
        "<li>"
        f"<code>{escape(str(commit.get('commit_oid', ''))[:12])}</code> "
        f"<span class=\"muted\">+{escape(str(commit.get('insertions') or 0))} -{escape(str(commit.get('deletions') or 0))}</span>"
        "</li>"
        for commit in commits[:8]
    )
    if len(commits) > 8:
        items += f"<li><span class=\"muted\">... {len(commits) - 8} more</span></li>"
    return f"<details><summary>Commits <span class=\"muted\">{len(commits)}</span></summary><ul class=\"mini-list\">{items}</ul></details>"

def _reasons_html(reasons: tuple[str, ...]) -> str:
    items = "\n".join(f"<li>{escape(reason)}</li>" for reason in reasons)
    return f"<details><summary>Outcome Reasons</summary><ul class=\"mini-list\">{items}</ul></details>"

def _memory_notes_html(notes: list[dict[str, object]]) -> str:
    items = "\n".join(
        "<div class=\"memory-note\">"
        f"{_badge(str(note.get('topic') or 'general'), kind='memory')}"
        f" <code>{escape(str(note.get('source', '')))}</code>"
        f"<pre>{escape(str(note.get('body', '')))}</pre>"
        "</div>"
        for note in notes
    )
    return f"<details open><summary>Memory Candidates <span class=\"muted\">{len(notes)}</span></summary>{items}</details>"

def _memory_facts_html(facts: list[dict[str, object]]) -> str:
    items = "\n".join(
        "<div class=\"memory-note\">"
        f"{_badge(str(fact.get('status') or 'unknown'), kind='status')}"
        f" {_badge(str(fact.get('kind') or 'fact'), kind='memory')}"
        f" <code>{escape(str(fact.get('id', '')))}</code>"
        f"<pre>{escape(str(fact.get('body', '')))}</pre>"
        f"<div class=\"muted\">confidence={escape(str(fact.get('confidence', '')))} "
        f"source_trace={escape(str(fact.get('source_trace_ref', '')))}</div>"
        "</div>"
        for fact in facts
    )
    return f"<details open><summary>Memory Facts <span class=\"muted\">{len(facts)}</span></summary>{items}</details>"

def _memory_retrievals_html(retrievals: list[dict[str, object]]) -> str:
    items: list[str] = []
    for retrieval in retrievals:
        facts = [item for item in retrieval.get("selected_facts", []) if isinstance(item, dict)]
        fact_items = "\n".join(
            "<li>"
            f"<code>{escape(str(fact.get('id', '')))}</code> "
            f"{_badge(str(fact.get('status') or 'unknown'), kind='status')} "
            f"{escape(str(fact.get('summary') or fact.get('body') or ''))}"
            "</li>"
            for fact in facts[:8]
        )
        if len(facts) > 8:
            fact_items += f"<li><span class=\"muted\">... {len(facts) - 8} more</span></li>"
        if not fact_items:
            fact_items = "<li><span class=\"muted\">none</span></li>"
        items.append(
            "<div class=\"memory-note\">"
            f"{_badge(str(retrieval.get('ranker_version') or 'ranker'), kind='memory')}"
            f" <code>{escape(str(retrieval.get('id', '')))}</code>"
            f"<div class=\"muted\">budget={escape(str(retrieval.get('budget_chars', '')))} "
            f"created={escape(str(retrieval.get('created_at', '')))}</div>"
            f"<pre>{escape(str(retrieval.get('query', '')))}</pre>"
            f"<ul class=\"mini-list\">{fact_items}</ul>"
            "</div>"
        )
    return f"<details open><summary>Memory Used <span class=\"muted\">{len(retrievals)}</span></summary>{''.join(items)}</details>"

def _memory_eval_html(memory_eval: dict[str, object]) -> str:
    events = [item for item in memory_eval.get("events", []) if isinstance(item, dict)]
    items: list[str] = []
    for event in events:
        issues = [str(item) for item in event.get("issues", [])]
        warnings = [str(item) for item in event.get("warnings", [])]
        missing = [str(item) for item in event.get("missing_relevant_fact_ids", [])]
        selected = [item for item in event.get("selected_facts", []) if isinstance(item, dict)]
        issue_items = "".join(f"<li>{escape(issue)}</li>" for issue in issues)
        warning_items = "".join(f"<li>{escape(warning)}</li>" for warning in warnings)
        missing_items = "".join(f"<li><code>{escape(fact_id)}</code></li>" for fact_id in missing)
        selected_items = "".join(
            "<li>"
            f"<code>{escape(str(fact.get('id', '')))}</code> "
            f"{escape(str(fact.get('summary', '')))} "
            f"<span class=\"muted\">relevance={escape(str(fact.get('relevance_score', '')))}</span>"
            "</li>"
            for fact in selected[:8]
        )
        sections = []
        if issues:
            sections.append(f"<div><strong>Issues</strong><ul class=\"mini-list\">{issue_items}</ul></div>")
        if warnings:
            sections.append(f"<div><strong>Warnings</strong><ul class=\"mini-list\">{warning_items}</ul></div>")
        if missing:
            sections.append(f"<div><strong>Missing Relevant Facts</strong><ul class=\"mini-list\">{missing_items}</ul></div>")
        if selected:
            sections.append(f"<div><strong>Selected Facts</strong><ul class=\"mini-list\">{selected_items}</ul></div>")
        items.append(
            "<div class=\"memory-note\">"
            f"{_badge(str(event.get('status') or 'unknown'), kind='memory-eval')}"
            f" <code>{escape(str(event.get('event_id', '')))}</code>"
            f"<div class=\"muted\">score={escape(str(event.get('score', '')))} "
            f"selected={escape(str(event.get('selected_count', '')))} "
            f"issues={escape(str(event.get('issue_count', '')))} "
            f"warnings={escape(str(event.get('warning_count', '')))}</div>"
            f"<pre>{escape(str(event.get('query', '')))}</pre>"
            + "".join(sections)
            + "</div>"
        )
    return (
        "<details open><summary>Memory Eval "
        f"{_badge(str(memory_eval.get('status') or 'unknown'), kind='memory-eval')} "
        f"<span class=\"muted\">score={escape(str(memory_eval.get('average_score', '')))} "
        f"events={escape(str(memory_eval.get('event_count', '')))}</span>"
        f"</summary>{''.join(items)}</details>"
    )

def _badge(value: str, *, kind: str) -> str:
    if not value:
        return ""
    css = "badge"
    lowered = value.lower()
    if kind == "outcome":
        if lowered in {"succeeded", "promoted"}:
            css += " badge-ok"
        elif lowered in {"succeeded_noop", "needs_review", "failed_with_evidence"}:
            css += " badge-warn"
        elif lowered.startswith("failed"):
            css += " badge-bad"
    elif kind == "status":
        if lowered in {"succeeded", "promoted"}:
            css += " badge-ok"
        elif lowered in {"pending", "discarded"}:
            css += " badge-warn"
        elif lowered == "failed":
            css += " badge-bad"
    elif kind == "memory-eval":
        if lowered == "pass":
            css += " badge-ok"
        elif lowered == "warn":
            css += " badge-warn"
        elif lowered == "fail":
            css += " badge-bad"
    elif kind == "health":
        if lowered == "pass":
            css += " badge-ok"
        elif lowered == "warn":
            css += " badge-warn"
        elif lowered == "fail":
            css += " badge-bad"
    return f"<span class=\"{css}\">{escape(value)}</span>"

def _health_panel_html(report_status: object) -> str:
    if not isinstance(report_status, dict):
        return '<div class="panel"><h2>AIT Health</h2><ul><li><span class="muted">unknown</span></li></ul></div>'
    health = report_status.get("health", {})
    if not isinstance(health, dict):
        return '<div class="panel"><h2>AIT Health</h2><ul><li><span class="muted">unknown</span></li></ul></div>'
    status = str(health.get("status") or "unknown")
    reasons = [str(item) for item in health.get("reasons", []) if str(item)]
    next_steps = [str(item) for item in health.get("next_steps", []) if str(item)]
    generated_at = str(report_status.get("generated_at") or "")
    items = [f"<li>Status {_badge(status, kind='health')}</li>"]
    if generated_at:
        items.append(f"<li>Generated <code>{escape(generated_at)}</code></li>")
    if reasons:
        items.append(
            "<li>Reasons<ul>"
            + "".join(f"<li>{escape(reason)}</li>" for reason in reasons)
            + "</ul></li>"
        )
    if next_steps:
        items.append(
            "<li>Next<ul>"
            + "".join(f"<li><code>{escape(step)}</code></li>" for step in next_steps)
            + "</ul></li>"
        )
    return "<div class=\"panel\"><h2>AIT Health</h2><ul>" + "".join(items) + "</ul></div>"

def _metric_list(values: dict[object, object]) -> str:
    if not values:
        return "<li><span class=\"muted\">none</span></li>"
    return "\n".join(
        f"<li>{escape(str(key))} <span class=\"muted\">{escape(str(value))}</span></li>"
        for key, value in sorted(values.items(), key=lambda item: str(item[0]))
    )

def _filter_options(values: dict[object, object]) -> str:
    return "".join(
        f"<option value=\"{escape(str(key), quote=True)}\">{escape(str(key))}</option>"
        for key in sorted(values, key=lambda item: str(item))
    )



__all__ = ["render_work_graph_html", "write_work_graph_html"]
