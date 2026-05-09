# AIT Review Orchestration Phase 5 Implementation Spec

Status: Proposed implementation spec

Phase 5 adds multi-reviewer profiles, consensus handling, richer finding lifecycle, and review/finding query/report refinement. This phase is only for high-value or critical-risk review paths.

## Objective

Support profile-based multi-reviewer review:

```bash
ait review attempt latest-reviewable --mode multi --profile security --profile regression
```

Critical risk may require multiple profiles. Disagreement should result in human review or hold, not silent pass.

## Non-Goals

Phase 5 不做：

- 不讓 multi-reviewer 成為 default for all attempts。
- 不自動修復 findings。
- 不刪除 finding history。
- 不把 accepted risk 偽裝成 passed。
- 不做 GitHub PR inline comment integration。

## Files To Change

預期變更：

- `src/ait/review.py`
  - multi-profile orchestration
  - finding merge/dedup v0
  - consensus result

- `src/ait/review_policy.py`
  - required profiles by path/risk
  - consensus rules
  - disagreement handling

- `src/ait/cli/review.py`
  - `review finding list`
  - `review finding update`
  - profile result display

- `src/ait/cli_parser.py`
  - finding lifecycle commands
  - multi-profile flags

- `src/ait/query/*` or review-specific listing
  - query/list open findings and overridden reviews

- `src/ait/report/*`
  - profile-level review result
  - consensus/disagreement
  - accepted risk

- tests:
  - `tests/test_review_profiles.py`
  - `tests/test_review_consensus.py`
  - `tests/test_review_findings.py`
  - `tests/test_review_query.py`

## Files Not To Change

Avoid modifying:

- verifier
- low-level Git workspace semantics
- unrelated memory acceptance behavior
- Phase 1 deterministic risk score unless required by profile selection tests

## Profile Contract

Supported profiles:

- `security`
- `regression`
- `maintainability`
- `release`

Profile responsibilities:

- `security`: auth, secrets, CI, deploy, dependencies, injection, permission boundary
- `regression`: behavior changes, edge cases, test gaps
- `maintainability`: architecture, readability, duplication, local pattern alignment
- `release`: migrations, versioning, docs, backward compatibility, operational risk

Policy example:

```json
{
  "review": {
    "required_profiles": {
      "auth/**": ["security", "regression"],
      ".github/workflows/**": ["security"],
      "migrations/**": ["regression", "release"]
    }
  }
}
```

## Consensus Contract

Consensus v0:

- any `critical` or `high` blocking finding -> blocked
- all required profiles passed -> passed
- required profile failed or missing -> blocked/hold
- profile disagreement on high/critical severity -> needs human review
- override can bypass but must mark review `overridden`

Represent needs-human-review as either:

- new status `needs_human_review`, or
- `blocked` with reason code `review_disagreement`

Pick one and document it in code/tests.

## Finding Lifecycle CLI Contract

Commands:

```bash
ait review finding list [--status open] [--severity high]
ait review finding update <finding-id> --status acknowledged --reason "triaged"
ait review finding update <finding-id> --status false_positive --reason "not reachable"
ait review finding update <finding-id> --status accepted_risk --reason "accepted for release"
```

Rules:

- `false_positive` requires reason.
- `accepted_risk` requires reason and should create audit entry.
- lifecycle update must not edit original finding body.
- lifecycle update must not mutate target attempt.

## Finding Dedup V0

Full semantic dedup is out of scope.

V0 dedup key can be:

```text
review_id + severity + path + line + normalized_title
```

If two profiles report same key:

- preserve both reviewer sources if possible
- show one merged finding in report
- keep raw findings in DB or artifact

## Required Tests

Profile tests:

- auth path requires security + regression
- workflow path requires security
- migration path requires regression + release
- non-sensitive path does not trigger multi-reviewer by default

Consensus tests:

- one high blocking finding blocks
- all profiles pass -> passed
- required profile missing -> blocked/hold
- reviewer disagreement -> needs human review / blocked with disagreement reason
- override changes review status to overridden without changing original findings

Lifecycle tests:

- open -> acknowledged
- open -> false_positive requires reason
- open -> accepted_risk requires reason and audit
- superseded review marks old findings stale/superseded
- lifecycle update does not change original title/body/evidence

Query/list tests:

- list open high findings
- list accepted risk findings
- list overridden reviews
- list findings by target attempt

Report tests:

- report shows profile results
- report shows consensus status
- report shows disagreement
- report shows accepted risk separately from passed

Regression tests:

- multi-reviewer not triggered for low-risk default
- apply gate still blocks high findings
- accepted risk does not become passed

## Verification Commands

Targeted:

```bash
PYTHONPATH=src uv run pytest tests/test_review_profiles.py tests/test_review_consensus.py tests/test_review_findings.py tests/test_review_query.py -q
```

Regression:

```bash
PYTHONPATH=src uv run pytest tests/test_cli_run_review.py tests/test_review_gate.py tests/test_landing.py -q
```

## Implementation Review Checklist

- Multi-reviewer only applies when policy/risk requires it.
- Consensus fails closed.
- Disagreement is visible and actionable.
- Lifecycle updates preserve original finding history.
- Accepted risk is auditable and not treated as passed.
- Query/report output helps humans triage findings.
