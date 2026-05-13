# 02 - Provenance

## Pain

After a manual agent session, it is hard to prove which intent, prompt, files,
and trace produced the result.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` asks Claude Code to create a provenance proof file. `verify.sh`
checks the changed file, verifies the attempt can be recovered by intent query,
and confirms AIT recorded a prompt or trace reference.
