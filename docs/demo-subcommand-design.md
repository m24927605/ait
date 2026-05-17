# `ait demo` Subcommand — Design Doc

Status: proposed
Owner: marketing-driven; implementation by any agent
Related: `docs/ai-vcs-mvp-spec.md`, `docs/getting-started.md`

## 1. Goal

Let a visitor with `ait` installed but **no Claude/Codex/Aider/Gemini configured**
see the value of ait in **<60 seconds, end-to-end, zero setup**. Every line of
output must come from real ait ledger state, not in-memory fakes.

## 2. Why

Today the smallest first-try cost is:

1. `pipx install ait-vcs` (cheap)
2. install + configure at least one agent adapter (heavy: API keys, wrappers)
3. find a real coding task worth running (cognitive)

Steps 2-3 lose most visitors before they see the core value (multi-agent
attempt ledger + adversarial review gate). `ait demo` removes both.

This unblocks:

- README first-screen demo gif
- Show HN / Reddit / X launches (link gif + "run `ait demo` in 30s")
- KOL outreach ("install + `ait demo` in one minute")
- LLM citation content ("how do I try ait? run `ait demo`")

## 3. Success metric

A first-time user runs `ait demo` in a fresh shell with no prior setup, sees
the full **intent → attempt → review finding → apply blocked** flow in
under 60 seconds, and is told the next real command to run.

## 4. User flow (target output)

```text
$ ait demo
[ait] Creating demo repo at /tmp/ait-demo-01HXYZ.../
[ait] Initialising ait + git (in-process, no daemon)

[ait] Intent  : "Add a divide() helper to calculator.py"
[ait] Attempt : 01HXYZABC...  agent=demo-implementer

      written: calculator.py
        def divide(a, b):
            return a / b

[ait] Review  : agent=demo-reviewer
      finding: divide() does not handle b == 0
      file   : calculator.py:1
      rule   : zero-division
      severity: critical

[ait] Apply gate: review finding severity=critical -> apply skipped.
[ait] Ledger state (from SQLite, not in-memory):
      intents:  1   attempts: 1 (succeeded)   reviews: 1 (critical)

[ait] What just happened
  - ait wrapped a coding task as an isolated attempt with provenance
  - a second agent reviewed the result before any code reached your tree
  - the reviewer caught a real bug, so 'ait apply' was blocked automatically
  - everything above lives in /tmp/ait-demo-01HXYZ.../.ait/state.sqlite3

[ait] Try the same with your real agents:
      cd your-repo
      ait init
      ait run --adapter claude-code --intent "fix N+1 query in users API"

[ait] Demo repo kept at /tmp/ait-demo-01HXYZ.../  (remove with 'ait demo --clean')
```

## 5. Non-goals (v1)

- Multiple scenarios / `--scenario` flag — single hard-coded scenario only
- asciinema / mp4 capture — separate task
- Daemon-mode demo — v1 runs fully in-process to avoid background-process surprises
- Network calls — zero; demo must work offline and in CI
- i18n — English only in v1

## 6. Implementation outline

### 6.1 New CLI handler

- **add** `src/ait/cli/demo.py` (~150 lines, single `handle(args, repo_root, parser)`)
- **modify** `src/ait/cli/main.py` — register `"demo": demo.handle` in `_HANDLERS`
- **modify** `src/ait/cli_parser.py` — add `demo` subparser with flags:
  - `--clean`   remove existing `/tmp/ait-demo-*` directories and exit
  - `--keep`    do not print "demo repo kept" hint (used in CI)
  - `--quiet`   suppress the explanatory blocks, keep machine-readable summary
  - `--json`    emit a single JSON object instead of pretty text

### 6.2 Mock adapter registration (display-only)

- **modify** `src/ait/adapter_registry.py` — add `demo-implementer` and
  `demo-reviewer` to a new `DEMO_ADAPTERS` dict
- Do **not** add them to the public `ADAPTERS` dict — keep `ait adapter list`
  output unchanged for real users
- Adapters are display-only: `cli/demo.py` does not spawn subprocesses for them;
  it writes the scripted output directly

### 6.3 Scripted scenario data

- **add** `src/ait/resources/demo/scenario.json` — single file containing:
  ```json
  {
    "intent": {
      "title": "Add a divide() helper to calculator.py",
      "kind": "feature",
      "description": "..."
    },
    "implementer": {
      "agent_id": "demo-implementer:scripted",
      "files": [
        {
          "path": "calculator.py",
          "content": "def divide(a, b):\n    return a / b\n"
        }
      ],
      "exit_code": 0
    },
    "reviewer": {
      "agent_id": "demo-reviewer:scripted",
      "findings": [
        {
          "rule": "zero-division",
          "severity": "critical",
          "file": "calculator.py",
          "line": 1,
          "message": "divide() does not handle b == 0"
        }
      ]
    }
  }
  ```
- **modify** `pyproject.toml` `[tool.setuptools.package-data]` — add
  `"resources/demo/*.json"` to the `ait` package-data list

### 6.4 Orchestration (reuse, don't reimplement)

In `cli/demo.py.handle()`:

1. If `--clean`: `shutil.rmtree` every `/tmp/ait-demo-*` dir, print count, return 0
2. Make a unique tmp dir: `tempfile.mkdtemp(prefix="ait-demo-")`
3. `subprocess.run(["git", "init"], cwd=tmp)` + an initial empty commit
4. Call `ait.app.init_ait(tmp)` (whatever the existing init entry point is —
   look up via `cli/init.py`)
5. `ait.app.create_intent(tmp, title=scenario.intent.title, ...)` — real intent row
6. `ait.app.create_attempt(tmp, intent_id, agent_id=scenario.implementer.agent_id)`
   — real attempt + workspace via `workspace.create_attempt_workspace`
7. Write the scenario files directly into the attempt workspace
8. `workspace.create_attempt_commit(...)` — real commit in the attempt branch
9. Update attempt with `verified_status="succeeded"` via the same code path
   `verifier.verify_attempt_with_connection` uses, so the ledger row is identical
   to a real run
10. Call existing `ait.review.create_fake_reviewer_review(...)` with the scripted
    finding — produces a real `reviews` row
11. Call `ait.review_policy.run_review_policy(...)` to determine that
    severity=critical blocks apply; do NOT call `landing.apply_attempt`
12. Print summary by **querying the SQLite ledger**, not by re-printing the
    scenario dict (this is the integrity rule; see §8)

### 6.5 Tests

- **add** `tests/test_cli_demo.py`:
  - `test_demo_runs_end_to_end_under_60s` — wall-clock < 60s
  - `test_demo_writes_real_ledger_rows` — open the demo SQLite and assert
    1 intent / 1 attempt / 1 review row with severity=critical
  - `test_demo_no_network` — patch `socket.socket` to raise; demo must still pass
  - `test_demo_clean_removes_prior_dirs` — create two demo dirs, `--clean`,
    assert both gone
  - `test_demo_idempotent` — running twice creates two separate dirs

## 7. Files touched (summary)

| Action | Path |
|--------|------|
| add    | `src/ait/cli/demo.py` |
| add    | `src/ait/resources/demo/scenario.json` |
| add    | `tests/test_cli_demo.py` |
| modify | `src/ait/cli/main.py` (register handler) |
| modify | `src/ait/cli_parser.py` (subparser) |
| modify | `src/ait/adapter_registry.py` (DEMO_ADAPTERS dict) |
| modify | `pyproject.toml` (package-data glob) |
| modify | `docs/getting-started.md` (add a "try in 60s" section linking demo) |

## 8. Integrity rules the implementer MUST follow

These are non-negotiable; failing any of them makes the demo dishonest and we
should not ship it:

1. **All summary output values are read from SQLite at print time**, not from the
   in-memory scenario dict. The whole point of the demo is to show that ait's
   ledger is real.
2. **The git worktree, commit, and attempt branch are real**: no skipping
   `workspace.create_attempt_workspace` or `create_attempt_commit`.
3. **The review row uses `create_fake_reviewer_review`**, the exact same function
   real users get when they configure a fake reviewer — no special demo-only
   codepath that would diverge from reality.
4. **The apply gate decision goes through `review_policy.run_review_policy`**,
   not a hard-coded `apply=skip`. If the policy logic ever changes, the demo
   must change with it.
5. **Zero network calls**. Verified by the no-network test (§6.5).
6. **The demo must not modify the user's HOME, git config, or any existing repo.**
   Everything happens inside the tmp dir.

## 9. Open questions to verify before implementation

1. Does `runner.run_agent_command` require a running daemon, or can it run fully
   in-process via `_LocalRunHarness` (seen at `src/ait/runner.py:46`)? Confirm
   the in-process path is used here so the demo never spawns a daemon.
2. Does `ait init` require an interactive prompt (e.g. for adapter setup)? If
   yes, the demo must call the lower-level functions in `src/ait/app.py`
   directly, not shell out to `ait init`.
3. Confirm `review_policy.py:540` (`severity in {"critical", "high"}`) is the
   right gate to trigger an apply block in the default policy. If not, the demo
   tmp repo needs to seed `.ait/policy.json` explicitly.

All three questions can be answered by reading the matching code; no design
decision is blocked on them.

## 10. Acceptance criteria

- [ ] `ait demo` completes in < 60 s on a clean machine with no network
- [ ] All printed numbers / IDs / statuses come from `sqlite3.connect(...).execute(...)`
      against the demo repo, not from the scenario dict
- [ ] `ait query "attempt"` against the demo repo returns the same attempt
- [ ] `ait demo` run twice creates two independent tmp dirs
- [ ] `ait demo --clean` removes every `/tmp/ait-demo-*` dir, prints the count, exits 0
- [ ] `ait demo --json` emits a single JSON object with `intent_id`, `attempt_id`,
      `review_id`, `demo_dir`, `apply_blocked: true`, `duration_seconds`
- [ ] No existing `ait` subcommand changes behaviour
- [ ] `tests/test_cli_demo.py` passes under `pytest -m "not slow"`
- [ ] `README.md` first-screen gets a "Try it in 30 seconds" block that runs
      `pipx install ait-vcs && ait demo`
