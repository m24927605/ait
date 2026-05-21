# Hero demo recordings — vhs `.tape` sources

Source files for the three AIT hero demo recordings. Each tape is
inspection-only: it shows the post-run artifacts of a pain-point demo,
not the live `run.sh` (which calls Claude Code / Codex CLI and is
non-deterministic).

Tooling: [`vhs`](https://github.com/charmbracelet/vhs) (`brew install vhs`).
Output: GIF, MP4, and PNG per tape, written into `docs/assets/`.

## Pre-flight

```bash
brew install vhs                                  # one-time, version ≥0.10
ait --version                                     # confirm AIT is on PATH
```

## Smoke test

Verify the toolchain works without touching any demo:

```bash
vhs docs/assets/tapes/smoke-test.tape
```

Produces `docs/assets/smoke-test.gif` (≈15 KB). If this succeeds, the
hero tapes will record on this machine.

## Producing the three hero recordings

Each hero demo needs its `run.sh` to have populated state once before the
tape can record useful output. The `run.sh` scripts call live Claude Code
and Codex CLI; you need both authenticated before running them.

```bash
# Pillar 1 — multi-agent communication
bash examples/pain-point-demos/07-cross-agent-handoff/run.sh
bash examples/pain-point-demos/07-cross-agent-handoff/verify.sh
vhs docs/assets/tapes/hero-cross-agent-handoff.tape

# Pillar 2 — adversarial review
bash examples/pain-point-demos/09-1-codex-reviewer/run.sh
bash examples/pain-point-demos/09-1-codex-reviewer/verify.sh
vhs docs/assets/tapes/hero-codex-reviewer.tape

# Pillar 3 — shared + long-term memory
bash examples/pain-point-demos/04-memory-reuse/run.sh
bash examples/pain-point-demos/04-memory-reuse/verify.sh
vhs docs/assets/tapes/hero-memory-recall.tape
```

After each `vhs` run you get:

- `docs/assets/hero-<demo>.gif` (≈2–4 MB; see size-cut below)
- `docs/assets/hero-<demo>.mp4` (for X / Twitter embeds)
- `docs/assets/hero-<demo>-{1,2,3}.png` (static frames, fallback for
  surfaces where a GIF can't render)

## Trimming GIF size

vhs defaults produce 3–5 MB GIFs. To hit the README ≤2 MB target:

```bash
brew install gifsicle
gifsicle --lossy=60 --optimize=3 --colors 128 \
  -o docs/assets/hero-cross-agent-handoff.gif \
  docs/assets/hero-cross-agent-handoff.gif
```

## Notes on the tapes

- All three tapes use vhs's built-in default theme so they work without
  a Nerd Font on the host. If `JetBrainsMono Nerd Font` is installed,
  add `Set FontFamily "JetBrainsMono Nerd Font"` to each tape before
  re-running for crisper ligatures.
- The tapes intentionally do NOT invoke `run.sh` — they record the
  post-run inspection, which is short (8–18 seconds), deterministic, and
  cheap (no API calls).
- Path commands assume cwd is the repo root.

## Replacing the live README hero asset

After the three GIFs land, swap the placeholder in the live READMEs:

```bash
# README.md and README.zh-TW.md
sed -i '' 's|site-docs/assets/ait-work-graph.png|docs/assets/hero-cross-agent-handoff.gif|' README.md README.zh-TW.md
```

The site-docs hero pages reference `site-docs/assets/ait-work-graph.png`
as a stand-in; update them with the same pattern once recordings exist.
