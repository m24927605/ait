# 04 - Memory Reuse

## Pain

Claude investigates a problem, then Codex starts from scratch and repeats the
same work.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` has Claude Code record an auth retry finding, stores that finding as
repo-local AIT memory, then asks Codex to read it from `AIT_CONTEXT_FILE`.
`verify.sh` checks that Codex copied the proof token from AIT context into its
own attempt workspace.
