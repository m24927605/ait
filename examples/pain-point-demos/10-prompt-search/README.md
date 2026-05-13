# 10 - Prompt Search

## Pain

Finding an old prompt through raw shell history is unreliable.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` queries the auth retry attempt from `04-memory-reuse`, running that
prerequisite first if needed. `verify.sh` proves AIT can recover the attempt
by intent text, changed file, and prompt or trace metadata.
