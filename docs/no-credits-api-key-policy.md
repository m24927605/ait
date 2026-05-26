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
the local `claude -p` CLI. The built-in `codex` reviewer resolves to
`codex exec --sandbox read-only -`. Reviewer subprocesses receive a minimal
allowlisted environment by default:

- `PATH`
- local CLI auth home (`HOME`) for built-in Claude Code/Codex reviewers
- temp directory variables (`TMPDIR`, `TEMP`, `TMP`)
- locale variables (`LANG`, `LC_ALL`, `LC_CTYPE`, `LC_MESSAGES`)

Provider keys and common secret names are not inherited by default, including
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GITHUB_TOKEN`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and generic `*TOKEN*`,
`*SECRET*`, `*PASSWORD*`, or `*KEY*` names. AIT does not silently fall back to
provider API-key mode when local reviewer auth is missing.

Use repo policy `review.adapters.<name>.env_allowlist` only when you explicitly
want to pass additional non-secret variables to a local reviewer command:

```json
{
  "review": {
    "adapters": {
      "codex": {
        "env_allowlist": ["PATH", "HOME", "TMPDIR", "CODEX_HOME"]
      }
    }
  }
}
```

If a reviewer fails because local CLI auth is unavailable, install and log in
with that CLI or add the required non-secret config path variable to the
adapter allowlist.
