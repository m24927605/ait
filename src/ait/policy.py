from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex

from ait.config import local_config_path

RUN_APPLY_VALUES = {"never", "ask", "auto", "current", "branch"}
EFFECTIVE_RUN_APPLY_VALUES = {"never", "auto", "current", "branch"}
APPLY_DIRTY_STRATEGY_VALUES = {"hold", "safe-patch"}
APPLY_INTEGRATION_ATTEMPT_VALUES = {"manual", "auto"}
APPLY_SEMANTIC_INTEGRATION_VALUES = {"off", "manual", "auto"}
REVIEW_DEFAULT_MODE_VALUES = {"never", "risk-based", "light", "adversarial", "multi"}
MEMORY_RERANKER_MODES = {"fallback", "fail-closed"}
DEFAULT_MEMORY_RERANKER_TIMEOUT_SECONDS = 5


@dataclass(frozen=True, slots=True)
class EffectivePolicy:
    policy: dict[str, object]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MemoryRerankerPolicy:
    enabled: bool = False
    command: tuple[str, ...] = ()
    timeout_seconds: int | float = DEFAULT_MEMORY_RERANKER_TIMEOUT_SECONDS
    mode: str = "fallback"
    env_allowlist: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.command)


def repo_policy(repo_root: str | Path) -> dict[str, object]:
    path = local_config_path(repo_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def run_apply_policy(repo_root: str | Path, explicit: str | None = None) -> str:
    if explicit is not None:
        return explicit
    run_config = repo_policy(repo_root).get("run")
    if not isinstance(run_config, dict):
        return "never"
    value = str(run_config.get("apply", "never")).strip().lower()
    if value == "ask":
        return "never"
    return value if value in {"never", "auto", "current", "branch"} else "never"


def run_auto_prune(repo_root: str | Path) -> bool:
    run_config = repo_policy(repo_root).get("run")
    if not isinstance(run_config, dict):
        return True
    return bool(run_config.get("auto_prune", True))


def apply_dirty_strategy(repo_root: str | Path) -> str:
    apply_config = repo_policy(repo_root).get("apply")
    if not isinstance(apply_config, dict):
        return "safe-patch"
    value = str(apply_config.get("dirty_strategy", "safe-patch")).strip().lower()
    return value if value in {"hold", "safe-patch"} else "safe-patch"


def apply_integration_attempt(repo_root: str | Path) -> str:
    apply_config = repo_policy(repo_root).get("apply")
    if not isinstance(apply_config, dict):
        return "manual"
    value = str(apply_config.get("integration_attempt", "manual")).strip().lower()
    return value if value in {"manual", "auto"} else "manual"


def apply_cleanup_after_apply(repo_root: str | Path) -> bool:
    apply_config = repo_policy(repo_root).get("apply")
    if not isinstance(apply_config, dict):
        return True
    return bool(apply_config.get("cleanup_after_apply", True))


def apply_semantic_integration(repo_root: str | Path) -> str:
    apply_config = repo_policy(repo_root).get("apply")
    if not isinstance(apply_config, dict):
        return "off"
    value = str(apply_config.get("semantic_integration", "off")).strip().lower()
    return value if value in {"off", "manual", "auto"} else "off"


def integration_allow_untracked_replay(repo_root: str | Path) -> bool:
    integration = repo_policy(repo_root).get("integration")
    if not isinstance(integration, dict):
        return False
    return bool(integration.get("allow_untracked_replay", False))


def integration_allow_binary_merge(repo_root: str | Path) -> bool:
    integration = repo_policy(repo_root).get("integration")
    if not isinstance(integration, dict):
        return False
    return bool(integration.get("allow_binary_merge", False))


def integration_allow_delete_merge(repo_root: str | Path) -> bool:
    integration = repo_policy(repo_root).get("integration")
    if not isinstance(integration, dict):
        return False
    return bool(integration.get("allow_delete_merge", False))


def integration_auto_test_command(repo_root: str | Path) -> str | None:
    integration = repo_policy(repo_root).get("integration")
    if not isinstance(integration, dict):
        return None
    value = integration.get("auto_test_command")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def integration_auto_test_shell(repo_root: str | Path) -> bool:
    """Whether ``integration.auto_test_command`` runs through /bin/sh -lc.

    Defaults to False: the command is parsed via :func:`shlex.split` and
    executed without a shell, eliminating shell-injection risk from a
    hostile ``policy.json`` on a shared CI runner. Set
    ``integration.auto_test_shell: true`` in policy to opt in if the
    command genuinely needs shell features (pipes, redirects, env
    expansion).
    """
    integration = repo_policy(repo_root).get("integration")
    if not isinstance(integration, dict):
        return False
    return bool(integration.get("auto_test_shell", False))


def integration_semantic_adapter(repo_root: str | Path) -> str | None:
    if apply_semantic_integration(repo_root) == "off":
        return None
    integration = repo_policy(repo_root).get("integration")
    if not isinstance(integration, dict):
        return None
    value = integration.get("semantic_adapter")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def memory_reranker_policy(repo_root: str | Path, *, mode: str | None = None) -> MemoryRerankerPolicy:
    memory_config = repo_policy(repo_root).get("memory")
    if not isinstance(memory_config, dict):
        return MemoryRerankerPolicy(mode=_reranker_mode(mode))
    reranker_config = memory_config.get("reranker")
    if not isinstance(reranker_config, dict):
        return MemoryRerankerPolicy(mode=_reranker_mode(mode))
    return _memory_reranker_policy_from_mapping(reranker_config, mode_override=mode)


def effective_policy(repo_root: str | Path) -> EffectivePolicy:
    payload = repo_policy(repo_root)
    warnings: list[str] = []

    run_config = _section(payload, "run", warnings)
    apply_config = _section(payload, "apply", warnings)
    integration_config = _section(payload, "integration", warnings)
    memory_config = _section(payload, "memory", warnings)
    memory_reranker_config = _section(memory_config, "reranker", warnings, display_name="memory.reranker")
    review_config = _section(payload, "review", warnings)
    review_baseline_config = _section(review_config, "baseline", warnings, display_name="review.baseline")
    review_adapters_config = _section(review_config, "adapters", warnings, display_name="review.adapters")

    run_apply_raw = _str_value(run_config, "apply", "never")
    run_apply = run_apply_raw if run_apply_raw in RUN_APPLY_VALUES else "never"
    if run_apply_raw not in RUN_APPLY_VALUES:
        warnings.append("run.apply invalid; using never")
    if run_apply == "ask":
        warnings.append("run.apply ask is non-interactive; using never")
        run_apply_effective = "never"
    else:
        run_apply_effective = run_apply if run_apply in EFFECTIVE_RUN_APPLY_VALUES else "never"

    dirty_raw = _str_value(apply_config, "dirty_strategy", "safe-patch")
    dirty = dirty_raw if dirty_raw in APPLY_DIRTY_STRATEGY_VALUES else "safe-patch"
    if dirty_raw not in APPLY_DIRTY_STRATEGY_VALUES:
        warnings.append("apply.dirty_strategy invalid; using safe-patch")

    integration_attempt_raw = _str_value(apply_config, "integration_attempt", "manual")
    integration_attempt = (
        integration_attempt_raw
        if integration_attempt_raw in APPLY_INTEGRATION_ATTEMPT_VALUES
        else "manual"
    )
    if integration_attempt_raw not in APPLY_INTEGRATION_ATTEMPT_VALUES:
        warnings.append("apply.integration_attempt invalid; using manual")

    semantic_raw = _str_value(apply_config, "semantic_integration", "off")
    semantic = semantic_raw if semantic_raw in APPLY_SEMANTIC_INTEGRATION_VALUES else "off"
    if semantic_raw not in APPLY_SEMANTIC_INTEGRATION_VALUES:
        warnings.append("apply.semantic_integration invalid; using off")

    review_default_mode_raw = _str_value(review_config, "default_mode", "never")
    review_default_mode = (
        review_default_mode_raw
        if review_default_mode_raw in REVIEW_DEFAULT_MODE_VALUES
        else "never"
    )
    if review_default_mode_raw not in REVIEW_DEFAULT_MODE_VALUES:
        warnings.append("review.default_mode invalid; using never")

    return EffectivePolicy(
        policy={
            "run": {
                "apply": run_apply_effective,
                "configured_apply": run_apply_raw,
                "auto_prune": _bool_value(run_config, "auto_prune", True),
            },
            "apply": {
                "dirty_strategy": dirty,
                "integration_attempt": integration_attempt,
                "cleanup_after_apply": _bool_value(apply_config, "cleanup_after_apply", True),
                "semantic_integration": semantic,
            },
            "integration": {
                "allow_untracked_replay": _bool_value(integration_config, "allow_untracked_replay", False),
                "allow_binary_merge": _bool_value(integration_config, "allow_binary_merge", False),
                "allow_delete_merge": _bool_value(integration_config, "allow_delete_merge", False),
                "auto_test_command": _optional_str(integration_config.get("auto_test_command")),
                "auto_test_shell": _bool_value(integration_config, "auto_test_shell", False),
                "semantic_adapter": None if semantic == "off" else _optional_str(integration_config.get("semantic_adapter")),
            },
            "memory": {
                "reranker": _memory_reranker_effective_value(
                    memory_reranker_config,
                    warnings,
                    "memory.reranker",
                ),
            },
            "review": {
                "default_mode": review_default_mode,
                "sensitive_paths": _string_list_value(review_config, "sensitive_paths", warnings, "review.sensitive_paths"),
                "required_profiles": _profile_mapping_value(review_config, "required_profiles", warnings, "review.required_profiles"),
                "auto_apply_requires_review": _bool_config_value(
                    review_config,
                    "auto_apply_requires_review",
                    False,
                    warnings,
                    "review.auto_apply_requires_review",
                ),
                "allow_override": _bool_config_value(
                    review_config,
                    "allow_override",
                    True,
                    warnings,
                    "review.allow_override",
                ),
                "baseline": {
                    "require_approved_facts": _bool_config_value(
                        review_baseline_config,
                        "require_approved_facts",
                        True,
                        warnings,
                        "review.baseline.require_approved_facts",
                    ),
                    "allow_candidate_memory": _bool_config_value(
                        review_baseline_config,
                        "allow_candidate_memory",
                        False,
                        warnings,
                        "review.baseline.allow_candidate_memory",
                    ),
                    "include_prior_failed_attempts": _bool_config_value(
                        review_baseline_config,
                        "include_prior_failed_attempts",
                        True,
                        warnings,
                        "review.baseline.include_prior_failed_attempts",
                    ),
                    "include_prior_review_findings": _bool_config_value(
                        review_baseline_config,
                        "include_prior_review_findings",
                        True,
                        warnings,
                        "review.baseline.include_prior_review_findings",
                    ),
                },
                "adapters": _adapter_mapping_value(
                    review_adapters_config,
                    warnings,
                    "review.adapters",
                ),
            },
        },
        warnings=tuple(warnings),
    )


def _section(
    payload: dict[str, object],
    name: str,
    warnings: list[str],
    *,
    display_name: str | None = None,
) -> dict[str, object]:
    value = payload.get(name)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    warnings.append(f"{display_name or name} section invalid; using defaults")
    return {}


def _str_value(section: dict[str, object], key: str, default: str) -> str:
    return str(section.get(key, default)).strip().lower()


def _bool_value(section: dict[str, object], key: str, default: bool) -> bool:
    value = section.get(key)
    if value is None:
        return default
    return bool(value)


def _bool_config_value(
    section: dict[str, object],
    key: str,
    default: bool,
    warnings: list[str],
    warning_key: str,
) -> bool:
    value = section.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    warnings.append(f"{warning_key} invalid; using {str(default).lower()}")
    return default


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _reranker_mode(value: str | None) -> str:
    if value is None:
        return "fallback"
    text = str(value).strip().lower()
    return text if text in MEMORY_RERANKER_MODES else "fallback"


def _memory_reranker_policy_from_mapping(
    raw_config: dict[str, object],
    *,
    mode_override: str | None = None,
) -> MemoryRerankerPolicy:
    enabled = raw_config.get("enabled")
    if enabled is not True:
        return MemoryRerankerPolicy(mode=_reranker_mode(mode_override))
    command = _reranker_command_tuple(raw_config)
    if not command:
        return MemoryRerankerPolicy(mode=_reranker_mode(mode_override))
    timeout = raw_config.get("timeout_seconds", DEFAULT_MEMORY_RERANKER_TIMEOUT_SECONDS)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        timeout = DEFAULT_MEMORY_RERANKER_TIMEOUT_SECONDS
    env_allowlist = raw_config.get("env_allowlist")
    mode = _reranker_mode(mode_override or _optional_str(raw_config.get("mode")))
    return MemoryRerankerPolicy(
        enabled=True,
        command=command,
        timeout_seconds=timeout,
        mode=mode,
        env_allowlist=tuple(str(item) for item in env_allowlist if str(item).strip())
        if isinstance(env_allowlist, list)
        else (),
    )


def _reranker_command_tuple(raw_config: dict[str, object]) -> tuple[str, ...]:
    command_text = _optional_str(raw_config.get("command"))
    if command_text is None:
        return ()
    try:
        command = tuple(shlex.split(command_text))
    except ValueError:
        return ()
    if not command:
        return ()
    args = raw_config.get("args")
    if isinstance(args, list):
        command = (*command, *(str(item) for item in args))
    return command


def _memory_reranker_effective_value(
    raw_config: dict[str, object],
    warnings: list[str],
    warning_key: str,
) -> dict[str, object]:
    enabled = _bool_config_value(raw_config, "enabled", False, warnings, f"{warning_key}.enabled")
    command = _reranker_command_tuple(raw_config) if enabled else ()
    if enabled and not command:
        warnings.append(f"{warning_key}.command missing or invalid; disabling reranker")
        enabled = False
    timeout = raw_config.get("timeout_seconds", DEFAULT_MEMORY_RERANKER_TIMEOUT_SECONDS)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        warnings.append(
            f"{warning_key}.timeout_seconds invalid; using {DEFAULT_MEMORY_RERANKER_TIMEOUT_SECONDS}"
        )
        timeout = DEFAULT_MEMORY_RERANKER_TIMEOUT_SECONDS
    mode = _optional_str(raw_config.get("mode")) or "fallback"
    if mode not in MEMORY_RERANKER_MODES:
        warnings.append(f"{warning_key}.mode invalid; using fallback")
        mode = "fallback"
    env_allowlist = raw_config.get("env_allowlist")
    if env_allowlist is not None and not isinstance(env_allowlist, list):
        warnings.append(f"{warning_key}.env_allowlist invalid; using []")
        env_allowlist = []
    return {
        "enabled": enabled,
        "command": list(command) if enabled else [],
        "timeout_seconds": timeout,
        "mode": mode,
        "env_allowlist": [str(item) for item in env_allowlist]
        if isinstance(env_allowlist, list)
        else [],
    }


def _string_list_value(
    section: dict[str, object],
    key: str,
    warnings: list[str],
    warning_key: str,
) -> list[str]:
    value = section.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"{warning_key} invalid; using []")
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _profile_mapping_value(
    section: dict[str, object],
    key: str,
    warnings: list[str],
    warning_key: str,
) -> dict[str, list[str]]:
    value = section.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(f"{warning_key} invalid; using {{}}")
        return {}
    result: dict[str, list[str]] = {}
    allowed = {"security", "regression", "maintainability", "release"}
    for pattern, raw_profiles in value.items():
        if not isinstance(raw_profiles, list):
            warnings.append(f"{warning_key}.{pattern} invalid; ignoring")
            continue
        profiles = [str(item).strip() for item in raw_profiles if str(item).strip() in allowed]
        if profiles:
            result[str(pattern)] = profiles
    return result


def _adapter_mapping_value(
    section: dict[str, object],
    warnings: list[str],
    warning_key: str,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name, raw_config in section.items():
        if not isinstance(raw_config, dict):
            warnings.append(f"{warning_key}.{name} invalid; ignoring")
            continue
        command = _optional_str(raw_config.get("command"))
        if command is None:
            warnings.append(f"{warning_key}.{name}.command missing; ignoring")
            continue
        timeout = raw_config.get("timeout_seconds", 300)
        if not isinstance(timeout, int) or timeout <= 0:
            warnings.append(f"{warning_key}.{name}.timeout_seconds invalid; using 300")
            timeout = 300
        args = raw_config.get("args")
        if args is not None and not isinstance(args, list):
            warnings.append(f"{warning_key}.{name}.args invalid; using []")
            args = []
        env_allowlist = raw_config.get("env_allowlist")
        if env_allowlist is not None and not isinstance(env_allowlist, list):
            warnings.append(f"{warning_key}.{name}.env_allowlist invalid; using []")
            env_allowlist = []
        result[str(name)] = {
            "command": command,
            "args": [str(item) for item in args] if isinstance(args, list) else [],
            "timeout_seconds": timeout,
            "env_allowlist": [str(item) for item in env_allowlist]
            if isinstance(env_allowlist, list)
            else [],
            "cwd": _optional_str(raw_config.get("cwd")),
            "output": _optional_str(raw_config.get("output")) or "json",
        }
    return result
