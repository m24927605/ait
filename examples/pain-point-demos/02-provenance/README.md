# 02 - Provenance

## Pain

After a manual agent session, it is hard to prove which intent, prompt, files,
and trace produced the result.

## Demo Project

This case owns its own project:

```text
02-provenance/workspace/
```

Claude Code writes `notes/provenance-proof.md` in an isolated AIT attempt.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `02-provenance/workspace/`.

```bash
ait query --on attempt 'title~"Claude: provenance proof"' --format table
ait attempt show <attempt-id>
```

Use the output to explain:

- `agent_harness` shows the result came from Claude Code.
- `files.changed` shows which file was changed.
- `raw_prompt_ref` and `raw_trace_ref` show AIT preserved the prompt/trace.
- The attempt can be recovered by intent text instead of terminal history.

## Demo Takeaway

AIT turns an agent run into searchable local evidence: intent, attempt,
changed files, and trace metadata.
