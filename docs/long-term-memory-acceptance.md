# Long-Term Memory Acceptance

## Scope

This document defines acceptance for the first Claude Code long-term
memory slice.

## Acceptance Criteria

1. `ait memory` works in a Git repository even before any attempts have
   been recorded.
2. `ait memory --format json` emits parseable JSON and does not print
   human text around it.
3. After an attempt changes files and is committed through `ait`, memory
   includes:
   - the intent title
   - the attempt id
   - the verified status
   - changed files
   - attempt commit ids
4. `ait run --adapter claude-code` writes `.ait-context.md` into the
   attempt worktree.
5. The generated `.ait-context.md` includes `AIT Long-Term Repo Memory`.
6. A no-change Claude Code wrapper run still succeeds and records no
   commits.
7. A changed Claude Code wrapper run still creates one attempt-linked
   commit.
8. `ait memory --path <prefix>` only includes attempts and hot files
   matching that path prefix.
9. `ait memory --promoted-only` only includes promoted attempts.
10. `ait memory note add/list/remove` can manage curated repo-local
    memory notes.
11. `ait memory --topic <topic>` filters curated notes by topic.
12. `ait memory --budget-chars <n>` compacts rendered memory to the
    configured character budget.
13. `ait memory search <query>` returns relevant repo-local memory
    evidence from curated notes and previous attempts.
14. `ait memory search <query> --format json` emits parseable JSON.
15. `ait memory search <query>` uses repo-local vector ranking by
    default and records the selected ranker in result metadata.
16. `ait memory search <query> --ranker lexical` keeps the deterministic
    lexical fallback available.
17. `ait run --adapter aider` and `ait run --adapter codex` write
    `.ait-context.md` by default and expose `AIT_CONTEXT_FILE`.
18. `ait bootstrap aider` and `ait bootstrap codex` install repo-local
    wrappers that route through `ait run`.
19. Aider and Codex wrapped runs capture stdout/stderr transcripts under
    `.ait/traces/`.
20. `ait memory search <query>` can find captured Aider and Codex
    transcript content.

## Manual Smoke

Create a temporary Git repository:

```bash
tmpdir="$(mktemp -d)"
python3.14 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/pip" install ait-vcs
mkdir "$tmpdir/repo"
cd "$tmpdir/repo"
git init
git config user.email test@example.com
git config user.name "Test User"
printf 'smoke\n' > README.md
git add README.md
git commit -m init
```

Verify empty memory:

```bash
"$tmpdir/venv/bin/ait" memory
"$tmpdir/venv/bin/ait" memory --format json
```

Run Claude Code through `ait`:

```bash
eval "$("$tmpdir/venv/bin/ait" doctor --fix)"
AIT_INTENT="Memory smoke" \
AIT_COMMIT_MESSAGE="memory smoke commit" \
claude -p 'Append one line to README.md'
```

Verify memory:

```bash
"$tmpdir/venv/bin/ait" memory
"$tmpdir/venv/bin/ait" memory --path README.md
"$tmpdir/venv/bin/ait" memory --budget-chars 1000
"$tmpdir/venv/bin/ait" memory note add --topic architecture "Keep memory repo-local."
"$tmpdir/venv/bin/ait" memory --topic architecture
"$tmpdir/venv/bin/ait" memory search "repo-local"
"$tmpdir/venv/bin/ait" memory search "repo-local" --ranker lexical
"$tmpdir/venv/bin/ait" attempt list
```

Verify non-Claude adapter automation with a fake binary on `PATH`:

```bash
mkdir "$tmpdir/bin"
printf '#!/bin/sh\ncp "$AIT_CONTEXT_FILE" context-copy.txt\nprintf transcript-token\n' > "$tmpdir/bin/codex"
chmod +x "$tmpdir/bin/codex"
PATH="$tmpdir/bin:$PATH" "$tmpdir/venv/bin/ait" bootstrap codex
PATH="$tmpdir/repo/.ait/bin:$tmpdir/bin:$PATH" codex
"$tmpdir/venv/bin/ait" memory search transcript-token
```

Expected result:

- `ait memory` includes a recent attempt.
- changed files include `README.md` when Claude changed it.
- the attempt has one commit when Claude changed files.
- curated notes appear in the `Curated Notes` section.
- budgeted output ends with a compaction marker if truncation is needed.
- memory search returns the matching curated note or attempt evidence.
- memory search JSON metadata includes `ranker`.
- Codex and Aider wrappers route through `ait run` and expose context.
- Codex and Aider transcript text is stored under `.ait/traces/` and
  searchable.
- the root checkout is unchanged until promotion.

## Automated Coverage

The automated test suite covers:

- memory summary construction
- memory filters
- curated memory note lifecycle
- local memory search over notes and attempt evidence
- vector and lexical memory search rankers
- non-Claude adapter context defaults and wrapper automation
- non-Claude transcript capture and search
- text rendering
- text compaction
- `ait memory` CLI output
- `.ait-context.md` memory injection
- no-change commit-message runs
- changed commit-message runs
