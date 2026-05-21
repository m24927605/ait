# smoke-test.tape — verify vhs toolchain works on this machine.
# Produces a tiny GIF showing `ait --version` and a simple command.
# Does NOT need Claude/Codex API authentication.
# Run: vhs docs/assets/tapes/smoke-test.tape

Output docs/assets/smoke-test.gif

Set Shell "bash"
Set FontSize 14
Set Width 900
Set Height 300
Set TypingSpeed 60ms
Set PlaybackSpeed 1.0
Set Framerate 24
Set Padding 20

Sleep 500ms

Type "ait --version"
Sleep 300ms
Enter
Sleep 1200ms

Type "ait --help | head -5"
Sleep 300ms
Enter
Sleep 1500ms

Sleep 800ms
