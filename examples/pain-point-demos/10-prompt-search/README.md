# 10 - Prompt Search

## Pain

Finding an old prompt through raw shell history is unreliable.

## Demo Project

This case owns its own project:

```text
10-prompt-search/workspace/
```

The demo creates a searchable Claude Code attempt, then recovers it through AIT
queries.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `10-prompt-search/workspace/`.

```bash
ait query --on attempt 'title~"auth retry"' --format table
ait query --on attempt 'files_changed~"notes/auth-retry.md"' --format table
ait attempt show <attempt-id>
```

Use the output to explain:

- AIT can recover an old attempt by intent text.
- AIT can recover an old attempt by changed file.
- `raw_prompt_ref` or `raw_trace_ref` points to captured prompt/trace evidence.
- This is more reliable than shell history or terminal scrollback.

## Demo Takeaway

AIT makes prompt and attempt history queryable through local metadata.
