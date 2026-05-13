# 09 - Verification Evidence

## Pain

An agent can say tests pass without actually running test commands.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` asks Claude Code to make a code change while avoiding test commands.
`verify.sh` checks AIT's observed test count and runs the light review so the
missing test evidence is visible.
