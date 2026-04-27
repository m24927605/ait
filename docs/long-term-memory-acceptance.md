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
"$tmpdir/venv/bin/ait" attempt list
```

Expected result:

- `ait memory` includes a recent attempt.
- changed files include `README.md` when Claude changed it.
- the attempt has one commit when Claude changed files.
- the root checkout is unchanged until promotion.

## Automated Coverage

The automated test suite covers:

- memory summary construction
- text rendering
- `ait memory` CLI output
- `.ait-context.md` memory injection
- no-change commit-message runs
- changed commit-message runs
