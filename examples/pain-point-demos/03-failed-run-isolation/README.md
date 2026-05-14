# 03 - Failed-Run Isolation

## Pain

A failed agent run can leave broken tests and partial edits in the main working
tree.

## Demo Project

This case owns its own project:

```text
03-failed-run-isolation/workspace/
```

Codex is asked to break `test/calculator.test.js` inside an isolated attempt.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `03-failed-run-isolation/workspace/`.

```bash
ait query --on attempt 'title~"Codex: intentionally broken test attempt"' --format table
ait attempt show <attempt-id>
```

Use the output to explain:

- `workspace_ref` points to the isolated failed attempt.
- `files.changed` shows the broken test file.
- `raw_trace_ref` keeps the Codex trace and failing test output.
- The failed work is recoverable evidence, not an accidental main-worktree edit.

## Demo Takeaway

AIT keeps failed work visible and inspectable without letting it silently
pollute the main workspace.
