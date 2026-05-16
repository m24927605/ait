# Review Benchmark Real Reviewer Dogfood Design

## Purpose

AIT now has deterministic benchmark fixtures and a fake-reviewer CI path. The
remaining weakness is evidence from real local reviewer adapters. This design
defines how to collect Claude Code and Codex reviewer dogfood data without
turning one machine-local run into a broad quality claim.

## Implementation Status

Implemented:

- `ait review benchmark run --reviewer-adapter <adapter> --dogfood` invokes the
  real reviewer adapter path explicitly.
- Real reviewer runs record adapter metadata, resolved binary path when known,
  redacted command argv, local auth assumptions, permission profile, optional
  model label, repo revision, fixture hash, latency, and token/cost placeholders.
- `--reviewer-adapter` without `--dogfood` fails closed.
- The fake reviewer path remains the CI-safe default and still requires no
  network, login state, API key, or paid credits.
- Mock real-adapter tests cover metadata capture and redaction.

Not yet done: no real Claude Code or Codex dogfood artifact is committed here,
so public docs must still avoid benchmark-proven quality claims.

## Non-goals

- No real reviewer run is required in CI.
- No API key, paid credit, network access, or local login state is required for
  the fake-reviewer benchmark.
- No public claim that adversarial review is benchmark-proven until the report
  includes enough repeated real reviewer runs.
- No raw prompt/output publication without redaction.

## Command model

The fake path remains:

```bash
ait review benchmark run --fixture tests/fixtures/review_benchmark/cases.json \
  --fake-reviewer fake:case --format json
```

Real dogfood uses an explicit adapter:

```bash
ait review benchmark run --fixture tests/fixtures/review_benchmark/cases.json \
  --reviewer-adapter claude-code \
  --dogfood \
  --output .ait/review-benchmark/claude-code-YYYYMMDDTHHMMSSZ.json \
  --format json
```

Codex follows the same shape:

```bash
ait review benchmark run --fixture tests/fixtures/review_benchmark/cases.json \
  --reviewer-adapter codex \
  --dogfood \
  --output .ait/review-benchmark/codex-YYYYMMDDTHHMMSSZ.json \
  --format json
```

The command must fail closed unless `--dogfood` is present for real adapters.
This prevents accidental network/local-auth use in CI.

## Permission capture

Before invoking a real reviewer, the command records:

- adapter name;
- resolved binary path;
- command argv with secrets redacted;
- local auth assumption, if known;
- selected permission mode, if supplied;
- model, if supplied or detectable;
- repo revision and fixture hash;
- environment notes such as "network may be used by local CLI".

For reviewer-only dogfood, the default permission profile should be read-only.
If the adapter asks for broader permissions, the run should stop and require an
explicit `--permission-profile` or adapter-specific flag. The report must record
that decision.

## Report schema additions

Real dogfood reports extend `ait.review_benchmark` with optional fields:

```json
{
  "schema": "ait.review_benchmark",
  "schema_version": 1,
  "reviewer": "claude-code",
  "dogfood": true,
  "fixture_hash": "sha256:...",
  "repo_revision": "...",
  "adapter": {
    "name": "claude-code",
    "binary": "...",
    "model": "unknown",
    "permission_profile": "read-only",
    "local_auth": "assumed"
  },
  "run_notes": [
    "real reviewer results are machine/local-auth dependent"
  ],
  "case_results": []
}
```

Raw reviewer output must either be omitted, stored under `.ait/` with redaction,
or linked as a local artifact that is not committed by default.

## Metrics

The report must include:

- finding recall;
- false positive count and false positive rate;
- evidence completeness;
- risk scoring calibration;
- baseline usefulness;
- trusted baseline contamination rate;
- latency per case and total latency;
- token/cost fields when available, otherwise `null`;
- non-actionable warning count.

## Implementation plan

1. Extend `src/ait/review_benchmark.py` with a reviewer adapter interface:
   - fake reviewer remains the default CI implementation;
   - real reviewer adapter is opt-in and marked dogfood.
2. Add `ait review benchmark run --reviewer-adapter ... --dogfood`.
3. Add redaction for argv, environment, and raw outputs.
4. Add report rendering sections for adapter metadata and limitations.
5. Add a dogfood artifact template under `docs/review-benchmark-dogfood-report.md`.
6. Run at least one Claude Code and one Codex local reviewer pass before making
   any "dogfooded" claim. The real adapter path is implemented, but those
   artifacts are still required for stronger claims.

## Tests

Required automated tests:

- Fake reviewer path still runs without network/API key/login.
- Real reviewer path without `--dogfood` exits nonzero.
- Mock real adapter records adapter metadata and fixture hash.
- Redaction removes API keys/tokens from command metadata.
- Markdown report includes limitations and local-auth dependency.
- Invalid fixture exits nonzero.
- Schema v1 golden fixture remains stable or bumps version.

Manual dogfood checks:

- Claude Code run captured or explicitly unavailable with reason.
- Codex run captured or explicitly unavailable with reason.
- Each report records model/permission assumptions.
- Report does not claim guarantee, proof, or complete bug detection.

## Acceptance

The dogfood measurement weakness is considered resolved when:

- fake benchmark remains green in CI;
- the explicit `--dogfood` real-adapter path records local metadata;
- at least one Claude Code and one Codex dogfood report are captured, or the
  report explains why an adapter was unavailable on the test machine;
- public docs link the report while saying results are local dogfood evidence;
- the comparison/docs pages still avoid benchmark-proven quality claims.

## Code Review Standard

Reviewers must block changes that:

- make real reviewer invocation part of required CI;
- hide local auth/network assumptions;
- commit raw unredacted reviewer output;
- compare real reviewer results without fixture hash/repo revision;
- describe dogfood data as proof, guarantee, or universal quality.
