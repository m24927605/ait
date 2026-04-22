# AGENT.md

## Working Rules

1. Commit by small, self-contained functionality. Do not bundle unrelated work into one commit.
2. Every commit message must include the referenced document file names and paths, plus explicit keywords.
   Required format:
   `docs:../path/to/a.md,../path/to/b.md keyword:xxxx,oooo`
3. Review the change three times before every commit.
4. If a refactor need is discovered, write or update the refactor document immediately so future refactoring has a clear basis.
5. If attention quality drops, notify the user explicitly.
6. Keep documents concise. Do not let documents grow too long; split them when necessary.
7. Do not guess before development. Verify the facts and relevant context first, then implement.
8. Do not lie, fabricate, or falsify. No fake results, no fake completion, no fake data.
9. Use SubAgents actively for parallel development when parallel work is beneficial and appropriate.
10. Do not over-expand scope. Follow the documents, keep moving by phase, and avoid endless work that blocks the next stage.

## Commit Checklist

Before commit:

1. Scope is limited to one small feature or one tight logical unit.
2. Related docs are identified and listed in the commit message.
3. Keywords are included in the commit message.
4. Review pass 1 completed.
5. Review pass 2 completed.
6. Review pass 3 completed.

## Documentation Rules

1. Prefer short, focused documents.
2. Split documents when a single file becomes hard to review or maintain.
3. When architecture or implementation changes imply later refactoring, record that explicitly in docs.

## Integrity Rules

1. Never claim tests ran if they did not.
2. Never claim a feature is complete if it is partial.
3. Never invent data, logs, outputs, or review results.
4. When uncertain, stop and verify.
