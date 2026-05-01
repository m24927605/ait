# Stage 4 Architecture Refactor Code Review

**審查時間**：2026-05-01
**HEAD commit**：`088abba` (Split repo brain into focused package modules)
**重構 commits**（baseline → HEAD）：

```
cdfdd19 Start Stage 4 architecture refactor skeleton
f51f199 Split DB repositories into focused modules
f4d35cd Split work graph report into package modules
8031a65 Split memory module into focused package modules
197b67f Split CLI parser and helper modules
7db55e8 Make CLI entrypoint a compatibility shim
088abba Split repo brain into focused package modules
```

**測試結果**：
- `.venv/bin/python -m pytest` → **384 passed in 301.97s** ✅
- `PYTHONPATH=src python3 -m unittest discover -s tests` → **384 OK in 299.86s** ✅

**git status**：乾淨；無 untracked

**Production readiness verdict**：**READY WITH CONDITIONS**（refactor ship-safe，但 plan 兩項硬性 acceptance 未達成）

---

## Executive summary

Stage 4 重構 ship-safe：
- 公開 API 相容（22 個關鍵 module 都能 import，無 circular）
- 測試 384/384 雙綠（refactor 過程沒打破現有行為）
- entrypoint `python -m ait.cli`、pyproject `ait.cli:main`、tests' `patch("ait.cli.*")` 都仍有效
- `cli.py` 變 shim（70 行）、`brain` 不再反向 import `app`、no top-level `memory.py/brain.py/report.py`

但對照 `docs/architecture-refactor-plan.md` 的 acceptance criteria：
- ❌ **MemoryRepository 完全沒做**（plan 第 68-72 行強制要求）；memory/ 套件中仍有 12 處 `connect_db()` 直接呼叫
- ❌ **CLI 沒按 command-family 拆**（plan 第 36-47 行要求 `cli/init.py`、`attempt.py`、`intent.py`、`memory.py`、`graph.py`、`daemon.py`、`shell.py`、`upgrade.py`）；實際是 flat `cli_main.py` 929 行 + 一個 700+ 行的 main() 含 32 個 `if args.command` 分支
- ⚠️ `cli.py` shim 用 runtime monkey-patch 把自己的 `_upgrade_payload`/`_upgrade_command` 注入 `cli_main`，且 `cli_main.py:881-925` 還留有同名重複實作（drift 風險）
- ⚠️ Plan 說的 `report/{models,status,health}.py` 與 `memory/{facts,eval}.py` 沒建立（功能散落他處或未實作）

「No critical/high release blockers found」**對 runtime 而言**正確，但對「Stage 4 完成」這個交付承諾而言是 **partial delivery**——須記入 follow-up scope，否則下一輪 reviewer 會以為已完成。

---

## Findings

### Critical

無 release blocker。所有測試綠、公開 API 完整、entrypoint 工作。

### High

#### H1 — MemoryRepository 未引入；memory/ 仍 12 處 `connect_db`，違反 plan 硬性 acceptance criteria
- **位置**：plan `docs/architecture-refactor-plan.md:68-72,126,157`；違反處：
  - `src/ait/memory/lint.py:56`
  - `src/ait/memory/candidates.py:158, 232`
  - `src/ait/memory/summary.py:58`
  - `src/ait/memory/notes.py:55, 85, 94, 111`
  - `src/ait/memory/importers.py:158, 329`
  - `src/ait/memory/recall.py:72, 451`
- **證據**：
  ```
  $ rg "class .*Repository\b" src/      → 0 matches
  $ rg "connect_db\s*\(" src/ait/memory/  → 12 matches
  ```
  Plan 第 68-72 行強制：「Introduce `MemoryRepository(conn)` and make high-level functions accept either `repo_root` or an injected repository… **This repository seam must be introduced before moving read-only memory helpers** so extracted modules do not duplicate the current connection pattern.」執行步驟第 2 項是 「Introduce MemoryRepository behind existing public functions」；但實際 commit 順序直接從 step 1（skeleton）跳到 step 4（CLI）與 step 7（DB），完全跳過 MemoryRepository。
  Acceptance criteria（plan:157）：「memory internals no longer open their own DB connection for every helper」— **未達成**。
- **影響**：
  1. 所有 memory helper 仍各自 `connect_db + run_migrations`，這正是 2026-04-30 review F4 / 2026-05-01 review AR-NEW-H3 兩輪都標的問題。Stage 4 的 file split 把 2,359 行 `memory.py` 拆成 8 個檔案，但**沒解決底層連線重複的根本問題**。
  2. 多 process 場景下 daemon 與 memory write 仍各自開 connection，跟 daemon 的 `db_lock` 完全分離。WAL 雖能承受，但 memory write 不被 daemon 觀察、無法整合 event/dedupe，這個系統性風險仍在。
  3. plan 第 70 行寫得很重：「This repository seam must be introduced before moving read-only memory helpers」— 順序倒置使後續若再加 helper，依然會抄目前的 connect_db 模式。
- **建議修法**：
  1. 新增 `src/ait/memory/repository.py` 定義 `MemoryRepository(conn, *, root)`，封裝所有 SQL 操作
  2. 對 memory/ 8 個 module 改造：所有內部 helper 接受 `MemoryRepository` 參數，不自己 connect_db；module-level public function（如 `add_memory_note(repo_root, ...)`）保留作為 facade，內部建立一次 conn → MemoryRepository → 把同一個 repo 傳給內部 helper
  3. 同步 `summary.build_repo_memory_with_connection` 等已有 with_connection 變體的命名規律
- **驗收**：
  - `rg "class MemoryRepository" src/` → 1 命中
  - `rg "connect_db\s*\(" src/ait/memory/` 應從 12 降至 ≤ 4（保留 module-level facade 入口處）
  - 既有 384 tests 全綠
  - 多 process daemon e2e（`tests/test_daemon_e2e.py`、`tests/test_concurrency.py`）仍綠

#### H2 — CLI 未按 plan 拆為 command-family modules；`cli_main.py` 仍是 929 行的 monolithic dispatcher
- **位置**：plan `docs/architecture-refactor-plan.md:36-47`；違反處：
  - `src/ait/cli_main.py` 929 行
  - `src/ait/cli_main.py:135` `def main()` 之後一個 700+ 行的 super-function，含 32 個 `if args.command == "..."` / `elif` 分支（grep 計數 = 32）
- **證據**：
  ```
  $ grep -c "if args\.command\|elif args\.command" src/ait/cli_main.py  → 32
  $ wc -l src/ait/cli_main.py                                              → 929
  $ ls src/ait/cli/                                                        → No such directory
  ```
  Plan 第 36-47 行明確列出 `cli/__init__.py`、`cli/main.py`、`cli/init.py`、`cli/attempt.py`、`cli/intent.py`、`cli/memory.py`、`cli/graph.py`、`cli/daemon.py`、`cli/shell.py`、`cli/upgrade.py` 共 10 個檔案。實際只有 flat `cli.py`（shim）+ `cli_main.py`（929 行）+ `cli_helpers.py`（881 行）+ `cli_parser.py`（279 行）+ `cli_installation.py`（282 行）。
  執行步驟第 4 項：「Move CLI parser/dispatcher one command family at a time.」實際上 parser 抽出來了（cli_parser.py 279 行），但 **dispatcher 沒按命令族拆**——所有 32 個分支仍在 main() 一個函式裡。
- **影響**：
  1. **可讀性沒實質改善**：929 行的 `cli_main.py` + 700+ 行 main() 維護痛點與重構前的 2,265 行 `cli.py` 是同樣的問題（一條 mega-function）。File 名換了，dispatcher 結構沒變。
  2. **日後新增 CLI 命令仍要動同一個檔**：違反 OCP；refactor 的目的（讓 maintainer 改 attempt 命令時不必碰 memory 命令）沒達成。
  3. **plan 與實作偏離不文件化**：refactor commit message 沒解釋為什麼選 flat 模組而非 plan 的 command-family 套件，也沒更新 `architecture-refactor-plan.md` 註明偏離原因。
- **建議修法（任一）**：
  - **A. 按 plan 完成**（推薦）：建 `src/ait/cli/` 套件，每個命令族一個檔，`main()` 改成 dispatch table（dict 映射 args.command → handler）；`cli.py` 變更瘦的 shim
  - **B. 接受偏離**：在 `architecture-refactor-plan.md` 補一段「flat 模組 vs 套件選擇的取捨」；同時把 main() 內 dispatch 改 dict-table 至少消除 if-chain（現況可讀性問題仍在）
- **驗收**：
  - 若選 A：`ls src/ait/cli/` 列出 plan 第 36-47 行的 10 個檔案；`grep -c "elif args\.command" src/ait/cli/main.py` ≤ 2；`wc -l src/ait/cli/*.py | awk '$1 > 400'` 應為空
  - 若選 B：plan 文件補偏離說明；`grep -c "if args\.command" src/ait/cli_main.py` ≤ 5（dispatch 用 dict-table 取代 if-chain）
  - 既有測試綠 + entrypoint smoke

#### H3 — `cli.py` shim 與 `cli_main.py` 兩處重複定義 `_upgrade_payload` / `_upgrade_command`，drift 風險
- **位置**：
  - `src/ait/cli.py:22-48` `_upgrade_payload`（cli.py 版本）
  - `src/ait/cli.py:51-66` `_upgrade_command`（cli.py 版本）
  - `src/ait/cli_main.py:881-907` `_upgrade_payload`（cli_main.py 版本）
  - `src/ait/cli_main.py:910-925` `_upgrade_command`（cli_main.py 版本）
  - `src/ait/cli.py:13-19` `main()` 在每次呼叫前都把 cli.py 版本的 `_upgrade_payload`、`_upgrade_command`、`_installation_payload` 寫入 `cli_main` 命名空間
- **證據**：兩個版本程式碼結構幾乎一樣（pipx / npm / venv 三條分支邏輯重複）；cli_main.py:881 與 cli.py:22 的函式體經肉眼比對可視為 fork。
  ```python
  # cli.py:13-19
  def main() -> int:
      _cli_main._installation_payload = _installation_payload
      _cli_main._upgrade_payload = _upgrade_payload
      _cli_main._upgrade_command = _upgrade_command
      _cli_main.shutil = shutil
      _cli_main.subprocess = subprocess
      return _cli_main.main()
  ```
- **影響**：
  1. **Drift risk**：將來修 npm 升級邏輯時，maintainer 可能只改一邊（例如 cli.py 改、cli_main.py 沒改）；行為依入口而異——`python -m ait.cli` vs `python -m ait.cli_main` 走不同路徑
  2. **入口語意不一致**：`python -m ait.cli_main` 與 `python -m ait.cli` 都會跑各自 `if __name__ == "__main__":` 區塊（cli.py:69、cli_main.py:928），前者觸發 monkey-patch，後者不觸發
  3. **Hidden coupling**：閱讀 cli_main.py 的 reader 不會知道其 `_installation_payload`、`shutil`、`subprocess` 在 production 路徑下會被外部覆寫；debugger 與 IDE 也看不到這層注入
  4. monkey-patch 設計只是為了讓既有 `patch("ait.cli._installation_payload", ...)` 測試 surface 不破——目標達成，但有更乾淨的方法
- **建議修法**：
  1. **去重 + 單一 source of truth**：cli.py 不要自己定義 `_upgrade_payload` / `_upgrade_command`；改成 `from ait.cli_main import _upgrade_payload, _upgrade_command`，這樣 monkey-patching 可以直接針對 cli_main 命名空間，或不做 monkey-patch（測試改用 `patch("ait.cli_main._installation_payload", ...)`）
  2. **若 backward compat 需保留 `ait.cli._installation_payload` 入口**：用 `__getattr__` module-level hook（PEP 562）回傳 cli_installation 的 reference，避免 main() 每次跑時 monkey-patch
  3. **移除 cli_main.py:928 `if __name__ == "__main__":`**，避免 `python -m ait.cli_main` 走未經 monkey-patch 的路徑（或讓它呼叫 `from ait.cli import main`）
- **驗收**：
  - `grep "def _upgrade_payload\|def _upgrade_command" src/ait/cli*.py` 各 1 命中（去重）
  - `python -m ait.cli --version` 與 `python -m ait.cli_main --version` 行為一致（兩者皆 0.55.26）
  - 既有測試 `patch("ait.cli._installation_payload", ...)` 仍綠

### Medium

#### M1 — `memory/recall.py` 796 行偏大；接近 plan 1,000 行門檻且 recall+search+ranking+rendering 混在一檔
- **位置**：`src/ait/memory/recall.py`（796 行）；`src/ait/memory/__init__.py:35-43` re-exports `_normalize_recall_ranker_scores`、`_temporal_ranked_result`、`build_relevant_memory_recall`、`render_memory_search_results`、`render_relevant_memory_recall`、`search_repo_memory`、`search_repo_memory_with_connection`
- **證據**：`wc -l src/ait/memory/recall.py` = 796；plan acceptance line 155 「no production module exceeds 1,000 lines without documented reason」雖然技術上未超，但 plan 第 60-66 行原本只列 `recall.py: search, temporal ranking, relevant memory rendering`——recall + search + temporal + render 四件事在同檔
- **影響**：未來補 ranker / 改 budget 時，需動同一個 800 行檔案；plan 寫的「extracted modules」精神是按職責拆，目前 recall.py 仍是「mini-monolith」
- **建議修法**（可選）：
  - 拆 `recall.py` 為 `recall.py`（高層 API）+ `search.py`（lexical/vector 搜尋）+ `temporal.py`（temporal ranking）+ `render.py`（rendering）。或
  - 在 plan 文件補「recall.py 保留 800 行的理由」並追蹤
- **驗收**：拆完後每檔 < 400 行；既有 import 路徑不變（透過 `__init__.py` re-export）

#### M2 — `cli_helpers.py` 881 行；32 個 helper 函式混在一檔
- **位置**：`src/ait/cli_helpers.py`（881 行）；定義 32 個 `_format_*` / `_init_payload` / `_repair_payload` / `_status_payload` 等 helpers
- **證據**：`grep -c "^def " src/ait/cli_helpers.py` = 32
- **影響**：與 H2 同源——plan 想看到的是「按命令族切」，不是「helper 全進一個檔」。如果 H2 採方案 A（建 cli/ 套件），cli_helpers 應分散到對應命令族檔（例如 `_format_init` 放 `cli/init.py`、`_format_repair` 放 `cli/init.py` 因屬 install 群、`_format_run_result` 放 `cli/run.py`）
- **建議修法**：與 H2 修法 A 同步處理；分發 cli_helpers 到對應 cli/ 套件 module
- **驗收**：cli_helpers.py 不再存在或縮小至 < 200 行通用 utility

#### M3 — Plan 第 60-66、109-115 行列出的部分檔案沒建立
- **位置**：plan 第 60-66 行（memory）、第 109-115 行（report）
  - **memory**：plan 列 `models / policy / notes / facts / candidates / recall / importers / lint / eval`；實際有 `common / candidates / importers / lint / models / notes / recall / summary`，**缺 `facts.py` 與 `eval.py`**，多了 `common.py` 與 `summary.py`
  - **report**：plan 列 `models / status / graph / html / health`；實際有 `graph / html / shared / text`，**缺 `models.py / status.py / health.py`**
- **證據**：`ls src/ait/memory/` `ls src/ait/report/` 與 plan 對照
- **影響**：
  1. fact CRUD 邏輯散落於 `memory/recall.py`（fact 過濾/取得）+ `memory/candidates.py`（fact upsert）+ `db/memory_repositories.py`（SQL）。沒有獨立 `facts.py`，supersede / valid_to 等 fact lifecycle 概念無法集中
  2. report 沒有 status/health 邏輯（這是 plan 範圍蹭到的，可能 status/health 還沒實作；應在 plan 文件註記）
  3. memory eval 邏輯仍在 top-level `src/ait/memory_eval.py`（332 行）—— plan 想把它搬進 memory 套件，沒做
- **建議修法**：
  - 把 `memory_eval.py` → `memory/eval.py`（單純 rename + `memory/__init__.py` 補 re-export，或保留原入口）
  - 把 fact CRUD 從 candidates.py 抽出 `memory/facts.py`
  - report status/health 若還沒實作，在 plan 明示「Stage 4 不涵蓋」
- **驗收**：`ls src/ait/memory/facts.py src/ait/memory/eval.py` 存在；plan 文件對未做項目註記原因

#### M4 — 沒有 multi-process e2e 測試 specifically for refactor smoke
- **位置**：plan 第 149-150 行「multi-process e2e tests for slices touching daemon, DB repositories, or workspace lifecycle」
- **證據**：refactor 涵蓋 db/repositories 拆分（commit f51f199），但這次 refactor 沒有新增針對拆分後 import 路徑的 multi-process smoke test。既有 `tests/test_daemon_e2e.py`、`tests/test_concurrency.py` 跑綠是好的，但這些測試是 fix batch 的 regression，不是專為 refactor 補的
- **影響**：refactor 不太可能引入 race（純檔案搬動），但 `db/repositories.py` 變 shim、`db/__init__.py` 重新 export 後，多 process 場景下 import 順序與 SQLite 行為的相容性沒有專門驗證
- **建議修法**：補一條 `tests/test_refactor_smoke.py`：兩個 subprocess 各 import `ait.db`、`ait.memory`、`ait.brain`、`ait.report` 後跑簡單 CRUD，斷言行為與單 process 一致
- **驗收**：新測試綠 + import path 各 entry 都能 multi-process

### Low

#### L1 — `report/__init__.py` 排版有多餘空白行
- **位置**：`src/ait/report/__init__.py` 23 行（含多個空 import 行）
- **證據**：
  ```python
  from __future__ import annotations
  
  
  
  from ait.report.graph import build_work_graph
  
  from ait.report.html import render_work_graph_html, write_work_graph_html
  
  from ait.report.text import render_work_graph_text
  ```
  多 1-2 個多餘空行；對比 `memory/__init__.py` / `brain/__init__.py` 排版較整齊
- **影響**：純 cosmetic，讀起來像 auto-generated 輸出未清整
- **建議修法**：合併空行；不是 blocker
- **驗收**：visual review

#### L2 — `db/__init__.py` 仍把 4 張 memory extension 表 re-export 在同一 `__all__`
- **位置**：`src/ait/db/__init__.py:7-46, 49-100`（`MemoryFactRecord`, `MemoryFactEntityRecord`, `MemoryFactEdgeRecord`, `MemoryRetrievalEventRecord` + memory CRUD 函式）
- **證據**：上輪 review CR-NEW-H2 / AR-NEW-H2 已標 high。本輪 db split 把實作搬到 `db/memory_repositories.py`，但 `db/__init__.py` 仍 re-export，外部 `from ait.db import MemoryFactRecord` 仍可用
- **影響**：spec § Storage Mapping 7 表 vs memory 擴充 4 表的邊界仍模糊；未來若要把 memory 子系統獨立發行，breaking import 仍需處理
- **建議修法**：分階段 — 先在 `db/__init__.py` 加 `DeprecationWarning` 提示外部改用 `ait.db.memory_repositories`；下次 minor release 移除 memory record re-export
- **驗收**：DeprecationWarning 觸發；外部 caller 收到提醒

#### L3 — `cli.py:14` `_cli_main.shutil = shutil` 與 `_cli_main.subprocess = subprocess` 是 no-op
- **位置**：`src/ait/cli.py:17-18`
- **證據**：`shutil` 與 `subprocess` 都是 stdlib 模組，cli.py 與 cli_main.py import 的是同一個 module object。`_cli_main.shutil = shutil` 把同一個物件賦回去，no-op
- **影響**：誤導 reader；看似有特殊用途但其實沒有
- **建議修法**：刪掉 line 17-18
- **驗收**：tests 仍綠

---

## 對 plan 的 acceptance criteria 對照

| Criterion | 結果 | 證據 |
|---|---|---|
| `cli.py` becomes a compatibility shim below 100 lines | ✅ | `wc -l src/ait/cli.py` = 70 |
| no production module exceeds 1,000 lines without documented reason | ✅ | 最大 `cli_main.py` 929 行（接近上限但未超）|
| `report.py` becomes a compatibility shim below 100 lines | ✅（轉為 package）| `report/__init__.py` 23 行；無 top-level `report.py` |
| memory internals no longer open their own DB connection for every helper | ❌ | `memory/` 套件仍 12 處 `connect_db()`（H1）|
| `brain` no longer imports from `app` | ✅ | `rg "from ait\.app\|import ait\.app" src/ait/brain*` 為空 |
| all existing tests pass | ✅ | pytest 384 / unittest 384 |
| package public behavior remains backward compatible | ✅ | `from ait.memory import ...` 等都成功；entrypoint smoke 過 |

**6 / 7 達成，1 條 high 未達（H1 MemoryRepository / 12 處 connect_db）**

---

## 對 plan 的 execution plan 對照

| Step | Plan 要求 | 實際 | 評語 |
|---|---|---|---|
| 1 | Add package skeletons and re-export shims with no logic movement | ✅ commit cdfdd19 | 第一階段做了 |
| 2 | **Introduce `MemoryRepository`** behind existing public functions | ❌ | **跳過** |
| 3 | Move memory read-only helpers, then write paths, then import/lint | ⚠️ | commit 8031a65 把所有 memory helper 一次搬完，沒分階段 |
| 4 | Move CLI parser/dispatcher one command family at a time | ❌ | parser 抽出，dispatcher 沒按命令族拆（H2）|
| 5 | Split brain rendering from graph building | ✅ commit 088abba | 做了 |
| 6 | Split report status/graph/html/health modules | ⚠️ | graph/html/text/shared 做了；status/health 沒做 |
| 7 | Split database repository files and keep compatibility exports | ✅ commit f51f199 | 做了 |
| 8 | Remove compatibility shims only after one release cycle | N/A | 未到此 step |

---

## 是否仍存在 working tree only 修法

**否**。`git status --short` 為空、`git ls-files --others --exclude-standard` 為空。所有改動都在 HEAD 之上的 commits 內（cdfdd19..088abba 共 7 個）。

---

## 是否有 circular import / lazy import / entrypoint breakage

實機驗證：

```
$ PYTHONPATH=src python3 -c "import ait.cli; import ait.cli_main; ..."
ait.cli: ok
ait.cli_main: ok
ait.cli_helpers: ok
ait.cli_parser: ok
ait.cli_installation: ok
ait.memory: ok
ait.brain: ok
ait.report: ok
ait.db: ok
ait.app: ok
ait.runner: ok
ait.daemon: ok
ait.events: ok

$ PYTHONPATH=src python3 -m ait.cli --version
ait 0.55.26 (exit 0)

$ PYTHONPATH=src python3 -c "import ait.cli; print(ait.cli.main, ait.cli._upgrade_payload, ait.cli._installation_payload)"
<function main>, <function _upgrade_payload>, <function _installation_payload>
```

✅ 無 circular import；entrypoint 與 monkey-patch surface 都能用。

---

## Verdict

**READY WITH CONDITIONS**

理由：
1. **runtime 安全**：384 tests 雙綠、無 API 破壞、無 circular import、entrypoint 工作、git 乾淨
2. **公開行為相容**：所有 `from ait.memory import`、`from ait.brain import`、`from ait.report import`、`from ait.db import` 路徑都有效
3. **2 條 high 未對齊 plan**：MemoryRepository 完全沒做（H1）、CLI 沒按 command-family 拆（H2）—— 這兩條不是 release blocker，但若把 Stage 4 標為「完成」會讓 plan 兩項 acceptance criteria 沒達成

### Conditions（依優先順序）

1. **H1 MemoryRepository**（必補）—— `memory/` 12 處 `connect_db` 是 plan 強制要求。沒做就違反 acceptance criteria。可以在 follow-up Stage 4.1 做
2. **H2 CLI command-family split**（建議補）—— 選方案 A 完成 plan，或選方案 B 在 plan 文件補偏離說明
3. **H3 cli.py monkey-patch 重複定義**（建議補）—— 移除 cli.py 自己的 `_upgrade_payload`/`_upgrade_command`，改成 from cli_main import 或用 `__getattr__` shim
4. **M1-M4 + L1-L3** —— 視 capacity 處理，不卡 release

### 釋出策略建議

可以 ship 當前 HEAD 作為 0.55.27，但 CHANGELOG 需誠實寫明「Stage 4 partial: file split done; MemoryRepository deferred to 0.56.0」。否則用戶以為 Stage 4 完成、後續 reviewer 拿到專案會誤判進度。

---

## 誠信宣告

- 全程 read-only review，沒改任何 source / test / docs（除新增本報告）
- 每條 finding 都附 `file:line` 與實機證據
- 兩套測試套件實機跑出 384 passed / 384 OK
- 對 plan 的 acceptance criteria 與 execution plan 逐條比對 source 與 commit
- 7 條 refactor commit 都讀過 stat 與部分 diff
- 報告所有檔案行數來自 `wc -l`、命中數來自 `rg`、import 結果來自 `python3 -c` 真實跑
- 不偽造、不猜測、不 fabricate
