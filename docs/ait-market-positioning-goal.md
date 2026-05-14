# /goal Prompt: Reposition AIT With A Sharper Market Narrative

請以 Staff+ Product Marketing、DevRel、Docs、Growth、Security/Trust、Open Source Maintainer 團隊視角，重新推導 AIT 的市場定位，並把 README / website hero 更新到足夠吸睛、但完全符合 AIT 事實的版本。

核心要求：不要沿用「AI coding agent 的 Git 安全工作層」、「Git workflow layer」、「開發沙盒與交接系統」這類已經不夠吸睛或太像 infra label 的定位。請跳脫原本想法，重新從 AIT 真正解決的痛點、功能組合、使用者焦慮與差異化切入。

請先做定位研究與討論，再實作文件修改。

## 必須先釐清

### 1. AIT 到底解決什麼高痛點？

- AI agents 會直接修改真實 repo
- failed / partial runs 會污染工作目錄
- prompt、diff、commits、review evidence 難以追溯
- Claude / Codex / Cursor / Aider / Gemini 之間沒有可靠交接
- 多 agent 平行開發會互踩
- agent 自稱修好但缺少 review gate
- 團隊不想把 repo metadata 送到 SaaS

### 2. AIT 實際提供什麼？

- isolated attempts / worktree isolation
- root checkout untouched until explicit apply
- attempt provenance
- shared repo-local memory
- long-term memory
- cross-agent handoff
- parallel attempts
- adversarial review / review-gated apply
- queryable prompt and attempt history
- local-first `.ait/`, no telemetry, no SaaS dashboard

### 3. AIT 的真正特色不是單點功能，而是組合

- isolated attempts
- provenance
- memory
- multi-agent handoff
- review gate
- explicit apply/recover
- local-first trust model

## 目標

推導出一個更吸睛、更有市場張力、更適合 README / website hero 的定位。

定位必須：

- 讓 first-time developer 立刻覺得「這就是我讓 Claude/Codex 改真實 repo 時需要的東西」
- 比「Git safety layer」更有畫面
- 比「sandbox」更完整
- 比「control plane」更不抽象
- 不誇大，不說 AIT 保證 AI 寫對
- 不讓 adversarial review 壓過主軸
- 明確表達 AIT 是包在既有 agent CLI 外面，不是另一個 agent，也不是 Git replacement
- 能同時支撐英文與繁中自然文案

## 請先產出定位推導

請在修改文件前，先用文件或工作筆記整理：

1. Staff team discussion
2. AIT solved problems
3. AIT capabilities
4. AIT differentiators
5. 不採用哪些定位，以及原因
6. 至少 10 個候選定位
7. 每個候選定位評分：
   - 吸睛程度
   - 事實準確度
   - 記憶點
   - first-time clarity
   - 是否能延展到 README / website / social launch
8. 最終推薦 1 個主定位、2-3 個 secondary lines
9. 中文與英文對應版本

## 實作範圍

根據最終定位，更新：

- `README.md`
- `README.zh-TW.md`
- `site-docs/index.md`
- `site-docs/zh-TW/index.md`
- `mkdocs.yml`
- `site-docs/llms.txt`
- 必要時同步 `site-docs/why-ait.md`
- 必要時同步 `site-docs/zh-TW/why-ait.md`
- 必要時同步 marketing docs，但不要做無關大改

## 文案要求

英文：

- concrete, sharp, developer-native
- avoid vague "AI-powered"
- avoid generic infra phrasing
- avoid overclaiming
- memorable enough for README hero / Show HN / GitHub stars

繁中：

- 面向台灣工程師，自然、直接、有產品感
- 不要逐句翻譯英文
- 可以保留 attempt、apply、recover、review gate、provenance、memory 等技術詞
- 避免「用 AI agent 寫 code」這類不自然表述

## 驗證

完成後執行：

```bash
git diff --check
```

並執行 docs build。若沒有全域 `mkdocs`，使用：

```bash
python3 -m venv /tmp/ait-docs-venv
/tmp/ait-docs-venv/bin/python -m pip install -q mkdocs-material mkdocs-static-i18n
/tmp/ait-docs-venv/bin/mkdocs build --strict
```

## 約束

- 不要 commit `uv.lock`
- 不要覆蓋 unrelated user changes
- 不要 commit 生成的 `site/`
- 不要改產品行為，除非文件揭露明顯錯誤指令

## 完成後回報

請回報：

- 最終市場定位
- 為什麼它比原本定位更吸睛
- 它如何符合 AIT 事實
- 修改了哪些檔案
- 英文與繁中文案品質說明
- adversarial review 是否保持為亮點但不壓過主軸
- memory / long-term memory 如何被呈現
- 驗證結果
- residual risks
