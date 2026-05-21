# hero-cross-agent-handoff.tape — Pillar 1: multi-agent communication.
# Shows Claude writing a decision to AGENTS.md, then Codex copying the
# exact proof string into handoff-proof.txt WITHOUT opening AGENTS.md —
# proving Codex received Claude's context through AIT, not by re-reading
# the file. Hero moment: beat 4, the two proof strings match.
#
# Pre-recording: run the demo once to populate state:
#   bash examples/pain-point-demos/07-cross-agent-handoff/run.sh
#   bash examples/pain-point-demos/07-cross-agent-handoff/verify.sh
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

# Beat 1: surface the two attempts AIT recorded
Type "ait query --on attempt 'agent.agent_id=\""
Sleep 100ms
Type "claude-code\"' --format table"
Sleep 200ms
Enter
Sleep 2000ms

Screenshot docs/assets/hero-cross-agent-handoff-1.png

# Beat 2: Claude's promoted decision in AGENTS.md
Type "cat AGENTS.md | grep AIT_HANDOFF_PROOF"
Sleep 200ms
Enter
Sleep 1800ms

# Beat 3: Codex's handoff proof — same string, different file, different agent
Type "cat ../.state/07-cross-agent-handoff/handoff-proof.txt 2>/dev/null || \\"
Enter
Type '  find ../../../.ait/workspaces -name handoff-proof.txt -exec cat {} \;'
Sleep 200ms
Enter
Sleep 2200ms

Screenshot docs/assets/hero-cross-agent-handoff-2.png

# Beat 4: Codex never opened AGENTS.md — handoff went through AIT_CONTEXT_FILE
Type "echo  # Codex received Claude's decision via the handoff file, not the source."
Sleep 200ms
Enter
Sleep 2500ms

Screenshot docs/assets/hero-cross-agent-handoff-3.png

Sleep 800ms
