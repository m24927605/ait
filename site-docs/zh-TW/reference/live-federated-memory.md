# Live Federated Memory

AIT memory 有兩種來源：

- **AIT-owned memory**：存在 `.ait/`，包含 attempts、prompts、traces、
  commits、curated notes、accepted facts、review findings、apply/recover
  outcomes 與 context manifests。
- **Live external memory**：repo 內既有的 `CLAUDE.md`、`.claude/memory.md`、
  `.claude/CLAUDE.md`、`AGENTS.md`、`.codex/memory.md`、
  `.codex/AGENTS.md`、`.cursor/rules`、`.cursor/rules.md`、`.cursorrules`。

External files 仍是自己的 source of truth。AIT 會在 `ait memory recall`、
`ait run`、`ait review` 當下即時讀取它們，不會自動匯入 `.ait/`。

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

AIT 在寫入 run 或 review context artifact 時，也會在 `.ait/` 記錄 context
manifest，包含 source id、path、hash、mtime、bytes used 與 policy status。
Live external sources 是 advisory context，不是 AIT captured provenance。

## Mutating paths

`ait memory backfill --dry-run` 是 zero-write preview。`ait memory backfill
--import` 是明確 mutation/deprecated path：它會把 advisory memory 寫進
`.ait/`，但 live recall 不需要 import。
