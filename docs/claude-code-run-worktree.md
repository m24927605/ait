# Claude Code Run Worktree

This workflow makes Claude Code edit an ait attempt worktree instead of
the root checkout. It is the preferred path when you want provenance,
reviewable isolation, an ait-linked commit, and an explicit promote step.

Validated on 2026-04-27 with:

- `ait-vcs` local build for `0.35.0`
- Claude Code `2.1.119`
- Python 3.14

## Setup

Use a clean Git repository:

```bash
tmpdir="$(mktemp -d)"
python3.14 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install -U pip
"$tmpdir/venv/bin/python" -m pip install ait-vcs

repo="$tmpdir/repo"
mkdir "$repo"
cd "$repo"
git init
git config user.email test@example.com
git config user.name "Test User"
printf 'run smoke\n' > README.md
git add README.md
git commit -m init
```

## Run Claude In The Attempt Worktree

Run Claude through `ait run` and provide a commit message:

```bash
"$tmpdir/venv/bin/ait" run \
  --adapter claude-code \
  --format json \
  --intent "Claude run worktree smoke" \
  --commit-message "claude run smoke" \
  -- claude -p --permission-mode bypassPermissions --max-budget-usd 1 \
    'Append exactly this line to README.md: ait run worktree smoke ok'
```

`ait run` creates an intent and attempt, starts the daemon, writes a
compact `.ait-context.md` handoff file, and executes Claude with the
attempt worktree as the current working directory. When the command
exits successfully, ait removes the generated context file, stages the
remaining worktree changes, creates an ait-linked commit, and verifies
the attempt.

In JSON mode, Claude's stdout and stderr are captured in the final ait
JSON result as `command_stdout` and `command_stderr`, so stdout remains
safe to parse with `jq` or `json.load`. The JSON result includes the
`attempt_id` and `workspace_ref`.

## Verify Isolation

Before promotion, the root checkout should not contain Claude's edit:

```bash
grep 'ait run worktree smoke ok' README.md
# no match before promote
```

The attempt worktree should contain the edit:

```bash
workspace_ref="<workspace_ref from the ait run JSON>"
grep 'ait run worktree smoke ok' "$workspace_ref/README.md"
```

For the validated run, the ait JSON result reported:

```text
exit_code: 0
changed: README.md
commit_count: 1
workspace_status: clean
root_has_line_before_promote: false
workspace_has_line: true
```

## Promote

After reviewing the attempt, promote it:

```bash
"$tmpdir/venv/bin/ait" attempt show <attempt-id>
"$tmpdir/venv/bin/ait" attempt promote <attempt-id> --to main
```

For repositories whose default branch is still `master`, use
`--to master`.

After promotion, the root checkout should contain Claude's edit:

```bash
grep 'ait run worktree smoke ok' README.md
```

For the validated run, promotion reported:

```text
verified_status: promoted
result_promotion_ref: refs/heads/master
root_has_line_after_promote: true
```

## Relationship To Native Hooks

`ait run --adapter claude-code` gives lifecycle, worktree isolation,
command provenance, and an ait-linked commit. Native Claude Code hooks
installed by `ait adapter setup claude-code` add tool-level evidence
such as individual file reads, writes, and shell commands.

Use `ait run` first when isolation and promote/review flow are the
priority. Add native hooks when you also need fine-grained tool
telemetry.

## Repo-Local Wrapper

For lower friction, install a wrapper once:

```bash
eval "$("$tmpdir/venv/bin/ait" init --shell)"
```

After that, `claude ...` resolves to `.ait/bin/claude` inside the repo.
The wrapper delegates to the real Claude Code binary through:

```bash
ait run --adapter claude-code --format json --commit-message ...
```

Set `AIT_INTENT` and `AIT_COMMIT_MESSAGE` to control the generated ait
intent and commit message without changing the Claude command:

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  'Append one line to README.md'
```

If `AIT_COMMIT_MESSAGE` is not set, ait derives a default commit message
from the adapter and intent. Successful runs with changes are committed
automatically in the attempt worktree. If Claude already creates a git
commit, ait records that existing commit and does not create a duplicate.

To set up direnv instead of changing the current shell directly:

```bash
"$tmpdir/venv/bin/ait" bootstrap
direnv allow
```

Verify the automation path:

```bash
"$tmpdir/venv/bin/ait" status
"$tmpdir/venv/bin/ait" doctor
```
