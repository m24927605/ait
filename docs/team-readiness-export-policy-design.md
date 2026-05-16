# Team Readiness Export And Policy Design

## Purpose

AIT is repo-local and alpha. The next adoption step is not automatic cloud sync;
it is a manual, inspectable way for power users and small teams to move metadata
and enforce shared policy.

This design covers two capabilities:

1. metadata export/import bundles;
2. repo-local team policy profiles.

Console mutation recovery is covered separately in
[`docs/console-mutation-recovery-design.md`](console-mutation-recovery-design.md).

## Implementation Status

Implemented as a local, dry-run-first slice:

- `src/ait/team_policy.py` validates `.ait/policy.json` with schema
  `ait.team_policy` and fail-closed validation output
  `ait.team_policy.validation`.
- `ait policy validate --format json` and `ait policy show --format json`
  expose the effective policy and validation errors.
- `src/ait/metadata_bundle.py` emits schema `ait.metadata_bundle` for local
  metadata export dry-run payloads and schema `ait.metadata_import_plan` for
  import dry-run plans.
- `ait metadata export --dry-run --output ... --format json` writes nothing and
  reports what would be exported.
- `ait metadata import --input ... --dry-run --format json` validates the bundle
  and reports a no-write import plan.

Not implemented: automatic cross-machine sync, non-dry-run import, telemetry,
SaaS dashboards, auto push, auto merge, or browser mutation recovery.

## Non-goals

- No automatic cross-machine sync.
- No remote service, account system, or telemetry.
- No implicit raw transcript export.
- No import that overwrites current repo state without dry-run conflict review.

## Metadata bundle

Current commands:

```bash
ait metadata export --dry-run --output ait-metadata.bundle.json --format json
ait metadata import --input ait-metadata.bundle.json --dry-run
```

Current bundle/report shape:

```json
{
  "schema": "ait.metadata_bundle",
  "schema_version": 1,
  "operation": "export",
  "dry_run": true,
  "status": "planned",
  "created_at": "2026-05-16T00:00:00Z",
  "repo": {
    "identity": "...",
    "name": "repo"
  },
  "object_counts": {},
  "contents": {},
  "redaction": {
    "absolute_paths": "omitted",
    "secrets": "redacted",
    "memory_bodies": "omitted",
    "review_finding_bodies": "omitted"
  }
}
```

Default export excludes:

- raw transcripts;
- raw reviewer outputs;
- absolute local paths;
- environment variables;
- files outside the repository;
- policy-blocked source content.

Import remains dry-run-only in this slice:

1. `--dry-run` reports identity match warnings, redactions, and object counts.
2. A future non-dry-run import must be explicitly designed and tested before it
   can write metadata.

## Team policy profile

Suggested path:

```text
.ait/policy.json
```

Schema:

```json
{
  "schema": "ait.team_policy",
  "schema_version": 1,
  "review": {
    "default_mode": "light",
    "required_before_apply": false,
    "blocking_severities": ["critical", "high"]
  },
  "memory": {
    "trusted_statuses": ["accepted"],
    "allow_live_sources": ["CLAUDE.md", "AGENTS.md"],
    "block_paths": ["secret/**"]
  },
  "apply": {
    "allow_dirty_root": false,
    "require_review_clearance": true
  },
  "console": {
    "actions_enabled": false
  },
  "redaction": {
    "exclude_env_patterns": ["*TOKEN*", "*KEY*", "*SECRET*"]
  }
}
```

Invalid policy must fail closed. If a policy file exists but is invalid, AIT
should reject mutation paths and show the validation error.

Suggested commands:

```bash
ait policy validate --format json
ait policy show --format json
ait doctor --policy
```

## Implementation plan

1. Add schema constants and parser:
   - `src/ait/team_policy.py`
2. Add golden fixtures:
   - `tests/fixtures/team_policy/schema_v1_contract.json`
   - `tests/fixtures/metadata_bundle/schema_v1_contract.json`
3. Add `ait policy validate/show` before enforcing every command.
4. Add `ait metadata export/import --dry-run`: implemented.
5. Wire policy into memory recall, review gate, apply gate, and console action
   preflight: follow-up; current slice validates and reports policy only.
6. Update README/site docs only after tests prove the behavior: implemented for
   this dry-run slice.

## Tests

Metadata bundle tests:

- export omits raw traces by default;
- export redacts absolute paths and env-like values;
- dry-run import reports repo identity mismatch;
- import writes nothing; non-dry-run import is not implemented;
- import does not duplicate existing attempts/findings/facts;
- schema golden fixture protects payload shape.

Policy profile tests:

- valid policy loads and appears in `ait policy show --format json`;
- invalid policy fails closed;
- missing policy preserves current defaults;
- memory source block rules are validated in policy output; runtime enforcement
  is follow-up;
- apply gate respects `require_review_clearance`: follow-up for team policy;
- console action mode respects `console.actions_enabled`: follow-up for browser
  action mode;
- schema golden fixture protects payload shape.

## Acceptance

This slice improves the alpha adoption weakness when:

- users can inspect redacted metadata export/import plans with dry-run reporting;
- teams can commit or ignore `.ait/policy.json` intentionally;
- invalid policy blocks mutation paths rather than silently falling back;
- public docs still say AIT has no automatic cross-machine sync;
- no telemetry or remote service is introduced.

Full resolution still requires runtime enforcement of team policy, non-dry-run
import design, and UI mutation recovery.

## Code Review Standard

Reviewers must block changes that:

- introduce automatic sync or network upload;
- export raw traces or secrets by default;
- import metadata without dry-run conflict reporting;
- let invalid policy silently pass;
- make policy behavior invisible in JSON/status output;
- weaken local-only/no-telemetry public docs.
