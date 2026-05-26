# Slice 04: Recovery Apply Mental Model

狀態：Ready for implementation
目標：收斂 `apply/recover/resume/continue` 的下一步指令、attempt handle 與 workspace 心智模型。

## Problem

AIT 已有 `a1/a2` handle，但部分 decision report 仍輸出 full canonical attempt id。
`recover` 的 next steps 偏 `apply/debug`，`resume` 的完成流程要求使用者手動
`git add`、`ait attempt commit`、`ait apply`。對使用者而言，attempt、workspace、
recoverable、applied、held、conflicted 的邊界仍過於複雜。

## Objective

讓 recovery/apply path 達到：

- Human output 一律使用 attempt handle。
- JSON 同時保留 canonical id 與 handle。
- 每個狀態只給一個 primary next step。
- `resume` 提供明確 finish command，降低手動 commit/apply 步驟。
- `continue`、`recover`、`resume` 的文案一致。

## Files To Change

- `src/ait/landing.py`
- `src/ait/recovery.py`
- `src/ait/resume.py`
- `src/ait/continue_flow.py`
- `src/ait/cli/recover.py`
- `src/ait/cli/resume.py`
- `src/ait/cli/continue_cmd.py` or equivalent continue CLI module
- `tests/test_landing.py`
- `tests/test_cli_recover.py`
- `tests/test_cli_resume.py`
- `tests/test_cli_continue.py`

## Files Not To Change

- Transcript persistence
- Release workflows
- Reviewer adapter environment
- DB schema unless required by handle lookup bug

## Design

State-to-action contract:

| State | Primary human next step | Secondary debug |
| --- | --- | --- |
| succeeded/apply-ready | `ait apply a1` | `ait attempt show a1` |
| held by dirty overlap | `ait recover a1` | `ait recover a1 --debug` |
| interrupted workspace | `ait resume a1` | `ait recover a1 --debug` |
| review required | `ait review attempt a1` | `ait apply a1 --debug` |
| conflicted integration | `ait resume a1` or integration handle | `ait recover a1 --debug` |
| already applied | `ait cleanup --apply` | none |

Human output should not require users to copy workspace paths by default.
`--debug` may show workspace and lease details.

## Resume Finish Design

Preferred option:

- Add `ait resume --finish a1` or `ait resume a1 --finish`.
- It runs the safe finish sequence:
  - verify current directory is the attempt workspace or use recorded workspace
  - stage changes in attempt workspace
  - commit with deterministic message or user-provided `-m`
  - return to repo root
  - run `ait apply a1` or print next step if apply is blocked

If full automation is too risky in this slice, add `ait resume a1 --finish-plan`
as an intermediate human-readable command, then implement finish in a follow-up.

## Tests

Required tests:

1. `test_apply_held_next_step_uses_handle`
   - Held apply output says `ait recover a1`, not full id.

2. `test_recover_next_step_matches_state`
   - Interrupted attempt recommends `ait resume a1`.

3. `test_resume_no_interactive_hides_workspace_by_default`
   - Default text does not force copying long workspace path.
   - `--debug` still exposes path.

4. `test_continue_no_interactive_uses_handle`
   - Continue text suggests `ait resume a1` or native attach with consistent labels.

5. `test_resume_finish_commits_and_applies_or_reports_blocker`
   - If implementing finish automation.

6. `test_json_contains_attempt_id_and_handle`
   - Machine output keeps canonical id.

## Verification Commands

```bash
uv run pytest tests/test_landing.py tests/test_cli_recover.py tests/test_cli_resume.py tests/test_cli_continue.py -q
uv run pytest tests/test_agent_first_workflow.py -q
```

## Acceptance

- All human next steps use handles where available.
- No default recovery output asks users to reason about full internal workspace paths.
- Every blocked state has one primary command and optional debug command.
- JSON/debug retains enough detail for automation and support.
- Existing apply safety gates remain unchanged.

## Review Checklist

- Search for `ait recover {attempt_id}`, `ait resume {attempt_id}`, `ait apply {attempt_id}` in human text paths.
- Confirm all replacements use handle only for human output.
- Confirm JSON tests still expose canonical id.
- Confirm no apply safety check was weakened to improve UX.

## Rollback

Human output changes can roll back independently. If `resume --finish` is added,
keep the command but make it print a safe finish plan rather than deleting it.

