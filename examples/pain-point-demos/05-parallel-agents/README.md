# 05 - Parallel Agents

## Pain

Claude Code and Codex cannot safely edit the same root working copy at the
same time without coordination.

## Demo

Open two terminal sessions in `~/lab/ait-pain-demo`.

Session A:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Claude: parallel approach A" \
AIT_COMMIT_MESSAGE="claude approach A" \
claude -p --permission-mode bypassPermissions \
  "Create approach.txt containing only A. Do not run git commands."
```

Session B:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Codex: parallel approach B" \
AIT_COMMIT_MESSAGE="codex approach B" \
codex "Create approach.txt containing only B. Do not run git commands."
```

## Proof

```bash
ait attempt list --limit 6
git status --short -- approach.txt
```

Expected result: both attempts exist independently, and root has no
`approach.txt` until you explicitly promote one attempt.

