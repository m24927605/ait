# Python Floor 3.11 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower AIT's pip-install Python floor from `>=3.14` to `>=3.11` and sweep docs accordingly, with zero code changes. The codebase already works on 3.11 — this is a metadata + documentation change.

**Architecture:** Six tightly-scoped commits: baseline verification, `pyproject.toml`, READMEs, `docs/` sweep, CHANGELOG + version bump, post-change re-verification. Each commit is independently revertable.

**Tech Stack:** Python 3.11 (`/opt/homebrew/bin/python3.11`), stdlib `unittest`, no new code.

---

## Conventions (read before any task)

- Repo: `/Users/michael.chen/products/ait`
- Branch: create `feature/python-floor-3-11` from `main` before starting
- Python 3.11 binary: `/opt/homebrew/bin/python3.11`
- Existing project tests are run with `.venv/bin/python` (3.14). For verification we create a **separate** venv at `/tmp/ait_311_verify/` — do not touch `.venv/`.
- Commit message footer (CLAUDE.md mandate) — every commit ends with:

  ```
  docs:<comma-separated-paths>
  keyword:<comma-separated-keywords>

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```

  Use HEREDOC for `-m`.

- HEREDOC commit pattern:

  ```bash
  git commit -m "$(cat <<'EOF'
  <subject line>

  <body>

  docs:<paths>
  keyword:<keys>

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

- After any commit that touches docs, verify nothing else accidentally changed by `git diff HEAD~1 HEAD --stat`. The stat output should only list the intended files.

- Spec reference: `docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md`.

---

## File inventory

The full set of files that need edits (discovered via `grep -l "Python 3\.14\|python3\.14\|>=3\.14" docs/ README*`):

```
pyproject.toml
README.md
README.zh-TW.md
docs/launch-kit-2026.md
docs/getting-started.md
docs/claude-code-live-smoke.md
docs/release-checklist.md
docs/seo-strategy.md
docs/claude-code-run-worktree.md
docs/ait-hero-demo-recording-plan.md
docs/ai-vcs-mvp-spec.md
docs/ait-rebrand-qa-report.md
docs/ait-rebrand-qa-reality.md
docs/repo-brain-acceptance.md
docs/long-term-memory-acceptance.md
CHANGELOG.md
```

Two categories:

- **Floor change** — rewrite "Python 3.14" to "Python 3.11+" in user-facing prose: `README.md`, `README.zh-TW.md`, `docs/launch-kit-2026.md`, `docs/getting-started.md`, `docs/claude-code-live-smoke.md`, `docs/seo-strategy.md`, `docs/ait-hero-demo-recording-plan.md`, `docs/ai-vcs-mvp-spec.md`.
- **Footnote-only** — keep literal `python3.14` commands intact (maintainer's local toolchain), but add a footnote saying any Python ≥ 3.11 works: `docs/release-checklist.md`, `docs/claude-code-run-worktree.md`, `docs/repo-brain-acceptance.md`, `docs/long-term-memory-acceptance.md`.

---

## Task 1: Baseline verification on Python 3.11

Confirms that the existing codebase passes the full test suite under Python 3.11 **before** we change `pyproject.toml`. If this step fails, the whole plan is moot.

**Files:** none (creates a temp venv only)

- [ ] **Step 1: Create a feature branch**

```bash
git checkout -b feature/python-floor-3-11
git branch --show-current
```

Expected output: `feature/python-floor-3-11`.

- [ ] **Step 2: Create a clean Python 3.11 venv outside the repo's `.venv/`**

```bash
/opt/homebrew/bin/python3.11 -m venv /tmp/ait_311_verify
/tmp/ait_311_verify/bin/python -V
```

Expected: `Python 3.11.<minor>`.

- [ ] **Step 3: Install AIT and test deps into the 3.11 venv**

```bash
/tmp/ait_311_verify/bin/pip install --upgrade pip
/tmp/ait_311_verify/bin/pip install pytest build
```

Note: this will currently **fail** at the `pyproject.toml` `requires-python` check unless we override it for this step. We're going to lower the floor anyway — but we haven't done it yet. So instead of installing AIT via pip, install it from source bypassing the version gate:

```bash
PYTHONPATH=src /tmp/ait_311_verify/bin/python -c "import ait; print('import OK')"
```

Expected: `import OK` (no traceback, no SyntaxError, no ImportError).

If this fails, **STOP**. The codebase actually uses a 3.12+ feature that the spec grep missed. Triage that bug before continuing.

- [ ] **Step 4: Run the full test suite under Python 3.11**

```bash
PYTHONPATH=src /tmp/ait_311_verify/bin/python -m unittest discover -s tests 2>/tmp/baseline_311.err
echo "exit=$?"
tail -5 /tmp/baseline_311.err
```

Expected: exit 0 and last lines say `Ran NNN tests in <time>` and `OK`. Approximately 955+ tests.

If any tests fail, **STOP** and triage:
- Read the failure output in `/tmp/baseline_311.err`
- If the failure is genuine (a Python 3.12+ feature is used somewhere), surface the file and line; that's a separate fix-bug task that must be done before continuing.
- If the failure is environmental (missing system tool, etc.), document it and decide whether it affects the plan.

- [ ] **Step 5: No commit for this task — it is verification only**

```bash
git status
```

Expected: `nothing to commit, working tree clean` (we only created `/tmp/ait_311_verify/`).

---

## Task 2: Update `pyproject.toml`

Lower `requires-python` and add Python classifiers.

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current pyproject**

```bash
head -40 pyproject.toml
```

Note the current value of `requires-python` (line 11 in the current state). Note whether `classifiers = [...]` block contains any `Programming Language :: Python :: 3.x` entries (currently it does not — visible Programming Language classifier list is absent or only `Programming Language :: Python :: 3`).

- [ ] **Step 2: Change `requires-python`**

Use the Edit tool to change:

```toml
requires-python = ">=3.14"
```

to:

```toml
requires-python = ">=3.11"
```

- [ ] **Step 3: Add Python version classifiers**

Find the `classifiers = [` block. If a `Programming Language :: Python :: 3` line already exists, leave it as the umbrella entry. Add four more lines (ascending order) after it:

```toml
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: 3.14",
```

If no Python version classifier exists yet, insert the full block above into the existing `classifiers` list at an appropriate position (after `Programming Language :: Python :: 3` if present, otherwise alphabetically with other classifiers).

- [ ] **Step 4: Verify the edit**

```bash
grep -nE "requires-python|Programming Language :: Python" pyproject.toml
```

Expected output includes:
```
requires-python = ">=3.11"
... Programming Language :: Python :: 3.11
... Programming Language :: Python :: 3.12
... Programming Language :: Python :: 3.13
... Programming Language :: Python :: 3.14
```

- [ ] **Step 5: Smoke-install into the 3.11 venv**

Now that the gate is lowered, pip should accept AIT under 3.11:

```bash
/tmp/ait_311_verify/bin/pip install -e .
```

Expected: succeeds without `requires a different Python` error. Tail of output: `Successfully installed ait-vcs-1.4.3`.

- [ ] **Step 6: Re-run tests under 3.11 (post-install)**

```bash
PYTHONPATH=src /tmp/ait_311_verify/bin/python -m unittest discover -s tests 2>/tmp/post_311.err
echo "exit=$?"
tail -5 /tmp/post_311.err
```

Expected: identical green to Task 1 Step 4.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
chore(pyproject): lower Python floor from 3.14 to 3.11

Codebase only uses 3.11-era features (tomllib, datetime.UTC). The >=3.14
requirement was unnecessarily restrictive and blocked install on most
contemporary systems. Verified tests pass under Python 3.11.

Also add Programming Language classifiers for 3.11..3.14.

docs:docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md,docs/superpowers/plans/2026-05-29-python-floor-3-11-plan.md
keyword:python-compat,requires-python,pyproject

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8: Verify the commit content**

```bash
git show --stat HEAD
```

Expected: 1 file changed (`pyproject.toml`), small +/- count.

---

## Task 3: Update READMEs

Rewrite "Python 3.14" → "Python 3.11+" in user-facing README copy.

**Files:**
- Modify: `README.md`
- Modify: `README.zh-TW.md`

- [ ] **Step 1: List current mentions in both READMEs**

```bash
grep -n "Python 3\.14\|python3\.14\|>=3\.14" README.md README.zh-TW.md
```

Capture the line numbers. There may be:
- A "Requirements" or install section
- An install snippet showing `pipx install --python python3.14 ait-vcs`
- A version line in the "About" section

- [ ] **Step 2: Update `README.md`**

For each match in `README.md`:

| Context | Old | New |
|---|---|---|
| Prose mentioning the minimum Python version | "Python 3.14+" / "requires Python 3.14" | "Python 3.11+" / "requires Python 3.11+" |
| Install snippet | `pipx install --python python3.14 ait-vcs` | `pipx install ait-vcs` (no `--python` flag needed) |
| Feature description / blurb | "Python 3.14, zero runtime dependencies" | "Python 3.11+, zero runtime dependencies" |

Use the Edit tool with enough surrounding context to make each `old_string` unique.

- [ ] **Step 3: Update `README.zh-TW.md`**

Apply the same rewrites in Traditional Chinese:

| Context | Old | New |
|---|---|---|
| 需求 / Requirements 段 | "需要 Python 3.14+" or similar | "需要 Python 3.11+" |
| 安裝指令 | `pipx install --python python3.14 ait-vcs` | `pipx install ait-vcs` |
| Blurb / feature line | "Python 3.14+，無外部相依" | "Python 3.11+，無外部相依" |

- [ ] **Step 4: Verify no `3\.14` mentions remain in READMEs**

```bash
grep -n "Python 3\.14\|python3\.14\|>=3\.14" README.md README.zh-TW.md
```

Expected: empty output (no matches).

- [ ] **Step 5: Smoke-render the READMEs**

```bash
wc -l README.md README.zh-TW.md
```

Expected: line counts close to pre-change (small deltas from prose edits).

- [ ] **Step 6: Commit**

```bash
git add README.md README.zh-TW.md
git commit -m "$(cat <<'EOF'
docs(readme): reflect Python 3.11+ floor

Match pyproject.toml: install snippets drop --python python3.14 and the
prose says Python 3.11+ instead of 3.14+.

docs:README.md,README.zh-TW.md,docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md
keyword:python-compat,readme,install-ux

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update user-facing docs (floor change)

Rewrite "Python 3.14" → "Python 3.11+" across the docs listed under "Floor change" in the file inventory above.

**Files:**
- Modify: `docs/launch-kit-2026.md`
- Modify: `docs/getting-started.md`
- Modify: `docs/claude-code-live-smoke.md`
- Modify: `docs/seo-strategy.md`
- Modify: `docs/ait-hero-demo-recording-plan.md`
- Modify: `docs/ai-vcs-mvp-spec.md`

- [ ] **Step 1: `docs/launch-kit-2026.md`**

List current mentions:

```bash
grep -n "Python 3\.14\|python3\.14" docs/launch-kit-2026.md
```

Expected matches around lines 50–51, 217, 309–310, 426–427, 451, 501.

For each match, replace:

| Pattern | Replacement |
|---|---|
| `Install (requires Python 3.14+; on 3.13 or older use \`pipx install --python python3.14 ait-vcs\`):` | `Install (requires Python 3.11+):` |
| `Try it on a repo you already trust git on (requires Python 3.14+):` | `Try it on a repo you already trust git on (requires Python 3.11+):` |
| `Alpha. MIT, Python 3.14+, zero runtime dependencies.` | `Alpha. MIT, Python 3.11+, zero runtime dependencies.` |
| `安裝（需要 Python 3.14+）：` | `安裝（需要 Python 3.11+）：` |

- [ ] **Step 2: `docs/getting-started.md`**

```bash
grep -n "Python 3\.14\|python3\.14" docs/getting-started.md
```

Replace each mention to read "Python 3.11+". If the doc shows an install command using `python3.14 -m pip install ...`, change to `python3 -m pip install ...` (let the user's default Python resolve, since the floor is now 3.11).

- [ ] **Step 3: `docs/claude-code-live-smoke.md`**

```bash
grep -n "Python 3\.14\|python3\.14" docs/claude-code-live-smoke.md
```

The line "- Python 3.14" in the prerequisites list becomes "- Python 3.11+".

- [ ] **Step 4: `docs/seo-strategy.md`**

```bash
grep -n "Python 3\.14\|python3\.14" docs/seo-strategy.md
```

The seller-blurb line containing "Python 3.14+" becomes "Python 3.11+". This blurb propagates to PyPI long_description, JSON-LD, etc., so accuracy matters here.

- [ ] **Step 5: `docs/ait-hero-demo-recording-plan.md`**

```bash
grep -n "Python 3\.14\|python3\.14" docs/ait-hero-demo-recording-plan.md
```

Around line 61: "Python 3.14+, `ait-vcs` via `pipx`" becomes "Python 3.11+, `ait-vcs` via `pipx`".

- [ ] **Step 6: `docs/ai-vcs-mvp-spec.md`** (special — has a technical justification, not just prose)

```bash
sed -n '50,56p' docs/ai-vcs-mvp-spec.md
```

Current text says:

> `sqlite-3.35-or-newer`: migrations use features from SQLite 3.35+ (notably `ALTER TABLE ... DROP COLUMN` in v3). Python 3.14 ships a newer SQLite, so this is satisfied by the declared `requires-python`.

Replace with:

> `sqlite-3.35-or-newer`: migrations use features from SQLite 3.35+ (notably `ALTER TABLE ... DROP COLUMN` in v3). Python 3.11+ ships SQLite ≥ 3.39, so this is satisfied by the declared `requires-python`.

- [ ] **Step 7: Verify**

```bash
grep -n "Python 3\.14\|python3\.14" \
  docs/launch-kit-2026.md docs/getting-started.md docs/claude-code-live-smoke.md \
  docs/seo-strategy.md docs/ait-hero-demo-recording-plan.md docs/ai-vcs-mvp-spec.md
```

Expected: empty output.

- [ ] **Step 8: Commit**

```bash
git add docs/launch-kit-2026.md docs/getting-started.md docs/claude-code-live-smoke.md \
        docs/seo-strategy.md docs/ait-hero-demo-recording-plan.md docs/ai-vcs-mvp-spec.md
git commit -m "$(cat <<'EOF'
docs: rewrite user-facing docs to Python 3.11+ floor

Sweep of launch-kit, getting-started, live-smoke, seo-strategy, hero-demo
plan, and the MVP spec to reflect the new pyproject floor. The MVP spec
also re-justifies the SQLite ≥3.35 requirement against 3.11's bundled
SQLite ≥3.39 instead of 3.14's.

docs:docs/launch-kit-2026.md,docs/getting-started.md,docs/claude-code-live-smoke.md,docs/seo-strategy.md,docs/ait-hero-demo-recording-plan.md,docs/ai-vcs-mvp-spec.md,docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md
keyword:python-compat,docs-sweep

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Footnote release / acceptance docs + resolve QA tracker

Docs that show maintainer-local commands literally (`python3.14 -m build`, etc.) keep the literal command but get a footnote. QA tracker entries that flagged the 3.14 cliff get a "Resolved" stamp.

**Files:**
- Modify: `docs/release-checklist.md`
- Modify: `docs/claude-code-run-worktree.md`
- Modify: `docs/repo-brain-acceptance.md`
- Modify: `docs/long-term-memory-acceptance.md`
- Modify: `docs/ait-rebrand-qa-reality.md`
- Modify: `docs/ait-rebrand-qa-report.md`

- [ ] **Step 1: `docs/release-checklist.md`** — footnote

```bash
grep -n "python3\.14" docs/release-checklist.md
```

Expected matches: lines 69–75 showing build/twine/wheel-smoke commands.

Above the first `python3.14 -m build` invocation (or at the top of the section that uses it), add this footnote line:

```markdown
> Note: `python3.14` here is the maintainer's local default. Any Python ≥ 3.11 works for build/release; substitute `python3` if you prefer.
```

Leave the literal commands intact below.

- [ ] **Step 2: `docs/claude-code-run-worktree.md`** — footnote

```bash
grep -n "Python 3\.14\|python3\.14" docs/claude-code-run-worktree.md
```

Add the same kind of footnote near the top of the document (or near the first `python3.14` reference):

```markdown
> Note: `python3.14` is the snippet's literal command. Any Python ≥ 3.11 works; substitute `python3` if you prefer.
```

- [ ] **Step 3: `docs/repo-brain-acceptance.md` and `docs/long-term-memory-acceptance.md`** — inspect, then footnote if appropriate

```bash
grep -n "Python 3\.14\|python3\.14" docs/repo-brain-acceptance.md
grep -n "Python 3\.14\|python3\.14" docs/long-term-memory-acceptance.md
```

For each match, read the surrounding context. If the doc says "tests require Python 3.14" as a fact (now wrong), update to "Python 3.11+". If it shows a literal `python3.14` command in a script snippet, prepend the same footnote used above and keep the command literal.

- [ ] **Step 4: `docs/ait-rebrand-qa-reality.md`** — mark H6 resolved

```bash
sed -n '40,60p' docs/ait-rebrand-qa-reality.md
```

Find the paragraph that flags the `pyproject.toml requires Python >=3.14` cliff (around line 44). Append immediately after that paragraph (or at the end of its bullet):

```markdown
> **Resolved 2026-05-29.** Floor lowered to 3.11 per
> `docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md`.
```

- [ ] **Step 5: `docs/ait-rebrand-qa-report.md`** — mark H6 resolved

```bash
sed -n '38,44p' docs/ait-rebrand-qa-report.md
```

Find the H6 row. Replace the "Reality" or status cell content with:

```
Resolved 2026-05-29 — floor lowered to 3.11.
```

Leave the rest of the table intact.

- [ ] **Step 6: Verify the footnote additions don't break formatting**

```bash
wc -l docs/release-checklist.md docs/claude-code-run-worktree.md \
      docs/repo-brain-acceptance.md docs/long-term-memory-acceptance.md \
      docs/ait-rebrand-qa-reality.md docs/ait-rebrand-qa-report.md
```

Expected: line counts increased by a small amount per file.

- [ ] **Step 7: Commit**

```bash
git add docs/release-checklist.md docs/claude-code-run-worktree.md \
        docs/repo-brain-acceptance.md docs/long-term-memory-acceptance.md \
        docs/ait-rebrand-qa-reality.md docs/ait-rebrand-qa-report.md
git commit -m "$(cat <<'EOF'
docs: footnote python3.14 literals and resolve QA tracker entries

Release checklist, run-worktree, and acceptance docs keep their literal
python3.14 commands (maintainer's local default) and get a footnote that
any Python ≥3.11 works. The two QA tracker entries that flagged the
3.14 install cliff are marked Resolved with a pointer to the spec.

docs:docs/release-checklist.md,docs/claude-code-run-worktree.md,docs/repo-brain-acceptance.md,docs/long-term-memory-acceptance.md,docs/ait-rebrand-qa-reality.md,docs/ait-rebrand-qa-report.md,docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md
keyword:python-compat,docs,qa-tracker

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: CHANGELOG entry and version bump

The change is user-visible (install requirements lowered) → minor version bump per semver.

**Files:**
- Modify: `pyproject.toml` (version)
- Modify: `npm/ait-vcs/package.json` (version, to stay aligned)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Inspect current versions**

```bash
grep "^version" pyproject.toml
grep '"version"' npm/ait-vcs/package.json
head -20 CHANGELOG.md
```

Expected: pyproject has `version = "1.4.3"`, npm package.json has `"version": "1.4.3"`, CHANGELOG has an empty `## Unreleased` section followed by `## 1.4.3 - 2026-05-28`.

- [ ] **Step 2: Bump `pyproject.toml` version**

Change `version = "1.4.3"` to `version = "1.5.0"`.

- [ ] **Step 3: Bump `npm/ait-vcs/package.json` version**

Change `"version": "1.4.3"` to `"version": "1.5.0"`.

- [ ] **Step 4: Add CHANGELOG entry**

Edit `CHANGELOG.md`. Replace the existing:

```markdown
## Unreleased
```

with:

```markdown
## Unreleased

## 1.5.0 - 2026-05-29

### Changed

- Lowered Python floor from 3.14 to 3.11. The codebase never used any
  3.12+ stdlib or syntax; the 3.14 minimum was unnecessarily restrictive
  and blocked most users at install time. No code changes — only
  metadata, classifiers, and documentation. See
  `docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md`.
```

- [ ] **Step 5: Verify the three edits**

```bash
grep "^version" pyproject.toml
grep '"version"' npm/ait-vcs/package.json
sed -n '1,15p' CHANGELOG.md
```

Expected: pyproject `version = "1.5.0"`, npm `"version": "1.5.0"`, CHANGELOG shows the new `## 1.5.0 - 2026-05-29` section.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml npm/ait-vcs/package.json CHANGELOG.md
git commit -m "$(cat <<'EOF'
chore(release): 1.5.0 — Python floor lowered to 3.11

User-visible change to install requirements. Bumps minor version per
semver. PyPI wheel and npm wrapper versions kept in sync.

docs:CHANGELOG.md,pyproject.toml,npm/ait-vcs/package.json,docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md
keyword:release,python-compat,version-bump

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final re-verification on Python 3.11

Make absolutely sure the published-ready branch still passes under 3.11 after all the doc/metadata churn.

**Files:** none (verification only)

- [ ] **Step 1: Reinstall AIT into the 3.11 venv (fresh from current branch)**

```bash
/tmp/ait_311_verify/bin/pip install --force-reinstall --no-deps -e .
```

Expected: `Successfully installed ait-vcs-1.5.0`.

- [ ] **Step 2: Run the full test suite under 3.11**

```bash
PYTHONPATH=src /tmp/ait_311_verify/bin/python -m unittest discover -s tests 2>/tmp/final_311.err
echo "exit=$?"
tail -5 /tmp/final_311.err
```

Expected: exit 0 and `Ran NNN tests in <time>` / `OK`.

- [ ] **Step 3: Quick smoke of the CLI surface**

```bash
PYTHONPATH=src /tmp/ait_311_verify/bin/python -m ait.cli --version
PYTHONPATH=src /tmp/ait_311_verify/bin/python -m ait.cli bug-report --help
```

Expected:
- `--version` prints `ait 1.5.0`
- `bug-report --help` prints the subcommand help

- [ ] **Step 4: Confirm the branch is ready for merge**

```bash
git log --oneline main..feature/python-floor-3-11
git diff main..feature/python-floor-3-11 --stat
```

Expected: 5 commits (Task 2, 3, 4, 5, 6), and the diff stat lists only the intended docs/metadata files plus `CHANGELOG.md`.

- [ ] **Step 5: No commit — verification only**

```bash
git status
```

Expected: `nothing to commit, working tree clean`.

- [ ] **Step 6: Clean up the verify venv (optional)**

```bash
rm -rf /tmp/ait_311_verify
```

This is optional; the venv is harmless to leave around for future regressions.

---

# Self-review

**Spec coverage:**

| Spec section | Plan task |
|---|---|
| Change 1 — `pyproject.toml` requires-python + classifiers | Task 2 |
| Change 2 — README sweep | Task 3 |
| Change 2 — user-facing docs sweep | Task 4 |
| Change 2 — release/acceptance docs footnote + QA tracker mark | Task 5 |
| Change 3 — CHANGELOG | Task 6 |
| Verification (clean 3.11 venv) | Task 1 (baseline) + Task 7 (post-change) |
| Version bump 1.5.0 | Task 6 |
| Spec: "Release sequence" — tag/release | Out of scope (this plan stops at branch ready for merge) |

The "release sequence" tag/publish step is intentionally not included in this plan — that is a maintainer action that follows from `docs/release-checklist.md`, not a code change.

**Placeholder scan:** No "TBD", "TODO", "implement later", "Add appropriate error handling", or "Similar to Task N" patterns in the plan.

**Type consistency:** No types, signatures, or new functions in this plan (pure metadata + docs).

**Scope check:** One focused PR-sized change. No decomposition needed.

---

# Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-29-python-floor-3-11-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints.
