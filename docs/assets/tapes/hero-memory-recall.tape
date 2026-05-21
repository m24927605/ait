# hero-memory-recall.tape — Pillar 3: shared + long-term memory.
# Hero moment: the same proof string appears in Claude's notes file and
# in Codex's later context file — both pulled from `.ait/`, not chat
# history. Same decision. Two agents. Different sessions.
#
# Pre-recording: run the demo once to populate state:
#   bash examples/pain-point-demos/04-memory-reuse/run.sh
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

# Beat 1: Claude's original finding
Type 'find .ait/workspaces -name auth-retry.md -exec grep -H AIT_PROOF_AUTH_RETRY {} \;'
Sleep 200ms
Enter
Sleep 2200ms

Screenshot docs/assets/hero-memory-recall-1.png

# Beat 2: hero moment — Codex referenced the same proof through memory
Type 'find .ait/workspaces -name context-proof.txt -exec grep -H AIT_PROOF_AUTH_RETRY {} \;'
Sleep 200ms
Enter
Sleep 2400ms

Screenshot docs/assets/hero-memory-recall-2.png

# Beat 3: caption
Type "echo  # Same decision. Two agents. Different sessions."
Sleep 200ms
Enter
Sleep 2200ms

Screenshot docs/assets/hero-memory-recall-3.png

Sleep 800ms
