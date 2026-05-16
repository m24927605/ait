# AIT 產品成熟度 Hardening Work Orders

## 目的

這份文件把目前尚未完成的產品弱點，從 roadmap 提升成可派工、可審查、可驗收的
work orders。它銜接
[`docs/ait-product-weakness-response-plan-zh.md`](ait-product-weakness-response-plan-zh.md)，
目標不是改變產品定位，而是把下一批工程工作拆到足以直接實作。

## 範圍

本文件只處理四個尚未解決的弱點：

1. repo-local daily console 已有 read-only MVP，但 mutation/action recovery 尚未實作。
2. review benchmark 已擴到 10 cases，但尚未有 real Claude/Codex reviewer
   dogfood report。
3. false-memory / stale-memory 已有可執行 fixtures/tests；後續需擴充到更多
   context manifest 與 reviewer benchmark 場景。
4. alpha adoption 的 metadata sync、team policy profile、UI mutation recovery
   還停在 high-level roadmap。

## 非目標

- 不建立 SaaS、帳號系統、cloud dashboard、remote telemetry。
- 不做自動 merge 或自動 push。
- 不把 AIT 包裝成已完成的 GUI-first desktop product。
- 不在 real reviewer dogfood 與足夠量測資料完成前宣稱 benchmark-proven review quality。
- 不把 repo-local metadata 自動同步到遠端。

## 成熟度分級

| Level | 定義 | 是否可公開宣稱已完成 |
| --- | --- | --- |
| L0 Idea | 只有問題描述。 | 不可。 |
| L1 Design | 有設計與邊界。 | 只能說 planned / designed。 |
| L2 Work Orders | 有 ticket、檔案範圍、測試、驗收。 | 只能說 implementation planned。 |
| L3 Implemented | 有程式碼與自動測試。 | 可說 implemented，但需保留限制。 |
| L4 Dogfooded | 有真實使用紀錄、失敗案例與修正。 | 可說 dogfooded。 |
| L5 Public Claim | 有 benchmark 或可重跑證據支持。 | 可做較強公開宣稱。 |

目前狀態：

| 項目 | 目前成熟度 | 下一步 |
| --- | --- | --- |
| Daily console | L3 read-only MVP + CLI action dry-run/journal | Browser mutation UI 與真正執行 action 仍需後續 gate。 |
| Review benchmark | L3，runner/10-case fixture/report CLI + explicit real-adapter dogfood path | 跑 real Claude/Codex reviewer dogfood artifact。 |
| False/stale memory demos | L3 recall/review baseline + run context manifest UX | Review/session context manifest parity 仍需補測。 |
| Alpha adoption/team readiness | L3 dry-run export/import + policy validation | Runtime policy enforcement、non-dry-run import、metadata sync 仍需後續設計。 |

## 解決方案設計文件

這四份文件把剩餘弱點從 roadmap 轉成可實作、可測試、可 code review 的方案：

| 剩餘弱點 | 解決方案文件 | 解決方式 |
| --- | --- | --- |
| Daily console 仍是 read-only | [`docs/console-mutation-recovery-design.md`](console-mutation-recovery-design.md) | 先建立 action layer、preflight、journal、retry/recovery，再開 `--actions`。 |
| 尚無 real Claude/Codex reviewer dogfood | [`docs/review-benchmark-real-dogfood-design.md`](review-benchmark-real-dogfood-design.md) | Fake benchmark 留在 CI；real adapter 用 explicit `--dogfood` 跑本機報告並記錄限制。 |
| Stale/blocked memory 的 `AIT_CONTEXT_FILE` UX 不完整 | [`docs/context-manifest-memory-trust-design.md`](context-manifest-memory-trust-design.md) | 新增 `ait.context_manifest`，把 trusted/advisory/excluded memory 與原因分開呈現。 |
| Alpha adoption 的 sync/policy/UI recovery 未落地 | [`docs/team-readiness-export-policy-design.md`](team-readiness-export-policy-design.md) | 做手動 metadata bundle、repo-local team policy profile，仍不做自動 sync。 |

## Milestone A：Repo-local Daily Console

### 目標

把 `ait.work_graph` JSON contract 變成 read-only daily console。這一步只讀，不做
mutation，先解決「沒有日常操作介面」的最大體感弱點。

### Work Order A1：Console CLI Skeleton

| 欄位 | 內容 |
| --- | --- |
| Goal | 新增本機 read-only console entrypoint。 |
| Implemented CLI | `ait console --read-only`、`ait console --read-only --serve-local --host 127.0.0.1 --port 0`。 |
| Primary files | `src/ait/cli/console.py`、`src/ait/cli/main.py`、`src/ait/cli_parser.py`、`src/ait/report/console.py`。 |
| Constraints | Bind loopback only by default；不開外部網路；不需要帳號；不寫 `.ait/`。 |
| Tests | JSON smoke、loopback host guard、no `.ait/` mutation test。 |
| Acceptance | Command writes read-only HTML；`--serve-local` prints a loopback URL；long-running Ctrl-C cleanup remains manual smoke。 |
| Status | Implemented for temp HTML output and loopback host guard；long-running serve remains manual smoke。 |

### Work Order A2：Read-only Console Page

| 欄位 | 內容 |
| --- | --- |
| Goal | 建立可掃描的 attempts/evidence/memory/review page。 |
| Views | latest attempts、blocked reviews、apply-ready attempts、hot files、memory sources、review findings、attempt detail。 |
| Data source | `build_work_graph()` output only。 |
| Primary files | `src/ait/report/console.py`、`tests/test_cli_run.py`。 |
| Constraints | No external CDN、no telemetry、no remote assets。 |
| Tests | HTML includes core sections；empty repo does not crash；graph JSON and console counts match。 |
| Acceptance | 使用者不用 CLI 查詢也能看出 latest attempt、blocked review、hot files、memory facts。 |
| Status | Implemented read-only page sections；graph/console count matching can be expanded with richer fixtures。 |

### Work Order A3：Console Compatibility Contract

| 欄位 | 內容 |
| --- | --- |
| Goal | 保護 `ait.work_graph` schema 對 console 的相容性。 |
| Primary files | `tests/fixtures/work_graph/schema_v1_contract.json`、`tests/fixtures/daily_console/schema_v1_contract.json`、`tests/test_cli_run.py`。 |
| Tests | Golden contracts；schema_version bump required on breaking key changes；filter tests continue passing。 |
| Acceptance | Console 不依賴未 versioned 或 private Python objects。 |
| Status | Implemented via `ait.work_graph` and `ait.daily_console` schema v1 golden fixtures。 |

### Work Order A4：Mutation Design Gate

| 欄位 | 內容 |
| --- | --- |
| Goal | 在任何 UI mutation 前先定義 action journal 與 rollback behavior。 |
| Actions | apply、recover、discard、review finding update。 |
| Primary files | `docs/console-mutation-recovery-design.md`，實作後新增 `src/ait/console_actions.py`、`tests/fixtures/console_action/schema_v1_contract.json`。 |
| Tests | 每個 action 的 dry-run、dirty repo、held review、failure path、retry path 必須有測試。 |
| Acceptance | UI action 只呼叫既有 domain/CLI path，不直接寫 Git、SQLite 或 worktree contents；read-only mode 不顯示 action controls。 |
| Status | Implemented CLI dry-run action layer、preflight、journal、schema fixture 與 smoke tests；browser `--actions`/execution/retry 仍未啟用。 |

### Daily Console Release Gate

- `ait graph --format json` 與 `ait console --read-only --format json` contract tests 通過。
- Console page 不使用外部資源。
- Empty repo、uninitialized repo、blocked review repo 都能 render。
- 沒有 mutation 功能時，UI 文案不得暗示可直接操作。
- 若加入 mutation，必須有 action journal、dry-run/confirmation、failure rollback tests。

## Milestone B：Review Benchmark 擴充與 Dogfood

### 目標

把 adversarial review 從「有 workflow」推進到「可量測」。先擴 deterministic
fixture，再新增 CLI report，最後才跑 real local reviewer dogfood。

### Work Order B1：Fixture Expansion To 10 Cases

| 欄位 | 內容 |
| --- | --- |
| Goal | 維持至少 10-case fixture，並持續擴充各風險類型深度。 |
| Primary files | `tests/fixtures/review_benchmark/cases.json`、`tests/fixtures/review_benchmark/README.md`。 |
| Required areas | auth、billing、dependency、migration、CI/deployment、missing tests、prompt injection、memory contamination、benign refactor、benign docs。 |
| Tests | `test_load_benchmark_cases_validates_fixture` 必須覆蓋新欄位。 |
| Acceptance | 至少 2 個 no-finding false-positive controls；至少 2 個 memory trust cases。 |
| Status | Implemented initial 10-case fixture；future work should deepen each area。 |

### Work Order B2：Benchmark JSON Schema And CLI

| 欄位 | 內容 |
| --- | --- |
| Goal | 補 benchmark command 與 versioned report schema。 |
| Implemented CLI | `ait review benchmark run --fixture ... --fake-reviewer fake:case --format json`。 |
| Report CLI | `ait review benchmark report --input .ait/review-benchmark/latest.json --format markdown`。 |
| Primary files | `src/ait/review_benchmark.py`、`src/ait/cli/review.py`、`tests/fixtures/review_benchmark/report_schema_v1_contract.json`、`tests/test_review_benchmark.py`。 |
| Tests | JSON schema_version/golden keys；Markdown report includes limitations；invalid fixture CLI test remains future。 |
| Acceptance | CI 可在 no network/no login/no API key 環境跑 fake reviewer benchmark。 |
| Status | Implemented JSON/Markdown run/report CLI for fake reviewers；invalid fixture CLI test remains future. |

### Work Order B3：Real Reviewer Dogfood Run

| 欄位 | 內容 |
| --- | --- |
| Goal | 記錄至少一輪 Claude Code 或 Codex local reviewer benchmark。 |
| Primary files | `docs/review-benchmark-real-dogfood-design.md`、`docs/review-benchmark-dogfood-report.md`、`.ait/review-benchmark/` generated artifact if committed intentionally。 |
| Required metadata | adapter、resolved binary、command、local auth mode、permission profile、model if known、elapsed time、environment assumptions、fixture hash、token/cost if available。 |
| Tests | Real reviewer 不進 required CI；fake path remains CI gate；mock real adapter validates report metadata/redaction。 |
| Acceptance | Claude Code 與 Codex 各有 dogfood artifact，或 report 明確記錄 unavailable 原因；不把單次結果當通用品質宣稱。 |
| Status | Implemented explicit `--dogfood` real-adapter path with metadata/redaction tests；real Claude/Codex artifacts still required before dogfood/quality claims。 |

### Review Benchmark Release Gate

- `tests/test_review_benchmark.py` 通過。
- Fake reviewer benchmark 不需要 network/login/API key。
- Report 同時呈現 recall、false positives、latency、token/cost when available。
- Public docs 不得使用 "proven"、"guaranteed"、"catches all" 等超出資料的 claim。

## Milestone C：False-memory / Stale-memory Executable Demos

### 目標

把目前 reference docs 的 acceptance spec 變成可重跑 fixture/test，證明 AIT 不把
candidate/stale/superseded/policy-blocked memory 當成 trusted baseline。

### Work Order C1：Memory Trust Fixture Schema

| 欄位 | 內容 |
| --- | --- |
| Goal | 建立 false/stale memory fixture schema。 |
| Primary files | `tests/fixtures/memory_trust/false_memory.json`、`tests/fixtures/memory_trust/stale_memory.json`。 |
| Required fields | `source_id`、`status`、`trust_level`、`topic`、`body`、`expected_in_context`、`expected_trusted`；optional `source_trace_ref`、`source_file_path`、`valid_to`、`superseded_by`。 |
| Tests | Fixture loader validates required fields and rejects unknown status。 |
| Acceptance | Fixture 能表達 accepted、candidate、stale、superseded、policy_blocked。 |
| Status | Implemented fixture validation in regression tests for `false_memory.json` and `stale_memory.json`。 |

### Work Order C2：Recall Payload Trust Metadata

| 欄位 | 內容 |
| --- | --- |
| Goal | 確認 memory recall、review baseline、`AIT_CONTEXT_FILE` manifest 都帶 source/status/trust metadata。 |
| Primary files | `docs/context-manifest-memory-trust-design.md`、`src/ait/memory/*`、`src/ait/context.py`、未來 `src/ait/context_manifest.py`、`tests/test_memory.py`。 |
| Tests | accepted facts 可作 trusted baseline；candidate/stale/superseded/policy-blocked 不可。 |
| Acceptance | Recall/review baseline 可以排除 blocked/stale/superseded facts 並留下原因；`AIT_CONTEXT_FILE` 與 manifest 能顯示 trusted/advisory/excluded 分類，policy-blocked body 不外洩。 |
| Status | Recall/review baseline regression 已實作；wrapped run `AIT_CONTEXT_FILE` manifest trust UX 已實作並覆蓋 policy-blocked body 不外洩；review/session parity remains follow-up。 |

### Work Order C3：Executable Demos

| 欄位 | 內容 |
| --- | --- |
| Goal | 加入可重跑 demo 或 pytest E2E。 |
| Suggested tests | `tests/test_memory_trust.py::test_false_memory_not_promoted`、`test_stale_memory_superseded`。 |
| Docs | 更新 `site-docs/reference/live-federated-memory.md`，把 spec 標示為 implemented only after tests land。 |
| Acceptance | 測試能在 clean repo 建立 fixture、跑 recall/review、驗證 trusted baseline。 |
| Status | Implemented clean-repo fixtures/tests for recall and deterministic review baseline。 |

### Work Order C4：Context Manifest Trust UX

| 欄位 | 內容 |
| --- | --- |
| Goal | 讓 `AIT_CONTEXT_FILE` 與 sibling manifest 明確顯示 trusted、advisory、excluded memory 與排除原因。 |
| Primary files | `docs/context-manifest-memory-trust-design.md`、未來 `src/ait/context_manifest.py`、`tests/fixtures/context_manifest/schema_v1_contract.json`。 |
| Required behavior | Policy-blocked content 不進 prompt/manifest body；stale/superseded/candidate 不能列為 trusted baseline；manifest 保留可審查 reason。 |
| Tests | accepted/candidate/stale/superseded/policy-blocked clean-repo fixture；run/review context manifest 使用同一套 trust labels。 |
| Acceptance | 使用者能從 manifest 看出為何某個 memory 被 trusted、advisory 或 excluded，且 secret/policy-blocked body 不外洩。 |
| Status | Implemented for wrapped run context manifest with schema fixture and clean-repo regression；review/session context manifest parity remains follow-up。 |

### Memory Trust Release Gate

- 沒有 explicit adoption path 時，candidate memory 不能進 trusted baseline。
- Superseded/stale facts 不得被 benchmark 或 reviewer 當成 current baseline。
- Context manifest 能解釋 source、status、trust reason。
- Docs 不宣稱 perfect recall 或 semantic truth。

## Milestone D：Alpha Adoption / Team Readiness

### 目標

不把 AIT 偽裝成 production-ready；而是把 local power-user 工具逐步硬化到小團隊
可評估。這一階段重點是 export/import、policy profile、mutation recovery，不做
cloud sync。

### Work Order D1：Metadata Export/Import Design

| 欄位 | 內容 |
| --- | --- |
| Goal | 先做手動 bundle，不做自動 sync。 |
| Suggested CLI | `ait metadata export --output ait-metadata.bundle.json`、`ait metadata import --dry-run ...`。 |
| Primary files | `docs/team-readiness-export-policy-design.md`，實作後再新增 `src/ait/metadata_bundle.py`。 |
| Bundle contents | schema_version、repo identity、attempt summaries、memory facts、review findings、source hashes。 |
| Exclusions | raw traces、secrets、absolute paths by default。 |
| Tests | dry-run reports conflicts；import refuses repo identity mismatch unless forced；redaction policy applied。 |
| Acceptance | 使用者能手動搬移 metadata，但文件仍說沒有 cross-machine sync。 |
| Status | Implemented dry-run export and dry-run import plan with `ait.metadata_bundle` / `ait.metadata_import_plan` schema fixtures；non-dry-run import and conflict resolution remain follow-up。 |

### Work Order D2：Team Policy Profile

| 欄位 | 內容 |
| --- | --- |
| Goal | 把 review/memory/apply policy 從散落 flags 變成 repo-local profile。 |
| Suggested file | `.ait/policy.toml` 或 `.ait/policy.json`。 |
| Policy areas | default review mode、required review severity、memory source allowlist、global source policy、apply hold behavior、redaction。 |
| Primary files | `docs/team-readiness-export-policy-design.md`、未來 `src/ait/team_policy.py`、`src/ait/memory_policy.py`、review policy modules、`tests/test_policy_profile.py`。 |
| Tests | invalid policy fails closed；default policy preserves current behavior；policy appears in `ait doctor` or status。 |
| Acceptance | 小團隊可以把 policy commit 或明確忽略，行為可審查。 |
| Status | Implemented `.ait/policy.json` validation/show with fail-closed schema tests；runtime enforcement across memory/apply/console remains follow-up。 |

### Work Order D3：UI Mutation Recovery

| 欄位 | 內容 |
| --- | --- |
| Goal | 為未來 console mutation 建立可審查、可失敗、可回復的 action layer。 |
| Primary files | `docs/console-mutation-recovery-design.md` first；implementation later under `src/ait/console_actions.py`。 |
| Required actions | apply、recover、discard、finding status update。 |
| Journal fields | action_id、actor label、attempt_id、preflight result、domain command、started_at、ended_at、status、error、rollback hint。 |
| Tests | preflight failure leaves repo unchanged；domain command failure records failed action；retry is explicit。 |
| Acceptance | UI mutation 不會繞過 existing apply/recover/discard semantics。 |
| Status | Implemented CLI dry-run/preflight/journal foundation for apply/recover/discard；browser mutation UI, execution, retry links, and review-finding action remain follow-up。 |

### Work Order D4：Alpha Adoption Docs Gate

| 欄位 | 內容 |
| --- | --- |
| Goal | 保持公開文案誠實，並讓目標使用者知道目前能做什麼。 |
| Primary files | `README.md`、`README.zh-TW.md`、`site-docs/facts.md`、`site-docs/getting-started.md`。 |
| Tests | `rg` gate 確認 alpha、local-only、no sync、power users/infra-minded engineers 仍存在。 |
| Acceptance | Public docs 不會讓使用者以為已有 production team sync 或 GUI dashboard。 |

### Alpha Adoption Release Gate

- Public docs 保留 alpha/local-only/no-sync 邊界。
- 新增 team readiness 功能不得引入 telemetry 或 remote service。
- Export/import 必須預設 redaction，且 dry-run 可檢查。
- Policy profile invalid config 必須 fail closed。
- UI mutation 必須有 preflight、journal、failure/retry path。

## Cross-milestone Code Review Checklist

每個 PR 必須回答：

- 這次 PR 對應哪個 work order？
- 是否新增或修改 public claim？
- 是否需要 schema_version？
- 是否有 no-network/no-telemetry 保證？
- 是否有 failure path test？
- 是否會把 roadmap 文案誤導成已完成？
- 是否保持 Git/source-of-truth semantics？

## 建議執行順序

1. A1/A2/A3：read-only daily console，因為 data contract 已先完成。
2. C1/C2/C3：memory trust demos，因為它支撐 benchmark 與 review claims。
3. B1/B2：benchmark fixture 與 CLI report，先保持 fake reviewer CI path。
4. C4：context manifest trust UX，已完成 wrapped run path；補 review/session parity。
5. B3：real reviewer dogfood path 已完成；下一步跑 Claude/Codex artifacts 並標示環境與限制。
6. D1/D2：metadata export/import dry-run 與 team policy validation 已完成；下一步做 runtime enforcement 與 non-dry-run import design。
7. D3：CLI action layer、journal、recovery dry-run tests 已完成；只有 execution/retry/UI tests 完成後才做 browser mutation。
8. D4：每個 release 都重跑 public claim audit。
