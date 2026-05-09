# AIT Review Orchestration Phase 1 Implementation Spec

Status: Proposed implementation spec

Phase 1 建立 deterministic review skeleton。這一階段沒有 DB persistence、沒有 baseline snapshot、沒有 apply gate、沒有 LLM reviewer。

## Objective

提供第一個可用的 review CLI：

```bash
ait review attempt latest-reviewable --format json
```

此命令只做三件事：

- 選出明確的 review target attempt。
- 收集 changed files 與基本 attempt metadata。
- 執行 deterministic risk scan 並輸出 JSON/text。

## Non-Goals

Phase 1 不做：

- 不新增 DB migration。
- 不寫入 review records。
- 不修改 `ait apply`。
- 不修改 `ait run` 預設行為。
- 不呼叫 LLM。
- 不呼叫 network。
- 不建立 async queue。
- 不建立 baseline artifact。
- 不新增 human override。

## Files To Change

預期變更：

- `src/ait/cli_parser.py`
  - 新增 `review` top-level command。
  - 新增 `review attempt <selector>`。
  - 新增 `--format {text,json}`。

- `src/ait/cli/main.py` 或現有 command dispatch 位置
  - wire `review` command handler。

- `src/ait/cli/review.py`
  - 新增 CLI handler。
  - 負責 formatting 與 exit codes。

- `src/ait/review.py`
  - 新增 selector resolution。
  - 新增 review target loading。
  - 新增 changed files summary。

- `src/ait/review_policy.py`
  - 新增 deterministic risk scoring v0。

- `tests/test_cli_review.py`
  - CLI command tests。

- `tests/test_review.py`
  - selector 與 target loading tests。

- `tests/test_review_policy.py`
  - risk scoring tests。

## Files Not To Change

Phase 1 不應修改：

- `src/ait/db/schema.py`
- `src/ait/landing.py`
- `src/ait/runner.py`
- `src/ait/verifier.py`
- `src/ait/memory/**`
- adapter resources

如果需要改這些檔案，代表 Phase 1 scope 已經失控，應先更新 spec。

## CLI Contract

命令：

```bash
ait review attempt <selector> [--format text|json]
```

支援 selector：

- full attempt id
- unambiguous short attempt id if existing id resolver supports it
- `latest-reviewable`

暫不支援：

- `ait review latest`
- `ait review attempt latest-succeeded`
- `ait review attempt latest-unapplied`
- `ait review override`

Exit codes:

- `0`: target resolved and risk scan completed。
- `1`: no reviewable attempt found。
- `2`: invalid selector、unknown attempt、internal evaluation error。

Text output 第一行必須明確顯示 target：

```text
Review target: <attempt-id>
Risk: medium (35)
Suggested mode: light
```

找不到 target 時：

```text
No reviewable attempt found.
Try: ait attempt list --verified-status succeeded
```

## JSON Contract

Phase 1 JSON output:

```json
{
  "schema_version": 1,
  "target_attempt_id": "repo:ulid",
  "selector": "latest-reviewable",
  "verified_status": "succeeded",
  "reported_status": "finished",
  "workspace_ref": "/path/to/worktree",
  "base_ref_oid": "abc123",
  "base_ref_name": "main",
  "changed_files": ["src/example.py"],
  "risk_level": "medium",
  "risk_score": 35,
  "risk_reasons": [
    {
      "code": "missing_test_evidence",
      "message": "attempt changed files but no test evidence was observed",
      "paths": []
    }
  ],
  "review_required": false,
  "suggested_mode": "light"
}
```

Required fields:

- `schema_version`
- `target_attempt_id`
- `selector`
- `verified_status`
- `reported_status`
- `changed_files`
- `risk_level`
- `risk_score`
- `risk_reasons`
- `review_required`
- `suggested_mode`

Optional but preferred:

- `workspace_ref`
- `base_ref_oid`
- `base_ref_name`

## Selector Rules

`latest-reviewable` selects the newest attempt, by existing attempt ordering, that satisfies:

- `verified_status == "succeeded"`
- `reported_status == "finished"`
- has at least one committed changed file from `attempt_commits`
- not promoted
- not discarded
- workspace/ref exists if required for changed file extraction

Tie-breaker:

- Use the same order as `list_attempts(conn)` unless a better existing ordering is already established.
- Pick the last matching attempt.

Skip:

- failed attempts
- running attempts
- discarded attempts
- promoted attempts
- attempts with no committed file changes
- attempts whose workspace is missing if workspace is needed to evaluate Phase 1 output

## Risk Scoring V0

Risk score starts at `0`. Cap at `100`.

Suggested v0 weights:

- `large_diff`: +20 if changed file count >= 10.
- `very_large_diff`: +35 if changed file count >= 30.
- `sensitive_path`: +30 for auth/security/payment/deploy/CI/workflow/migration paths.
- `dependency_change`: +25 for lockfiles, package manifests, dependency metadata.
- `test_deletion_or_skip`: +25 if changed paths indicate test files removed or transcript includes skip markers when trace is available.
- `missing_test_evidence`: +20 if changed files exist and evidence summary observed no tests.
- `binary_or_generated`: +15 for likely generated or binary paths.
- `public_api_without_tests`: +20 if public API-like paths changed and tests did not.

Risk levels:

- `low`: 0-19
- `medium`: 20-49
- `high`: 50-79
- `critical`: 80-100

Suggested mode:

- `none` for low
- `light` for medium
- `adversarial` for high/critical

Review required:

- `false` in Phase 1 for all levels because no apply gate exists yet.
- Still include the field so the contract is forward-compatible.

## Fixture Design

Prefer existing test helpers if available. If new helpers are needed, keep them local to review tests first.

Fixtures should create temporary Git repos with:

- initialized AIT repo
- at least one intent
- multiple attempts
- one succeeded attempt with committed changes
- one failed attempt
- one promoted attempt if existing helpers can promote safely
- one noop succeeded attempt

Avoid daemon/network/LLM in Phase 1 tests.

## Required Tests

Selector tests:

- selects newest succeeded changed unapplied attempt
- skips failed attempt
- skips discarded attempt
- skips promoted attempt
- skips noop attempt
- returns no-reviewable error if none match

Risk tests:

- sensitive path produces `sensitive_path`
- workflow path produces sensitive path risk
- lockfile produces `dependency_change`
- missing tests produces `missing_test_evidence`
- multiple reasons accumulate and score caps at 100
- low/medium/high/critical boundaries are stable

CLI tests:

- JSON output parses and includes required fields
- text output names target attempt
- invalid selector exits 2
- no reviewable attempt exits 1 and suggests `ait attempt list --verified-status succeeded`

Regression tests:

- `ait run` parser behavior unchanged when `review` is unused
- `ait apply` tests still pass
- verifier tests still pass

## Verification Commands

Targeted:

```bash
PYTHONPATH=src uv run pytest tests/test_cli_review.py tests/test_review.py tests/test_review_policy.py -q
```

Regression:

```bash
PYTHONPATH=src uv run pytest tests/test_cli_run.py tests/test_landing.py tests/test_verifier.py -q
```

If `tests/test_verifier.py` does not exist, run the nearest verifier/landing/app-flow tests already present in the repo.

## Implementation Review Checklist

- No DB migration added.
- No LLM or network invocation.
- No change to `verified_status`.
- No apply gate added.
- `latest-reviewable` semantics are explicit and tested.
- JSON output is deterministic.
- Risk reason codes are stable strings.
- Errors are actionable.
