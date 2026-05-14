# 08 - Local-Only Provenance

## Pain

Agent metadata should not require a hosted service just to be inspectable.

## Demo Project

This case owns its own project:

```text
08-local-only-provenance/workspace/
```

The AIT metadata being inspected is repo-local under `workspace/.ait/`.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `08-local-only-provenance/workspace/`.

```bash
ait status --all --json
ait attempt list --format table
ait memory list --format table
```

Use the output to explain:

- AIT status is available from the local repo.
- Adapter health is inspectable from the CLI.
- Attempts and memory are inspectable without a hosted dashboard.
- The repo-local `.ait` directory is AIT's storage.

## Demo Takeaway

AIT provenance is local-first: the important metadata can be inspected with
AIT commands inside the repo.
