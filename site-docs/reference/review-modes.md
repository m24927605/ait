---
title: ait review modes
description: >-
  Exact boundaries for ait review modes: light deterministic risk scan,
  adversarial reviewer adapters, risk-based run orchestration, and the local
  Claude Code reviewer path.
---

# Review modes

AIT separates verification, risk scanning, and reviewer-agent execution.

The practical split is simple:

- `light` answers "how risky does this attempt look from deterministic signals?"
- `adversarial` answers "what would a separate reviewer agent block before this lands?"
- `risk-based` lets AIT choose between those paths during `ait run`

## `light`

`light` mode is a deterministic risk scan. It does not call Claude Code,
Codex, or any other LLM.

```bash
ait review attempt latest-reviewable --mode light
```

It checks:

- changed-file count: `large_diff` at 10+ files, `very_large_diff` at 30+ files
- sensitive paths: `.github/workflows/**` or path parts named `auth`,
  `authentication`, `authorization`, `security`, `payment`, `payments`,
  `billing`, `deploy`, `deployment`, `ci`, `migrations`, or `migration`
- dependency or lockfile metadata: `pyproject.toml`, `uv.lock`,
  `poetry.lock`, `requirements.txt`, `requirements-dev.txt`, `package.json`,
  `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `cargo.lock`, `go.mod`,
  `go.sum`, or `gemfile.lock`
- generated or binary files: paths containing `/generated/`, files ending in
  `.generated.py`, or suffixes `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`,
  `.pdf`, `.zip`, `.gz`, `.bin`, or `.wasm`
- missing test evidence when changed files exist but no tests were observed

The result is persisted as a review record:

- `low` risk becomes `passed`
- `medium`, `high`, and `critical` risk become `warning`
- it does not create line-by-line findings
- it does not block by itself

## `adversarial`

`adversarial` mode invokes a reviewer adapter and expects structured JSON
findings.

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
```

The reviewer receives a structured brief with trusted baseline context,
advisory evidence, risk reasons, and the required JSON output schema. AIT runs
the reviewer outside the target attempt worktree and captures stdout/stderr.

High or critical findings can become blocking findings when the reviewer
returns them in the expected schema.

This is the mode to use when review quality matters. The reviewer is given a
clear adversarial job: challenge the implementation, look for missing edge
cases, weak tests, regressions, security-sensitive paths, and reasons the
attempt should not be accepted as-is.

When repo policy requires review before apply, a blocked adversarial review can
hold the result:

```bash
ait apply <attempt-id> --mode current
```

```text
Status: held
Reason: review gate: required review is blocked
```

For the end-to-end workflow, see
[Adversarial code review](adversarial-code-review.md).

## Claude Code reviewer

The built-in `claude-code` review adapter resolves to local Claude Code:

```bash
claude -p
```

AIT passes the reviewer brief on stdin and removes `ANTHROPIC_API_KEY` from
the child process environment. This prevents a silent fallback to provider API
credits and keeps the path aligned with local Claude Code authentication.

Check the local adapter state:

```bash
ait adapter doctor claude-code --json
```

Expected local CLI auth reports:

```json
{
  "auth_mode": "local_cli",
  "will_use_api_key": false,
  "will_fallback_to_credits": false
}
```

If the local `claude` CLI is unavailable or not logged in, the review fails
closed instead of switching to an API-key path.

## `risk-based`

`risk-based` is a run policy, not a direct `ait review attempt --mode` value.
Use it when you want AIT to choose review behavior from the risk assessment:

```bash
ait run --review risk-based --review-adapter claude-code --adapter claude-code -- claude
```

The current risk policy suggests:

- `low`: no review
- `medium`: `light`
- `high` or `critical`: `adversarial`

Risk scoring is based on the same signals used by `light` mode.

## Memory boundary

Review baselines use the same local memory discipline as runs. Trusted
baseline context comes from approved or accepted local facts. Candidate,
stale, superseded, or policy-blocked memory remains advisory or excluded
instead of being treated as trusted context.
