# Live Federated Memory Goal Prompt

Use this prompt with `/goal` when asking an AI coding agent to implement the
AIT live federated memory direction.

````text
/goal 請以 Staff+ Product、DevRel、Security/Trust、Docs、Open Source Maintainer、Senior Python Engineer 團隊視角，將 AIT memory 重新設計並落實為「Live Federated Memory」架構。

核心目標：
AIT 必須同時解決：
1. 單一 agent 的長期記憶
2. 跨 agent 的共同記憶
3. 跨 agent 的長期記憶
4. 記憶必須隨時即時，不依賴 import/backfill snapshot
5. read-only 操作必須 zero-touch，不寫 `.ait/`，不改來源檔

請不要把「把 CLAUDE.md / AGENTS.md / .cursor/rules 匯入 `.ait/`」當成主軸。這不是零干擾。正確方向是 live federation：AIT 在 run / review / recall 時即時讀取 repo-local live memory sources，並與 AIT-native memory 組合成同一份 repo memory view。

請先閱讀並遵守：
- `docs/live-federated-memory-design-zh.md`
- `docs/attempt-provenance-hardening-spec.md`

## 必須先釐清

1. AIT-native memory 是什麼：
   - attempts
   - prompts
   - traces/transcripts
   - changed files / commits
   - review findings
   - accepted facts
   - apply/recover outcomes
   - run/review context manifests

2. Live external memory sources 是什麼：
   - `CLAUDE.md`
   - `.claude/memory.md`
   - `.claude/CLAUDE.md`
   - `AGENTS.md`
   - `.codex/memory.md`
   - `.codex/AGENTS.md`
   - `.cursor/rules`
   - `.cursor/rules.md`
   - `.cursorrules`

3. 原則：
   - external memory sources are source of truth
   - AIT must read them live
   - AIT must not auto-import them
   - read-only commands must not create or mutate `.ait/`
   - adoption/materialization must be explicit and clearly documented as mutation
   - global or out-of-repo memory must require explicit `--global --path`
   - no hidden network calls
   - no fake provenance

## 實作目標

請分階段實作：

### Phase 0: Correct semantics

- 停止把 `.ait/` writes 稱為 zero-interference
- 停止在 `ait init` / `ait run` 自動 import external agent memory
- `ait memory backfill --import` 若保留，必須標成 mutation 或 deprecated
- 更新 CLI help / README / website docs，清楚區分：
  - zero-touch read
  - AIT-local mutation
  - source mutation

### Phase 1: Live source discovery

新增 read-only 指令：

```bash
ait memory sources
ait memory sources --format json
ait memory sources --source claude
ait memory sources --include-docs
ait memory sources --global --path <explicit-path>
```

要求：
- default 不寫 `.ait/`
- default 不掃 global memory
- 可在未 `ait init` 的 repo 中使用
- 輸出 source id、path、agent/source kind、hash、mtime、size、policy result、skip reason
- unsafe symlink / path traversal 要拒絕

### Phase 2: Federated recall

改造 `ait memory recall`：
- default read-only，不寫 `.ait/`
- 即時讀 live external memory sources
- 組合 AIT-native memory（若 `.ait/` 存在）
- 第二次 recall 必須看到 source file 最新內容，不需 import
- 可選 `--record` 才寫 retrieval evidence 到 `.ait/`

### Phase 3: Run / review live context

- `ait run` / `ait review` 在執行時即時組合 live sources + AIT-native memory
- 寫入 AIT_CONTEXT_FILE 是 run/review artifact，可以存在 `.ait/`
- attempt/review evidence 必須記錄 context manifest：
  - source id
  - path
  - hash
  - mtime
  - bytes used
  - policy status
- 不得把 live external memory 表示成 captured AIT provenance

### Phase 4: Cache/index only if safe

若需要 cache/index：
- 必須可重建
- 不是 source of truth
- hash/mtime 改變時必須 invalidated 或 read-through
- read-only commands default 不更新 cache

### Phase 5: Explicit adoption/materialization

若需要把外部 memory 轉成 AIT-owned memory，請新增或設計明確指令：

```bash
ait memory adopt CLAUDE.md
ait memory materialize --source codex AGENTS.md
```

要求：
- 必須明確說明會寫 `.ait/`
- 不改來源檔
- 不得稱為 zero-touch
- 記錄原始 source path/hash/mtime
- 標成 adopted_external，不得偽裝為 AIT captured provenance

## 測試與驗收

請新增/更新測試，至少覆蓋：

1. `ait memory sources` 不建立 `.ait/`
2. `ait memory recall` default 不寫 `.ait/`
3. live source 修改後，下一次 recall 立刻看到新內容
4. `CLAUDE.md` / `AGENTS.md` / `.cursor/rules` 可同時被 federated recall 看見
5. default 不掃 global memory
6. `--global --path` 才能讀 repo 外來源
7. policy-blocked source 不會進 context
8. redaction 在 context output 前發生
9. unsafe symlink / path traversal 被拒絕
10. `ait run` / `ait review` 會記錄 context manifest
11. old `.ait/` memory notes 仍可搜尋，不做破壞性 migration
12. `backfill --import` 若保留，必須有 mutation/deprecation warning 測試

## Code review 標準

請把以下視為 blocking findings：

- read-only command 寫 `.ait/`
- `ait init` 或 `ait run` auto-import external memory
- 修改 `CLAUDE.md` / `AGENTS.md` / `.cursor/rules`
- default 掃 global memory
- cache stale 仍被當 live memory
- policy-blocked memory 被注入 context
- external memory 被標成 captured AIT provenance
- 缺少 zero-write 測試
- 隱藏 network call

## 驗證

完成後執行：

```bash
git diff --check
PYTHONPATH=src .venv/bin/pytest tests/test_memory.py tests/test_memory_security.py -q
PYTHONPATH=src .venv/bin/pytest tests/test_live_memory_sources.py tests/test_federated_recall.py -q
PYTHONPATH=src .venv/bin/pytest tests/test_cli_run.py tests/test_review_prompt.py -q
/tmp/ait-docs-venv/bin/mkdocs build --strict --site-dir /tmp/ait-site-build
```

如果 `.venv` 或 docs venv 不存在，請使用專案既有方式建立，但不要 commit `uv.lock`、不要 commit `site/`、不要覆蓋 unrelated user changes。

## 完成後回報

請回報：
- 最終 memory 架構
- 哪些 commands 是 zero-touch
- 哪些 commands 會寫 `.ait/`
- 如何保證 live / 即時
- 如何支援單 agent 長期記憶
- 如何支援跨 agent 共同記憶
- 如何支援跨 agent 長期記憶
- 修改了哪些檔案
- 測試與 docs build 結果
- residual risks
````
