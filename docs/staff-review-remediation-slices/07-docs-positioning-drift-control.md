# Slice 07: Docs Positioning Drift Control

狀態：Ready for implementation
目標：讓 README、site docs、facts、package metadata、install examples 與 CLI reality 保持一致。

## Problem

Docs 已出現版本與能力漂移：site facts 仍寫 current release `1.1.x`，getting-started
pinned GitHub tag 是 `v1.2.0`，README 是 `v1.3.0`。部分 docs 提到的 command/flag
與 parser 不一致。這會讓新使用者照文件操作時遇到不存在或過期路徑。

## Objective

建立 docs drift control：

- 版本、install tag、package version 由單一檢查保護。
- Docs 裡的日常 commands 可以被 smoke 或 static validation。
- Public claims 必須對齊 alpha status、local-only、no SaaS、review limitations。
- JSON-LD/facts 不可硬編過期版本。

## Files To Change

- `README.md`
- `README.zh-TW.md`
- `site-docs/getting-started.md`
- `site-docs/facts.md`
- `docs/release-checklist.md`
- `tests/test_docs_drift.py` or equivalent new test
- optional docs generation helper

## Files Not To Change

- Core CLI implementation unless docs smoke reveals real command mismatch covered by another slice
- Release publish workflow except adding docs drift test command
- Transcript/reviewer/migration internals

## Design

Add docs drift tests:

1. Version consistency
   - `pyproject.toml` version
   - `npm/ait-vcs/package.json` version
   - README pinned tag
   - site getting-started pinned tag
   - facts current release text or generated metadata

2. Command existence
   - Extract fenced `bash` command snippets from primary quickstarts.
   - Validate `ait <subcommand> --help` exists for commands intended to be runnable.
   - Keep non-runnable examples marked with comments or placeholders.

3. Claim lint
   - Disallow unsupported phrases such as `guaranteed`, `production-ready`, `catches every bug`.
   - Require alpha/local-only limitations near strong claims.

4. JSON-LD consistency
   - Facts page should not hardcode stale `current release` text.

## Tests

Required tests:

1. `test_docs_versions_match_package_versions`
   - Fail on `1.1.x` vs `1.3.0` drift.

2. `test_docs_pinned_github_tags_match_version`
   - Fail if README/site pinned tags diverge.

3. `test_quickstart_ait_commands_exist`
   - Validate subcommands/options where feasible.

4. `test_public_claims_do_not_overstate_review_or_production_readiness`
   - Static lint with allowlist for quoted negative claims like "not a guarantee".

## Verification Commands

```bash
uv run pytest tests/test_docs_drift.py -q
uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py -q
```

Manual docs check:

```bash
rg "1\\.1|1\\.2\\.0|production-ready|guarantee|catches every" README.md README.zh-TW.md site-docs docs
```

## Acceptance

- README, site docs, facts, package metadata, and pinned install tags match current version.
- Docs no longer mention commands or flags absent from parser.
- Alpha/local-only/review limitation language is consistent.
- Drift tests are included in CI or release gate.

## Review Checklist

- Confirm docs changes do not make stronger product claims than current tests support.
- Confirm install examples are copy-pasteable.
- Confirm Traditional Chinese docs match English docs for warnings and limitations.
- Confirm docs drift test is not brittle on prose unrelated to install/claims.

## Rollback

Docs fixes can roll back independently, but keep drift tests once introduced.
If generated docs are added later, generated files must include a regeneration command.

