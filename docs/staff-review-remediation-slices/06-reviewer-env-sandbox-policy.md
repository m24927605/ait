# Slice 06: Reviewer Env Sandbox Policy

狀態：Ready for implementation
目標：讓 local reviewer adapter 的 environment policy 變成 allowlist-first，避免 secrets 意外傳給 reviewer child process。

## Problem

`claude-code` reviewer 目前只移除 `ANTHROPIC_API_KEY`。`codex` local reviewer 或自訂
command 在沒有 allowlist/blocklist 時會繼承完整 process environment。這可能把 cloud
credentials、proxy token、private env 傳給 reviewer command。

## Objective

建立 reviewer env safety policy：

- Local reviewer 預設只傳必要 env allowlist。
- Agent auth 必須透過明確 allowlist 或 agent 自身 config files。
- `ANTHROPIC_API_KEY` 等 provider API key 預設不傳給 local CLI reviewer。
- 自訂 command 可以透過 repo policy 明確 opt in env vars。
- Review fail closed，不因 env 被限制而 silent fallback。

## Files To Change

- `src/ait/review_adapter.py`
- `src/ait/review_policy.py`
- `tests/test_review_adapter*.py`
- `docs/no-credits-api-key-policy.md`
- `site-docs/reference/adversarial-code-review.md` if behavior/docs need alignment

## Files Not To Change

- Transcript storage
- Apply/recover safety gates
- Release workflow
- SQLite schema unless policy schema must be versioned additively

## Design

Default reviewer env allowlist:

- `PATH`
- `HOME` only if required by local CLI auth, otherwise prefer explicit agent config path
- `TMPDIR`, `TEMP`, `TMP`
- locale variables such as `LANG`, `LC_ALL`
- any AIT-required safe variables

Default blocklist:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `GITHUB_TOKEN`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- generic `*TOKEN*`, `*SECRET*`, `*PASSWORD*`, `*KEY*` unless explicitly allowlisted

Policy opt-in example:

```json
{
  "review_adapters": {
    "codex": {
      "env_allowlist": ["PATH", "HOME", "TMPDIR"]
    }
  }
}
```

## Tests

Required tests:

1. `test_local_reviewer_does_not_inherit_secret_env_by_default`
   - Fake reviewer prints env.
   - Assert `SECRET_TOKEN` absent.

2. `test_claude_reviewer_blocks_anthropic_key`
   - Existing guarantee remains.

3. `test_codex_reviewer_uses_minimal_env`
   - Assert safe allowlist only.

4. `test_policy_allowlist_can_pass_specific_safe_var`
   - Explicit repo policy passes selected env.

5. `test_missing_auth_fails_closed_with_actionable_error`
   - No silent provider fallback.

## Verification Commands

```bash
uv run pytest tests/test_review_adapter.py tests/test_review_adapter_config.py tests/test_review_gate.py -q
uv run pytest tests/test_review_benchmark.py -q
```

## Acceptance

- Fake reviewer cannot observe arbitrary env secrets by default.
- Claude Code path still strips `ANTHROPIC_API_KEY`.
- Codex path does not inherit all env by default.
- Docs explain how local CLI auth works without API key leakage.
- Review failure message tells the user how to configure local auth or env allowlist.

## Review Checklist

- Confirm `env=None` is not used for reviewer subprocesses unless explicitly intended.
- Confirm blocklist does not create false sense of safety when allowlist is empty.
- Confirm tests use fake secrets only.
- Confirm docs do not claim stronger isolation than implemented.

## Rollback

If allowlist breaks too many local reviewer setups, keep the safe default and add documented
per-adapter opt-in. Do not revert to full env inheritance silently.

