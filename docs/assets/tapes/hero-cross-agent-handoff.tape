# hero-cross-agent-handoff.tape — Pillar 1: multi-agent communication.
# Hero moment: the same proof string appears in AGENTS.md (written by
# Claude) and in handoff-proof.txt (written by Codex). Codex never
# opened AGENTS.md — it received the decision through AIT's handoff
# file. Two agents. One reproducible handoff.
#
# Pre-recording: run the demo once to populate state:
#   bash examples/pain-point-demos/07-cross-agent-handoff/run.sh
# Then: vhs docs/assets/tapes/hero-cross-agent-handoff.tape

Output docs/assets/hero-cross-agent-handoff.gif
Output docs/assets/hero-cross-agent-handoff.mp4

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 480
Set TypingSpeed 50ms
Set PlaybackSpeed 1.0
Set Framerate 24
Set Padding 20

Hide
Type "cd examples/pain-point-demos/07-cross-agent-handoff/workspace" Enter
Type "clear" Enter
Show

Sleep 600ms

# Beat 1: Claude's decision, promoted to AGENTS.md
Type "grep AIT_HANDOFF_PROOF AGENTS.md"
Sleep 200ms
Enter
Sleep 1800ms

Screenshot docs/assets/hero-cross-agent-handoff-1.png

# Beat 2: hero moment — Codex copied the same string into handoff-proof.txt
Type 'find .ait/workspaces -name handoff-proof.txt -exec grep -H AIT_HANDOFF_PROOF {} \;'
Sleep 200ms
Enter
Sleep 2400ms

Screenshot docs/assets/hero-cross-agent-handoff-2.png

# Beat 3: caption
Type "echo  # Same proof. Two agents. One handoff file."
Sleep 200ms
Enter
Sleep 2200ms

Screenshot docs/assets/hero-cross-agent-handoff-3.png

Sleep 800ms
