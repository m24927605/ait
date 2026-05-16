# Context Manifest Memory Trust Design

## Purpose

AIT already prevents candidate, stale, superseded, and policy-blocked memory
from becoming trusted review baseline. The remaining gap is user-visible
explanation in `AIT_CONTEXT_FILE` and context manifests.

This design makes memory trust decisions inspectable for run, review, and
multi-agent handoff contexts.

## Implementation Status

Implemented for wrapped run context generation:

- `src/ait/context_manifest.py` writes versioned `ait.context_manifest` payloads.
- `AIT_CONTEXT_FILE` now renders separate `Trusted Baseline` and
  `Advisory Or Excluded Memory` sections for run context.
- The sibling manifest records trusted, advisory, and excluded entries with
  explicit reasons such as `candidate_not_adopted`, `expired_fact`,
  `superseded_fact`, and `policy_blocked`.
- Policy-blocked content is never copied into the context body or manifest
  body/hash fields.
- Regression coverage lives in `tests/test_runner.py` and
  `tests/fixtures/context_manifest/schema_v1_contract.json`.

Review/session-specific context manifests should reuse this schema, but are not
yet separately verified by end-to-end review/session tests.

## Non-goals

- No hidden chat sync.
- No external vector database.
- No automatic adoption of candidate memory.
- No inclusion of policy-blocked secret content in prompts.

## Data contract

Every generated context file should have a sibling manifest:

```text
.ait/context/<context-id>.md
.ait/context/<context-id>.manifest.json
```

Manifest schema:

```json
{
  "schema": "ait.context_manifest",
  "schema_version": 1,
  "context_id": "ctx_...",
  "owner_kind": "attempt",
  "owner_id": "repo:01ATTEMPT",
  "generated_at": "2026-05-16T00:00:00Z",
  "policy_hash": "sha256:...",
  "entries": [
    {
      "source_id": "fact:auth-owner-required",
      "source_type": "memory_fact",
      "topic": "authorization",
      "status": "accepted",
      "trust_level": "trusted",
      "selected": true,
      "trusted_baseline": true,
      "included_in_context": true,
      "body_included": true,
      "reason": "accepted_trusted_fact",
      "source_ref": "trusted:auth",
      "source_path_redacted": null,
      "content_hash": "sha256:...",
      "bytes_included": 128
    }
  ]
}
```

## Trust rendering rules

| Memory state | Trusted baseline | Body in `AIT_CONTEXT_FILE` | Manifest behavior |
| --- | --- | --- | --- |
| accepted + trusted | Yes | Yes | `trusted_baseline: true` |
| candidate | No | No by default | `reason: candidate_not_adopted` |
| stale / expired | No | No by default | `reason: expired_fact` |
| superseded | No | No by default | `reason: superseded_fact`, include `superseded_by` |
| policy-blocked | No | Never | `reason: policy_blocked`, no body/hash of secret content |

Policy-blocked entries may record a redacted path or source label, but not the
blocked content. Stale and superseded entries may be listed in an "Excluded or
advisory context" section only if they are clearly marked non-trusted.

## Context file layout

`AIT_CONTEXT_FILE` should separate trust levels:

```markdown
# AIT Context

## Trusted Baseline

- Authorization owner checks are required before returning private resources.

## Advisory Or Excluded Memory

- fact:billing-superseded-queue: excluded, superseded by fact:billing-current-queue.
- fact:auth-owner-not-required-policy-blocked: excluded by policy.
```

The excluded section must not include policy-blocked body text.

## Implementation plan

1. Add `src/ait/context_manifest.py`:
   - schema constants;
   - manifest entry builder;
   - writer for context markdown + manifest JSON.
2. Wire context manifest generation into:
   - wrapped run context: implemented;
   - adversarial review context: follow-up verification;
   - session participant context when applicable: follow-up verification.
3. Reuse memory policy and review baseline exclusion reasons:
   - `candidate_not_adopted`;
   - `policy_blocked`;
   - `superseded_fact`;
   - `expired_fact`.
4. Add schema v1 golden fixture:
   - `tests/fixtures/context_manifest/schema_v1_contract.json`
5. Extend memory trust fixtures so each fact has expected manifest behavior.

## Tests

Required tests:

- Accepted trusted facts appear in trusted baseline and manifest.
- Candidate facts do not appear as trusted baseline.
- Stale/expired facts are excluded with `expired_fact`.
- Superseded facts are excluded with `superseded_fact`.
- Policy-blocked facts do not include body text in context file or manifest.
- Wrapped run context uses the trust labels; review/session contexts must add
  explicit regression coverage before claiming parity.
- Manifest schema golden fixture protects top-level and entry keys.
- Redacted path behavior is stable.

## Acceptance

This weakness is resolved when a clean-repo fixture can:

1. create accepted, candidate, stale, superseded, and policy-blocked facts;
2. generate `AIT_CONTEXT_FILE` plus manifest;
3. prove only accepted/trusted facts enter trusted baseline;
4. prove excluded/advisory entries are inspectable with reasons;
5. prove policy-blocked body text never leaks.

## Code Review Standard

Reviewers must block changes that:

- put candidate/stale/superseded/policy-blocked facts into trusted baseline;
- include policy-blocked body text in prompts, manifests, or reports;
- add a context source without source/status/trust metadata;
- change manifest shape without schema_version/golden fixture update;
- describe memory as perfect recall, semantic truth, or hidden chat sync.
