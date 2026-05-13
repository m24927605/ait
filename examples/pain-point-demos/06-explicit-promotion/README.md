# 06 - Explicit Promotion

## Pain

An agent saying "done" should not automatically mean its result is accepted
into `main`.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` promotes only Claude Code's approach from `05-parallel-agents` to
`main`, running that prerequisite first if needed. `verify.sh` proves
`approach.txt` appears in `main` only after explicit promotion.
