from __future__ import annotations

import json
from pathlib import Path

from ait.config import local_config_path


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
