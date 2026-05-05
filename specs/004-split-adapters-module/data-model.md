# Data Model: Split Adapters Module

## AgentAdapter

Public metadata for one supported adapter.

Fields:

- `name`
- `default_agent_id`
- `default_with_context`
- `command_name`
- `env`
- `native_hooks`
- `description`
- `setup_hint`

## AdapterDoctorCheck

Public result for one doctor condition.

Fields:

- `name`
- `ok`
- `detail`

## AdapterDoctorResult

Public aggregate result for native adapter setup readiness.

Fields:

- `adapter`
- `checks`

Rule:

- `ok` is true only when every check is true.

## AutomationDoctorResult

Public aggregate result for wrapper and shell automation readiness.

Fields:

- `adapter`
- `checks`

Rules:

- Required checks include Git repository, AIT importability, wrapper file, and
  real binary discovery.
- Claude Code uses `real_claude_binary`; other fixed-binary adapters use
  `real_agent_binary`.
- The shell must have either the path wrapper active or the direnv environment
  loaded.

## AdapterSetupResult

Public result describing setup output.

Fields:

- `adapter`
- `hook_path`
- `settings_path`
- `wrapper_path`
- `direnv_path`
- `settings`
- `wrote_files`

## AdapterBootstrapResult

Public result describing bootstrap output.

Fields:

- `adapter`
- `setup`
- `checks`
- `next_steps`

Rule:

- `ok` reflects Git repository, wrapper file, and real binary readiness.

## AdapterAutoEnableResult

Public result describing automatic enablement.

Fields:

- `installed`
- `skipped`
- `shell_snippet`

Rule:

- `ok` is true only when at least one adapter was installed and every installed
  bootstrap result is ready.

## Adapter Registry

Supported adapter metadata keyed by canonical name.

Validation:

- `shell` remains the default when no adapter name is supplied.
- Listing order is sorted by adapter name.
- Unknown names raise `AdapterError` with the supported choices.

## Adapter Resource

Generated hook or settings content loaded from packaged resources.

Validation:

- Resource existence checks are read-only.
- Settings merge preserves existing unrelated settings and appends generated
  hook entries only when missing.

## Wrapper Environment

Generated wrapper scripts, `.envrc`, and real agent binary state.

Validation:

- Real binary discovery skips the generated wrapper path.
- Wrapper scripts preserve failure messages and exit codes.
- `.envrc` updates are idempotent and preserve existing content.
