# AIT Local Multi-Agent Session Room 設計

Status: proposed design, implementation plan, test acceptance, and code review standard
Owner: AIT Staff+ Product, Platform Architecture, DevRel, Security/Trust,
Docs, Open Source Maintainer, and Senior Python Engineering Team
Scope: local multi-agent session coordination for Claude Code, Codex, Aider,
Gemini, Cursor, shell agents, and future local agent adapters.

本文是設計文件，不代表功能已存在。除非後續 phase 明確要求，本文不要求實作
production code。

Implementation note:

- `ait session start/ask/show/list/responses/export` now has a repo-local
  `.ait/sessions/` JSON artifact store.
- `ait session run --mode panel|council|sequential` supports real local adapter
  invocation for active participants, plus local fake agents and explicit local
  command participants for deterministic fan-out, attribution, timeout/cancel
  simulation, retry, redaction, and per-agent context manifests. The default
  real paths use non-interactive advisory commands where AIT knows them
  (`claude -p --permission-mode plan`, `codex exec --sandbox read-only -`).
  Codex CLI 0.130 removed `--ask-for-approval`, so AIT stores the consented
  Codex approval policy as session metadata instead of passing a removed flag.
- Real adapter invocation uses the session's consented permission policy:
  `--claude-permission-mode`, `--codex-sandbox`, and `--codex-approval` are
  captured at `ait session start` and reused for later panel/council turns.
- `ait session run --mode role` currently has isolated attempt/review linkage
  scaffold, but the implementer path still uses a deterministic shell fixture
  instead of invoking the requested external agent. Real implementer/reviewer
  adapter invocation for Role Mode is a P0 gap tracked in
  [`multi-agent-session-ux-optimization-plan-zh.md`](multi-agent-session-ux-optimization-plan-zh.md).
  Do not present Role Mode as production-ready Claude/Codex role invocation
  until that plan lands.
- `ait session attempt --from <response-id>` turns an advisory response into a
  new isolated attempt without applying it.
- `ait session decision --accept <response-id> --promote-memory` promotes an
  accepted session decision through an explicit accepted memory fact gate.
- `participant add/remove/list`, split implementation overlap detection, and
  adaptive allocation dry-run are implemented as local session orchestration
  primitives.
- This implementation remains additive. Existing `ait run`, `ait review`,
  `ait apply`, and `ait recover` remain the authoritative mutation/review gate
  paths.
- Interactive terminal / PTY orchestration is specified separately in
  [`local-multi-agent-terminal-orchestration-design-zh.md`](local-multi-agent-terminal-orchestration-design-zh.md).

## Executive Summary

AIT 可以成為本機 multi-agent session room：

> AIT can become a local multi-agent session room: Codex and Claude Code can
> work in the same user-facing session, while each agent response, attempt,
> context, evidence, and responsibility remains isolated, attributable,
> reviewable, and gated before it changes the repo.

繁中定位：

> AIT 可以成為本機 multi-agent session room：使用者在同一個 session 裡和
> Codex、Claude Code 一起討論與開發，但每個 agent 的發言、修改、證據與責任
> 歸屬都被 AIT 分開記錄，最後仍透過 review/apply gate 落地。

核心產品界線：

- AIT 不是新的 AI agent。
- AIT 不是 SaaS chat，也不是 dashboard。
- AIT 不讓 agents 無限制互相聊天。
- AIT 不因多個 agent 同意就自動 apply。
- AIT 是 local-first、repo-local、attempt-first 的 session coordinator。

核心技術方向：

```text
one user-facing session
  -> many isolated participant responses
  -> optional isolated attempts
  -> attributable evidence
  -> explicit decision
  -> existing review/apply/recover gate
```

每個 agent 的輸出都應保留自己的 provenance。每個可能修改 repo 的行為都應回到
既有 attempt isolation，而不是在 session transcript 裡直接改 root checkout。

### 先釐清

這不是：

- 不是 Google Docs / Notion 式即時多人共筆。
- 不是 SaaS dashboard。
- 不是 Git replacement。
- 不是新的 AI agent。
- 不是讓 Claude/Codex 直接互相無限制聊天。
- 不是自動 apply 多 agent 共識。

這是：

- AIT 作為 local session coordinator。
- 使用者在同一個 session 裡發出任務或問題。
- AIT 將同一輪 user input、live federated memory、repo state、prior
  session turns 分發給多個 agent。
- 每個 agent 產生獨立 response / proposal / attempt / review。
- AIT 聚合成 user-facing transcript。
- 每個 agent output 都保留 provenance。
- 任何 repo mutation 都仍然走 isolated attempt + review/apply gate。

需要支援的模式：

- Panel Mode：Claude / Codex / Aider 等各自回覆，AIT 並列顯示與摘要。
- Role Mode：例如 Claude implement、Codex review、AIT gate apply。
- Council Mode：多 agent 對同一問題提出觀點，AIT 彙整共識、衝突與下一步。
- Optional Sequential Mode：一個 agent 的輸出成為下一個 agent 的 advisory
  context。

必須維持的 AIT 信任模型：

- local-first。
- repo-local metadata。
- no hidden network。
- no SaaS dependency。
- no telemetry。
- root checkout untouched until explicit apply。
- external agent memory remains source of truth。
- live federated memory is read live, not auto-imported。

## 1. Product Framing

### 使用者痛點

今天使用者可以同時使用 Claude Code、Codex、Aider、Gemini 或 Cursor，但協作
通常發生在多個 terminal、不同 session、不同 transcript 與不同記憶系統中。
常見問題是：

- 使用者要手動複製 prompt、diff、錯誤與結論。
- Claude 的建議和 Codex 的審查缺少共同 session trace。
- 不同 agent 的建議容易混在一起，事後看不出誰說了什麼。
- 一個 agent 產生 patch，另一個 agent 審查時缺少 attempt provenance。
- 多 agent 討論容易變成「誰比較有說服力」，而不是可審核的 evidence。
- 如果多個 agent 同時動手，沒有 coordinator 時很容易覆蓋同一個 checkout。

AIT 已經有 isolated attempts、attempt provenance、live federated memory、
review gate、explicit apply/recover、本機 `.ait/` metadata、no SaaS/no
telemetry 的產品邊界。Local multi-agent session room 是把這些能力提升到
session 層，而不是引入新的雲端協作產品。

### 為什麼單一 agent session 不夠

單一 agent session 很適合連續實作，但它有幾個天然限制：

- 實作者和審查者是同一個模型或同一份上下文時，容易合理化自己的決策。
- 不同模型擅長不同工作：一個適合規劃，一個適合補測試，一個適合 code review。
- 使用者想比較多個方案時，需要並列看法、衝突點與 evidence，而不是只看單一
  agent 的最終回答。
- 單一 transcript 很難把「已接受決策」、「agent opinion」、「外部 memory
  文字」和「AIT captured evidence」分清楚。

### 為什麼多 agent 需要 AIT coordinator

多 agent 不是只要開多個 terminal。需要 coordinator 的原因是信任邊界：

- AIT 能給每個 agent 分開的 context file 與 context manifest。
- AIT 能保存每個 response 的 prompt、stdout/stderr、exit code、adapter、role、
  policy result、redaction status 與 source references。
- AIT 能把可能修改 repo 的工作放進各自 attempt workspace。
- AIT 能把 reviewer 輸出連到 target attempt，而不是讓 reviewer 默默改同一個
  workspace。
- AIT 能把 session decision 記為明確的人類或工具決策，再決定是否進入 memory
  fact 或 apply gate。

### 如何延伸既有 AIT 能力

Local multi-agent session room 不取代既有 workflow，而是增加 session-level
coordination：

| Existing AIT substrate | Session room extension |
| --- | --- |
| Intent | Session 可以建立或引用一個 root intent。 |
| Attempt | Role Mode 的 implementer response 可以產生 isolated attempt。 |
| Attempt provenance | 每個 agent response/proposal 有自己的 provenance。 |
| Live federated memory | 每輪 fan-out 讀 live memory，並寫 per-agent context manifest。 |
| Review gate | Reviewer response 連到 target attempt，apply 前仍由 review gate 判斷。 |
| Explicit apply/recover | Session decision 不等於 apply；apply 仍是明確動作。 |
| `.ait/` metadata | Session transcript、manifest、decision、summary 都存在 repo-local `.ait/`。 |

### 與多人協作、shared memory、長期記憶的關係

此能力不是 Google Docs / Notion 式多人共筆，也不是所有 agent 共用一份長期
記憶。正確關係是：

- 使用者在同一個 AIT session 裡協調多個 local agent。
- Live federated memory 仍在每次需要 context 時即時讀取。
- 外部 agent memory 保持 source of truth，不自動 import。
- Session transcript 是 AIT-native evidence，但 agent opinion 預設是
  advisory，不是 trusted fact。
- 只有明確接受的 session decision 才能透過 memory gate promote 成 accepted
  memory fact。

## 2. Scope And Non-Goals

### In Scope

- Local session coordinator for multiple existing agent CLIs.
- Same user-facing session with separate agent responses.
- Panel Mode, Role Mode, Council Mode, and optional Sequential Mode.
- Per-agent context generation and context manifests.
- Per-agent stdout/stderr capture, transcript storage, cancellation, timeout,
  partial failure, and retry records.
- Session decisions that link to response ids, proposal ids, attempts, reviews,
  memory facts, and source manifests.
- Optional attempt creation from a selected response or role.
- Review/apply gate integration for repo mutations.
- JSON-first machine-readable state for agent loops and tooling.
- Deterministic markdown export after redaction.

### Out Of Scope

- SaaS chat, hosted dashboard, web sync, account system, or telemetry.
- Google Docs / Notion style collaborative editing.
- Replacing Git, PRs, branches, commits, or merge conflict semantics.
- Building a new coding agent.
- Letting Claude, Codex, or other agents chat with each other without user or
  policy-bounded orchestration.
- Automatic apply based on multi-agent consensus.
- Semantic merge conflict resolution.
- Global agent memory scanning by default.
- Importing external memory into `.ait/` without explicit adopt/materialize.

### 不承諾的事情

- 不保證多 agent 共識代表程式正確。
- 不保證 reviewer agent 找出所有 bug。
- 不保證所有 agent CLI 都支援 streaming、interactive 或 structured output。
- 不保證不同 provider 的模型行為可重現。
- 不承諾 cross-machine session sync。
- 不承諾 session transcript 可安全公開；必須先 redaction 與明確 export。

### 不應出現在 Marketing Copy 的 Overclaims

避免這些說法：

- "Autonomous multi-agent team that ships code for you."
- "Consensus-based auto-merge."
- "Shared brain for all coding agents."
- "Guaranteed safer code."
- "Realtime collaborative AI workspace."
- "Cloud control plane for local agents."

可接受說法應強調 local、attributable、isolated、reviewable、gated。

## 3. UX Modes

### Panel Mode

使用場景：

- 使用者想同時問 Claude、Codex、Aider 對同一問題的看法。
- 使用者想比較重構策略、安全風險、測試策略或錯誤診斷。
- 預設不產生 repo mutation，只產生 advisory responses。

CLI 草案：

```bash
ait session start "Refactor auth retry" --agents claude-code,codex
ait session ask latest "What is the safest approach?"
ait session run latest --mode panel
ait session panel latest
```

Transcript 草案：

```text
Session ses_01H...
Turn 3: user
  What is the safest approach?

[claude-code][response rsp_01H...][advisory][completed]
  建議先抽出 retry policy，再補 integration tests。
  Evidence: docs/auth.md, prior attempt att_...

[codex][response rsp_01H...][advisory][completed]
  風險在 backoff 和 token refresh 交互，先加 failing test。
  Evidence: src/auth/retry.py, review finding revf_...

AIT summary:
  Agreement: 先補測試，避免直接改 token refresh。
  Conflict: Claude 建議先抽 abstraction；Codex 建議先寫 failing test。
  Next: choose a response, ask follow-up, or create isolated attempt.
```

Provenance：

- 每個 response 有 `response_id`、`session_id`、`turn_id`、`participant_id`。
- 記錄 adapter、role、command、exit code、stdout/stderr refs、raw/redacted
  transcript refs、context manifest ref。
- AIT summary 是 derived artifact，必須連到 source response ids。

Attempt 行為：

- Panel Mode 預設只產生 advisory response，不產生 attempt。
- 若使用者執行 `ait session attempt latest --from <response-id>`，才建立
  isolated attempt。
- 若某 agent CLI 本身會動手，Panel Mode 必須在 read-only/advisory adapter
  policy 下執行，或轉成 explicit attempt。

避免 context 污染：

- Fan-out 時每個 agent 收到同一輪 user input、相同 trusted baseline、自己的
  role brief。
- 同一輪內 agent 不看其他 agent 尚未完成的 response。
- 下一輪若包含 prior responses，必須標成 `advisory_response` 並保留 attribution。

### Role Mode

使用場景：

- 使用者想讓 Claude 實作、Codex 審查、AIT 決定是否可 apply。
- 使用者想把 producer 與 reviewer 分開，避免自審。
- 高風險路徑需要 role-specific context。

CLI 草案：

```bash
ait session run latest --mode role \
  --implementer claude-code \
  --reviewer codex

ait session decision latest --accept <response-id>
ait apply <attempt-id>
```

Transcript 草案：

```text
Turn 4: user
  Implement auth retry with tests.

[claude-code][role=implementer][attempt att_01H...][completed]
  Changed 3 files, tests added.
  Result: attempt ready for review.

[codex][role=reviewer][review rev_01H...][completed]
  Finding: missing test for expired refresh token retry.
  Status: blocked

AIT gate:
  Apply blocked by review finding revf_01H...
  Safe next actions: recover attempt, ask implementer to fix, override with reason.
```

Provenance：

- Implementer output links to attempt id, workspace ref, commits, changed files,
  prompt ref, context manifest.
- Reviewer output links to target attempt id, target head, baseline snapshot,
  review findings, policy hash, reviewer context manifest.
- AIT gate output links to review status and apply blocking reasons.

Attempt 行為：

- Implementer role normally creates an isolated attempt.
- Reviewer role does not mutate repo by default.
- Reviewer may create a separate review attempt only if explicitly configured,
  and it must not write the implementer workspace.

Advisory response：

- Reviewer comments, risk analysis, and design critique are evidence, not repo
  mutation.
- A reviewer fix suggestion becomes a new implementer attempt only after explicit
  user/session decision.

避免 context 污染：

- Implementer receives implementation baseline and task.
- Reviewer receives target diff, tests, policy, prior failures, accepted facts,
  and risk context, not the implementer chain-of-thought or self-justification.
- Reviewer cannot silently modify target workspace.

#### Role Mode Variant: Split Implementation

Different agents can split implementation work, but they must not share a
writable checkout. AIT should model split work as explicit work packages:

```bash
ait session run latest --mode role \
  --implementer claude-code:backend \
  --implementer codex:tests \
  --reviewer codex \
  --package backend=src/auth/** \
  --package tests=tests/auth/**
```

Rules:

- Each implementer receives a scoped work package, role brief, and per-agent
  context manifest.
- Each implementer creates its own isolated attempt workspace.
- Work package boundaries are advisory and policy-enforced where feasible, but
  AIT must still detect overlap after execution.
- If attempts touch disjoint files, AIT can create an integration plan or
  integration attempt.
- If attempts overlap, AIT must hold and ask for an explicit integration
  decision; it must not silently merge competing agent changes.
- Reviewer roles review each implementation attempt and the final integration
  attempt separately.
- Apply remains explicit and gated after integration.

Split implementation is useful for backend/frontend, implementation/tests,
docs/code, or migration/runtime separation. It is not a shared multi-agent
editing surface.

#### Role Mode Variant: Adaptive Work Allocation

AIT can recommend adaptive work allocation, but it should be explainable and
policy-bounded. The goal is not to make AIT a manager agent; the goal is to use
local evidence to draft a work package plan that the user can accept, edit, or
reject.

CLI 草案：

```bash
ait session allocate latest \
  --strategy adaptive \
  --agents claude-code,codex,aider \
  --dry-run

ait session allocation accept latest --plan <allocation-plan-id>
ait session run latest --mode role --allocation <allocation-plan-id>
```

Adaptive allocation inputs:

- User goal and accepted session decisions.
- Repo state, touched-file history, hot files, and ownership hints.
- Live federated memory after policy and redaction.
- Prior attempt outcomes, review findings, failed attempts, and test evidence.
- Agent adapter capabilities, configured roles, known interactive/non-interactive
  behavior, and local availability.
- Work package constraints from user flags or repo policy.
- Risk model signals such as sensitive paths, dependency changes, migrations,
  test gaps, and overlap risk.

Allocation output:

- Proposed work packages.
- Recommended agent per package.
- Why that agent was selected.
- Files/path scope and expected outputs.
- Required reviewer role, if any.
- Overlap and dependency risks.
- Safe next command.
- Blocking reasons if allocation is unsafe.

Rules:

- Adaptive allocation produces an `AllocationPlan`; it does not invoke agents or
  mutate repo unless explicitly accepted and run.
- The plan must be deterministic enough to review: inputs, scoring factors, and
  selected constraints are recorded.
- Agent performance scores must be repo-local and evidence-based; no telemetry
  or global ranking service.
- User constraints override adaptive scoring.
- If confidence is low, AIT should ask for a human decision instead of inventing
  ownership.
- Rebalancing is allowed only between turns or after cancellation; AIT must not
  move a running agent's active workspace to another agent.

### Council Mode

使用場景：

- 架構決策、API design、安全 tradeoff、migration plan。
- 使用者需要多個觀點、共識、衝突與 recommendation。
- 預設不改 repo。

CLI 草案：

```bash
ait session run latest --mode council \
  --agents claude-code,codex,aider \
  --question "Should auth retry live in middleware or client?"

ait session summarize latest
ait session decision latest --accept <summary-id>
```

Transcript 草案：

```text
Council question:
  Should auth retry live in middleware or client?

[claude-code][architecture]
  Middleware gives central policy but risks hiding client-specific errors.

[codex][security/review]
  Client-level retry is easier to test and avoids retrying non-idempotent flows.

[aider][implementation]
  Existing code has retry hooks near client; minimal change is client-level.

AIT council summary:
  Consensus: avoid broad middleware retry for auth.
  Conflict: central policy vs local testability.
  Recommended next step: implement client-level retry behind explicit policy.
  Decision status: proposed, not accepted.
```

Provenance：

- Each council response is independent.
- Summary stores source response ids and summary algorithm/version.
- Decision remains proposed until accepted.

Attempt 行為：

- No attempt by default.
- A decision can spawn a follow-up attempt with `ait session attempt latest
  --from <decision-id> --agent claude-code`.

Advisory response：

- Council opinions are advisory evidence.
- Consensus is not a trusted fact until user accepts it through session decision
  and optional memory promotion.

避免 context 污染：

- Same-round council participants do not see each other.
- Optional second-round "respond to conflicts" must pass only attributed,
  redacted summaries, not raw untrusted instructions.

### Optional Sequential Mode

使用場景：

- 使用者想讓一個 agent 的 output 成為下一個 agent 的 advisory context。
- 例如 Claude 先提出 plan，Codex 以 reviewer 身份挑戰，Aider 只看 accepted
  plan 執行。

CLI 草案：

```bash
ait session run latest --mode sequential \
  --sequence claude-code:plan,codex:review,aider:implement
```

Transcript 草案：

```text
Step 1 [claude-code:plan][response rsp_plan]
  Plan proposed.

Step 2 [codex:review][response rsp_review]
  Uses advisory context: rsp_plan summary.
  Blocks two risky assumptions.

Step 3 [aider:implement][attempt att_impl]
  Uses accepted decision: dec_...
  Does not receive raw reviewer prompt as instruction.
```

Provenance：

- Every step records input context refs and upstream advisory response refs.
- Derived context must distinguish `trusted_baseline`, `accepted_decision`, and
  `advisory_response`.

Attempt 行為：

- Only steps with role permission `can_create_attempt=true` create attempts.
- Planning/reviewing steps normally remain advisory.

避免 context 污染：

- Upstream response enters downstream context only as attributed advisory
  summary or accepted decision.
- Any instruction-like text from another agent is quoted as evidence, not
  system/user instruction.

## 4. Data Model

The session model should be additive. Existing attempts, reviews, memory facts,
and apply/recover flows remain source systems for repo mutation and trust gates.

### Storage Under `.ait/`

Recommended storage layout:

```text
.ait/
  sessions/
    index.jsonl
    <session-id>/
      session.json
      turns/
        <turn-ordinal>-turn.json
      responses/
        <response-id>.json
      proposals/
        <proposal-id>.json
      decisions/
        <decision-id>.json
      summaries/
        <summary-id>.md
        <summary-id>.json
      contexts/
        <turn-id>-<participant-id>.md
        <turn-id>-<participant-id>-manifest.json
      transcripts/
        <response-id>.stdout.txt
        <response-id>.stderr.txt
        <response-id>.redacted.md
      events.jsonl
```

Longer-term implementation may also add SQLite tables for query performance,
but the canonical artifact refs should stay inspectable and recoverable under
`.ait/sessions/`.

### Session

Required fields:

- `id`
- `schema_version`
- `repo_id`
- `title`
- `description`
- `state`
- `default_mode`
- `created_at`, `updated_at`, `closed_at`
- `created_by_actor`
- `root_intent_id`
- `participants`
- `turn_count`
- `current_turn_id`
- `policy_ref`
- `redaction_policy_ref`
- `summary_ref`
- `metadata_json`

State transitions:

```text
created -> active -> waiting_agents -> awaiting_decision -> active
active -> closed
active -> abandoned
waiting_agents -> partial
partial -> awaiting_decision
any non-terminal -> failed
```

Owner/actor:

- Session owner is `user` by default.
- AIT may be actor for summaries, manifests, gate decisions, and exports.
- Agents are actors only for their own responses/proposals/attempts.

Links:

- `root_intent_id`
- `turn_ids`
- `decision_ids`
- `summary_refs`
- `memory_fact_ids` only after explicit promotion.

### SessionTurn

Required fields:

- `id`
- `session_id`
- `ordinal`
- `mode`
- `user_input_ref`
- `user_input_redacted_ref`
- `state`
- `created_at`, `dispatched_at`, `completed_at`
- `participants_snapshot`
- `context_policy_ref`
- `response_ids`
- `summary_id`
- `blocking_reasons`

State transitions:

```text
queued -> context_prepared -> dispatching -> running
running -> completed
running -> partial
running -> timed_out
running -> cancelled
running -> failed
partial -> awaiting_decision
completed -> awaiting_decision
```

Links:

- User input links to prompt record.
- Responses link to context manifests.
- Turn summary links to response ids.

### AgentParticipant

Required fields:

- `id`
- `session_id`
- `agent_id`
- `adapter_name`
- `role`
- `display_name`
- `command_template`
- `capabilities`
- `permissions`
- `state`
- `added_at`
- `removed_at`
- `removed_by_actor`
- `remove_reason`

Permissions:

- `can_respond`
- `can_create_attempt`
- `can_review_attempt`
- `can_read_prior_responses`
- `can_receive_advisory_context`
- `can_stream`
- `can_use_interactive_tty`

Role examples:

- `panelist`
- `implementer`
- `reviewer`
- `council_member`
- `summarizer`

Participant state transitions:

```text
invited -> active
invited -> rejected
active -> paused
active -> removing
removing -> removed
paused -> active
```

Adding a participant mid-session means including that agent in future turns only.
AIT must not synthesize retroactive responses for earlier turns, and summaries
must make it clear that the new participant did not participate in prior
discussion. The participant may receive accepted decisions and redacted session
summaries as context, but prior agent responses remain advisory and attributed.

Removing a participant means excluding that agent from future turns. It must not
delete, rewrite, or anonymize prior responses, attempts, reviews, context
manifests, or transcript provenance. If the participant has a running response,
AIT should first record a cancellation decision for that response, then mark the
participant removed after capture/cleanup completes.

### AgentResponse

Required fields:

- `id`
- `session_id`
- `turn_id`
- `participant_id`
- `agent_id`
- `adapter_name`
- `role`
- `state`
- `invocation_id`
- `command_ref`
- `context_manifest_ref`
- `stdout_ref`
- `stderr_ref`
- `raw_trace_ref`
- `redacted_response_ref`
- `exit_code`
- `started_at`, `ended_at`
- `timeout_seconds`
- `cancellation_reason`
- `provenance`
- `trust_class`
- `proposal_ids`
- `attempt_id`
- `review_id`
- `metadata_json`

State transitions:

```text
queued -> context_prepared -> invoked -> streaming -> completed
invoked -> failed
streaming -> timed_out
streaming -> cancelled
completed -> recorded
recorded -> selected
recorded -> superseded
```

Trust classes:

- `captured_response`: AIT captured this output from an invoked local CLI.
- `advisory`: useful but not accepted as fact.
- `review_evidence`: reviewer output linked to target attempt.
- `attempt_result`: output linked to isolated attempt.

### AgentProposal

Required fields:

- `id`
- `session_id`
- `response_id`
- `kind`
- `title`
- `summary`
- `recommended_action`
- `risk_level`
- `requires_attempt`
- `requires_review`
- `source_refs`
- `state`

Proposal kinds:

- `plan`
- `patch_request`
- `attempt_candidate`
- `review_finding`
- `test_plan`
- `memory_candidate`
- `decision_candidate`
- `allocation_candidate`

State transitions:

```text
proposed -> accepted
proposed -> rejected
proposed -> superseded
accepted -> attempt_created
accepted -> memory_candidate_created
```

### SessionWorkPackage

Required fields:

- `id`
- `session_id`
- `allocation_plan_id`
- `title`
- `scope_paths`
- `excluded_paths`
- `role`
- `assigned_participant_id`
- `assigned_agent_id`
- `state`
- `depends_on_package_ids`
- `risk_level`
- `expected_outputs`
- `attempt_id`
- `review_id`
- `overlap_status`
- `created_at`, `updated_at`

State transitions:

```text
proposed -> accepted -> running -> completed
accepted -> cancelled
completed -> integration_pending
integration_pending -> integrated
any non-terminal -> blocked
```

### SessionAllocationPlan

Required fields:

- `id`
- `session_id`
- `turn_id`
- `strategy`
- `state`
- `created_by`
- `created_at`
- `input_refs`
- `scoring_factors`
- `work_package_ids`
- `recommended_next_action`
- `safe_actions`
- `unsafe_actions`
- `blocking_reasons`
- `confidence`
- `rationale_ref`

State transitions:

```text
draft -> accepted
draft -> rejected
accepted -> running
running -> completed
running -> partial
completed -> integration_pending
```

Allocation plans are advisory until accepted. They may guide Role Mode dispatch,
but each package still creates isolated attempts and remains subject to review,
integration, and explicit apply.

### SessionContextManifest

Required fields:

- `id`
- `session_id`
- `turn_id`
- `participant_id`
- `agent_id`
- `context_ref`
- `created_at`
- `trusted_baseline_refs`
- `live_memory_source_manifest`
- `accepted_decision_refs`
- `prior_response_refs`
- `advisory_response_refs`
- `policy_exclusions`
- `redaction_result`
- `budget_chars`
- `content_sha256`
- `write_mode`

Context manifest extends existing context manifest behavior from attempts.
`owner_kind` should support `session_response` and `session_attempt` in addition
to existing `attempt`.

### SessionDecision

Required fields:

- `id`
- `session_id`
- `turn_id`
- `actor`
- `decision_type`
- `selected_response_id`
- `selected_proposal_id`
- `accepted_summary`
- `state`
- `rationale`
- `created_at`
- `links`
- `memory_promotion_status`
- `attempt_id`
- `review_id`
- `apply_status`

Decision types:

- `accept_response`
- `reject_response`
- `create_attempt`
- `request_review`
- `promote_memory_candidate`
- `apply_attempt`
- `close_session`

Important rule:

```text
SessionDecision can select a response or proposal.
SessionDecision does not mutate root checkout by itself.
```

### SessionSummary

Required fields:

- `id`
- `session_id`
- `turn_ids`
- `source_response_ids`
- `summary_kind`
- `body_ref`
- `json_ref`
- `created_by`
- `created_at`
- `deterministic_ordering`
- `redaction_result`

Summary kinds:

- `turn_summary`
- `council_summary`
- `decision_summary`
- `export_summary`

### Safe To Git-Share vs Local-Only

`.ait/` is ignored by default in this repo, so sharing is always explicit.

Usually safe to export after redaction:

- Session title and high-level summaries.
- Accepted decisions.
- Response ids without raw local paths.
- Attempt ids and review ids that already belong to AIT evidence.
- Redacted markdown export.
- Context source manifests with content hashes and policy results.

Local-only by default:

- Raw prompts and raw responses.
- stdout/stderr logs.
- context files containing repo excerpts.
- workspace refs and absolute paths.
- command env, ownership tokens, socket paths, local user names.
- policy-blocked, redacted, or sensitive memory source content.
- unaccepted agent opinions.

## 5. CLI / API Design

### Core CLI

```bash
ait session start "Refactor auth retry" --agents claude-code,codex
ait session ask latest "What is the safest approach?"
ait session panel latest
ait session run latest --mode panel
ait session run latest --mode role --implementer claude-code --reviewer codex
ait session run latest --mode council --agents claude-code,codex,aider
ait session run latest --mode sequential --sequence claude-code:plan,codex:review
ait session summarize latest
ait session decision latest --accept <response-id>
ait session attempt latest --from <response-id>
ait session participant list latest
ait session participant add latest --agent aider --role panelist
ait session participant remove latest --agent codex --reason "too noisy"
ait session allocate latest --strategy adaptive --agents claude-code,codex,aider --dry-run
ait session allocation accept latest --plan <allocation-plan-id>
ait session export latest --format md
```

Additional operational CLI:

```bash
ait session list --format table
ait session show latest --format json
ait session responses latest --format jsonl
ait session participant list latest --format json
ait session participant add latest --agent aider --role panelist
ait session participant remove latest --participant <participant-id>
ait session allocate latest --strategy adaptive --format json
ait session allocation show latest --plan <allocation-plan-id> --format json
ait session cancel latest --turn latest
ait session retry latest --response <response-id>
ait session close latest
```

### CLI Semantics

- `session start` creates session metadata only; it must not invoke agents.
- `session ask` appends a user turn; it must not invoke agents unless paired
  with `--run`.
- `session run` prepares per-agent context and invokes participants according to
  mode.
- `session panel` renders latest panel responses and AIT summary.
- `session decision` records explicit selection/rejection/rationale.
- `session attempt` creates an isolated attempt from a selected response,
  proposal, or decision.
- `session participant add` adds an agent for future turns. It may provide
  accepted decisions and redacted summaries as onboarding context, but must not
  create retroactive responses.
- `session participant remove` removes an agent from future turns. It preserves
  prior transcript/provenance and cancels any active response before removal.
- `session allocate --strategy adaptive` proposes work packages and agent
  assignments from local evidence. It is advisory unless accepted.
- `session allocation accept` records an explicit decision to use an allocation
  plan for future Role Mode dispatch.
- `session export` emits deterministic redacted artifacts.

### JSON Output Contract

Every `ait session ... --format json` should return machine-readable state:

```json
{
  "schema_version": 1,
  "kind": "session_state",
  "session_id": "ses_01HXYZ",
  "state": "awaiting_decision",
  "mode": "panel",
  "current_turn_id": "turn_0003",
  "participants": [
    {
      "participant_id": "part_claude",
      "agent_id": "claude-code",
      "role": "panelist",
      "state": "completed"
    },
    {
      "participant_id": "part_codex",
      "agent_id": "codex",
      "role": "panelist",
      "state": "failed"
    }
  ],
  "responses": [
    {
      "response_id": "rsp_01HAAA",
      "participant_id": "part_claude",
      "state": "completed",
      "trust_class": "advisory",
      "context_manifest_ref": ".ait/sessions/ses_01HXYZ/contexts/turn_0003-part_claude-manifest.json",
      "provenance_refs": {
        "stdout_ref": ".ait/sessions/ses_01HXYZ/transcripts/rsp_01HAAA.stdout.txt",
        "redacted_response_ref": ".ait/sessions/ses_01HXYZ/transcripts/rsp_01HAAA.redacted.md"
      }
    }
  ],
  "summary": {
    "summary_id": "sum_01HBBB",
    "agreements": ["add failing tests first"],
    "conflicts": ["abstraction timing"],
    "source_response_ids": ["rsp_01HAAA"]
  },
  "next_action": {
    "recommended_command": "ait session decision latest --accept rsp_01HAAA",
    "reason": "one response completed and one participant failed; no repo mutation occurred"
  },
  "safe_actions": [
    "ait session retry latest --response rsp_01HCCC",
    "ait session decision latest --accept rsp_01HAAA",
    "ait session export latest --format md"
  ],
  "unsafe_actions": [
    {
      "command": "ait apply latest",
      "reason": "no attempt has been created from this session"
    }
  ],
  "blocking_reasons": [],
  "partial_failures": [
    {
      "participant_id": "part_codex",
      "state": "failed",
      "exit_code": 127,
      "message": "agent command not executable"
    }
  ],
  "provenance_refs": [
    ".ait/sessions/ses_01HXYZ/events.jsonl"
  ]
}
```

JSON requirements:

- Include `recommended_command` when there is a clear next step.
- Include `safe_actions` and `unsafe_actions`.
- Include blocking reasons for apply, attempt creation, review, cancellation, or
  export.
- Include provenance refs for every response and summary.
- Never mix different agents' output into one unattributed string.

## 6. Context And Memory Design

### Live Federated Memory

Session context uses the existing live federated memory principle:

- Read live repo-local memory at context build time.
- Do not auto-import external agent memory into `.ait/`.
- Apply memory policy before content reaches context.
- Redact before durable transcript/context storage.
- Record source manifest with path, source kind, hash, size, mtime, policy
  result, selected/skipped status, and redaction result.

### 每個 Agent 收到哪些 Context

All participants may receive:

- Current user input.
- Session title and accepted decisions.
- Relevant intent metadata.
- Trusted baseline from AIT-native accepted facts, prior successful attempts,
  review findings, repo brain, and live federated memory.
- Role-specific instructions.

Role-specific examples:

- Implementer: relevant files, implementation hints, accepted decisions,
  successful prior attempts, local conventions.
- Reviewer: target attempt diff, tests, sensitive path rules, prior failed
  attempts, prior review findings, accepted facts, memory eval warnings.
- Council member: compact question, trusted baseline, no same-round peer output.
- Sequential downstream step: accepted decisions plus attributed advisory
  summaries from upstream steps.

### Per-Agent `AIT_CONTEXT_FILE`

`AIT_CONTEXT_FILE` must be generated separately per participant.

For advisory session responses:

```text
.ait/sessions/<session-id>/contexts/<turn-id>-<participant-id>.md
.ait/sessions/<session-id>/contexts/<turn-id>-<participant-id>-manifest.json
```

For attempt-producing responses:

- The context file should also be placed inside that attempt workspace when the
  agent command needs a local path.
- The session-level manifest should link to the attempt-level manifest and
  attempt id.

No two participants should share a writable context file path.

### Prior Agent Responses In Next-Round Context

Default behavior:

- Same-round responses are not visible to other participants.
- Prior user turns and accepted session decisions can enter context.
- Prior agent responses do not become trusted baseline automatically.

Allowed behavior:

- Prior agent responses may enter later context as attributed advisory evidence.
- AIT should prefer compact redacted summaries over raw responses.
- Context must label them as `advisory_response`, include response ids, and
  avoid turning their instruction text into system/user instructions.

### Trusted Baseline vs Advisory Evidence

Trusted baseline:

- AIT-captured attempt evidence.
- Accepted memory facts.
- Accepted session decisions.
- Review findings with explicit status.
- Live external source text after policy, as source text only.

Advisory evidence:

- Agent opinions.
- Council summaries before acceptance.
- Failed attempt conclusions.
- Imported or inferred memory candidates.
- External memory claims that have not been accepted by AIT.

Rule:

```text
Agent output can be evidence that an agent said something.
It is not evidence that the claim is true.
```

### Promoting Session Decisions To Memory Facts

Promotion must be explicit:

```bash
ait session decision latest --accept <summary-id> --promote-memory
```

or a follow-up memory command:

```bash
ait memory fact accept --from-session-decision <decision-id>
```

Promotion requirements:

- Decision must have a human or explicit tool actor.
- Source response ids and summary refs must be preserved.
- The fact body must distinguish accepted decision from agent quote.
- Memory policy and redaction must pass again.
- Policy-blocked memory must never be promoted.

## 7. Execution Model

### Interactive vs Non-Interactive Agent CLI

Non-interactive CLIs:

- Preferred for Panel, Council, and automated Role Mode.
- Use subprocess capture or existing adapter mechanisms.
- Capture stdout/stderr, exit code, start/end time, and raw trace refs.
- Support per-response timeout and retry.

Interactive CLIs:

- Supported only when adapter declares `can_use_interactive_tty`.
- One attached interactive participant should own the user's TTY at a time.
- Parallel interactive fan-out should require buffered/non-interactive mode or
  separate PTY capture without competing for stdin.
- Transcript capture must make interruption and partial output visible.

### Long-Running Sessions

Long-running sessions should be supported as repo-local state:

- Session remains `active` across terminal restarts.
- Running responses heartbeat through event records or daemon state.
- Stale running responses become `crashed` or `timed_out` using TTL rules.
- `ait session show latest --format json` reports recoverable state and safe
  next actions.

### Fan-Out

One user message fan-out:

```text
append SessionTurn
  -> load policy
  -> build participant snapshot
  -> read live federated memory
  -> write per-agent context + manifest
  -> invoke agents under per-response locks
  -> capture outputs
  -> redact and persist transcripts
  -> synthesize AIT summary
  -> report next action
```

Fan-out should not change root checkout. If a participant has permission to
mutate, it must run through isolated attempt creation.

### Timeout, Cancellation, Partial Failure

Requirements:

- Each response has a timeout.
- A timed-out response stores partial stdout/stderr and state `timed_out`.
- Cancellation sends an adapter-appropriate signal and records whether cleanup
  succeeded.
- One failed agent does not fail the whole session unless policy marks it
  required.
- Retry creates a new response id linked to the previous response as
  `retry_of_response_id`.

### stdout/stderr Capture

Capture rules:

- Raw stdout/stderr refs are local-only by default.
- Redacted transcript refs are used for summaries and export.
- stderr should not be discarded just because exit code is zero.
- Binary or oversized output must be truncated with explicit marker and byte
  counts.

### Streaming vs Buffered Output

Phase 1 and 2 may use buffered output.

Streaming UX should add:

- Ordered event stream per response.
- Stable event sequence numbers.
- Terminal rendering that keeps agent attribution visible.
- Backpressure and truncation policy.
- Final deterministic transcript assembled from ordered events.

### Deterministic Transcript Storage

Deterministic export ordering:

1. session ordinal
2. turn ordinal
3. participant ordinal
4. response attempt/retry ordinal
5. event sequence

Wall-clock timestamps may be stored, but exports should be stable when
`--deterministic` is requested by omitting volatile fields or normalizing them.

### Concurrency And Locks

Locks:

- Session lock: append turns, decisions, and summaries.
- Turn lock: dispatch once.
- Participant response lock: one active response per participant per turn.
- Attempt/workspace lock: existing attempt workspace ownership remains
  authoritative.
- Apply/review locks: existing review/apply gate remains authoritative.

No agent may write another agent's response, context, transcript, or workspace.

## 8. Safety And Trust Model

Non-negotiable rules:

1. Repo mutation must go through attempt isolation.
2. No automatic apply from session consensus.
3. No agent can overwrite another agent's workspace.
4. Role permissions are enforced before invocation.
5. Reviewer cannot silently mutate repo unless explicitly allowed and isolated.
6. AIT must not add hidden network calls; only invoked local agent CLIs may use
   their configured provider/network behavior.
7. Redaction runs before durable transcript/context storage and export.
8. Prompt, context, response, summary, decision, attempt, and review provenance
   must be linked.
9. Prompt injection across agents must be treated as untrusted text.
10. Policy-blocked memory must not enter session context.

### Root Checkout Safety

- `ait session start`, `ask`, `panel`, `summarize`, `decision`, and `export`
  must not mutate root checkout.
- `ait session run --mode panel` and `--mode council` must not mutate root
  checkout.
- `ait session run --mode role` may create isolated attempts only for roles
  with `can_create_attempt=true`.
- `ait session attempt` creates or links an attempt; it does not apply it.
- `ait session participant add` affects future dispatch only. New participants
  receive accepted decisions and redacted summaries, not untrusted peer output as
  instructions.
- `ait session participant remove` affects future dispatch only. Prior
  responses, attempts, reviews, transcripts, and context manifests remain
  attributable evidence.
- `ait session allocate --strategy adaptive` may recommend assignments, but it
  must not invoke agents, create attempts, or apply changes until an explicit
  allocation decision is accepted.
- `ait apply <attempt-id>` remains the explicit gate.

### No Hidden Network

AIT itself must not introduce a SaaS dependency for session coordination.
Network behavior belongs to the invoked local agent CLI and must be visible in
the command/provenance. AIT session orchestration, transcript storage, memory
recall, redaction, export, and decisions must work without AIT calling external
services.

### Redaction

Redaction must apply to:

- user input before durable prompt storage
- context files before transcript/export reuse
- stdout/stderr before summaries
- memory excerpts before context
- exported markdown/json

Raw local refs can be retained under `.ait/` for recovery, but JSON output and
export should clearly identify redacted vs raw artifacts.

### Prompt Injection Across Agents

Risks:

- Agent A writes "ignore previous instructions" and Agent B receives it as
  context.
- External memory source contains malicious instruction text.
- Reviewer output contains patch instructions that bypass implementer role.

Mitigations:

- All prior agent responses enter context as quoted advisory evidence.
- Role/system instructions are generated by AIT, not copied from agent output.
- Policy-blocked or redacted content cannot be reintroduced through summary.
- Context manifests label source authority and trust class.

## 9. Implementation Plan

### Phase 0: 文件與 Terminology

Files likely touched:

- `docs/local-multi-agent-session-room-design-zh.md`
- Optional later: `site-docs/reference/local-multi-agent-session-room.md`
- Optional later: `site-docs/zh-TW/reference/local-multi-agent-session-room.md`

Code changes:

- None.

Docs changes:

- Define session room terminology and safety model.
- Clarify non-goals and marketing language.

Tests:

- None required beyond docs review.

Migration/backward compatibility:

- No schema migration.
- Existing `ait run`, `ait review`, `ait apply`, `ait recover` unchanged.

Acceptance criteria:

- Design explains product framing, modes, data model, CLI/API, context/memory,
  execution, safety, implementation plan, tests, and review standards.
- No production code changes.

### Phase 1: Session Data Model + Read-Only Transcript

Files likely touched:

- `src/ait/session_models.py`
- `src/ait/session_store.py`
- `src/ait/db/schema.py`
- `src/ait/db/session_repositories.py`
- `src/ait/cli/session.py`
- `src/ait/cli_parser.py`
- `src/ait/cli/main.py`
- `tests/test_session_store.py`
- `tests/test_cli_session.py`

Code changes:

- Add session, turn, participant, response, decision, and summary models.
- Add `.ait/sessions/` artifact writer.
- Add `ait session start`, `ask`, `show`, `list`, `export`.
- Add JSON output with `next_action`, `safe_actions`, `unsafe_actions`,
  `blocking_reasons`, and provenance refs.
- No agent invocation yet.

Docs changes:

- Add command reference draft.
- Document local-only storage and export behavior.

Tests:

- Session start does not mutate root checkout.
- Session ask appends deterministic turn artifact.
- Export is deterministic.
- JSON is machine-actionable.
- Existing `ait run` and `ait review` tests pass unchanged.

Migration/backward compatibility:

- Additive schema migration only if SQLite indexing is implemented.
- Existing `.ait/` without sessions remains valid.

Acceptance criteria:

- Users can create/read/export a session transcript without invoking agents.
- All session artifacts have schema version and provenance refs.

### Phase 2: Panel Mode Fan-Out, No Repo Mutation

Files likely touched:

- `src/ait/session_orchestrator.py`
- `src/ait/session_runner.py`
- `src/ait/session_context.py`
- `src/ait/adapters.py`
- `src/ait/runner_transcript.py`
- `src/ait/redaction.py`
- `tests/test_session_panel.py`
- `tests/test_session_partial_failure.py`

Code changes:

- Add fake/local test agent adapter support for session responses.
- Build per-agent context files and manifests.
- Fan out one user turn to multiple non-mutating agent invocations.
- Capture stdout/stderr, exit code, partial failures, timeout, retry links.
- Generate AIT summary from completed responses using deterministic local
  summarization rules first.

Docs changes:

- Document Panel Mode real adapter invocation and fake-agent testing pattern.

Tests:

- Panel mode invokes a real adapter CLI when no explicit `--agent-command` is
  provided.
- Panel mode runs two fake agents and records separate responses.
- Failed one agent does not fail entire session.
- Timeout/cancel records partial response.
- Context files are per-agent and have separate manifests.
- No root checkout mutation.

Migration/backward compatibility:

- Additive fields only.
- Panel Mode default must not affect `ait run`.

Acceptance criteria:

- `ait session run latest --mode panel` produces attributed responses and
  session summary with no repo mutation.

### Phase 3: Role Mode With Attempt/Review Linkage

Files likely touched:

- `src/ait/session_orchestrator.py`
- `src/ait/session_attempts.py`
- `src/ait/runner.py`
- `src/ait/review.py`
- `src/ait/review_report.py`
- `src/ait/cli/session.py`
- `tests/test_session_role.py`
- `tests/test_session_review_gate.py`

Code changes:

- Implement implementer role through existing isolated `run_agent_command`.
- Link implementer response to attempt id, commits, changed files, and context
  manifest.
- Invoke reviewer role through existing review substrate.
- Store reviewer response and review findings separately from implementer
  attempt.
- Expose gate status and apply blocking reasons in session JSON.

Docs changes:

- Document Role Mode and reviewer permissions.

Tests:

- Role mode creates implementer attempt and reviewer evidence separately.
- Reviewer cannot mutate implementer workspace.
- No auto apply.
- Apply gate sees review finding and blocks when policy requires.

Migration/backward compatibility:

- Existing attempt/review tables remain source of truth.
- Session metadata only links to attempts/reviews.

Acceptance criteria:

- Claude implementer / Codex reviewer workflow can be represented without
  mixing outputs or bypassing apply gate.

### Phase 4: Session Context Manifests + Memory Promotion

Files likely touched:

- `src/ait/session_context.py`
- `src/ait/runner_context.py`
- `src/ait/memory/live_sources.py`
- `src/ait/memory/models.py`
- `src/ait/memory_policy.py`
- `src/ait/cli/memory.py`
- `tests/test_session_context.py`
- `tests/test_session_memory_promotion.py`

Code changes:

- Extend context manifest owner kinds for `session_response` and
  `session_attempt`.
- Add trusted/advisory source labels to manifests.
- Add session decision to memory candidate/promotion flow.
- Enforce policy-blocked memory exclusion in session context.
- Record prior agent response inclusion as advisory.

Docs changes:

- Add memory promotion reference.
- Update live federated memory docs if terminology changes.

Tests:

- Prior agent response is advisory, not trusted fact.
- Policy-blocked memory excluded.
- Redaction before transcript/context storage.
- Accepted session decision can become memory candidate only through explicit
  gate.

Migration/backward compatibility:

- Additive memory source metadata.
- Existing memory recall behavior remains unchanged outside session commands.

Acceptance criteria:

- Session context can be audited source-by-source and trust-class-by-trust-class.

### Phase 5: Streaming UX And Richer Orchestration

Files likely touched:

- `src/ait/session_events.py`
- `src/ait/session_stream.py`
- `src/ait/runner_pty.py`
- `src/ait/daemon.py`
- `src/ait/daemon_transport.py`
- `src/ait/cli/session.py`
- `tests/test_session_stream.py`
- `tests/test_session_long_running.py`

Code changes:

- Add streaming event store with sequence numbers.
- Add live `ait session panel --watch`.
- Improve interactive PTY support.
- Add cancellation and resume UX.
- Add richer Council/Sequential orchestration after safety model is proven.

Docs changes:

- Document streaming limitations and interactive adapter behavior.

Tests:

- Streaming transcript remains attributed.
- Cancelled response preserves partial output.
- Long-running session can be inspected after restart.
- Deterministic export still works from event stream.

Migration/backward compatibility:

- Event stream is additive.
- Buffered transcript remains supported.

Acceptance criteria:

- Users can watch multi-agent output without losing provenance or attribution.

## 10. Testing And Acceptance

| Area | Test | Acceptance |
| --- | --- | --- |
| Root safety | `session start` does not mutate root checkout | `git status --short` unchanged except ignored `.ait/` metadata. |
| Panel fan-out | Panel mode invokes real adapter CLI or fake agents | Separate `AgentResponse` records with distinct ids, command refs, and manifests. |
| Partial failure | One fake agent exits non-zero | Session state becomes `partial` or `awaiting_decision`, not total failure. |
| Timeout/cancel | Fake agent sleeps past timeout or receives cancel | Partial stdout/stderr stored; state `timed_out` or `cancelled`. |
| Role attempt | Implementer role creates attempt | Attempt is isolated and linked to implementer response. |
| Reviewer evidence | Reviewer role reviews target attempt | Review evidence stored separately; no target workspace mutation. |
| No auto apply | Multi-agent agreement occurs | Root checkout unchanged; JSON says apply requires explicit command. |
| Context isolation | Two agents run same turn | Separate `AIT_CONTEXT_FILE` paths and separate manifests. |
| Advisory prior response | Sequential mode passes prior output | Manifest labels prior output `advisory_response`, not `trusted_baseline`. |
| Policy memory | Memory policy blocks source | Source excluded from context and listed in `policy_exclusions`. |
| Redaction | Prompt/context/output contains secret fixture | Stored summary/export redacts it before durable reuse. |
| JSON next action | `session show --format json` | Includes recommended next action, safe/unsafe actions, blocking reasons. |
| Deterministic export | Export same session twice | Markdown output stable except explicitly volatile fields. |
| Local metadata | Session commands run with real local adapters or fake agents | AIT metadata stays under `.ait/`; model/network behavior is controlled by the chosen local adapter CLI. |
| Backward compatibility | Existing `ait run` and `ait review` | Existing tests pass with session feature disabled. |
| Locking | Two processes append turns | No duplicate ordinals; one writer waits or fails with actionable error. |
| Workspace isolation | Two implementers in same session | Separate attempt workspaces; no overwrite. |
| Split implementation | Two implementers touch disjoint packages | Separate attempts are linked to one session and produce an integration plan. |
| Split overlap | Two implementers touch same file | Session holds with overlap blocking reason; no silent merge. |
| Adaptive allocation dry-run | Allocation strategy proposes work packages | JSON includes scoring factors, rationale, safe/unsafe actions, and no agent invocation. |
| Adaptive allocation low confidence | Signals are ambiguous | Allocation plan is blocked or asks for human decision; no invented ownership. |
| Apply gate | Required review blocked | `ait apply` holds with review blocking reason. |
| Export safety | Export includes responses | Output is attributed and redacted; raw stdout/stderr not exported by default. |

Feasible local-only/no hidden network test:

- Use fake local agents that are shell scripts or Python fixtures.
- Monkeypatch or audit AIT session orchestration to ensure it does not call
  network libraries.
- Assert command provenance lists only the invoked local agent command.

## 11. Code Review Standards

The following are blocking findings:

- Session command mutates root checkout directly.
- Multi-agent agreement auto-applies changes.
- Agent responses lose provenance.
- Claude/Codex outputs are mixed without attribution.
- One agent can overwrite another agent workspace.
- Policy-blocked memory enters context.
- External memory or agent opinion is promoted to trusted fact without explicit
  gate.
- Hidden SaaS/network dependency.
- Missing redaction.
- No tests for partial failure/cancellation.
- JSON output is not machine-actionable.

Additional high-severity findings:

- Reviewer can mutate implementer workspace by default.
- Context manifest omits source policy result or redaction status.
- Retry overwrites original response instead of linking a new response id.
- Export includes raw local paths, tokens, or unredacted stdout/stderr by
  default.
- Session summary quotes agent output without response attribution.
- Existing `ait run`, `ait review`, `ait apply`, or `ait recover` behavior
  changes when session feature is not used.

Review checklist:

- Does every user-visible statement map back to response, attempt, review,
  decision, memory, or source manifest refs?
- Can a failed or cancelled participant be diagnosed without rerunning?
- Does every repo mutation go through attempt/review/apply gates?
- Is role permission enforced before command invocation?
- Are all context files per-agent and immutable after invocation?
- Is JSON useful for an external tool or agent loop?

## 12. Documentation / Marketing Language

### English

Approved copy:

- Local multi-agent session room for AI coding agents
- Same session, separate attempts, attributable evidence
- Let Claude implement, Codex review, and AIT keep the repo gated
- Not a shared SaaS chat, not automatic consensus apply

Longer draft:

```text
AIT coordinates local AI coding agents in one user-facing session while keeping
their responses, attempts, evidence, and responsibilities separate. Ask Claude
and Codex the same question, let one implement and another review, then use
AIT's existing attempt isolation and review/apply gate before anything changes
your repo.
```

Avoid:

```text
AI agents collaborate autonomously and apply the best consensus patch.
```

### 繁中

可用文案：

- 本機 multi-agent session room
- 同一個 session，多個 agent；每個回覆、attempt、證據都分開歸屬
- 讓 Claude 實作、Codex 審查，AIT 負責隔離、記錄與 gate
- 不是 SaaS 聊天室，也不是多 agent 同意就自動套用

較完整草案：

```text
AIT 讓你在同一個本機 session 裡協調多個 AI coding agents，同時保留清楚的
責任邊界。Claude 可以負責實作，Codex 可以負責審查；每個回覆、attempt、
context、證據與決策都保留 provenance，最後仍由 AIT 的 isolated attempt 與
review/apply gate 決定是否落地。
```

避免：

```text
多個 agent 達成共識後自動替你合併最好的版本。
```

## 13. Final Output

### 最終設計定位

AIT Local Multi-Agent Session Room 是 local-first session coordinator，不是
新的 agent、SaaS chat、Git replacement 或 consensus auto-apply system。它讓
使用者在同一個 session 裡協調多個既有 agent，同時維持 response、attempt、
context、evidence、decision 的隔離、歸屬、審查與 gate。

### 建議新增/修改的文件

本階段建議新增：

- `docs/local-multi-agent-session-room-design-zh.md`

後續若進入實作，可再新增：

- `site-docs/reference/local-multi-agent-session-room.md`
- `site-docs/zh-TW/reference/local-multi-agent-session-room.md`
- command reference updates under `site-docs/reference/commands.md`

### 核心 Data Model

核心模型：

- `Session`
- `SessionTurn`
- `AgentParticipant`
- `AgentResponse`
- `AgentProposal`
- `SessionContextManifest`
- `SessionDecision`
- `SessionSummary`

設計原則：

- Session model links to existing intents, attempts, reviews, memory facts, and
  context manifests.
- Attempt/review remain authoritative for repo mutation and apply gates.
- Agent response is captured evidence, not trusted fact.

### CLI/API 草案

Primary CLI:

```bash
ait session start "Refactor auth retry" --agents claude-code,codex
ait session ask latest "What is the safest approach?"
ait session panel latest
ait session run latest --mode panel
ait session run latest --mode role --implementer claude-code --reviewer codex
ait session summarize latest
ait session decision latest --accept <response-id>
ait session attempt latest --from <response-id>
ait session export latest --format md
```

API output must include state, participants, responses, next action,
safe/unsafe actions, blocking reasons, and provenance refs.

### 分階段實作計畫

- Phase 0: 文件與 terminology。
- Phase 1: session data model + read-only transcript。
- Phase 2: panel mode fan-out, no repo mutation。
- Phase 3: role mode with attempt/review linkage。
- Phase 4: session context manifests + memory promotion。
- Phase 5: streaming UX and richer orchestration。

### 測試驗收矩陣

Minimum required coverage:

- no root checkout mutation
- fake two-agent panel fan-out
- partial failure, timeout, cancellation, retry
- implementer attempt and reviewer evidence separation
- no auto apply
- per-agent context and manifests
- advisory prior response handling
- policy-blocked memory exclusion
- redaction before storage/export
- machine-actionable JSON
- deterministic export
- local-only/no hidden network where feasible
- backward compatibility with existing `ait run` and `ait review`

### Code Review Blocking Standards

Blocking review findings include direct root mutation, auto-apply from
multi-agent agreement, lost provenance, unattributed output mixing, workspace
overwrite, policy-blocked memory in context, un-gated memory fact promotion,
hidden network/SaaS dependency, missing redaction, missing partial
failure/cancellation tests, and non-actionable JSON.

### 與既有 AIT Workflow 銜接

- Live federated memory: session reads live memory at context-build time and
  records per-agent source manifests.
- Review gate: reviewer responses link to target attempts and existing review
  findings; apply remains gated.
- Attempt workflow: any mutation-producing role creates isolated attempts;
  session decisions only select or link work, not apply it.
- Apply/recover: unchanged; session JSON can recommend these commands when
  safe, but does not bypass them.

### Residual Risks

- Some agent CLIs may not support reliable non-interactive mode, streaming, or
  cancellation.
- Provider CLIs may use network by design; AIT can record invocation but cannot
  make third-party tools offline.
- Summarization quality can distort nuance unless source response ids and
  redacted excerpts remain easy to inspect.
- Sequential Mode increases prompt-injection risk and should stay optional
  until advisory context labeling is proven.
- Session artifacts may contain sensitive repo excerpts; export must remain
  explicit and redacted by default.
