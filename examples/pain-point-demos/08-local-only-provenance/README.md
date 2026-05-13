# 08 - Local-Only Provenance

## Pain

Agent metadata should not require a hosted service just to be inspectable.

## Demo

```bash
./run.sh
./verify.sh
```

`run.sh` captures AIT status and local `.ait` files. `verify.sh` proves the
state database and status metadata are repo-local.
