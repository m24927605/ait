# DB Migration Fixtures

These SQLite files are synthetic `.ait/state.sqlite3` snapshots used to verify
schema upgrades from old populated databases.

## Sensitive Data Policy

Fixtures must contain only synthetic repo IDs, prompts, paths, commits, tokens,
reviews, and memory content. Do not copy real `.ait` databases, user paths,
credentials, proprietary source paths, transcripts, or production prompts into
this directory.

## Fixtures

| Fixture | Source version | Expected user row counts |
| --- | ---: | --- |
| `v8_populated.sqlite3` | 8 | intents: 2, attempts: 2, attempt_commits: 2, evidence_files: 4, memory_facts: 2, memory_retrieval_events: 1, attempt_reviews: 1, attempt_review_findings: 1 |
| `v9_populated.sqlite3` | 9 | v8 rows plus attempt_identities: 2 |
| `v10_minimal.sqlite3` | 10 | intents: 1, attempts: 1, attempt_commits: 1, evidence_files: 3, memory_facts: 1, memory_retrieval_events: 1, attempt_identities: 1, attempt_aliases: 1 |

The fixtures are generated from the checked-in migrations in
`src/ait/db/schema.py`, applying migrations up to the source version and then
seeding deterministic synthetic rows.

## Regeneration

Run from the repository root:

```bash
PYTHONPATH=src uv run python tests/fixtures/db_migrations/generate.py
```

After regeneration, run:

```bash
uv run pytest tests/test_db_migrations.py -q
```
