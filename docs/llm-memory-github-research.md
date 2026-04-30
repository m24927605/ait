# LLM Long-Term Memory GitHub Research

## Purpose

This document summarizes memory-system patterns from public GitHub
projects and related papers that are relevant to AIT.

The goal is not to copy one project. The goal is to identify proven
ideas that fit AIT's product constraints:

- repo-local by default
- Git-aware
- low user interruption
- agent CLI compatible
- auditable from traces, files, commits, and tests

## Research Boundary

Primary projects reviewed:

- Mem0: https://github.com/mem0ai/mem0
- Graphiti / Zep: https://github.com/getzep/graphiti
- Letta / MemGPT: https://github.com/letta-ai/letta
- LangMem: https://github.com/langchain-ai/langmem
- Supermemory: https://github.com/supermemoryai/supermemory
- MemMachine: https://github.com/MemMachine/MemMachine
- Hindsight: https://github.com/vectorize-io/hindsight
- ByteRover: https://www.byterover.dev/

Related papers and docs:

- Mem0 paper: https://arxiv.org/abs/2504.19413
- Zep paper: https://arxiv.org/abs/2501.13956
- ByteRover paper: https://arxiv.org/abs/2604.01599
- MemMachine paper: https://arxiv.org/abs/2604.04853
- Letta memory docs: https://docs.letta.com/concepts/memory-management
- Graphiti quickstart: https://help.getzep.com/graphiti/getting-started/quick-start

## Findings

### 1. Memory Is Not Just RAG

RAG retrieves documents. Long-term memory must also decide:

- what is worth remembering
- whether a fact is still current
- what evidence supports the fact
- whether a newer fact supersedes an older one
- how much context to inject

AIT implication:

- AIT should not treat `.ait/traces/` as a simple document corpus.
- AIT needs structured memory objects with provenance, time, confidence,
  and supersession metadata.

### 2. Hybrid Retrieval Is The Current Practical Baseline

Mem0 and Graphiti both emphasize retrieval beyond plain vector search.
Useful signals include:

- lexical search
- semantic search
- entity matching
- graph relationships
- recency
- source confidence

AIT implication:

- AIT should keep the current lexical/literal search path.
- AIT should add optional semantic ranking.
- AIT should add entity and Git-evidence signals before depending on a
  heavy external vector database.

### 3. Temporal Memory Matters For Coding

Zep / Graphiti's core lesson is that memory changes over time.

Coding examples:

- "Use REST" can later become "Use GraphQL."
- "Run npm test" can later become "Run pnpm test."
- "This approach failed" can later become "This approach works after
  adding a migration."

AIT implication:

- AIT must model memory as temporal evidence, not a single mutable note.
- Old memory should be superseded or marked stale, not silently deleted.

### 4. Agent-Managed Memory Is Useful But Must Be Governed

Letta and LangMem expose memory tools that agents can call during a
conversation. This supports natural workflows where users do not manually
manage memory.

AIT implication:

- AIT should not require daily `ait memory add` commands.
- Wrapped agents should receive relevant memory automatically.
- Post-run consolidation should happen in the background.
- Agent-written memory must be policy-checked before becoming durable.

### 5. Background Consolidation Is Necessary

LangMem separates hot-path memory use from background memory management.
This is important because high-quality extraction and deduplication can
cost extra time and tokens.

AIT implication:

- Run-time recall must stay fast and compact.
- Expensive extraction, conflict detection, and consolidation can run
  after the agent exits.
- AIT should degrade gracefully: raw trace remains available even when
  consolidation fails.

### 6. Human-Readable Local Memory Is A Strong Fit For Coding Agents

ByteRover's local-first, markdown-oriented approach is highly relevant
to coding agents because agents are good at reading structured markdown,
and humans can review it.

AIT implication:

- AIT should store canonical memory in SQLite for indexing and also
  render durable memory into human-readable markdown.
- Markdown memory should be generated from structured state, not become
  the only source of truth.

### 7. Mistake Memory Is Underrated

Hindsight and similar systems emphasize learning from failed actions,
not only storing facts.

AIT implication:

- AIT should treat failed attempts as first-class evidence.
- Failure memories should include:
  - failed command or approach
  - observed error
  - files involved
  - attempted fix
  - whether a later attempt superseded the failure

### 8. Security And Memory Poisoning Are Core Risks

Memory systems can persist prompt injection, secrets, wrong facts, or
malicious instructions.

AIT implication:

- Memory extraction must obey `.ait/memory-policy.json`.
- Durable memory needs source references and reviewability.
- Secrets must be redacted before durable storage.
- Retrieved memory should be advisory, not authoritative.

## Comparative Table

| Project | Main Pattern | What AIT Should Borrow | What AIT Should Avoid |
| --- | --- | --- | --- |
| Mem0 | Multi-level memory and hybrid retrieval | Multi-signal ranking, entity linking, memory benchmarks | Treating user-personalization assumptions as repo memory |
| Graphiti / Zep | Temporal knowledge graph | Time-aware facts, supersession, hybrid graph search | Requiring Neo4j/FalkorDB as a hard dependency in first version |
| Letta / MemGPT | Agent-managed memory | Agent can decide when memory is relevant | Letting agents mutate durable memory without governance |
| LangMem | Hot-path tools + background manager | Separate fast recall from post-run consolidation | Requiring LangGraph runtime |
| Supermemory | Memory + RAG + profiles + contradiction handling | Contradiction handling and forgetting/expiry concepts | Remote-first assumptions |
| MemMachine | Episodic/profile/working memory | Distinguish memory types and MCP/API boundaries | Heavy service dependency for default local AIT |
| Hindsight | Learning from mistakes | Failure memory and experience-based improvement | Overfitting AIT to user-personalized assistant tasks |
| ByteRover | Local markdown hierarchy | Human-readable local memory for coding agents | Making markdown the only authoritative store |

## Best-Fit Direction For AIT

AIT should implement a repo-local temporal evidence memory system:

```text
raw trace
  -> normalized transcript
  -> evidence extraction
  -> candidate memory
  -> policy and redaction
  -> temporal durable memory
  -> hybrid retrieval
  -> compact context injection
  -> graph/report/debug views
```

The architecture should be Git-aware:

- every durable memory links back to attempt id, trace ref, file path, or
  commit oid
- memory facts can be superseded by later attempts
- failed attempts are retained as evidence
- promotion/rebase/discard state affects confidence

## AIT-Specific Memory Types

AIT should model at least these memory types:

- `decision`: architecture or product decision
- `rule`: user or project rule
- `workflow`: test, build, deploy, or agent workflow
- `failure`: failed approach and observed reason
- `entity`: file, module, service, API, dependency
- `current_state`: unfinished or recently active work
- `superseded`: old fact replaced by newer evidence

## Recommended First Production Slice

Do not start with a large vector database or graph database. Start with:

1. SQLite temporal memory tables.
2. Human-readable generated markdown memory.
3. Hybrid lexical + entity + recency ranking.
4. Optional embedding provider behind a feature flag.
5. Post-run memory consolidation.
6. `ait memory recall` used by wrappers before agent launch.
7. HTML graph/report showing why a memory was retrieved.

This keeps AIT local, auditable, and installable while leaving a path to
Graphiti-style temporal graph retrieval later.

## Research Conclusion

The strongest external pattern is not "use a vector database." The
strongest pattern is:

- preserve episodes
- extract durable facts
- model temporal change
- retrieve with multiple signals
- keep evidence links
- let agents use memory automatically
- govern what becomes durable memory

AIT already has strong provenance primitives that most general memory
systems do not have: Git commits, worktrees, attempts, outcomes, files,
and traces. The correct direction is to build memory on top of that
evidence layer instead of replacing it with generic chat memory.
