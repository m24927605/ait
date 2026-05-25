---
title: Why ait
description: >-
  The plain-English reason ait exists: AI coding agents need local attempts,
  explicit apply, cross-agent handoff, adversarial review, and memory recall.
---

# Why ait

AI coding agents are useful, but their work is easy to lose track of.

`ait` exists for engineers who already use Claude Code, Codex, Aider, Gemini
CLI, Cursor CLI, or similar tools and want every run to leave a local,
reviewable record in the repo.

## The short version

Without `ait`, an agent run is usually just a chat transcript plus whatever
changed in your working tree.

With `ait`, an agent run becomes an attempt:

- what you asked
- what the agent changed
- what another agent found during review
- what decision should be remembered later
- whether you explicitly applied it

The attempt lives under `.ait/` in the repo. It is local. No telemetry. No SaaS.

## Problem 1: the next agent starts from zero

Yesterday Claude investigated a bug and found a constraint. Today Codex opens
the same repo and repeats the investigation because the useful context lived in
a closed chat.

With `ait`, the next wrapped agent can receive a compact handoff from prior
attempts, accepted facts, notes, and live repo memory files such as
`CLAUDE.md`, `AGENTS.md`, `.claude/memory.md`, `.codex/memory.md`, and
`.cursor/rules`.

Try the demo:

```bash
ait demo
```

See also: [Pain-point demos](demos/pain-point-demos.md).

## Problem 2: the implementer reviews its own work

An agent finishes and says the tests pass. That is useful, but it is not the
same as an independent review. The same model, in the same context, often misses
the same blind spots.

With `ait`, you can ask a different agent to review the attempt before apply:

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait review finding list --severity high
```

This is not a correctness guarantee. It is a separate review pass with recorded
findings.

## Problem 3: failed runs leave debris

An agent is interrupted, times out, or makes a risky edit. Without isolation,
you may be left with a confusing working tree.

With `ait`, the wrapped run lands in an isolated workspace. Your root checkout
should not change until you decide to apply:

```bash
ait apply latest
```

If the result needs inspection:

```bash
ait recover latest
ait resume latest
```

## Problem 4: useful decisions disappear

You decided the retry budget should be three. Three weeks later, a new agent
proposes five because it never saw the earlier reasoning.

With `ait`, you can search prior attempts and repo memory:

```bash
ait memory recall "retry budget"
```

You still decide which recalled context matters. `ait` gives you the record; it
does not outsource judgment.

## What ait is not

`ait` is intentionally narrow.

It is not:

- an IDE plugin
- an autocomplete engine
- a hosted dashboard
- a cross-machine sync service
- a replacement for Claude Code, Codex, Aider, Cursor, Cline, or Git
- proof that an AI reviewer catches every bug

## When it is worth using

Use `ait` when the cost of losing agent context is higher than the cost of one
extra workflow layer.

It is most useful when you:

- use more than one agent CLI
- want explicit apply/recover instead of direct working-tree mutation
- want a separate reviewer agent for risky changes
- need old prompts, diffs, findings, and decisions to be searchable
- prefer local-first metadata over SaaS provenance tools

Ready to try it: [Getting started](getting-started.md).
