# hero-memory-recall.tape — Pillar 3: shared + long-term memory.
# Shows Claude's earlier decision in notes/auth-retry.md surfacing in a
# later Codex run via `ait memory recall`. Hero moment: the same proof
# string appears in two attempts from two different agents — handoff
# through repo-local memory, not chat history.
#
# Pre-recording: run the demo once to populate state:
#   bash examples/pain-point-demos/04-memory-reuse/run.sh
#   bash examples/pain-point-demos/04-memory-reuse/verify.sh
# Then: vhs docs/assets/tapes/hero-memory-recall.tape

Output docs/assets/hero-memory-recall.gif
Output docs/assets/hero-memory-recall.mp4

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 480
Set TypingSpeed 50ms
Set PlaybackSpeed 1.0
Set Framerate 24
Set Padding 20

Hide
Type "cd examples/pain-point-demos/04-memory-reuse/workspace" Enter
Type "clear" Enter
Show

Sleep 600ms

# Beat 1: prior decision is queryable, not lost
Type "ait memory recall 'auth retry'"
Sleep 200ms
Enter
Sleep 2400ms

Screenshot docs/assets/hero-memory-recall-1.png

# Beat 2: Claude's original finding
Type "cat notes/auth-retry.md 2>/dev/null || \\"
Enter
Type '  find ../../../.ait/workspaces -name auth-retry.md -exec cat {} \;'
Sleep 200ms
Enter
Sleep 2000ms

# Beat 3: Codex (later run) referenced the same proof through memory
Type 'find ../../../.ait/workspaces -name context-proof.txt -exec cat {} \;'
Sleep 200ms
Enter
Sleep 2200ms

Screenshot docs/assets/hero-memory-recall-2.png

Type "echo  # Same decision, two agents, different sessions."
Sleep 200ms
Enter
Sleep 2000ms

Screenshot docs/assets/hero-memory-recall-3.png

Sleep 800ms
