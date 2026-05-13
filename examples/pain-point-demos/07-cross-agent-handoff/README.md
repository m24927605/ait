# 07 - Cross-Agent Handoff

## Pain

Claude Code can make a decision, then Codex takes over without seeing that
context.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` has Claude Code write and promote an `AGENTS.md` decision, imports it
as repo-local AIT memory, then asks Codex to read it from `AIT_CONTEXT_FILE`.
`verify.sh` checks that Codex copied the handoff proof token.
