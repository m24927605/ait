# AIT 產品弱點解決方案、設計與驗收規格

## 文件狀態

本文是工程執行規格，不是 marketing copy。它把目前 AIT 的五個產品弱點轉成
可實作、可測試、可 code review 的工作項目：

1. 產品類別不夠直覺。
2. 缺少日常 UI，容易輸給 GUI-first agent managers。
3. Alpha quality 限制 adoption。
4. 共同記憶容易被誤解成 prompt/context 拼接。
5. Review gate 的可量化效果還不夠。

所有公開文件可以誠實描述限制，但必須同時提出解法。內部實作則要讓每個解法
都有設計、測試、驗收與 code review 標準。

## 核心定位

主定位：

> Local control plane for AI coding agents.

副定位：

> Git-native attempt ledger and review gate for Claude Code, Codex, Aider,
> Gemini CLI, and Cursor.

這個定位把 worktree isolation、provenance、shared memory、long-term memory、
agent-to-agent handoff、adversarial review、apply/recover 都收斂到同一個核心：

> Agent work becomes attempts. Attempts become evidence. Evidence feeds memory
> and review. Review can gate apply. Git remains the source of truth.

## 解法總表

| 弱點 | 解決方案 | 主要交付物 | 驗收標準 |
| --- | --- | --- | --- |
| 產品類別不夠直覺 | 把所有公開敘事統一到 local control plane / Git-native attempt ledger。 | README、docs home、facts、llms.txt、OpenGraph、comparison docs。 | 新使用者能在 10 秒內說出 AIT 是 agent CLI 與 Git 之間的本機 control plane。 |
| 缺少日常 UI | 把 `ait graph --html` 背後資料整理成穩定 JSON contract，再做 repo-local daily console。 | Graph JSON schema、console UI、read-only views、apply/recover/discard actions。 | 不開 CLI 也能看出 latest attempts、blocked reviews、memory sources、hot files、可 apply attempt。 |
| Alpha quality 限制 adoption | 明確鎖定 power users / infra-minded engineers，並建立 hardening roadmap。 | Status 文案、getting started、dogfood workflow、hardening checklist。 | 文件誠實標示 alpha，但目標使用者知道現在能解決哪些真痛點。 |
| 共同記憶容易被誤解 | 定義為 attempt-derived, evidence-backed repo memory，不是 hidden chat memory / vector DB / `CLAUDE.md` generator。 | Memory reference、source/status 表、false-memory demo、policy docs。 | 使用者能檢查 memory 來源、狀態、policy、保留/丟棄路徑。 |
| Review gate 缺量化效果 | 建 review benchmark 與 dogfood case report。 | Benchmark fixtures、runner、metrics report、docs case study。 | 能報告 caught bugs、false positives、latency、token cost、effective risk patterns。 |

## 目標與非目標

### 目標

- 讓 AIT 的產品類別變得清楚、可比較、可引用。
- 把視覺化資料模型從 static report 推進到 daily console 的設計。
- 讓 alpha 狀態變成明確 ICP，而不是單純扣分。
- 讓 memory 文案與實作都維持 evidence-backed、repo-local、policy-filtered。
- 讓 adversarial review 從「好聽的詞」變成可量測工作流。

### 非目標

- 不把 AIT 做成 SaaS dashboard。
- 不在沒有 benchmark 前宣稱 review gate 已量化降低 bug rate。
- 不把 external vector DB、team sync、cloud identity 放進短期核心路線。
- 不讓 UI 直接改 Git 狀態；所有 mutation 必須走既有 domain/CLI path。
- 不讓 memory 自動吞入所有聊天或所有 repo 文件。

## Phase 1：產品定位與文件一致性

### 問題

「AI agent 的共同記憶與對抗式審查」準確，但市場分類太散。使用者可能把 AIT
誤放到 worktree manager、memory layer、review bot 或 provenance tool。

### 解法

把公開敘事統一成：

- AIT 是 local control plane。
- Attempt ledger 是核心資料模型。
- Memory、handoff、review、apply/recover 是 ledger 的能力，不是分散產品。

### 設計

Public copy 必須遵守以下階層：

1. Category：local control plane for AI coding agents。
2. Mechanism：Git-native attempt ledger and review gate。
3. Proof surface：attempts、commits、memory、review findings、apply/recover。
4. Boundaries：alpha、local-only、metadata 不跨機器同步。

### 實作切片

- `README.md` / `README.zh-TW.md`
  - 首屏改成 category + mechanism。
  - Status section 保留 alpha，但說明 ICP。
- `site-docs/index.md` / `site-docs/zh-TW/index.md`
  - 首屏、capability table、product direction 一致。
- `site-docs/facts.md`
  - Q&A 必須能被 AI search 引用。
  - JSON-LD 必須同步新增 Q&A。
- `site-docs/llms.txt`
  - 第一段必須包含 category、mechanism、local-only、package name。
- `mkdocs.yml`
  - `site_name` 與 `site_description` 使用相同 category。
- `site-docs/assets/og-default.svg`
  - Social card source 使用 local control plane 文案。
  - PNG 只有在能輸出正確 1200x630 時才更新。

### 測試

- `git diff --check`
- MkDocs strict build。
- JSON-LD parse check：

```bash
node -e "const fs=require('fs'); const s=fs.readFileSync('site-docs/facts.md','utf8'); const m=s.match(/<script type=\"application\\/ld\\+json\">\\n([\\s\\S]*?)\\n<\\/script>/); if(!m) throw new Error('JSON-LD script not found'); JSON.parse(m[1]);"
```

### 驗收

- README、docs home、facts、llms.txt 對 AIT 的一句話定義一致。
- 沒有把 AIT 稱為 SaaS、vector DB、standalone review bot 或 Git replacement。
- Version references 與目前 release 一致。
- Alpha/status 文案不遮掩限制，也不讓目標使用者以為無法使用。

### Code Review 標準

- 任何新增產品 claim 都必須能指到現有功能、測試、demo 或明確 roadmap。
- 不接受「best」「guarantees」「solves hallucination」這類無證據絕對詞。
- Public docs 不能只列弱點，必須連到 solution path。

## Phase 2：Repo-local Daily Console

### 問題

AIT 的資料模型很視覺化：attempt graph、evidence、memory、hot files、review
results。但 `ait graph --html` 目前是 static report，不是日常操作介面。

### 解法

先把 graph/report data contract 穩定化，再做 repo-local daily console。
Console 必須是 local-first、offline-capable、no telemetry，並且所有 mutation
都透過既有 AIT domain/CLI 執行。

### 設計

#### Data Contract

新增或穩定化 `ait graph --format json` 的 schema，schema 來源應接近：

- `src/ait/report/graph.py`
- `src/ait/report/html.py`
- `src/ait/cli/graph.py`

建議 schema：

```json
{
  "schema_version": 1,
  "repo_root": "...",
  "generated_at": "...",
  "summary": {
    "status_counts": {},
    "outcome_counts": {},
    "agent_counts": {},
    "hot_files": []
  },
  "intents": [
    {
      "id": "...",
      "title": "...",
      "attempts": [
        {
          "id": "...",
          "agent_id": "...",
          "status": "...",
          "outcome": "...",
          "files": {},
          "commits": [],
          "review": {},
          "memory_facts": [],
          "memory_retrievals": []
        }
      ]
    }
  ]
}
```

#### UI Views

Daily console 至少包含：

- Attempt timeline / graph。
- Latest attempts。
- Blocked review queue。
- Apply-ready attempts。
- Hot files。
- Memory sources and accepted facts。
- Review findings with severity / blocking / status。
- Attempt detail：prompt、files、commits、review、memory、transcript refs。

#### Actions

UI action 只允許呼叫既有 command/domain path：

- `ait apply <attempt-id> --mode current`
- `ait recover <attempt-id>`
- `ait attempt discard <attempt-id>`
- `ait review finding update ...`

UI 不得直接修改 `.git/`、`.ait/state.sqlite3` 或 worktree contents。

### 實作切片

1. `graph` JSON contract
   - `ait graph --format json`
   - golden fixture tests
   - schema version field
2. Local console read-only
   - `ait console` 或 `ait graph --serve-local`
   - local loopback only
   - no external assets by default
3. Console actions
   - action endpoint 僅呼叫 domain functions
   - 每個 mutation action 要有 confirmation / dry-run option
4. Docs
   - `site-docs/reference/commands.md`
   - `site-docs/zh-TW/reference/commands.md`
   - screenshot / demo flow

### 測試

- Unit
  - graph JSON includes attempts、review summary、memory、hot files。
  - missing `.ait/` returns initialized=false，不 crash。
  - schema remains backward compatible。
- CLI
  - `ait graph --format json` returns valid JSON。
  - filters by agent/status/file work。
- UI
  - static HTML render contains expected views。
  - Playwright screenshot smoke test for desktop/mobile if console becomes interactive.
  - No external network requests in generated page.
- Mutation
  - action calls domain layer once。
  - dirty worktree / overlap uses existing apply hold behavior。
  - failed action leaves repo unchanged。

### 驗收

- 使用者可以在 UI 找到 latest attempt、blocked review、hot files、memory facts。
- UI 顯示與 CLI `ait status` / `ait review status` / `ait graph` 一致。
- 所有 mutation 有 audit trail 或 attempt/review record。
- Console 在沒有網路時可使用。

### Code Review 標準

- 不接受 UI 直接寫 `.git/`、直接改 SQLite、或自行實作 apply/recover semantics。
- 不接受未 versioned 的 JSON contract。
- 不接受依賴 CDN、外部 JS、telemetry 或 remote assets。
- 所有 action 必須有 failed/held path 測試。
- UI text 不得暗示 AIT 已是 SaaS/team dashboard。

## Phase 3：Alpha Adoption 與 Hardening

### 問題

Alpha quality、local-only metadata、不跨機器同步，會限制一般團隊 adoption。

### 解法

短期明確服務：

- power users
- infra-minded engineers
- 多 agent heavy users
- local-only / no SaaS / provenance-sensitive repo owners

同時建立 hardening roadmap，避免 alpha 變成永久藉口。

### 設計

Public docs 要用「目前適合誰」描述 alpha：

- 適合本機 dogfooding。
- 適合熟 Git workflow 的早期使用者。
- 適合需要 local-only metadata 的 repo。
- 不承諾跨機器同步與一般團隊治理。

Hardening roadmap 分三層：

1. Local reliability
   - wrapper bypass detection
   - daemon lifecycle robustness
   - recovery/apply safety
2. Policy reliability
   - review gate defaults
   - memory policy status
   - safe mutation boundaries
3. Team readiness
   - export/import
   - sync design
   - UI affordances

### 實作切片

- `site-docs/getting-started.md`
  - power-user onboarding path。
- `site-docs/facts.md`
  - alpha Q&A 保留 target ICP。
- `docs/production-hardening-design.md`
  - 補 local reliability / team readiness map。
- Demo docs
  - 每個 pain-point demo 標示「今天已可用」與「仍是 alpha」。
- `docs/ait-product-maturity-hardening-work-orders-zh.md`
  - 把 metadata export/import、team policy profile、UI mutation recovery
    拆成 ticket-level work orders。

### 測試

- Docs tests
  - rg 確認 `alpha` 周邊文案包含 target ICP 和 local-only metadata。
- Runtime regression
  - full pytest before release。
  - daemon/socket tests 必須在允許 Unix socket 的環境跑。
- Upgrade/regression
  - `ait upgrade --dry-run`
  - `ait doctor`
  - wrapper bypass status tests。

### 驗收

- 使用者不會以為 AIT 已提供 team sync。
- 使用者知道現在適合 local dogfooding / power users。
- Release notes 不迴避 alpha，但每版都能指出 hardening 改進。

### Code Review 標準

- 不接受把 alpha 文案刪掉。
- 不接受新增 team-ready / production-ready claim，除非有同步、policy、UI、
  regression coverage。
- Release PR 必須列出已跑測試與未覆蓋風險。

## Phase 4：Evidence-backed Repo Memory

### 問題

「共同記憶」容易被誤解成 prompt stuffing、hidden chat memory、vector DB 或
`CLAUDE.md` generator。

### 解法

把 memory 定義與實作都固定為：

- attempt-derived
- evidence-backed
- repo-local
- policy-filtered
- inspectable
- searchable
- reviewable
- tied to Git state

### 設計

#### Memory Source Types

| Type | Source | Trust model |
| --- | --- | --- |
| attempt | `.ait/` attempts | traceable to prompt/output/files/commits |
| commit | Git commits linked to attempts | Git-backed |
| note | curated `.ait/` notes | user/adoption controlled |
| fact | accepted memory fact | trusted only after acceptance |
| review | review findings | structured evidence |
| live external | `CLAUDE.md`, `AGENTS.md`, `.codex/`, `.cursor/` | source of truth remains external |

#### Memory Status

| Status | Meaning | Can be trusted baseline? |
| --- | --- | --- |
| accepted | explicitly accepted/adopted | yes |
| candidate | discovered but not accepted | no, advisory |
| stale | likely outdated | no |
| superseded | replaced by newer fact | no |
| policy-blocked | excluded by policy | no |
| external-live | current external file | advisory unless policy elevates |

#### Context Manifest

Every generated `AIT_CONTEXT_FILE` should have a manifest with:

- source id
- source path
- source kind
- hash
- mtime
- bytes used
- policy status
- trust status

### 實作切片

- `site-docs/reference/live-federated-memory.md`
  - source/status tables。
- `src/ait/memory/*`
  - ensure recall payload includes status/trust metadata。
- `src/ait/context.py` / context manifest path
  - include trust/status fields if missing。
- Examples
  - false-memory trap demo。
  - stale/superseded memory demo。
- CLI
  - `ait memory sources --format json`
  - `ait memory recall --format json`

### 測試

- Unit
  - accepted facts can appear as trusted baseline。
  - candidate/stale/superseded/policy-blocked are advisory or excluded。
  - live external files remain source-of-truth and are not auto-imported。
- CLI
  - `ait memory sources` zero-touch: no `.ait/` creation。
  - `ait memory recall` zero-touch by default。
  - `ait memory backfill --dry-run` no write。
  - `backfill --import` explicit write only。
- E2E
  - false-memory trap: agent/context should not invent a decision that lacks evidence。
  - superseded fact: newer fact wins。

### 驗收

- Docs clearly say memory is not hidden chat, vector DB, or `CLAUDE.md`
  generator。
- JSON output exposes source and trust information。
- Context manifest can explain why a fact was included or excluded。

### Code Review 標準

- 不接受把 unaccepted candidate 記憶當 trusted baseline。
- 不接受 auto-import external memory without explicit mutation。
- 不接受沒有 context manifest 的 context injection。
- 不接受 memory docs 宣稱 perfect recall 或 semantic truth。

## Phase 5：Review Gate Benchmark 與 Dogfood Evidence

### 問題

「對抗式審查」是強定位，但如果沒有量化證據，就容易變成 marketing term。

### 解法

建立 review benchmark 與 dogfood case report，量測：

- reviewer 找到多少 implementer 漏掉的 bug
- false positive rate
- review latency
- token cost
- effective risk patterns
- deterministic `light` review 何時足夠
- 何時值得升級到 LLM-backed adversarial reviewer

### 現有基礎

目前已有：

- `src/ait/review_benchmark.py`
- `tests/test_review_benchmark.py`
- `tests/fixtures/review_benchmark/cases.json`
- `ait review attempt --mode light`
- `ait review attempt --mode adversarial`
- structured findings
- review-gated apply

### 設計

#### Benchmark Case Schema

每個 case 至少包含：

```json
{
  "id": "case-id",
  "risk_area": "security",
  "vulnerable_diff": "...",
  "implementer_claim": "...",
  "misleading_memory": "...",
  "expected_findings": [
    {
      "severity": "high",
      "blocking": true,
      "path": "src/example.py",
      "title": "Missing authorization check",
      "body": "..."
    }
  ],
  "expected_risk_level": "high",
  "expected_summary_contains": "authorization"
}
```

#### Metrics

| Metric | Definition |
| --- | --- |
| finding_recall | expected findings matched / expected findings |
| false_positive_count | findings not in expected set |
| evidence_completeness | findings with path/title/body/evidence |
| risk_scoring_calibration | high-risk cases classified as high-risk |
| latency_ms | elapsed review time |
| token_cost | input/output/cached tokens if adapter reports them |
| baseline_usefulness | findings requiring repo memory / all relevant findings |
| trusted_baseline_contamination_rate | blocked or stale memory used as trusted baseline |

#### Report

產出：

- JSON report for automation。
- Markdown report for docs/dogfood。
- Comparison table: no review / light / adversarial。

### 實作切片

1. Expand fixtures
   - security, auth, billing, dependency, migration, test-evidence cases。
2. Benchmark CLI
   - `ait review benchmark run --fixture ... --fake-reviewer fake:case`
   - real Claude/Codex reviewer optional local runs still require separate dogfood command design。
3. Metrics
   - add token/cost fields when adapter exposes them。
   - preserve fake reviewer path for deterministic CI。
4. Dogfood report
   - `docs/review-benchmark-dogfood-report.md`
   - link from adversarial review docs。

### 測試

- Unit
  - fixture validation rejects missing required fields。
  - fake reviewer case mode yields recall=1.0。
  - fake warn mode produces false positives/non-actionable warnings。
  - blocked/stale memory does not contaminate trusted baseline。
- CLI
  - benchmark command exits nonzero on invalid fixture。
  - JSON report schema version present。
  - Markdown report includes metric table。
- E2E
  - run benchmark against fake reviewer in CI。
  - optional local-only job for real Claude/Codex reviewers outside CI。

### 驗收

- At least 10 benchmark cases across multiple risk areas。
- Deterministic CI path does not need API keys or paid credits。
- Public docs can cite benchmark data once available。
- Until benchmark exists, docs explicitly say review is an extra safety pass,
  not a correctness guarantee。

### Code Review 標準

- 不接受 benchmark 依賴真實 LLM 才能通過 CI。
- 不接受只報成功率而不報 false positives。
- 不接受把 `light` deterministic scan 和 LLM reviewer 混在同一指標。
- 不接受未記錄 latency/cost 的 benchmark output schema。
- 不接受用 benchmark 結果宣稱 formal verification。

## Phase 6：Comparison 與競品邊界

### 問題

使用者會拿 AIT 去和 Conductor、Nimbalyst、Vibe Kanban、review bots、memory
layers、raw worktrees 比較。若 AIT 不主動定義比較軸，競品比較會發散。

### 解法

新增 comparison matrix，所有比較都回到本地 attempt ledger：

| Category | AIT position |
| --- | --- |
| GUI-first agent manager | AIT 目前 CLI-first，但會把 graph/report 轉為 local console。 |
| Worktree manager | AIT 使用 worktree，但額外提供 provenance、memory、review、apply/recover。 |
| Memory layer | AIT memory 來自 attempts/evidence，不是 standalone vector DB。 |
| Review bot | AIT review target 是 attempt，finding 可 gate apply，不是只留言。 |
| Provenance tool | AIT metadata local-first，commit-linked，不是 SaaS observability。 |

### 實作切片

- `site-docs/compare/` 新增 comparison page。
- `README.md` Compared to alternatives 補充 GUI-first / memory layer / review bot。
- `site-docs/facts.md` 增加 comparison Q&A。

### 測試

- MkDocs strict build。
- Link check via strict navigation。
- Claims review checklist。

### 驗收

- 使用者能理解 AIT 與 GUI-first tools 的差距與路線。
- 不貶低競品；只描述 tradeoff。
- 所有比較都保留 AIT alpha/local-only 邊界。

## Cross-cutting 測試策略

### 必跑

```bash
git diff --check
uv run --no-project --with mkdocs-material --with mkdocs-static-i18n mkdocs build --strict --site-dir /tmp/ait-site-build
PYTHONPATH=src .venv/bin/python -m pytest -q
```

若 full pytest 因 sandbox 無法 bind Unix socket 失敗，必須在允許本機 Unix
socket 的環境重跑；不能把 sandbox failure 當成產品 regression。

### Docs 專用

- JSON-LD parse。
- `rg` 檢查 obsolete version references。
- `rg` 檢查 forbidden claims：
  - `guarantee`
  - `production-ready`
  - `perfect memory`
  - `eliminates hallucination`
  - `formal proof`

### Runtime 專用

- `tests/test_cli_run.py` for graph/report。
- `tests/test_review_benchmark.py` for benchmark metrics。
- `tests/test_cli_review.py` / `tests/test_cli_review_adversarial.py` for review。
- `tests/test_memory.py` / live memory source tests for memory boundary。
- `tests/test_landing.py` for apply/recover safety。

## Release Gate

Release PR 必須勾選：

- [ ] README 與 docs site category 一致。
- [ ] Facts JSON-LD valid。
- [ ] Version references correct。
- [ ] Alpha/local-only/status wording preserved。
- [ ] Memory docs do not claim hidden chat memory, external vector DB, or
      auto-import behavior。
- [ ] Review docs do not claim benchmark-proven quality unless real reviewer
      dogfood and enough measurement data are linked。
- [ ] UI docs describe `ait console --read-only` as read-only and do not imply
      mutation actions exist。
- [ ] `git diff --check` passed。
- [ ] MkDocs strict build passed。
- [ ] Relevant pytest suite passed。

## Code Review 標準總則

### Claims

- 每個 claim 必須屬於三類之一：
  1. already implemented and tested
  2. documented roadmap
  3. explicit limitation
- Reviewer 必須要求 claim 對應到 code、test、demo、issue/spec 或 roadmap。

### Safety

- AIT 的核心安全邊界不可破壞：
  - root checkout 不應被 agent run 直接污染。
  - apply/recover/discard 必須走既有 domain logic。
  - local-only/no telemetry 不得被 UI 或 benchmark 破壞。

### Memory

- Memory injection 必須可追溯。
- Context manifest 必須能解釋來源與 policy status。
- Candidate/stale/superseded/policy-blocked 不得被當成 trusted baseline。

### Review

- Review gate 必須 fail closed on malformed/failed required review。
- Reviewer adapter failure 不得被當作 pass。
- Benchmark 必須報 false positives 與 latency/cost。

### UI

- UI mutation 必須可審核、可失敗、可回復。
- UI 不得使用外部 CDN 或 telemetry。
- UI must not hide blocked review state。

### Tests

- 新增 schema 必須有 golden fixture。
- 新增 CLI output 必須有 JSON mode test。
- 新增 docs claim 必須有至少 docs build + claim review。

## 已完成項目

- README / README.zh-TW 首屏改為 local control plane。
- Docs home / zh-TW home 改用相同 category。
- `mkdocs.yml` site name 與 description 改為 local control plane。
- `site-docs/facts.md` 新增 category、UI、memory、review benchmark 與 weakness
  solution Q&A。
- `site-docs/llms.txt` 改為 local control plane / attempt ledger 摘要。
- Memory docs 明確說明 attempt-derived、evidence-backed repo memory。
- Memory docs 補上 source/status/trust model，以及 false-memory /
  stale-memory acceptance demo 規格。
- Adversarial review docs 補上 review quality measurement 邊界。
- `docs/review-benchmark-dogfood-report.md` 新增 review benchmark dogfood 初版，
  記錄現有 deterministic fake reviewer baseline metrics 與未滿足的公開宣稱門檻。
- `tests/fixtures/review_benchmark/README.md` 補上 benchmark fixtures 的下一步
  擴充規格與 code review standard。
- `ait graph --format json` 新增 `ait.work_graph` schema/version contract，
  並以 golden fixture 鎖定 payload 形狀。
- `site-docs/compare/agent-managers-memory-review-vs-ait.md` 與 zh-TW 對應頁
  補上 AIT 對 GUI-first agent managers、worktree managers、memory layers、
  review bots、provenance tools 的類別邊界。
- `docs/ait-product-maturity-hardening-work-orders-zh.md` 補上未解弱點的
  ticket-level 成熟度計畫，涵蓋 daily console、review benchmark、memory trust
  demos、metadata export/import、team policy profile、UI mutation recovery。
- `ait console --read-only` 新增 read-only daily console MVP，消費
  `ait.work_graph` data contract；`--serve-local` 僅允許 loopback host。
- `tests/fixtures/memory_trust/` 與 `tests/test_memory_trust.py` 新增
  false-memory / stale-memory 可執行 regression，驗證 candidate、stale、
  superseded、policy-blocked memory 不會進 trusted baseline。
- `tests/fixtures/review_benchmark/cases.json` 擴充到 10 cases，並補
  `ait review benchmark run/report` JSON/Markdown CLI smoke coverage。
- `docs/console-mutation-recovery-design.md`、`docs/review-benchmark-real-dogfood-design.md`、
  `docs/context-manifest-memory-trust-design.md`、`docs/team-readiness-export-policy-design.md`
  把剩餘四個弱點拆成可實作、可測試、可 code review 的解決方案。
- Changelog 記錄此產品方向與解法規格。

## 下一步建議

1. 實作 `docs/context-manifest-memory-trust-design.md`：先讓 run/review context
   manifest 清楚標示 trusted/advisory/excluded memory，避免後續 dogfood 與 UI
   action 建在不透明 context 上。
2. 實作 `docs/review-benchmark-real-dogfood-design.md`：保留 fake reviewer CI
   path，新增 explicit `--dogfood` real adapter path，產出 Claude Code / Codex
   本機 dogfood artifacts。
3. 實作 `docs/console-mutation-recovery-design.md`：先完成 action layer、dry-run、
   journal、failure/retry tests，再讓 console 開 `--actions`。
4. 實作 `docs/team-readiness-export-policy-design.md`：先做手動 metadata
   export/import 與 `.ait/policy.json`，仍不做自動 sync。
5. 每一批實作都要重跑 public claim audit，確保 docs 不宣稱 GUI mutation、
   benchmark-proven quality、SaaS、telemetry、remote sync、auto push 或 auto merge。
