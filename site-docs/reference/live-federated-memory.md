# Live Federated Memory

AIT memory has two sources:

- **AIT-owned memory** under `.ait/`: attempts, prompts, traces, commits,
  curated notes, accepted facts, review findings, apply/recover outcomes, and
  context manifests.
- **Live external memory** in the repo: `CLAUDE.md`, `.claude/memory.md`,
  `.claude/CLAUDE.md`, `AGENTS.md`, `.codex/memory.md`, `.codex/AGENTS.md`,
  `.cursor/rules`, `.cursor/rules.md`, and `.cursorrules`.

External files remain their own source of truth. AIT reads them live during
`ait memory recall`, `ait run`, and `ait review`; it does not auto-import them
into `.ait/`.

## Zero-touch reads

These commands do not create `.ait/` and do not mutate source files:

```bash
ait memory sources
ait memory sources --format json
ait memory recall "project policy"
```

`ait memory sources` reports source id, path, kind, hash, mtime, size, policy
status, and skip reason. By default it only reads repo-local sources. Global or
out-of-repo sources require an explicit path:

```bash
ait memory sources --source claude --global --path ~/.claude/projects/example.md
```

## Context manifests

When AIT writes a run or review context artifact, it also records a context
manifest under `.ait/` with source id, path, hash, mtime, bytes used, and policy
status. Live external sources are advisory context, not captured AIT
provenance.

## Mutating paths

`ait memory backfill --dry-run` is a zero-write preview. `ait memory backfill
--import` is an explicit mutation/deprecated path: it writes advisory memory
under `.ait/` and is not required for live recall.
