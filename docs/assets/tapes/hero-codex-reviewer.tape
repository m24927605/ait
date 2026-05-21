# hero-codex-reviewer.tape — Pillar 2: adversarial review.
# Shows the implementer's attempt blocked by a separate reviewer agent
# before `ait apply` lets it touch main. Hero moment: `ait apply`
# returns held: review gate citation, severity high finding visible.
#
# Pre-recording: run the demo once to populate state:
#   bash examples/pain-point-demos/09-1-codex-reviewer/run.sh
#   bash examples/pain-point-demos/09-1-codex-reviewer/verify.sh
# Then: vhs docs/assets/tapes/hero-codex-reviewer.tape

Output docs/assets/hero-codex-reviewer.gif
Output docs/assets/hero-codex-reviewer.mp4

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 480
Set TypingSpeed 50ms
Set PlaybackSpeed 1.0
Set Framerate 24
Set Padding 20

Hide
Type "cd examples/pain-point-demos/09-1-codex-reviewer/workspace" Enter
Type "clear" Enter
Show

Sleep 600ms

# Beat 1: high-severity finding from the separate reviewer
Type "ait review finding list --severity high --format text"
Sleep 200ms
Enter
Sleep 2200ms

Screenshot docs/assets/hero-codex-reviewer-1.png

# Beat 2: the adversarial review record itself
Type "cat ../.state/09-1-codex-reviewer/codex-adversarial-review.json | head -20"
Sleep 200ms
Enter
Sleep 2200ms

# Beat 3: the hero moment — review gate holds apply
Type "ait apply latest --mode current --json | head -10"
Sleep 200ms
Enter
Sleep 2500ms

Screenshot docs/assets/hero-codex-reviewer-2.png

Type "echo  # The implementer did not review its own work."
Sleep 200ms
Enter
Sleep 2000ms

Screenshot docs/assets/hero-codex-reviewer-3.png

Sleep 800ms
