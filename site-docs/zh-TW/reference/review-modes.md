---
title: ait review modes
description: >-
  ait review modes 的精確邊界：light deterministic risk scan、
  adversarial reviewer adapter、risk-based run orchestration，以及本機
  Claude Code reviewer path。
---

# Review modes

AIT 會把驗證、風險掃描、reviewer agent 執行分開處理。

實務上可以這樣理解：

- `light` 回答「從 deterministic signals 看，這次 attempt 風險多高？」
- `adversarial` 回答「如果交給另一個 reviewer agent，它會擋下什麼？」
- `risk-based` 讓 AIT 在 `ait run` 期間依風險自動選擇路徑

## `light`

`light` mode 是 deterministic risk scan。它不會呼叫 Claude Code、Codex，
也不會呼叫任何 LLM。

```bash
ait review attempt latest-reviewable --mode light
```

它會檢查：

- 變更檔案數：10+ 檔案標記 `large_diff`，30+ 檔案標記 `very_large_diff`
- 敏感路徑：`.github/workflows/**`，或路徑片段包含 `auth`、
  `authentication`、`authorization`、`security`、`payment`、`payments`、
  `billing`、`deploy`、`deployment`、`ci`、`migrations`、`migration`
- dependency 或 lockfile metadata：`pyproject.toml`、`uv.lock`、
  `poetry.lock`、`requirements.txt`、`requirements-dev.txt`、
  `package.json`、`package-lock.json`、`pnpm-lock.yaml`、`yarn.lock`、
  `cargo.lock`、`go.mod`、`go.sum`、`gemfile.lock`
- binary 或 generated files：路徑含 `/generated/`、檔名以
  `.generated.py` 結尾，或副檔名是 `.png`、`.jpg`、`.jpeg`、`.gif`、
  `.webp`、`.pdf`、`.zip`、`.gz`、`.bin`、`.wasm`
- 有變更檔案但沒有觀測到 test evidence 時，標記 `missing_test_evidence`

結果會存成 review record：

- `low` risk 會成為 `passed`
- `medium`、`high`、`critical` risk 會成為 `warning`
- 不會產生逐行 findings
- 不會單獨阻擋 apply

## `adversarial`

`adversarial` mode 會呼叫 reviewer adapter，並期待 reviewer 回傳 structured
JSON findings。

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
```

Reviewer 會收到 structured brief，內容包含 trusted baseline context、
advisory evidence、risk reasons，以及必須遵守的 JSON output schema。AIT 會在
target attempt worktree 外執行 reviewer，並捕捉 stdout/stderr。

當 reviewer 依 schema 回傳 high 或 critical finding 時，這些 finding 可以成為
blocking findings。

當 review 品質很重要時，就應該用這個 mode。Reviewer 會被賦予明確的對抗式
任務：挑戰實作、找遺漏邊界條件、薄弱測試、regression、安全敏感路徑，以及
這個 attempt 不應該被直接接受的理由。

當 repo policy 要求 apply 前必須通過 review，blocked adversarial review
可以 hold 住結果：

```bash
ait apply <attempt-id> --mode current
```

```text
Status: held
Reason: review gate: required review is blocked
```

完整操作流程請看 [對抗式 code review](adversarial-code-review.md)。

## Claude Code reviewer

內建 `claude-code` review adapter 會解析成本機 Claude Code：

```bash
claude -p
```

AIT 會透過 stdin 傳入 reviewer brief，並從子行程環境移除
`ANTHROPIC_API_KEY`。這避免 silent fallback 到 provider API credits，也讓這條
path 維持使用本機 Claude Code auth。

檢查本機 adapter 狀態：

```bash
ait adapter doctor claude-code --json
```

本機 CLI auth 的預期報告包含：

```json
{
  "auth_mode": "local_cli",
  "will_use_api_key": false,
  "will_fallback_to_credits": false
}
```

如果本機 `claude` CLI 不存在或尚未登入，review 會 fail closed，而不是切到
API-key path。

## `risk-based`

`risk-based` 是 run policy，不是 `ait review attempt --mode` 可直接使用的
值。當你希望 AIT 依風險評估選擇 review 行為時使用：

```bash
ait run --review risk-based --review-adapter claude-code --adapter claude-code -- claude
```

目前的 risk policy 會建議：

- `low`：不 review
- `medium`：`light`
- `high` 或 `critical`：`adversarial`

Risk scoring 使用和 `light` mode 相同的訊號。

## Memory boundary

Review baseline 使用和 run 相同的本機 memory discipline。Trusted baseline
context 只來自 approved 或 accepted local facts。Candidate、stale、
superseded 或 policy-blocked memory 只會是 advisory，或被排除；不會被當成
trusted context。
