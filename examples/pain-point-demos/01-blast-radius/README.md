# 01 - Blast Radius

## Pain

An agent can make a broad risky edit, and without isolation it can damage the
working tree immediately.

## Demo Project

This case owns its own project:

```text
01-blast-radius/workspace/
```

The file Claude Code is asked to delete is:

```text
01-blast-radius/workspace/src/calculator.js
```

If `workspace/` does not exist yet, `./run.sh` creates it.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `01-blast-radius/workspace/`.

```bash
ait query --on attempt 'title~"Claude: broad risky edit"' --format table
ait attempt show <attempt-id>
```

Use the output to explain:

- `workspace_ref` is the isolated attempt worktree.
- `files.changed` shows the risky edit captured by AIT.
- `raw_prompt_ref` or `raw_trace_ref` shows AIT kept prompt/trace evidence.
- The main workspace is not changed unless the attempt is applied.

## Demo Takeaway

AIT does not ask the audience to trust the agent. It gives them an attempt,
changed-file metadata, an isolated worktree path, and captured trace evidence
that can be inspected with AIT commands.
