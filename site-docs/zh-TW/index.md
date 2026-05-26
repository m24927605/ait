---
title: ait — AI coding agent 的本機 attempt ledger
description: >-
  ait 會把 Claude Code、Codex、Aider、Gemini CLI、Cursor CLI 和其他 agent
  run 記成本機 attempt，讓下一個 agent 可以審查、接手，或在失敗後復原。
hide:
  - navigation
  - toc
---

<div class="ait-home">
  <section class="ait-hero" aria-labelledby="ait-hero-title">
    <div class="ait-hero__glow" aria-hidden="true"></div>
    <div class="ait-badge">Local · no telemetry</div>
    <h1 id="ait-hero-title">AI coding run 的本機紀錄本。</h1>
    <p class="ait-hero__lead">
      ait 會把每次 Claude Code、Codex、Aider、Gemini、Cursor run 記成 repo-local
      attempt，讓下一個 agent 可以審查、接手，或在失敗後復原。
    </p>
    <div class="ait-actions">
      <a class="ait-button ait-button--primary" href="#quickstart">開始使用</a>
      <a class="ait-button ait-button--ghost" href="https://github.com/m24927605/ait">View on GitHub</a>
    </div>
    <p class="ait-hero__note">
      套件：<code>ait-vcs</code>。指令：<code>ait</code>。需要 Python 3.14+。
    </p>
  </section>

  <section class="ait-section ait-grid ait-grid--two" aria-label="ait 做什麼">
    <div class="ait-copy">
      <div class="ait-badge">為什麼需要</div>
      <h2>Agent 很會改程式，但流程很容易失去脈絡。</h2>
      <p>
        下一個 agent 從零開始。寫程式的 agent 審自己的程式。失敗 run 留下一堆狀態。
        重要決定消失在聊天紀錄裡。
      </p>
      <p>
        ait 把每次 run 變成 attempt：一個有 prompt、diff、review state、memory，
        而且必須明確 apply 才會落地的提案。
      </p>
    </div>
    <div class="ait-stack">
      <div class="ait-mini-card"><strong>Prompt</strong><span>這次 agent 被要求做什麼。</span></div>
      <div class="ait-mini-card"><strong>Diff</strong><span>隔離 workspace 裡改了什麼。</span></div>
      <div class="ait-mini-card"><strong>Review</strong><span>另一個 agent 在 apply 前看見什麼。</span></div>
      <div class="ait-mini-card"><strong>Decision</strong><span>下一個 agent 應該記住什麼。</span></div>
    </div>
  </section>

  <section id="quickstart" class="ait-section ait-panel ait-quickstart" aria-labelledby="quickstart-title">
    <div class="ait-badge">Get started</div>
    <h2 id="quickstart-title">30 秒試用。</h2>
    <p>不用 API key。不需要現有 repo。也不會真的呼叫 agent。</p>
    <div class="ait-terminal" role="img" aria-label="ait quickstart commands">
      <div class="ait-terminal__bar"><span></span><span></span><span></span></div>
      <pre><code>pipx install ait-vcs
ait demo

# 之後清掉 demo repos
ait demo --clean</code></pre>
    </div>
    <div class="ait-card-grid ait-card-grid--three">
      <a class="ait-card" href="getting-started/">
        <span>01</span>
        <strong>安裝與初始化</strong>
        <p>在 repo 裡建立 `.ait/`，並確認 agent 指令會經過 ait。</p>
      </a>
      <a class="ait-card" href="reference/commands/">
        <span>02</span>
        <strong>執行與檢查</strong>
        <p>照常使用 agent，然後查看被記下來的 attempt。</p>
      </a>
      <a class="ait-card" href="reference/adversarial-code-review/">
        <span>03</span>
        <strong>Apply 前先審</strong>
        <p>讓另一個 agent 先挑戰 diff，再決定要不要落地。</p>
      </a>
    </div>
  </section>

  <section class="ait-section" aria-labelledby="flow-title">
    <div class="ait-section-heading">
      <div class="ait-badge">使用感</div>
      <h2 id="flow-title">Agent 照常跑，apply 變清楚。</h2>
      <p>只要你還沒執行 <code>ait apply</code>，被包住的結果就只是提案。</p>
    </div>
    <div class="ait-flow">
      <div><span>1</span><strong>Run</strong><p><code>claude ...</code>、<code>codex ...</code> 或 <code>aider ...</code></p></div>
      <div><span>2</span><strong>Record</strong><p>Prompt、diff、trace、檔案、commit、review state。</p></div>
      <div><span>3</span><strong>Review</strong><p>高風險修改可交給第二個 agent 先審。</p></div>
      <div><span>4</span><strong>Apply</strong><p>你確認可以接受時，才把 attempt 推進 root checkout。</p></div>
    </div>
  </section>

  <section class="ait-section ait-grid ait-grid--three" aria-label="核心 workflow">
    <div class="ait-feature">
      <span>handoff</span>
      <h3>Cross-agent handoff</h3>
      <p>下一個被包住的 agent 可以收到先前 attempts、accepted facts、notes 與現場 memory files。</p>
    </div>
    <div class="ait-feature">
      <span>review</span>
      <h3>對抗式審查</h3>
      <p>一個 agent 實作，另一個 agent 在 apply 前挑戰它。</p>
    </div>
    <div class="ait-feature">
      <span>recall</span>
      <h3>Memory recall</h3>
      <p>當舊決定又變重要時，可以搜尋以前的 prompt、finding 與 decision。</p>
    </div>
  </section>

  <section class="ait-section ait-panel" aria-labelledby="compare-title">
    <div class="ait-section-heading">
      <div class="ait-badge">定位</div>
      <h2 id="compare-title">ait 不是另一個 coding agent。</h2>
      <p>它是包在你現有 agent 外面的本機 workflow layer。</p>
    </div>
    <div class="ait-compare">
      <div><strong>Cursor / Cline</strong><span>IDE 裡的 agent 體驗。</span><p>ait 補上可跨工具使用的 CLI-first attempt ledger。</p></div>
      <div><strong>Claude Code / Codex</strong><span>讀程式、改程式、跑指令的 agent。</span><p>ait 補上隔離、review records、memory 與 explicit apply。</p></div>
      <div><strong>Aider</strong><span>模型 pair-programming 與 commits。</span><p>ait 補上 attempt 邊界與可選的 second-agent review。</p></div>
      <div><strong>Git worktree</strong><span>隔離目錄。</span><p>ait 補上 prompt、trace、review、handoff 與 recover/apply 指令。</p></div>
    </div>
  </section>

  <section class="ait-section ait-warning" aria-labelledby="not-title">
    <div>
      <div class="ait-badge">誠實邊界</div>
      <h2 id="not-title">如果你需要 hosted product，ait 不適合。</h2>
      <p>
        ait 是 CLI-only、alpha、單機、local-first。它不是 IDE plugin、
        autocomplete engine、hosted dashboard、team sync service，也不是 AI
        reviewer 一定找得到所有缺陷的證明。
      </p>
    </div>
    <a class="ait-button ait-button--ghost" href="why-ait/">閱讀邊界</a>
  </section>
</div>
