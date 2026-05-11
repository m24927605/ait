# Claude Code Adapter Local Auth

The `claude-code` adapter uses the local `claude` CLI. It does not require
`ANTHROPIC_API_KEY` for normal agent operation.

The adversarial reviewer path follows the same local-auth rule:

```sh
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
```

This invokes the local `claude -p` command and removes `ANTHROPIC_API_KEY`
from that child process environment so AIT does not silently fall back to
provider API credits. If you intentionally want a different reviewer command,
configure it explicitly under `review.adapters`.

Diagnostic command:

```sh
ait adapter doctor claude-code --json
```

The JSON includes:

- `agent_auth.auth_mode`
- `agent_auth.actual_command`
- `agent_auth.local_cli_available`
- `agent_auth.active_binary`
- `agent_auth.real_binary`
- `agent_auth.api_key_env_present`
- `agent_auth.will_use_api_key`
- `agent_auth.will_fallback_to_credits`
- `agent_auth.failure_reason`
- `agent_auth.recommended_fix`

Expected local CLI mode:

```json
{
  "auth_mode": "local_cli",
  "will_use_api_key": false,
  "will_fallback_to_credits": false
}
```

If unavailable, install Claude Code, run the local login flow, and retry:

```sh
ait adapter doctor claude-code --json
```
