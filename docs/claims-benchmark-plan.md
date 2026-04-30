# AIT Claims Benchmark Plan

## Purpose

AIT should not claim that it solves long-term memory, LLM hallucination,
token cost, or multi-agent collaboration without repeatable evidence.
This plan defines the experiments required to measure those claims.

The goal is not to prove perfection. The goal is to measure whether AIT
improves practical AI-agent software development workflows compared with
using the agent CLIs directly.

## Claims Under Test

### Claim 1: Long-Term Memory

Precise claim:

- AIT helps future agent sessions recover useful project facts from past
  work without requiring the user to re-explain them.

Non-claim:

- AIT does not claim human-equivalent memory.
- AIT does not claim perfect semantic recall.
- AIT does not claim that every transcript line should become durable
  memory.

### Claim 2: Hallucination Reduction

Precise claim:

- AIT reduces unverifiable or stale claims by giving agents and users
  access to traceable evidence: attempts, transcripts, files, commits,
  outcomes, and memory notes.

Non-claim:

- AIT does not eliminate LLM hallucination.
- AIT does not guarantee that an agent's reasoning is correct.

### Claim 3: Token Cost Reduction

Precise claim:

- AIT can reduce repeated context transmission by replacing repeated
  user explanations with compact repo memory and graph references.

Non-claim:

- AIT does not guarantee lower token usage for every run.
- AIT memory injection can increase token usage if unmanaged.

### Claim 4: Multi-Agent Collaboration

Precise claim:

- AIT improves collaboration among Claude Code, Codex, and Gemini by
  isolating attempts, recording provenance, and making cross-agent
  history inspectable.

Non-claim:

- AIT is not yet a full autonomous scheduler.
- AIT does not yet guarantee conflict-free merges.

## Experiment Design

Each experiment compares two modes:

1. Baseline mode:
   Use the agent CLI directly without AIT wrappers, AIT memory, AIT graph,
   or AIT workspaces.

2. AIT mode:
   Use `ait init`, repo-local wrappers, AIT workspaces, graph, memory,
   transcripts, outcomes, and reports.

The same task set must be executed in both modes.

## Test Agents

In scope:

- Claude Code
- Codex
- Gemini

Out of scope:

- Cursor
- aider

## Test Repositories

Use at least three repositories:

1. Empty repository:
   Verifies onboarding and unborn Git repo handling.

2. Small application:
   A minimal web or CLI project with tests and a few modules.

3. Existing medium repository:
   A real project with prior commits, existing conventions, and enough
   context for memory to matter.

Each repository must be reset to a known Git commit before each run.

## Task Suite

### Memory Tasks

M1. Project rule recall:

- Session A tells the agent a durable project rule.
- Session B asks the agent to implement a feature that requires applying
  that rule.
- Measure whether the rule is recovered and applied.

Example rule:

- "All API route inputs must use zod validation."

Pass criteria:

- The later change follows the rule.
- The report shows traceable memory evidence.
- `ait memory search` can find the rule.

M2. Design decision recall:

- Session A makes an architectural decision.
- Session B asks for a related implementation.
- Measure whether the decision is reused instead of contradicted.

M3. Failed-attempt avoidance:

- Session A records a failed approach.
- Session B asks for a similar task.
- Measure whether the agent avoids repeating the same failed path.

### Hallucination Tasks

H1. Evidence-grounded explanation:

- Ask the agent to explain what changed in the last successful attempt.
- Score whether the answer is supported by actual files, commits, and
  transcripts.

H2. False-memory trap:

- Ask the agent about a project decision that was never made.
- Score whether it admits no evidence instead of inventing one.

H3. Stale-fact trap:

- Record a decision, later supersede it, then ask which decision is
  current.
- Score whether the answer follows the newer evidence.

### Token-Cost Tasks

T1. Repeated context task:

- Baseline mode: user repeats the same project background in every
  session.
- AIT mode: user provides the background once, then relies on AIT memory.

Measure:

- Total input tokens.
- Total output tokens.
- Total cached tokens when available.
- Number of user words required.

T2. Large transcript recall:

- Run a multi-step project task.
- Ask a follow-up question in a new session.
- Compare full transcript replay versus compact AIT memory/graph recall.

### Multi-Agent Tasks

A1. Parallel non-overlapping edits:

- Claude modifies one module.
- Codex modifies another module.
- Gemini updates tests or docs.
- Measure whether AIT records separate attempts, files, commits, and
  outcomes without cross-agent state confusion.

A2. Conflicting edits:

- Two agents edit the same file in incompatible ways.
- Measure whether the conflict is visible in graph/report and whether
  promotion refuses unsafe integration.

A3. Cross-agent handoff:

- Claude starts a task and records decisions.
- Codex continues from AIT memory and graph.
- Gemini verifies tests and explains outcome.
- Measure continuity and correctness.

## Metrics

### Memory Metrics

- Recall precision:
  Fraction of retrieved memory items that are relevant.

- Recall coverage:
  Fraction of expected durable facts retrievable through `ait memory
  search`.

- Application rate:
  Fraction of later tasks that correctly apply the remembered fact.

- Stale-memory rate:
  Fraction of answers that use superseded or contradicted memory.

Target for initial acceptance:

- Recall coverage >= 80% on curated durable facts.
- Stale-memory rate <= 10%.
- Application rate improves over baseline by >= 25 percentage points.

### Hallucination Metrics

- Unsupported-claim count:
  Number of claims not backed by files, commits, transcripts, tests, or
  memory notes.

- False-answer rate:
  Fraction of trap questions answered with fabricated facts.

- Evidence citation rate:
  Fraction of answers that reference concrete AIT evidence when asked.

Target for initial acceptance:

- Unsupported-claim count decreases by >= 30% versus baseline.
- False-answer rate decreases by >= 30% versus baseline.
- Evidence citation rate >= 80% for evidence-seeking prompts.

### Token Metrics

- Total input tokens.
- Total output tokens.
- Total cached tokens.
- User-provided context words.
- Context compression ratio:
  `full_context_tokens / ait_context_tokens`.

Target for initial acceptance:

- User-provided context words decrease by >= 50% in repeated-context
  tasks.
- Total non-cached input tokens decrease by >= 20% in repeated-context
  tasks.
- No task should exceed baseline token usage by more than 20% unless it
  also improves correctness or evidence quality.

### Multi-Agent Metrics

- Agent attribution accuracy:
  Whether each file, commit, attempt, and transcript is attributed to the
  correct agent.

- Isolation success rate:
  Whether concurrent attempts avoid corrupting the main working tree.

- Conflict visibility:
  Whether conflicting edits are visible in graph/report before unsafe
  promotion.

- Handoff success rate:
  Whether a later agent can continue from earlier AIT evidence.

Target for initial acceptance:

- Agent attribution accuracy >= 95%.
- Isolation success rate = 100% for non-overlapping edits.
- Unsafe conflicting promotion must not silently succeed.
- Handoff success rate improves over baseline by >= 25 percentage points.

## Instrumentation Requirements

AIT must collect or expose:

- `intent_id`
- `attempt_id`
- `agent_id`
- `agent_harness`
- `workspace_ref`
- `raw_trace_ref`
- `normalized_trace_ref`
- `verified_status`
- `outcome_class`
- changed files
- commit OIDs
- memory notes and sources
- graph JSON
- HTML report

Token collection:

- If the agent CLI reports token usage, parse it into structured run
  metadata.
- If the agent CLI does not expose token usage, preserve raw transcript
  lines and mark token metrics as unavailable for that run.
- Do not infer token usage without evidence.

## Scoring Rubric

Each task receives four scores:

1. Correctness:
   Did the final code or answer satisfy the task?

2. Evidence:
   Can the result be traced to files, commits, transcripts, tests, or
   memory?

3. Continuity:
   Did the session correctly use relevant prior work?

4. Cost:
   Did token or user-context cost improve?

Scores:

- 0: failed
- 1: partially successful
- 2: successful

Each experiment report must include raw observations, not only aggregate
scores.

## Execution Procedure

For each repository and task:

1. Reset to the known base commit.
2. Run the baseline mode.
3. Save CLI transcript, commits, tests, and token usage if available.
4. Reset to the same base commit.
5. Run the AIT mode.
6. Save `.ait` state, graph JSON, memory output, HTML report, commits,
   tests, and token usage if available.
7. Score both modes with the rubric.
8. Record differences and failure modes.

## Required Commands

Baseline examples:

```bash
claude
codex
gemini
git log --oneline --stat
```

AIT examples:

```bash
ait init
direnv allow
ait status
claude
codex
gemini
ait graph --format json > artifacts/ait-graph.json
ait memory > artifacts/ait-memory.txt
ait graph --html
cp .ait/report/graph.html artifacts/graph.html
```

## Acceptance Gates

AIT may claim "helps with long-term memory" only if:

- Memory recall coverage and application targets pass.
- False durable memory additions are documented and below threshold.

AIT may claim "reduces hallucination risk" only if:

- Unsupported-claim and false-answer rates improve versus baseline.
- Evidence citation rate passes threshold.

AIT may claim "can reduce token cost" only if:

- Token or user-context metrics improve on repeated-context tasks.
- The report distinguishes measured savings from unsupported claims.

AIT may claim "supports multi-agent collaboration" only if:

- Agent attribution, isolation, conflict visibility, and handoff targets
  pass.

If a gate fails, the public claim must be downgraded to the narrower
proven capability.

## Deliverables

Each benchmark run must produce:

- `benchmark-summary.md`
- `scores.json`
- baseline transcripts
- AIT graph JSON
- AIT memory output
- AIT HTML report
- Git commit list
- test logs
- token usage evidence where available

## Initial Implementation Work

1. Add a benchmark harness command:
   `ait benchmark claims`.

2. Add artifact directory layout:
   `.ait/benchmarks/<run-id>/`.

3. Add structured scoring schema:
   `scores.json`.

4. Add token usage extraction from known Claude, Codex, and Gemini
   transcript patterns.

5. Add fixtures for empty, small, and medium test repositories.

6. Add a generated benchmark report that states which claims passed,
   failed, or remain unmeasured.

## Risks

- Agent model changes can make results noisy.
- Token reporting differs across CLIs.
- Human prompts can bias outcomes.
- Some tasks require manual scoring unless an oracle is built.
- AIT memory injection may improve continuity but worsen token cost.

## Review Checklist

- Every claim has a measurable metric.
- Every metric has a baseline comparison.
- Every acceptance gate has a numeric threshold.
- Every output can be audited from artifacts.
- No success claim depends on unsupported inference.
- Failed or inconclusive results are explicitly reportable.
