# Stage 4 Refactor Acceptance Code Review

**審查時間**：2026-05-01
**HEAD commit**：`65ac012` (Fix M4: add cross-process refactor smoke test)
**Baseline**：`088abba`（上輪 Stage 4 file split 完成點）
**待驗收 commits**（baseline → HEAD，6 條）：
- `0bf0044` Fix H1: introduce MemoryRepository seam
- `6b4c1ce` Fix H2/H3: split CLI into command-family package
- `9269c46` Fix M2: split CLI helper functions by command family
- `c8e2cd7` Fix M1: split memory recall into focused modules
- `339f793` Fix M3: move memory eval and fact helpers into memory package
- `65ac012` Fix M4: add cross-process refactor smoke test

**測試實跑結果**：
- `.venv/bin/python -m pytest` → **386 passed in 308.27s** ✅
- `PYTHONPATH=src python3 -m unittest discover -s tests` → **386 OK in 307.33s** ✅

---

## Final verdict

**READY**。可以 ship。

`docs/code-review-stage4-refactor-2026-05-01.md` 列出的 3 條 High（H1/H2/H3）+ 4 條 Medium（M1-M4）全部對齊 plan 完成；測試 386/386 兩套綠；CLI surface、SQLite schema、memory ranking、daemon protocol envelope 等 spec 行為均無變更；無 working-tree-only 修法；無 public API breakage。

---

## Per-finding 驗收結果

| Finding | 狀態 | 證據 |
|---|---|---|
| **H1** MemoryRepository seam | ✅ **Fixed** | `src/ait/memory/repository.py:16` `class MemoryRepository`；`memory/` 內 `connect_db(` 從 12 處降到 2 處（`repository.py:136` facade 入口、`eval.py:94` evaluator）— 達到 plan acceptance 「memory internals no longer open their own DB connection for every helper」|
| **H2** CLI command-family split | ✅ **Fixed** | `src/ait/cli/` package 建立、`cli/main.py:9-29` 用 dict-based dispatch table 取代 if-chain（`grep -c "if/elif args.command" cli/main.py = 0`）、19 個命令家族檔（init/intent/attempt/memory/daemon/shell/upgrade/graph/run/query/reconcile/adapter）+ 7 個 helper 檔；最大檔 `cli/memory.py` 287 行，全部 < 300 行 |
| **H3** monkey-patch 去重 | ✅ **Fixed** | `_upgrade_payload`/`_upgrade_command` 唯一定義在 `src/ait/cli/upgrade.py:39, 68`；`cli/__init__.py` 直接 re-export，不再 monkey-patch；`python -m ait.cli --version` 與 `python -m ait.cli_main --version` 同樣回 `ait 0.55.26`；`ait.cli._installation_payload`、`ait.cli.subprocess`、`ait.cli.shutil`、`ait.cli.build_parser` 補在 `cli/__init__.py:7-15` 維持 backward compat |
| **M1** memory/recall split | ✅ **Fixed** | `recall.py` 從 796 行降到 260 行；新增 `search.py` 398 行、`temporal.py` 144 行、`render.py` 30 行；recall.py 是高層 facade，依賴 search/temporal/render 而非自己實作；ranking、policy filtering、retrieval event recording 都在 search/temporal/repository 內，public API 從 `memory/__init__.py` 走（`build_relevant_memory_recall`、`search_repo_memory`、`render_memory_search_results` 等都仍可 import）|
| **M2** cli_helpers shim | ✅ **Fixed** | `src/ait/cli_helpers.py` 83 行純 re-export shim，從 `cli.{query_helpers, adapter_helpers, memory_helpers, init_helpers, runtime_helpers, status_helpers, hint_helpers}` 拉所有 helper 並 `__all__` 對外 |
| **M3** memory.eval / memory.facts | ✅ **Fixed** | `src/ait/memory_eval.py` 縮為 19 行 shim 從 `ait.memory.eval` re-export；`src/ait/memory/eval.py` 332 行為實作；`src/ait/memory/facts.py` 60 行抽出 `upsert_memory_fact_for_candidate` / `memory_fact_kind` / `memory_fact_summary`，與 candidates.py 解耦 |
| **M4** refactor smoke test | ✅ **Fixed** | `tests/test_refactor_smoke.py` 真覆蓋兩個 `subprocess.Popen` 起 child Python，import `ait.brain` `ait.db` `ait.memory` `ait.report`，跑 create_intent / create_attempt / add_memory_note；parent 也做同樣事 + 用 list_memory_notes 查 3 個 source；test 1 個 case in pytest 第 86% 通過 |

---

## 命令式驗證輸出

### `git status --short`
```
?? docs/code-review-stage4-refactor-2026-05-01.md
```
> 1 個 untracked = 上輪 review 留下的 task list source-of-truth 文件，Codex 被禁止修改它（且根本沒列入這次 commits）；不是 refactor 的修法漏 commit。屬上輪 review 流程的清潔項，不阻擋 ship。

### `rg "class MemoryRepository" src/`
```
src/ait/memory/repository.py:16:class MemoryRepository:
```
唯一 source of truth ✓

### `rg "connect_db\s*\(" src/ait/memory/ -n`
```
src/ait/memory/repository.py:136:    conn = connect_db(root / ".ait" / "state.sqlite3")
src/ait/memory/eval.py:94:    conn = connect_db(db_path)
```
**2 處** — 都在合理 facade 邊界（一個是 `open_memory_repository` context manager，另一個是 `evaluate_memory_retrievals` 的 evaluator 入口）。前一輪 12 處 → 現在 2 處，遠優於 plan 「≤ 4」目標。

### `find src/ait/cli -maxdepth 1 -type f -name '*.py'`
```
      38 src/ait/cli/__init__.py
       5 src/ait/cli/__main__.py
     137 src/ait/cli/_shared.py
     180 src/ait/cli/adapter_helpers.py
      49 src/ait/cli/adapter.py
      78 src/ait/cli/attempt.py
      29 src/ait/cli/daemon.py
      36 src/ait/cli/graph.py
     117 src/ait/cli/hint_helpers.py
     236 src/ait/cli/init_helpers.py
     188 src/ait/cli/init.py
      44 src/ait/cli/intent.py
      39 src/ait/cli/main.py
     194 src/ait/cli/memory_helpers.py
     287 src/ait/cli/memory.py
      91 src/ait/cli/query_helpers.py
      28 src/ait/cli/query.py
      13 src/ait/cli/reconcile.py
      42 src/ait/cli/run.py
     134 src/ait/cli/runtime_helpers.py
      31 src/ait/cli/shell.py
     215 src/ait/cli/status_helpers.py
      83 src/ait/cli/upgrade.py
    2294 total
```
- 全部檔 < 300 行（最大 cli/memory.py 287）✓
- main.py 39 行 ✓
- 各命令家族（init/intent/attempt/memory/daemon/shell/upgrade/graph/run/query/reconcile/adapter）皆有獨立檔 ✓

### `grep -c "elif args\.command\|if args\.command" src/ait/cli/main.py`
```
0
```
**0** — 完全用 dispatch table，無 if-chain ✓

### `python -m ait.cli --version` 與 `python -m ait.cli_main --version`
```
ait 0.55.26 (exit 0)   ← cli
ait 0.55.26 (exit 0)   ← cli_main shim
```
兩個 entrypoint 一致 ✓

### `rg "def _upgrade_payload|def _upgrade_command" src/ -n`
```
src/ait/cli/upgrade.py:39:def _upgrade_payload(...):
src/ait/cli/upgrade.py:68:def _upgrade_command(...):
```
單一 source of truth ✓

### `rg "from ait\.app|import ait\.app" src/ait/brain* -n`
無 match — brain 仍未反向 import app ✓

### Public API 表面相容（`import ait.cli; print(...)`）
```
main: <function main>
_installation_payload: <function _installation_payload>
_upgrade_payload: <function _upgrade_payload>
_upgrade_command: <function _upgrade_command>
subprocess: <module>
shutil: <module>
build_parser: <function build_parser>
```
舊測試的 `patch("ait.cli._installation_payload", ...)` / `patch("ait.cli.subprocess.run", ...)` / `patch("ait.cli.shutil.which", ...)` 全都仍可 patch ✓

### CLI subcommand surface
`PYTHONPATH=src python3 -m ait.cli --help` 顯示 `{init, intent, attempt, query, blame, run, context, memory, bootstrap, doctor, status, upgrade, graph, repair, enable, shell, adapter, reconcile, daemon}` —  19 個命令一個都沒少 ✓

### Spec / refactor plan / review docs 內容比對
```
$ git diff 088abba..HEAD -- docs/ai-vcs-mvp-spec.md docs/architecture-refactor-plan.md docs/code-review-stage4-refactor-2026-05-01.md
(無輸出)
```
spec、plan、上輪 review 檔都沒被改 ✓

---

## Findings

### Critical

無。所有測試綠、entrypoint 工作、public API 相容、spec 不變。

### High

無。3 條 High（H1/H2/H3）皆已修。

### Medium

無。4 條 Medium（M1-M4）皆已修。

### Low

#### L1 — `cli/_shared.py:97` 與 `cli/__init__.py:15` 走 cli_helpers shim 而非直接 import cli.*helpers
- **位置**：`src/ait/cli/_shared.py:97`、`src/ait/cli/__init__.py:15`
- **證據**：
  ```
  $ rg "from ait\.cli_helpers" src/ait/cli/
  src/ait/cli/__init__.py:15:from ait.cli_helpers import _format_status
  src/ait/cli/_shared.py:97:from ait.cli_helpers import (
  ```
  `cli_helpers.py` 是 backward-compat shim，自己 re-export from `cli.{*helpers}`。`_shared` 與 `__init__` 走 shim 等於：`cli/_shared` → `cli_helpers shim` → `cli.adapter_helpers`。多一層 indirection，且讓「cli 套件內部依賴 ait.cli_helpers shim」這件事不一致（其他 cli/*.py 直接 import）
- **影響**：純風格/可讀性。Python module cache 後 runtime cost 為零；不會 circular（已實機 `importlib.import_module(...)` 全部成功）；不影響 functionality
- **建議修法**：改成直接 import：
  - `cli/__init__.py:15` `from ait.cli.status_helpers import _format_status`
  - `cli/_shared.py:97` `from ait.cli.{adapter_helpers, init_helpers, ...} import ...`（看實際引用了哪些）
- **驗收**：`rg "from ait\.cli_helpers" src/ait/cli/` 應為空；既有測試仍綠

#### L2 — `docs/code-review-stage4-refactor-2026-05-01.md` 仍 untracked
- **位置**：`docs/code-review-stage4-refactor-2026-05-01.md`
- **證據**：`git status --short` 顯示 `??`
- **影響**：上輪 review 留下的 task list source-of-truth 沒進 HEAD。Codex 被指示「不准修改本檔」是正確行為；但這檔本身應該由人工 commit 進 HEAD 才能讓未來 reviewer 在 git log 找到
- **建議修法**：直接 `git add docs/code-review-stage4-refactor-2026-05-01.md && git commit -m "Add Stage 4 refactor review (acceptance source-of-truth)"`（與本份 acceptance 報告一同 commit 也可）
- **驗收**：`git status --short` 乾淨

#### L3 — concurrent pytest + unittest 跑時殘留 daemon orphan（既有觀察）
- **位置**：`tests/test_daemon_e2e.py`、`tests/test_daemon_lifecycle.py`
- **證據**：審查當下 `ps -eo | grep "ait.cli daemon serve" | wc -l` = 41。前次 follow-up #3 已詳述，是 concurrent test runner 短暫 race，會在 default `daemon_idle_timeout_seconds=600` 內自清
- **影響**：這是上輪 follow-up #3 OBS-1 的延續，**不是這次 refactor 引入的 regression**。production 的 graceful shutdown + idle_timeout 仍有效
- **建議修法**：可選，把 test_runner 的 setUp/addCleanup 模式推到 test_daemon_e2e.py 與 test_daemon_lifecycle.py（與本次 refactor scope 無關）
- **驗收**：跑兩套並行 test 後 `ps -eo` 殘留 ≤ 5

---

## Plan acceptance criteria 對照

對照 `docs/architecture-refactor-plan.md:154-160` 與 `docs/code-review-stage4-refactor-2026-05-01.md` 列出的條件：

| Criterion | 結果 |
|---|---|
| `cli.py` becomes a compatibility shim below 100 lines | ✅（top-level cli.py 已被 cli/ package 取代，等同更乾淨）|
| no production module exceeds 1,000 lines without documented reason | ✅（最大 query.py 844 行；非 refactor scope）|
| `report.py` becomes a compatibility shim below 100 lines | ✅（report/ package；__init__.py 23 行）|
| **memory internals no longer open their own DB connection for every helper** | ✅（12 → 2，遠超目標）|
| `brain` no longer imports from `app` | ✅（rg 為空）|
| all existing tests pass | ✅（pytest 386 / unittest 386）|
| package public behavior remains backward compatible | ✅（python -m ait.cli、ait.cli.* surface、from ait.memory import 等都仍可用）|

7/7 達成。

---

## Plan execution plan 對照

| Step | Plan 要求 | 實際 | 評語 |
|---|---|---|---|
| 1 | Add package skeletons and re-export shims with no logic movement | ✅ 上輪 Stage 4 已做 | |
| 2 | **Introduce `MemoryRepository`** behind existing public functions | ✅ commit 0bf0044 | 新引入 |
| 3 | Move memory read-only helpers, then write paths, then import/lint | ✅ commit c8e2cd7 (M1) + 339f793 (M3) | recall split + facts/eval move |
| 4 | Move CLI parser/dispatcher one command family at a time | ✅ commit 6b4c1ce + 9269c46 | dispatch table + helpers split |
| 5 | Split brain rendering from graph building | ✅ 上輪 Stage 4 已做 | |
| 6 | Split report status/graph/html/health modules | ⚠️ 部分 | report/ 有 graph/html/text/shared，無 status/health。屬未來 scope，本次未觸 |
| 7 | Split database repository files and keep compatibility exports | ✅ 上輪 Stage 4 已做 | |
| 8 | Remove compatibility shims only after one release cycle | N/A | 屬未來 |

---

## 是否仍有 working tree only 修法

**否（runtime code 而言）**。`git diff HEAD` 只在 production source / tests 上為空，所有 refactor 都在 6 個 commit 內。

**Untracked**：1 個檔（`docs/code-review-stage4-refactor-2026-05-01.md`）= 上輪 review 留下的 source-of-truth 任務清單，Codex 被禁止修改是正確行為，但需另行 commit（見 L2）。

---

## 是否有 spec 行為變更 / public API 破壞 / 假綠

| 檢查項 | 結果 |
|---|---|
| spec docs 變動（git diff vs baseline）| 無 |
| CLI command surface（`ait --help`）| 19 個命令一個都沒少 |
| `from ait.{memory,brain,report,db} import ...` | 所有 public symbol 仍可 import（M4 smoke test 已驗）|
| `from ait.memory_eval import ...` | shim 保留，`evaluate_memory_retrievals` 等仍可用 |
| `python -m ait.cli` / `python -m ait.cli_main` | 兩條入口都回 0.55.26 |
| `ait.cli.subprocess` / `ait.cli.shutil` / `ait.cli._installation_payload` 測試 patch surface | 全部仍可 patch |
| 假綠 / 寬鬆 assert | M4 smoke test 用 strict 結構（assertEqual 對 attempt id、source set） |
| 既有 384 → 386 tests | 1 條新加（refactor smoke）+ 可能 1 條補充；無關 disable / xfail |

---

## 測試結果與輸出摘要

```
$ .venv/bin/python -m pytest
=== 386 passed in 308.27s (0:05:08) ===
（含 tests/test_refactor_smoke.py 1 個新測試）

$ PYTHONPATH=src python3 -m unittest discover -s tests
Ran 386 tests in 307.33s
OK

$ python -m ait.cli --version            → ait 0.55.26
$ python -m ait.cli_main --version       → ait 0.55.26
$ rg "class MemoryRepository" src/        → 1 命中
$ rg "connect_db\s*\(" src/ait/memory/    → 2 命中
$ grep -c "if/elif args.command" cli/main.py → 0
$ rg "def _upgrade_payload|_upgrade_command" → 1 處 each (cli/upgrade.py)
$ rg "from ait\.app" src/ait/brain*       → 0 match
```

---

## Ship 建議

可以 ship 當前 HEAD 作為 0.56.0（或 0.55.27 minor patch）。CHANGELOG 建議列：

```
- Stage 4 architecture refactor complete: introduce MemoryRepository seam,
  split CLI into command-family package with dispatch table, split memory
  recall into focused modules, deduplicate cli upgrade helpers.
- New tests/test_refactor_smoke.py to prevent cross-process import drift.
- No CLI surface, SQLite schema, memory ranking, or daemon protocol changes.
```

Ship 前可一併處理（非 blocker）：
- L1：cli/__init__ + cli/_shared 改直接 import（≤ 5 行 diff）
- L2：把 `docs/code-review-stage4-refactor-2026-05-01.md` 進 HEAD（任務清單記錄保留）

---

## 誠信宣告

- 全程 read-only review，沒改任何 source / test / 既有 docs（除新增本份 acceptance 報告）
- 6 條 commit 都實際讀過 source，不是只看 diff（已讀 cli/main.py、cli/__init__.py、cli/upgrade.py、memory/repository.py、memory/recall.py、memory/search.py、memory/temporal.py、memory/render.py、memory/facts.py、memory_eval.py、cli_helpers.py、cli_main.py、tests/test_refactor_smoke.py）
- 兩套測試套件實機跑出 386 passed / 386 OK，task output file 留檔
- 實機跑 `python -m ait.cli --version`、`python -m ait.cli_main --version`、`importlib.import_module` 全套 36 個 module 確認無 circular import
- file:line 引用都來自實機 `wc -l` / `rg` / `grep -n` / `head` 真實輸出
- 不偽造、不假裝、不 fabricate
