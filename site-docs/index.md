---
title: ait — a local attempt ledger for AI coding agents
description: >-
  ait records Claude Code, Codex, Aider, Gemini CLI, Cursor CLI, and other
  agent runs as local attempts so another agent can review, continue, or recover
  the work later.
hide:
  - navigation
  - toc
---

<div class="ait-home">
  <section class="ait-hero" aria-labelledby="ait-hero-title">
    <div class="ait-hero__glow" aria-hidden="true"></div>
    <div class="ait-badge">Local · no telemetry</div>
    <h1 id="ait-hero-title">A local ledger for AI coding runs.</h1>
    <p class="ait-hero__lead">
      ait records every Claude Code, Codex, Aider, Gemini, or Cursor run as a
      repo-local attempt so another agent can review, continue, or recover it
      later.
    </p>
    <div class="ait-actions">
      <a class="ait-button ait-button--primary" href="#quickstart">Get started</a>
      <a class="ait-button ait-button--ghost" href="https://github.com/m24927605/ait">View on GitHub</a>
    </div>
    <p class="ait-hero__note">
      Package: <code>ait-vcs</code>. Command: <code>ait</code>. Requires Python 3.14+.
    </p>
  </section>

  <section class="ait-section ait-grid ait-grid--two" aria-label="What ait does">
    <div class="ait-copy">
      <div class="ait-badge">Why it exists</div>
      <h2>Agents can write code. The workflow around them is still fragile.</h2>
      <p>
        The next agent starts from zero. The implementer reviews its own work.
        Failed runs leave clutter. Useful decisions disappear into chat history.
      </p>
      <p>
        ait turns each run into an attempt: a proposal with prompt, diff,
        review state, memory, and an explicit apply step.
      </p>
    </div>
    <div class="ait-stack">
      <div class="ait-mini-card"><strong>Prompt</strong><span>What the agent was asked to do.</span></div>
      <div class="ait-mini-card"><strong>Diff</strong><span>What changed in the isolated workspace.</span></div>
      <div class="ait-mini-card"><strong>Review</strong><span>What another agent found before apply.</span></div>
      <div class="ait-mini-card"><strong>Decision</strong><span>What future agents should remember.</span></div>
    </div>
  </section>

  <section id="quickstart" class="ait-section ait-panel ait-quickstart" aria-labelledby="quickstart-title">
    <div class="ait-badge">Get started</div>
    <h2 id="quickstart-title">Try it in 30 seconds.</h2>
    <p>No API keys. No existing repo. No real agent required.</p>
    <div class="ait-terminal" role="img" aria-label="ait quickstart commands">
      <div class="ait-terminal__bar"><span></span><span></span><span></span></div>
      <pre><code>pipx install ait-vcs
ait demo

# clean up demo repos later
ait demo --clean</code></pre>
    </div>
    <div class="ait-card-grid ait-card-grid--three">
      <a class="ait-card" href="getting-started/">
        <span>01</span>
        <strong>Install and init</strong>
        <p>Set up `.ait/` in a repo and confirm your agent command is wrapped.</p>
      </a>
      <a class="ait-card" href="reference/commands/">
        <span>02</span>
        <strong>Run and inspect</strong>
        <p>Use your agent normally, then inspect the recorded attempt.</p>
      </a>
      <a class="ait-card" href="reference/adversarial-code-review/">
        <span>03</span>
        <strong>Review before apply</strong>
        <p>Ask a different agent to challenge the diff before it lands.</p>
      </a>
    </div>
  </section>

  <section class="ait-section" aria-labelledby="flow-title">
    <div class="ait-section-heading">
      <div class="ait-badge">How it feels</div>
      <h2 id="flow-title">Same agents. A clearer apply gate.</h2>
      <p>Until you run <code>ait apply</code>, a wrapped agent's work is a proposal.</p>
    </div>
    <div class="ait-flow">
      <div><span>1</span><strong>Run</strong><p><code>claude ...</code>, <code>codex ...</code>, or <code>aider ...</code></p></div>
      <div><span>2</span><strong>Record</strong><p>Prompt, diff, trace, files, commits, review state.</p></div>
      <div><span>3</span><strong>Review</strong><p>Optional separate reviewer agent for high-risk changes.</p></div>
      <div><span>4</span><strong>Apply</strong><p>Promote the attempt only when you decide it is ready.</p></div>
    </div>
  </section>

  <section class="ait-section ait-grid ait-grid--three" aria-label="Core workflows">
    <div class="ait-feature">
      <span>handoff</span>
      <h3>Cross-agent handoff</h3>
      <p>The next wrapped agent can receive prior attempts, accepted facts, notes, and live repo memory files.</p>
    </div>
    <div class="ait-feature">
      <span>review</span>
      <h3>Adversarial review</h3>
      <p>One agent implements. Another agent challenges the attempt before apply.</p>
    </div>
    <div class="ait-feature">
      <span>recall</span>
      <h3>Memory recall</h3>
      <p>Search old prompts, findings, and decisions when context matters again.</p>
    </div>
  </section>

  <section class="ait-section ait-panel" aria-labelledby="compare-title">
    <div class="ait-section-heading">
      <div class="ait-badge">Positioning</div>
      <h2 id="compare-title">ait is not another coding agent.</h2>
      <p>It is the local workflow layer around the agents you already use.</p>
    </div>
    <div class="ait-compare">
      <div><strong>Cursor / Cline</strong><span>IDE-native agent experience.</span><p>ait adds a CLI-first attempt ledger across tools.</p></div>
      <div><strong>Claude Code / Codex</strong><span>Coding agents that edit and run commands.</span><p>ait adds isolation, review records, memory, and explicit apply.</p></div>
      <div><strong>Aider</strong><span>Pair-programming loop with commits.</span><p>ait adds an attempt boundary and optional separate reviewer.</p></div>
      <div><strong>Git worktrees</strong><span>Isolated directories.</span><p>ait adds prompts, traces, reviews, handoff, and recover/apply commands.</p></div>
    </div>
  </section>

  <section class="ait-section ait-warning" aria-labelledby="not-title">
    <div>
      <div class="ait-badge">Honest boundary</div>
      <h2 id="not-title">Do not use ait when you need a hosted product.</h2>
      <p>
        ait is CLI-only, alpha, single-machine, and local-first. It is not an
        IDE plugin, autocomplete engine, hosted dashboard, team sync service, or
        proof that an AI reviewer will find every defect.
      </p>
    </div>
    <a class="ait-button ait-button--ghost" href="why-ait/">Read the boundaries</a>
  </section>
</div>
