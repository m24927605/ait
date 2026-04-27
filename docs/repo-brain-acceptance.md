# AIT Repo Brain Acceptance

## Scope

This document defines acceptance for the first repo brain production
slice.

## Acceptance Criteria

1. `ait memory graph show` works in a Git repository with no prior AIT
   attempts.
2. `ait memory graph show --format json` emits parseable JSON.
3. `ait memory graph build` writes `.ait/brain/graph.json`.
4. `ait memory graph build` writes `.ait/brain/REPORT.md`.
5. Re-running `ait memory graph build` is idempotent for unchanged
   repo state.
6. The graph contains a repo node.
7. The graph contains doc nodes for visible markdown docs such as
   `README.md`, `AGENT.md`, `CLAUDE.md`, and `docs/*.md`.
8. Policy-excluded docs and files do not appear in the graph.
9. After an attempt changes a file and creates an attempt-linked commit,
   the graph contains intent, attempt, agent, file, and commit nodes.
10. Attempt nodes connect to their intent, agent, changed files, and
    commits through typed edges.
11. Curated memory notes appear as note nodes and connect to topic
    nodes.
12. Note text is redacted before appearing in graph reports or query
    output.
13. `ait memory graph query <text>` returns relevant graph nodes.
14. Graph query output includes directly connected neighbor context.
15. `ait memory graph query <text> --format json` emits parseable JSON.
16. Wrapped agent runs refresh `.ait/brain/graph.json` before launch when
    context injection is enabled.
17. Wrapped agent context includes an `AIT Repo Brain Briefing` section.
18. Claude Code, Codex, and Aider continue to receive
    `AIT_CONTEXT_FILE` through their wrappers.
19. Existing `ait memory` and `ait memory search` behavior is unchanged.
20. The full automated test suite passes.
21. Build and query commands do not require external services or network
    access.
22. Graph output identifies whether evidence is extracted or inferred.
23. Failed, succeeded, and promoted attempt statuses remain visible in
    graph output.
24. Running from an attempt worktree still refreshes the root repo
    `.ait/brain/` output.

## Manual Smoke

```bash
tmpdir="$(mktemp -d)"
python3.14 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/pip" install /path/to/ait/dist/ait_vcs-<version>-py3-none-any.whl
mkdir "$tmpdir/repo"
cd "$tmpdir/repo"
git init
git config user.email test@example.com
git config user.name "Test User"
printf 'repo brain smoke\n' > README.md
git add README.md
git commit -m init
"$tmpdir/venv/bin/ait" memory graph show
"$tmpdir/venv/bin/ait" memory graph build
test -f .ait/brain/graph.json
test -f .ait/brain/REPORT.md
"$tmpdir/venv/bin/ait" memory graph query "repo brain"
"$tmpdir/venv/bin/ait" memory graph brief "repo brain"
```

## Automated Coverage

Automated tests must cover:

- empty repo brain construction
- docs indexing
- policy path exclusion
- attempt, agent, file, commit, note, and topic nodes
- edge construction
- text rendering
- JSON rendering
- graph query ranking
- connected neighbor context
- graph build idempotency
- agent context includes repo brain
- wrapped runs refresh the graph
- no external service dependency
- JSON output without human text around it
- unchanged `ait memory search` behavior

## Document Review Log

Completed before implementation:

1. Architecture review: acceptance is tied to the existing memory and
   runner boundaries.
2. Data model review: no schema migration is required for the first
   sidecar implementation.
3. Developer experience review: manual graph commands exist for
   inspection, but wrapped agent runs refresh automatically.
4. Security/privacy review: policy-excluded paths and redacted text must
   be absent from graph reports and query output.
5. Test/release review: acceptance includes unit tests, CLI JSON tests,
   local build, package smoke, and GitHub/PyPI release checks.

## Implementation Review Log

The implementation must pass five code review rounds before release:

1. Architecture and module boundary review
2. Data correctness and determinism review
3. Security/privacy review
4. Test coverage review
5. Release readiness review
