# AIT Pain-Point Demos

This directory contains one executable demo folder for each pain point on the
`why-ait` page. The demos use the real Claude Code CLI and Codex CLI through
AIT's repo-local wrappers.

## Prerequisites

- `ait` on `PATH`
- `git`
- Node.js and `npm`
- `python3`
- Claude Code CLI installed and logged in
- Codex CLI installed and logged in

## Setup

Run this once before demoing:

```bash
cd examples/pain-point-demos
./setup.sh
```

By default this resets:

```text
~/lab/ait-pain-demo
~/lab/ait-pain-demo-state
```

Override those paths when needed:

```bash
AIT_PAIN_DEMO_WORKSPACE=/tmp/ait-pain-demo \
AIT_PAIN_DEMO_STATE_DIR=/tmp/ait-pain-demo-state \
./setup.sh
```

## Run One Demo

Each pain-point folder has the same interface:

```bash
cd examples/pain-point-demos/01-blast-radius
./run.sh
./verify.sh
```

`run.sh` creates the relevant AIT attempt. `verify.sh` prints `PASS ...` or
exits non-zero with `FAIL ...`.

## Run The Full Suite

This calls `setup.sh`, then runs and verifies all ten demos in order:

```bash
cd examples/pain-point-demos
./run-all.sh
```

To verify previous runs without rerunning agents:

```bash
./verify-all.sh
```

## Folder Map

1. `01-blast-radius`
2. `02-provenance`
3. `03-failed-run-isolation`
4. `04-memory-reuse`
5. `05-parallel-agents`
6. `06-explicit-promotion`
7. `07-cross-agent-handoff`
8. `08-local-only-provenance`
9. `09-verification-evidence`
10. `10-prompt-search`

## Notes

- The demos intentionally use throwaway paths under `~/lab`.
- Claude Code demo scripts unset `ANTHROPIC_API_KEY` for the child command so a
  stale external API key does not override the local Claude Code login.
- `05-parallel-agents` starts Claude Code and Codex concurrently.
- `06-explicit-promotion` depends on the attempts from `05-parallel-agents`
  and runs that prerequisite automatically if needed.
- `10-prompt-search` depends on the auth retry attempt from
  `04-memory-reuse` and runs that prerequisite automatically if needed.
