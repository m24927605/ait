# No Credits/API-Key Policy Guide

AIT agent adapters should prefer local CLI authentication. For Claude Code and
Codex, adapter doctor reports API-key environment variables but does not use
them as a silent fallback.

Disable API-key mode explicitly:

```sh
export AIT_NO_API_KEY_MODE=1
```

or:

```sh
export AIT_DISABLE_API_KEY_MODE=1
```

Then inspect:

```sh
ait adapter doctor claude-code --json
ait adapter doctor codex --json
```

The doctor payload reports:

- whether an API-key env var is present
- whether API-key mode is allowed by local policy
- whether AIT would use an API key
- whether AIT would fall back to credits
- the exact command AIT will execute

For local CLI adapters, `will_use_api_key` and `will_fallback_to_credits` should
remain `false`.

For adversarial reviews, the built-in `claude-code` review adapter resolves to
the local `claude -p` CLI and strips `ANTHROPIC_API_KEY` from the reviewer child
process environment. Use repo policy `review.adapters` only when you explicitly
want to define another local reviewer command and environment allowlist.
