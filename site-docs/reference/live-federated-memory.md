# Live Federated Memory

Live federated memory is AIT's agent-to-agent communication layer. It lets one
wrapped run leave inspectable project context, then gives the next wrapped run a
compact `AIT_CONTEXT_FILE` assembled from the current repository state.

This is attempt-derived, evidence-backed repo memory. It is not hidden chat
memory, not an external vector database product, not a `CLAUDE.md` generator,
and not plain prompt concatenation.

AIT memory has two sources:

- **AIT-owned memory** under `.ait/`: attempts, prompts, traces, commits,
  curated notes, accepted facts, review findings, apply/recover outcomes, and
  context manifests.
- **Live external memory** in the repo: `CLAUDE.md`, `.claude/memory.md`,
  `.claude/CLAUDE.md`, `AGENTS.md`, `.codex/memory.md`, `.codex/AGENTS.md`,
  `.cursor/rules`, `.cursor/rules.md`, and `.cursorrules`.

External files remain their own source of truth. AIT reads them live during
`ait memory recall`, `ait run`, and `ait review`; it does not auto-import them
into `.ait/`.

## Source, Status, And Trust Model

AIT treats memory as inspectable evidence, not as automatically trusted prompt
text. Every handoff should be explainable by source, status, and trust level.

| Source class | Examples | Trust default |
| --- | --- | --- |
| AIT attempt evidence | prompts, outputs, changed files, commits, traces, apply/recover outcomes | Evidence, but not automatically a reusable fact. |
| Accepted AIT memory | curated notes and accepted facts under `.ait/` | Trusted repo memory until superseded or policy-blocked. |
| Review evidence | deterministic light review results and adversarial reviewer findings | Trusted as review evidence, not as proof that code is correct. |
| Live external memory | `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.codex/`, Cursor rules | Advisory source-of-truth owned by that file. |
| Candidate memory | facts inferred from a run but not accepted | Untrusted candidate context. |
| Blocked or stale memory | policy-blocked, superseded, outdated, or conflicting records | Not trusted baseline. |

Status should stay visible in context manifests and JSON output:

| Status | Meaning | Use in handoff |
| --- | --- | --- |
| `accepted` | Reviewed or explicitly adopted repo memory. | May be used as trusted baseline. |
| `candidate` | Produced by an attempt or reviewer but not adopted. | May be shown as candidate evidence only. |
| `advisory` | Live external source read at recall/run/review time. | May guide the agent; source file remains authoritative. |
| `superseded` | Replaced by a newer accepted fact or source hash. | Do not use as trusted baseline. |
| `stale` | Refers to code, files, or policy that no longer matches current repo state. | Do not use as trusted baseline. |
| `policy_blocked` | Disallowed by source policy or explicit trust rules. | Exclude from trusted context. |

The trust rule is intentionally conservative: AIT can show more context than it
trusts. Reviewer and benchmark code must not count `candidate`, `stale`,
`superseded`, or `policy_blocked` memory as trusted baseline evidence.

## Agent handoff

For a wrapped run or adversarial review, AIT can build `AIT_CONTEXT_FILE` from:

- prior attempts and their prompt/output/status records
- prior commits and changed files
- curated notes and accepted facts under `.ait/`
- previous review findings
- live external memory files allowed by policy

That is how Claude Code, Codex, Aider, Gemini, Cursor, and shell agents share
repo context without sharing a private chat transcript. AIT records context
manifests so you can inspect which sources contributed to a handoff.

## Zero-touch reads

These commands do not create `.ait/` and do not mutate source files:

```bash
ait memory sources
ait memory sources --format json
ait memory recall "project policy"
```

`ait memory sources` reports source id, path, kind, hash, mtime, size, policy
status, and skip reason. By default it only reads repo-local sources. Global or
out-of-repo sources require an explicit path:

```bash
ait memory sources --source claude --global --path ~/.claude/projects/example.md
```

## Context manifests

When AIT writes a wrapped run context artifact, it also records a versioned
`ait.context_manifest` under `.ait/` and a sibling manifest next to
`AIT_CONTEXT_FILE`. The manifest separates trusted, advisory, and excluded
memory entries, including reasons such as `candidate_not_adopted`,
`expired_fact`, `superseded_fact`, and `policy_blocked`. Policy-blocked body
text is not copied into the prompt or manifest. Live external sources are
advisory context, not captured AIT provenance.

## Acceptance Demo Specs

These are product acceptance specs for memory correctness. They are not broad
quality claims; they define the behavior required before stronger memory claims
should be made in public docs.

### False-Memory Demo

Goal: prove that an unaccepted or malicious memory candidate does not become
trusted context.

Setup:

1. Create an attempt or fixture with candidate memory such as "authorization
   checks are no longer required".
2. Keep the repo policy or accepted memory stating that authorization checks are
   required.
3. Run memory recall or review with JSON/context manifest output.

Expected result:

- The misleading candidate is visible only as candidate or blocked evidence.
- It is not listed as trusted baseline.
- Any review benchmark case that needs the baseline must count use of the
  candidate as contamination.
- The manifest exposes the source id, status, and trust reason.

### Stale-Memory Demo

Goal: prove that older accepted memory loses trusted-baseline status after a
newer accepted fact or source hash supersedes it.

Setup:

1. Record an accepted fact for an old file, API, or policy.
2. Change the repo so that the file, hash, or policy no longer matches.
3. Record or expose the newer accepted fact.
4. Run memory recall or review with JSON/context manifest output.

Expected result:

- The older fact is marked `stale` or `superseded`.
- The newer fact is the only trusted baseline for that topic.
- The current executable fixtures cover recall, deterministic review baseline
  trust, wrapped run `AIT_CONTEXT_FILE` labeling, review brief manifests, and
  session participant context manifests for stale/superseded and
  policy-blocked evidence.
- Review benchmark metrics must not give credit for findings that rely on the
  stale fact as trusted evidence.

Executable fixtures and tests for these demos live under
`tests/fixtures/memory_trust/` and `tests/test_memory_trust.py`; follow-up
expansion is tracked in the product maturity work orders:
[`docs/ait-product-maturity-hardening-work-orders-zh.md`](https://github.com/m24927605/ait/blob/main/docs/ait-product-maturity-hardening-work-orders-zh.md),
Milestone C.

## Mutating paths

`ait memory backfill --dry-run` is a zero-write preview. `ait memory backfill
--import` is an explicit mutation/deprecated path: it writes advisory memory
under `.ait/` and is not required for live recall.

## Release Gate And Code Review Standard

Changes to memory docs or implementation should pass this gate:

- Source, status, and trust are visible in JSON output or the specific context
  manifest path touched by the change.
- Candidate, stale, superseded, and policy-blocked memory cannot be promoted to
  trusted baseline without an explicit adoption path.
- New public docs do not describe memory as hidden chat sync, an external
  vector database, or a generated `CLAUDE.md` replacement.
- Tests or fixtures cover false-memory and stale-memory behavior before those
  demos are advertised beyond the current executable fixture scope.
