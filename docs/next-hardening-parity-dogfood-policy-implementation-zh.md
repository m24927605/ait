# AIT Context Parity, Real Dogfood, And Runtime Policy Implementation Plan

## 目的

這份文件把三個尚未完成的成熟度缺口轉成可實作、可測試、可審查的工程標準。
本文件不是 roadmap：文件落地後，對應實作與測試必須在同一工作批次完成。

## Prompt-To-Artifact Checklist

| Requirement | Artifact |
| --- | --- |
| Review context 使用 versioned `ait.context_manifest` | `src/ait/review_baseline.py` writes review brief sidecar manifests and central `.ait/context/review-*.manifest.json` |
| Session participant context 使用 versioned `ait.context_manifest` | `src/ait/session_room.py` writes session context sidecar manifests with `schema: ait.context_manifest` |
| trusted / advisory / excluded memory 明確分開 | Context markdown includes trust sections; manifests expose `trust_level`, `trusted_baseline`, `reason` |
| candidate/stale/superseded/policy-blocked 不成為 trusted baseline | Context manifest regression tests for run/review/session |
| policy-blocked body 不進 prompt/manifest/artifact | Regression tests seed blocked facts and assert secret body absence |
| 真實 Claude/Codex dogfood | `docs/review-benchmark-real-dogfood-results-*.json` artifacts from actual local CLI command, or truthful unavailable artifacts |
| Dogfood 不造假 | Artifact must say `status: unavailable` or failed if CLI/auth/env is unavailable; no mock adapter may be labeled as real |
| Team policy runtime enforcement | `src/ait/team_policy.py` enforcement schema and hooks in apply, review, console action, and context trust filtering |
| Invalid policy fail closed | CLI JSON tests for apply/review/console/context generation with invalid `.ait/policy.json` |
| No SaaS / telemetry / sync / auto push / auto merge | Docs and artifacts explicitly state local-only boundaries |

## Design

### 1. Review/Session Context Manifest Parity

The single source of truth for context trust manifests is `ait.context_manifest`.
Review and session paths must not keep custom manifest shapes that silently
diverge from wrapped runs.

Implementation rules:

- Review briefs keep their existing reviewer-friendly markdown, but every brief
  gets a sibling `*.md.manifest.json` with `schema: ait.context_manifest`.
- Review artifacts include `context_manifest_ref` so reports can trace the
  brief to the trust manifest.
- Session participant contexts use the same schema. Session-specific metadata
  such as `session_id`, `turn_id`, `participant_id`, accepted decisions, and
  prior advisory responses can appear as additive metadata, but trust fields
  must stay in the shared `entries` contract.
- Live external memory in session context is advisory, not trusted baseline.
- Policy-blocked memory may be listed by id/path/reason, but never by body.

### 2. Real Reviewer Dogfood Artifacts

Real dogfood must use the public command path:

```bash
ait review benchmark run --fixture tests/fixtures/review_benchmark/cases.json \
  --reviewer-adapter claude-code --dogfood --permission-profile read-only \
  --output docs/review-benchmark-real-dogfood-claude-code.json --format json
```

and the same shape for Codex. If the local CLI is missing, not authenticated,
blocked by sandbox, or times out, the artifact must say so. A failed real
adapter run is still valid dogfood evidence if it truthfully records the local
failure. A mock adapter artifact is never acceptable as a real dogfood artifact.

Required artifact fields:

- adapter name and resolved binary path if available;
- command argv with secrets redacted;
- local auth assumption;
- permission profile and model label;
- repo revision and fixture hash;
- latency and token/cost placeholder;
- clear limitation that this is local dogfood evidence, not benchmark-proven
  review quality.

### 3. Team Policy Runtime Enforcement

`.ait/policy.json` cannot remain validate-only. Runtime paths must consume the
same fail-closed validation result.

Initial enforced paths:

- `ait apply`: invalid policy blocks; `apply.require_review_clearance` blocks
  apply when the target attempt has no clear latest review.
- `ait review attempt`: invalid policy blocks review commands and surfaces the
  validation payload in JSON.
- `ait console action ... --dry-run`: invalid policy blocks; `console.actions_enabled:
  false` blocks action preflight.
- Context trust filtering: invalid policy blocks context generation; memory
  whose `source_file_path` matches `memory.block_paths` is treated as
  `policy_blocked` and cannot enter trusted baseline.

## Implementation Plan

1. Add team policy enforcement payload/schema helpers.
2. Add context trust filtering that applies team policy before context text and
   manifest generation.
3. Wire review baseline/brief generation to write `ait.context_manifest`.
4. Replace session custom context manifest with additive `ait.context_manifest`
   payloads.
5. Wire apply/review/console action CLI paths to fail closed on invalid policy.
6. Run real dogfood commands for Claude Code and Codex, or write truthful
   unavailable artifacts when the real CLI cannot complete.
7. Update public docs and release notes without stronger quality claims.

## Test Plan

- Review context regression:
  - accepted facts appear in trusted baseline;
  - candidate/stale/superseded/policy-blocked facts do not;
  - blocked body text is absent from brief, manifest, and review artifact;
  - artifact links `context_manifest_ref`.
- Session context regression:
  - manifest schema is `ait.context_manifest`;
  - allowed live source text is advisory, not trusted baseline;
  - blocked live source appears only as excluded metadata;
  - blocked body text is absent.
- Team policy enforcement:
  - invalid policy blocks `ait apply --format json`;
  - invalid policy blocks `ait review attempt ... --format json`;
  - invalid policy blocks `ait console action ... --dry-run --format json`;
  - `console.actions_enabled: false` blocks console action preflight;
  - `memory.block_paths` excludes selected facts from context trust.
- Dogfood:
  - artifacts exist for Claude Code and Codex;
  - each artifact is either a real run payload or an explicit unavailable
    payload;
  - no artifact labels a mock adapter as real.

## Acceptance

This work is acceptable only when:

1. Review, session, and wrapped run contexts all produce `ait.context_manifest`
   payloads with schema version and tests.
2. No policy-blocked body string appears in prompts, manifests, or review
   artifacts in regression fixtures.
3. At least the apply, review, console action, and context trust paths consume
   team policy at runtime and fail closed on invalid policy.
4. Real dogfood artifacts exist and truthfully record success, failure, or
   unavailable reasons for both Claude Code and Codex.
5. Documentation says these artifacts are local dogfood evidence, not
   benchmark-proven quality.

## Code Review Standard

Reviewers must block changes that:

- add a new context path without `ait.context_manifest`;
- keep a custom trust manifest that lacks `schema`, `schema_version`, `entries`,
  `trust_level`, and `reason`;
- put candidate, stale, superseded, or policy-blocked memory into trusted
  baseline;
- include policy-blocked body text in context, manifest, review artifact, or
  dogfood artifact;
- make invalid `.ait/policy.json` silently fall back;
- claim real dogfood from a fake or mock adapter;
- imply benchmark-proven review quality without repeated real reviewer evidence;
- add telemetry, SaaS sync, automatic push, or automatic merge.
