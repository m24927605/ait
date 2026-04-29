from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path

AIT_DIRNAME = ".ait"
OBJECTS_DIRNAME = "objects"
LOCAL_CONFIG_FILENAME = "config.json"
DEFAULT_DAEMON_SOCKET_PATH = f"{AIT_DIRNAME}/daemon.sock"
GITIGNORE_ENTRY = f"{AIT_DIRNAME}/"
LOCAL_CONFIG_SCHEMA_VERSION = 2
DEFAULT_DAEMON_IDLE_TIMEOUT_SECONDS = 600


@dataclass
class LocalConfig:
    schema_version: int = LOCAL_CONFIG_SCHEMA_VERSION
    install_nonce: str = ""
    repo_identity: str | None = None
    daemon_socket_path: str = DEFAULT_DAEMON_SOCKET_PATH
    reaper_ttl_seconds: int | None = None
    daemon_idle_timeout_seconds: int | None = None


def bootstrap_ait_dir(repo_root: str | Path) -> Path:
    root = Path(repo_root).resolve()
    ait_dir = root / AIT_DIRNAME
    (ait_dir / OBJECTS_DIRNAME).mkdir(parents=True, exist_ok=True)
    return ait_dir


def local_config_path(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / AIT_DIRNAME / LOCAL_CONFIG_FILENAME


def load_local_config(repo_root: str | Path) -> LocalConfig | None:
    config_path = local_config_path(repo_root)
    if not config_path.exists():
        return None

    data = json.loads(config_path.read_text(encoding="utf-8"))
    return LocalConfig(
        schema_version=int(data.get("schema_version", LOCAL_CONFIG_SCHEMA_VERSION)),
        install_nonce=str(data["install_nonce"]),
        repo_identity=_coerce_optional_str(data.get("repo_identity")),
        daemon_socket_path=str(
            data.get("daemon_socket_path", DEFAULT_DAEMON_SOCKET_PATH)
        ),
        reaper_ttl_seconds=_coerce_optional_int(data.get("reaper_ttl_seconds")),
        daemon_idle_timeout_seconds=_coerce_optional_int(data.get("daemon_idle_timeout_seconds")),
    )


def save_local_config(repo_root: str | Path, config: LocalConfig) -> Path:
    bootstrap_ait_dir(repo_root)
    config_path = local_config_path(repo_root)
    payload = asdict(config)
    config_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config_path


def ensure_local_config(repo_root: str | Path) -> LocalConfig:
    existing = load_local_config(repo_root)
    if existing is None:
        config = LocalConfig(install_nonce=_generate_install_nonce())
        save_local_config(repo_root, config)
        return config

    updated = LocalConfig(
        schema_version=LOCAL_CONFIG_SCHEMA_VERSION,
        install_nonce=existing.install_nonce or _generate_install_nonce(),
        repo_identity=existing.repo_identity,
        daemon_socket_path=existing.daemon_socket_path or DEFAULT_DAEMON_SOCKET_PATH,
        reaper_ttl_seconds=existing.reaper_ttl_seconds,
        daemon_idle_timeout_seconds=existing.daemon_idle_timeout_seconds,
    )
    if updated != existing:
        save_local_config(repo_root, updated)
    return updated


def ensure_repo_identity(repo_root: str | Path, repo_identity: str) -> LocalConfig:
    if not repo_identity:
        raise ValueError("repo_identity is required.")
    config = ensure_local_config(repo_root)
    if config.repo_identity == repo_identity:
        return config
    if config.repo_identity and not (
        config.repo_identity.startswith("unborn:")
        and not repo_identity.startswith("unborn:")
    ):
        return config
    updated = LocalConfig(
        schema_version=LOCAL_CONFIG_SCHEMA_VERSION,
        install_nonce=config.install_nonce,
        repo_identity=repo_identity,
        daemon_socket_path=config.daemon_socket_path,
        reaper_ttl_seconds=config.reaper_ttl_seconds,
        daemon_idle_timeout_seconds=config.daemon_idle_timeout_seconds,
    )
    save_local_config(repo_root, updated)
    return updated


def ensure_ait_ignored(repo_root: str | Path) -> bool:
    gitignore_path = Path(repo_root).resolve() / ".gitignore"
    if gitignore_path.exists():
        lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    if any(line.strip() == GITIGNORE_ENTRY for line in lines):
        return False

    new_lines = list(lines)
    if new_lines and new_lines[-1] != "":
        new_lines.append("")
    new_lines.append(GITIGNORE_ENTRY)
    gitignore_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def _generate_install_nonce() -> str:
    return secrets.token_hex(16)


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
