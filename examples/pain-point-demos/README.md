# AIT Pain-Point Demos

This directory contains executable demo folders for AIT pain points, plus a
`09-1` variant that demonstrates Claude Code implementation with Codex review.
Each folder owns its own demo project under `workspace/`, so the files being
changed are visible inside the same pain-point folder.

The demos use the real Claude Code CLI and Codex CLI through AIT's repo-local
wrappers.

## Prerequisites

- `ait` on `PATH`
- `git`
- Node.js and `npm`
- `python3`
- Claude Code CLI installed and logged in
- Codex CLI installed and logged in

## Setup

To prepare every demo workspace:

```bash
cd examples/pain-point-demos
./setup.sh
```

This creates or resets:

```text
examples/pain-point-demos/01-blast-radius/workspace/
examples/pain-point-demos/02-provenance/workspace/
...
examples/pain-point-demos/10-prompt-search/workspace/
```

## Run One Demo

Each pain-point folder has its own `run.sh`:

```bash
cd examples/pain-point-demos/01-blast-radius
./run.sh
```

After `run.sh` finishes, follow that folder's AIT verification flow to explain the result from AIT metadata and CLI output.

## Run The Full Suite

This resets every workspace, then runs every scenario:

```bash
cd examples/pain-point-demos
./run-all.sh
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
9. `09-verification-evidence` - deterministic adversarial review
9-1. `09-1-codex-reviewer` - Claude Code implementation, Codex review
10. `10-prompt-search`

## Presentation Flow

For presentation, make the evidence come from AIT CLI output:

```bash
ait query ...
ait attempt list ...
ait attempt show ...
ait memory list ...
ait review attempt ...
ait status ...
```

The shell scripts are only scenario launchers. The evidence should come from AIT
metadata and AIT CLI output.
