# hero-codex-reviewer.tape — Pillar 2: adversarial review.
# Hero moment: ait apply held by the review gate after a separate Codex
# reviewer raises a high-severity finding on the Claude implementation.
# The implementer cannot review its own work.
#
# Pre-recording: run the demo once to populate state:
#   bash examples/pain-point-demos/09-1-codex-reviewer/run.sh
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

# Beat 1: a separate reviewer raised a high-severity finding
Type "ait review finding list --severity high --format text"
Sleep 200ms
Enter
Sleep 2400ms

Screenshot docs/assets/hero-codex-reviewer-1.png

# Beat 2: hero moment — review gate holds apply
Type "ait apply latest --mode current 2>&1 | head -8"
Sleep 200ms
Enter
Sleep 2400ms

Screenshot docs/assets/hero-codex-reviewer-2.png

# Beat 3: caption
Type "echo  # The implementer did not review its own work."
Sleep 200ms
Enter
Sleep 2200ms

Screenshot docs/assets/hero-codex-reviewer-3.png

Sleep 800ms
