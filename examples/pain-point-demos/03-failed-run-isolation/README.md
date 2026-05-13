# 03 - Failed-Run Isolation

## Pain

A failed agent run can leave broken tests and partial edits in the main
working tree.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` asks Codex to intentionally break the calculator test and stop after
the failure. `verify.sh` proves the failing test exists in the attempt
worktree while the main demo workspace still has the passing test.
