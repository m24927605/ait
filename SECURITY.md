# Security Policy

## Supported Versions

`ait` is currently in alpha. Only the latest published release receives
security updates.

| Version | Supported |
| ------- | --------- |
| 0.55.x  | ✅        |
| < 0.55  | ❌        |

## Reporting a Vulnerability

If you discover a security vulnerability in `ait`, please report it
privately so we can address it before public disclosure.

**How to report:**

1. Open a private security advisory at
   <https://github.com/m24927605/ait/security/advisories/new>, or
2. Email `m24927605@gmail.com` with the subject prefix `[ait security]`.

Please include:

- A description of the issue and its impact.
- Steps to reproduce.
- Affected versions, if known.
- Any suggested mitigation.

**What to expect:**

- Acknowledgement within 3 business days.
- Initial assessment within 7 business days.
- Coordinated disclosure timeline once a fix is available.

## Scope

`ait` is a local-first tool. It runs entirely on the developer's
machine, communicates with its harness daemon over a Unix socket, and
does not contact remote services. Security-relevant areas include:

- The harness daemon (`ait.daemon`) and its Unix-socket protocol.
- Hook installers that touch agent configuration files
  (`.claude/settings.json`, `.codex/hooks.json`, `.gemini/settings.json`).
- The query DSL parser (`ait.query`) handling user input.
- Workspace and worktree provisioning (`ait.workspace`).
- Memory imports of `CLAUDE.md`, `AGENTS.md`, and prior attempts.

## Out of Scope

- Vulnerabilities in upstream agent CLIs (Claude Code, Codex, Aider,
  Gemini CLI, Cursor) — please report those to their respective
  maintainers.
- Misuse of `ait` against repositories the reporter does not own.

## Acknowledgements

We will credit reporters in release notes unless anonymity is
requested.
