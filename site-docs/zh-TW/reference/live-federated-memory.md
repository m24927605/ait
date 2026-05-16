# Live Federated Memory

Live federated memory 是 AIT 的 agent-to-agent communication layer。它讓一個
wrapped run 留下可檢查的 project context，下一個 wrapped run 再收到由目前
repo 狀態組出的 `AIT_CONTEXT_FILE`。

這是 attempt-derived、evidence-backed repo memory。它不是隱藏聊天記憶，
不是外部 vector database 產品，不是 `CLAUDE.md` generator，也不是單純把
prompt/context 串起來。

AIT memory 有兩種來源：

- **AIT-owned memory**：存在 `.ait/`，包含 attempts、prompts、traces、
  commits、curated notes、accepted facts、review findings、apply/recover
  outcomes 與 context manifests。
- **Live external memory**：repo 內既有的 `CLAUDE.md`、`.claude/memory.md`、
  `.claude/CLAUDE.md`、`AGENTS.md`、`.codex/memory.md`、
  `.codex/AGENTS.md`、`.cursor/rules`、`.cursor/rules.md`、`.cursorrules`。

External files 仍是自己的 source of truth。AIT 會在 `ait memory recall`、
`ait run`、`ait review` 當下即時讀取它們，不會自動匯入 `.ait/`。

## Source / Status / Trust Model

AIT 把 memory 當成可檢查 evidence，不會把所有文字都自動當成可信 prompt
context。每次 handoff 都應能解釋 source、status 與 trust level。

| Source class | 例子 | 預設 trust |
| --- | --- | --- |
| AIT attempt evidence | prompts、outputs、changed files、commits、traces、apply/recover outcomes | 是 evidence，但不自動變成可重用 fact。 |
| Accepted AIT memory | `.ait/` 裡 curated notes 與 accepted facts | 在被 supersede 或 policy-block 前，可作 trusted repo memory。 |
| Review evidence | deterministic light review 結果與 adversarial reviewer findings | 可作 review evidence，但不是程式碼正確性的證明。 |
| Live external memory | `CLAUDE.md`、`AGENTS.md`、`.claude/`、`.codex/`、Cursor rules | Advisory source-of-truth，由該檔案自身維護。 |
| Candidate memory | run 推論出的、尚未接受的 facts | Untrusted candidate context。 |
| Blocked or stale memory | policy-blocked、superseded、outdated、conflicting records | 不得作 trusted baseline。 |

Status 應在 context manifests 與 JSON output 裡可見：

| Status | 意義 | Handoff 用法 |
| --- | --- | --- |
| `accepted` | 已審核或明確 adopt 的 repo memory。 | 可以作 trusted baseline。 |
| `candidate` | attempt 或 reviewer 產生，但尚未 adopt。 | 只能作 candidate evidence 顯示。 |
| `advisory` | recall/run/review 當下讀取的 live external source。 | 可以引導 agent；source file 仍是權威來源。 |
| `superseded` | 已被較新的 accepted fact 或 source hash 取代。 | 不得作 trusted baseline。 |
| `stale` | 指向已不符合目前 repo state 的 code、files 或 policy。 | 不得作 trusted baseline。 |
| `policy_blocked` | 被 source policy 或明確 trust rules 擋下。 | 排除於 trusted context。 |

Trust rule 採保守設計：AIT 可以顯示比它信任更多的 context。Reviewer 與
benchmark code 不得把 `candidate`、`stale`、`superseded` 或
`policy_blocked` memory 算成 trusted baseline evidence。

## Agent handoff

Wrapped run 或 adversarial review 可以由 AIT 建立 `AIT_CONTEXT_FILE`，來源包含：

- prior attempts 與它們的 prompt/output/status records
- prior commits 與 changed files
- `.ait/` 裡 curated notes 與 accepted facts
- previous review findings
- policy 允許的 live external memory files

這就是 Claude Code、Codex、Aider、Gemini、Cursor 與 shell agents 能共享
repo context，卻不需要共享私人 chat transcript 的方式。AIT 會記錄 context
manifests，讓你檢查 handoff 實際使用了哪些 sources。

## Zero-touch reads

以下指令不會建立 `.ait/`，也不會修改來源檔：

```bash
ait memory sources
ait memory sources --format json
ait memory recall "project policy"
```

`ait memory sources` 會列出 source id、path、kind、hash、mtime、size、policy
status 與 skip reason。預設只讀 repo-local sources。Global 或 repo 外部來源
必須明確指定 path：

```bash
ait memory sources --source claude --global --path ~/.claude/projects/example.md
```

## Context manifests

AIT 在寫入 wrapped run context artifact 時，也會在 `.ait/` 記錄 versioned
`ait.context_manifest`，並在 `AIT_CONTEXT_FILE` 旁建立 sibling manifest。
Manifest 會分開 trusted、advisory、excluded memory entries，並記錄
`candidate_not_adopted`、`expired_fact`、`superseded_fact`、`policy_blocked`
等原因。Policy-blocked body text 不會被寫進 prompt 或 manifest。Live
external sources 是 advisory context，不是 AIT captured provenance。

## 驗收 Demo 規格

這些是 memory correctness 的產品驗收規格，不是廣泛品質宣稱。只有在行為與
測試都完成後，公開文件才應宣稱 demo 已完成。

### False-Memory Demo

目標：證明尚未 accepted 或惡意的 memory candidate 不會變成 trusted context。

Setup：

1. 建立一個 attempt 或 fixture，放入 candidate memory，例如「authorization
   checks are no longer required」。
2. 保留 repo policy 或 accepted memory，指出 authorization checks 仍然必要。
3. 執行 memory recall 或 review，輸出 JSON/context manifest。

Expected result：

- 誤導 candidate 只會以 candidate 或 blocked evidence 出現。
- 它不會列入 trusted baseline。
- 需要 baseline 的 review benchmark case，若使用 candidate，必須計為 contamination。
- Manifest 必須露出 source id、status 與 trust reason。

### Stale-Memory Demo

目標：證明較舊的 accepted memory 在較新的 accepted fact 或 source hash 出現後，
會失去 trusted-baseline status。

Setup：

1. 對舊 file、API 或 policy 記錄 accepted fact。
2. 修改 repo，讓 file、hash 或 policy 不再符合。
3. 記錄或暴露新的 accepted fact。
4. 執行 memory recall 或 review，輸出 JSON/context manifest。

Expected result：

- 舊 fact 標記為 `stale` 或 `superseded`。
- 同 topic 只有新 fact 可作 trusted baseline。
- 目前可執行 fixtures 覆蓋 recall、deterministic review baseline trust、
  wrapped run `AIT_CONTEXT_FILE`、review brief manifest，以及 session
  participant context manifest 對 stale/superseded 與 policy-blocked evidence
  的標示。
- Review benchmark metrics 不得把依賴 stale fact 的 findings 算成 trusted evidence。

這些 demo 的可執行 fixtures 與 tests 已放在 `tests/fixtures/memory_trust/`
與 `tests/test_memory_trust.py`；後續擴充由產品成熟度 work orders 追蹤：
[`docs/ait-product-maturity-hardening-work-orders-zh.md`](https://github.com/m24927605/ait/blob/main/docs/ait-product-maturity-hardening-work-orders-zh.md)，
Milestone C。

## Mutating paths

`ait memory backfill --dry-run` 是 zero-write preview。`ait memory backfill
--import` 是明確 mutation/deprecated path：它會把 advisory memory 寫進
`.ait/`，但 live recall 不需要 import。

## Release Gate 與 Code Review Standard

Memory docs 或 implementation 的修改應通過這個 gate：

- Source、status、trust 必須能在 JSON output 或這次修改實際觸及的
  context manifest path 中被檢查。
- Candidate、stale、superseded、policy-blocked memory 不得在沒有明確 adoption
  path 的情況下升級成 trusted baseline。
- 公開文件不得把 memory 描述成隱藏聊天同步、外部 vector database 或生成
  `CLAUDE.md` 的替代品。
- 若要把 false-memory / stale-memory demo 宣稱超過目前 executable fixture
  scope，必須先有更完整 tests 或 fixtures 覆蓋對應行為。
