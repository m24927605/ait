---
title: 為什麼用 ait
description: >-
  用白話說明 ait 存在的原因：AI coding agent 需要本機 attempts、明確 apply、
  跨 agent 交接、對抗式審查與 memory recall。
---

# 為什麼用 ait

AI coding agent 很有用，但它做過什麼很容易失去脈絡。

`ait` 給已經在用 Claude Code、Codex、Aider、Gemini CLI、Cursor CLI 或類似
工具的工程師一個本機紀錄：每次 run 都會在 repo 裡留下可審查、可復原的
attempt。

## 簡短版

沒有 `ait` 時，一次 agent run 通常只剩聊天紀錄，以及 working tree 裡被改過的
東西。

有 `ait` 時，一次 agent run 會變成一筆 attempt：

- 你問了什麼
- agent 改了什麼
- 另一個 agent 審查時發現什麼
- 哪些決定之後應該被記住
- 你有沒有明確 apply

Attempt 存在 repo 的 `.ait/` 裡。本機、沒有 telemetry、沒有 SaaS。

## 問題 1：下一個 agent 從零開始

昨天 Claude 查 bug，找到一個重要限制。今天 Codex 打開同一個 repo，因為有用
脈絡留在已關閉的 chat 裡，只好重查一次。

有 `ait` 時，下一個被包住的 agent 可以收到一份 handoff，來源包含先前
attempts、accepted facts、notes，以及 `CLAUDE.md`、`AGENTS.md`、
`.claude/memory.md`、`.codex/memory.md`、`.cursor/rules` 這類現場 memory 檔。

可以先跑 demo：

```bash
ait demo
```

也可以看：[痛點 demos](demos/pain-point-demos.md)。

## 問題 2：實作 agent 審自己的程式

Agent 做完後說測試都過了，這很有用，但不等於獨立審查。同一個模型、同一段
上下文，很可能在 review 時也漏掉同一種盲點。

有 `ait` 時，可以在 apply 前叫另一個 agent 審查 attempt：

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait review finding list --severity high
```

這不是正確性保證。它是一道獨立審查，並且把 finding 記下來。

## 問題 3：失敗 run 污染 working tree

Agent 被中斷、timeout，或做出高風險修改。沒有隔離時，你可能會留下很難判斷的
working tree 狀態。

有 `ait` 時，被包住的 run 會先落在隔離 workspace。Root checkout 不應該被改動，
直到你決定 apply：

```bash
ait apply latest
```

如果結果需要檢查：

```bash
ait recover latest
ait resume latest
```

## 問題 4：有用的決定消失

你曾經決定 retry budget 應該是三次。三週後，新 agent 提議改成五次，因為它
沒看到之前的理由。

有 `ait` 時，可以搜尋過去 attempts 與 repo memory：

```bash
ait memory recall "retry budget"
```

最後仍然由你判斷哪段脈絡該採用。`ait` 提供紀錄，不取代工程判斷。

## ait 不是什麼

`ait` 的範圍刻意很窄。

它不是：

- IDE plugin
- autocomplete engine
- hosted dashboard
- 跨機器同步服務
- Claude Code、Codex、Aider、Cursor、Cline 或 Git 的替代品
- AI reviewer 一定抓得到所有 bug 的證明

## 什麼時候值得用

當「失去 agent 脈絡」的成本高於「多一層 workflow」的成本時，就值得用 `ait`。

特別適合這些情境：

- 你會使用多個 agent CLI
- 你希望 apply/recover 是明確步驟，而不是直接污染 working tree
- 高風險修改想交給第二個 agent 先審
- 舊 prompt、diff、finding、decision 需要能查回來
- 你偏好 local-first metadata，而不是 SaaS provenance 工具

下一步：[開始使用](getting-started.md)。
