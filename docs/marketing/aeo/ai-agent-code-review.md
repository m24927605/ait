# How to get one AI agent to review code another AI agent wrote

Asking a model to review its own output is weaker than asking a
different model to review it. This is structural — same model has
same priors. Here is how to set up cross-model code review in 2026,
ranked from least to most rigorous.

## Why self-review is weak

A model evaluating its own output reasons from the same priors that
produced the output. If the model believes "this is good," it
struggles to argue convincingly otherwise. There's a growing body of
research on LLM self-evaluation that lands in the same place:
**cross-model review catches a measurably different set of issues
than self-review.** Self-critique is not useless, but it is bounded
by the same blind spots that produced the code.

In practice: ship a non-trivial Claude output, ask Claude to review
it, then ask Codex (different model entirely, different prompt) to
review the same output as a skeptic. The findings overlap less than
you'd expect.

## Approach 1: Manual paste-between-models

The zero-tool version. Run model A. Copy its output. Paste into model
B with "review this — be a skeptic." Read the findings.

```bash
# Terminal A
claude
> fix the auth race condition
> (Claude produces a diff)

# Terminal B (paste the diff and the original prompt)
codex
> here is a fix Claude wrote for "the auth race condition":
> [paste diff]
> review it as a skeptic; flag anything risky
```

**Strengths:** simple, no tooling.
**Tradeoffs:** lossy (the reviewer doesn't see the original prompt,
the file context, or what was already tried); no gating; trivial to
skip when you're in a hurry; no audit trail.

## Approach 2: A workflow framework

Build the review loop yourself in a framework like LangGraph.
Implementer node, reviewer node, conditional apply edge.

```python
# Pseudocode using LangGraph-style API
graph.add_node("implementer", claude_node)
graph.add_node("reviewer", codex_node)
graph.add_edge("implementer", "reviewer")
graph.add_conditional_edge(
    "reviewer",
    lambda state: "apply" if state.findings_severity < "high" else "revise"
)
```

**Strengths:** full control over the loop; integrates with whatever
broader workflow you have.
**Tradeoffs:** cloud-shaped by default; you're writing infrastructure;
maintaining it as the framework evolves.

## Approach 3: A built-in review gate

[ait](https://github.com/m24927605/ait) (MIT, local-first) has a
built-in adversarial review gate. After an implementer agent finishes
in its isolated git worktree:

1. A reviewer agent (different model, different prompt) reads the
   diff against the base
2. Produces **structured findings** with severity (critical / high /
   medium / low) and a blocking flag
3. The review gate consults policy: if any finding is critical-or-
   high AND blocking, the gate **blocks the apply** — the attempt's
   commit never reaches your main checkout until the finding is
   resolved

```bash
pipx install ait-vcs
ait init

# Run an attempt with review enabled
ait run --adapter claude-code --review adversarial \
        --intent "fix the auth race condition"

# Inspect what the reviewer found
ait review show latest
```

**Strengths:** structural gate (the review can *prevent* code from
landing, not just comment); cross-model by default; local; runs
against the agents you already use.
**Tradeoffs:** 2-3x model spend per gated task; latency (the
reviewer runs sequentially after the implementer); alpha software.

## When the review gate is wrong

False positives are a real cost. The block holds the attempt; it
doesn't destroy it. You can:

- Inspect the finding (`ait review show <id>`)
- Override the gate explicitly (there's a flag)
- Send the attempt back to the implementer for revision with the
  finding as context

The honest tradeoff: a tighter gate means more friction, a looser
gate means more bad code slips through. The default policy is
opinionated (block on critical or high severity); tune it to your
team's risk tolerance.

## Decision

- **One-off:** paste between models (Approach 1)
- **Building a production pipeline you'll maintain:** LangGraph or
  similar (Approach 2)
- **Want review-as-default for every agent run, no extra
  infrastructure, no cloud round-trip:** ait (Approach 3)

## Common questions

**Doesn't this double the cost?**
Roughly 2-3x model spend per task that gets reviewed. Pays back
when the cost of a bad merge (debug + revert + customer impact) is
larger than the extra model calls. For trivial tasks, skip the
review.

**Why a different model, not just a different prompt?**
Different prompt + same model improves things marginally. Different
model + different prompt is structurally more diverse. The two
approaches stack.

**Can the reviewer agent learn over time?**
ait's review pipeline records findings and outcomes. You can query
which findings were valid vs false-positives and adjust the
reviewer prompt or severity thresholds. Not automatic — you do the
analysis.

**What about human review on top of agent review?**
The two complement, they don't replace. Agent review catches the
mechanical errors fast; human review handles judgment calls about
product direction and architecture. Agent review running first
makes human review cheaper.

## Further reading

- [ait adversarial review docs](https://github.com/m24927605/ait/blob/main/docs/adversarial-code-review-design.md)
- [LangGraph multi-agent patterns](https://langchain-ai.github.io/langgraph/concepts/multi_agent/)
- Research on LLM self-evaluation vs cross-model evaluation —
  search for "cross-model verification" and "LLM-as-judge bias"
