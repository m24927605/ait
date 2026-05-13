# 01 - Blast Radius

## Pain

An agent can make a broad risky edit, and without isolation it can damage the
working tree immediately.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` asks Claude Code to create two files and delete
`src/calculator.js`. `verify.sh` proves those changes exist only in the AIT
attempt worktree and the main demo workspace is untouched.
