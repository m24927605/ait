# Claude Code Live Smoke

This smoke test verifies the native Claude Code hook path with a real
Claude Code run, not only simulated hook payloads.

Validated on 2026-04-27 with:

- `ait-vcs` local build for `0.5.2`
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
printf 'live smoke\n' > README.md
git add README.md
git commit -m init
```

Install ait and Claude Code hook settings:

```bash
"$tmpdir/venv/bin/ait" init
"$tmpdir/venv/bin/ait" adapter setup claude-code
"$tmpdir/venv/bin/ait" adapter doctor claude-code
```

The generated `.claude/settings.json` should call the Python executable
from the same environment that ran `ait adapter setup claude-code`. This
matters for `pipx` and virtualenv installs because the hook process must
be able to import `ait`.

## Run Claude Code

Run Claude Code in non-interactive mode and allow it to edit the test
repository:

```bash
claude -p \
  --settings .claude/settings.json \
  --permission-mode bypassPermissions \
  --max-budget-usd 1 \
  'Append exactly this line to README.md: ait live hook smoke ok'
```

## Verify

Check the file edit:

```bash
grep 'ait live hook smoke ok' README.md
```

Check that ait recorded a Claude Code attempt and tool evidence:

```bash
"$tmpdir/venv/bin/ait" intent list
"$tmpdir/venv/bin/ait" attempt list
"$tmpdir/venv/bin/ait" query --on attempt 'observed.tool_calls>0'
```

For the validated run, `ait attempt show <attempt-id>` reported:

```text
reported_status: finished
result_exit_code: 0
verified_status: succeeded
observed_tool_calls: 3
observed_file_reads: 1
observed_file_writes: 1
observed_commands_run: 1
```

The evidence files included the test repository `README.md` as both a
read and touched path.

## Current Limitation

The Claude Code hook records provenance for the live session, but it
does not force Claude Code to edit inside the ait attempt worktree.
Claude edited the active repository checkout during this smoke test,
while ait created a separate attempt workspace for provenance tracking.
A deeper integration should make Claude Code execute inside
`AIT_WORKSPACE_REF` or use Claude Code worktree support directly.
