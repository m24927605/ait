# 05 - Parallel Agents

## Pain

Running Claude Code and Codex in the same checkout can cause them to overwrite
each other's files.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` starts Claude Code and Codex concurrently. Both create
`approach.txt`, but with different contents. `verify.sh` proves the two
outputs landed in separate AIT worktrees.
