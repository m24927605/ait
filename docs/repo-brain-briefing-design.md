# AIT Repo Brain Briefing Design

## Goal

The repo brain graph gives AIT durable project memory, but wrapped
agents should not receive the full graph by default. They should receive
a compact briefing selected for the current intent.

The briefing answers:

- what prior facts are likely relevant
- which files are likely involved
- which attempts and statuses matter
- which docs or notes should be read first
- which evidence is extracted versus inferred

## Non-Goals

- Do not call a remote model or embedding service.
- Do not replace `.ait/brain/graph.json`.
- Do not hide failed or unpromoted attempt status.
- Do not require the user to run a manual workflow command before
  starting an agent.

## Selection Strategy

The first implementation uses deterministic local graph query:

1. Build or refresh the repo brain.
2. Query it with the current intent title and optional description.
3. Keep the top matching nodes.
4. Include directly connected neighbor context.
5. Group output into stable briefing sections.

The full graph report remains available through:

```bash
ait memory graph show
```

The compact briefing is available through:

```bash
ait memory graph brief "release process"
ait memory graph brief "release process" --auto --explain
```

## Context Injection

Wrapped agent context should include:

```text
AIT Repo Brain Briefing
Relevant Project Facts
Relevant Attempts
Likely Files
Relevant Docs And Notes
Connected Evidence
```

The full graph should not be injected by default. The graph files remain
under `.ait/brain/` for inspection and query.

Wrapped agent runs use automatic query generation. The query includes
intent text, command args, agent identity, recent failed attempts, hot
files, and memory note topics. The selected query sources are rendered
in the briefing so the agent can see why memory was chosen.

## Safety

Briefing content uses the same redaction and memory policy filters as
the repo brain graph. It is advisory; the text must remind agents to
verify current files before editing.

## Acceptance

- `ait memory graph brief <query>` renders text.
- `ait memory graph brief <query> --format json` emits parseable JSON.
- `ait memory graph brief <query> --auto --explain` shows generated
  query sources.
- Wrapped agent context includes `AIT Repo Brain Briefing`.
- Wrapped agent context does not include the full graph report by
  default.
- Briefings include relevant neighbors for matched graph nodes.
- Briefings remain bounded by a character budget.
