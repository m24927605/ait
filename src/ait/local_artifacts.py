from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess


DEFAULT_MAX_AUTO_COPY_BYTES = 64 * 1024

_GENERATED_DIR_NAMES = {
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "venv",
}

_SAFE_AUTO_COPY_FILES = {
    ".vscode/settings.json",
}

_SECRET_PATH_PARTS = {
    "credential",
    "credentials",
    "secret",
    "secrets",
    "token",
    "tokens",
}

_SECRET_KEY_PARTS = {
    "api_key",
    "apikey",
    "auth_token",
    "client_secret",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
}


@dataclass(frozen=True, slots=True)
class LocalArtifact:
    path: str
    kind: str
    size_bytes: int | None
    git_status: str
    is_text: bool
    secret_risk: bool


@dataclass(frozen=True, slots=True)
class ArtifactDecision:
    path: str
    action: str
    reason: str
    destination: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    detected: tuple[str, ...] = ()
    copied: tuple[ArtifactDecision, ...] = ()
    skipped: tuple[ArtifactDecision, ...] = ()
    pending: tuple[ArtifactDecision, ...] = ()
    blocked: tuple[ArtifactDecision, ...] = ()
    cleanup_allowed: bool = True


@dataclass(frozen=True, slots=True)
class ArtifactRecommendation:
    action: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RedactedArtifactMetadata:
    path: str
    kind: str
    size_bytes: int | None
    git_status: str
    is_text: bool
    secret_risk: bool
    env_keys: tuple[str, ...] = ()


def reconcile_local_artifacts(
    source_root: str | Path,
    destination_root: str | Path,
    *,
    max_auto_copy_bytes: int = DEFAULT_MAX_AUTO_COPY_BYTES,
    recommender=None,
) -> ReconciliationReport:
    source = Path(source_root).resolve()
    destination = Path(destination_root).resolve()
    artifacts = scan_local_artifacts(source)
    decisions = [
        decide_artifact(
            artifact,
            source,
            destination,
            max_auto_copy_bytes=max_auto_copy_bytes,
            recommender=recommender,
        )
        for artifact in artifacts
    ]
    copied: list[ArtifactDecision] = []
    skipped: list[ArtifactDecision] = []
    pending: list[ArtifactDecision] = []
    blocked: list[ArtifactDecision] = []
    for decision in decisions:
        if decision.action == "copy":
            _copy_artifact(source, destination, decision.path)
            copied.append(decision)
        elif decision.action == "skip":
            skipped.append(decision)
        elif decision.action == "pending":
            pending.append(decision)
        else:
            blocked.append(decision)
    return ReconciliationReport(
        detected=tuple(artifact.path for artifact in artifacts),
        copied=tuple(copied),
        skipped=tuple(skipped),
        pending=tuple(pending),
        blocked=tuple(blocked),
        cleanup_allowed=not pending and not blocked,
    )


def scan_local_artifacts(worktree_root: str | Path) -> tuple[LocalArtifact, ...]:
    root = Path(worktree_root).resolve()
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--ignored", "--untracked-files=normal", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return ()
    artifacts: list[LocalArtifact] = []
    for raw_entry in completed.stdout.split(b"\0"):
        if not raw_entry:
            continue
        status = raw_entry[:2].decode("ascii", errors="replace")
        if status not in {"!!", "??"}:
            continue
        raw_path = raw_entry[3:].decode("utf-8", errors="surrogateescape")
        rel_path = _normalize_relative_path(raw_path)
        if rel_path is None:
            continue
        git_status = "ignored" if status == "!!" else "untracked"
        for expanded_path in _expand_artifact_path(root, rel_path):
            artifacts.append(_inspect_artifact(root, expanded_path, git_status))
    return tuple(sorted(artifacts, key=lambda artifact: artifact.path))


def decide_artifact(
    artifact: LocalArtifact,
    source_root: str | Path,
    destination_root: str | Path,
    *,
    max_auto_copy_bytes: int = DEFAULT_MAX_AUTO_COPY_BYTES,
    recommender=None,
) -> ArtifactDecision:
    source = Path(source_root).resolve()
    destination = Path(destination_root).resolve()
    source_path = _safe_join(source, artifact.path)
    destination_path = _safe_join(destination, artifact.path)

    hard_decision = _hard_guardrail_decision(
        artifact,
        source_path,
        destination_path,
        max_auto_copy_bytes=max_auto_copy_bytes,
    )
    if hard_decision is not None:
        return hard_decision

    recommendation = None
    if recommender is not None:
        recommendation = recommender(redacted_metadata_for(artifact, source_path))
    if recommendation is not None and recommendation.action == "skip":
        return ArtifactDecision(artifact.path, "skip", recommendation.reason or "classifier recommended skip")

    if artifact.path in _SAFE_AUTO_COPY_FILES:
        return ArtifactDecision(
            artifact.path,
            "copy",
            "small editor settings file",
            destination=artifact.path,
        )
    return ArtifactDecision(
        artifact.path,
        "pending",
        "local file requires confirmation before cleanup",
        destination=artifact.path,
    )


def redacted_metadata_for(artifact: LocalArtifact, source_path: str | Path) -> RedactedArtifactMetadata:
    path = Path(source_path)
    return RedactedArtifactMetadata(
        path=artifact.path,
        kind=artifact.kind,
        size_bytes=artifact.size_bytes,
        git_status=artifact.git_status,
        is_text=artifact.is_text,
        secret_risk=artifact.secret_risk,
        env_keys=_read_env_keys(path) if artifact.is_text else (),
    )


def _hard_guardrail_decision(
    artifact: LocalArtifact,
    source_path: Path,
    destination_path: Path,
    *,
    max_auto_copy_bytes: int,
) -> ArtifactDecision | None:
    if _is_git_or_ait_path(artifact.path):
        return ArtifactDecision(artifact.path, "skip", "AIT or Git-owned path")
    if _is_generated_path(artifact.path):
        return ArtifactDecision(artifact.path, "skip", "generated dependency or build artifact")
    if artifact.kind == "symlink":
        return ArtifactDecision(artifact.path, "blocked", "symlink is not copied automatically")
    if artifact.kind == "directory":
        return ArtifactDecision(artifact.path, "skip", "directory is not copied automatically")
    if artifact.kind != "file":
        return ArtifactDecision(artifact.path, "blocked", "unsupported artifact type")
    if artifact.size_bytes is None or artifact.size_bytes > max_auto_copy_bytes:
        return ArtifactDecision(artifact.path, "blocked", "file exceeds safe auto-copy size")
    if not artifact.is_text:
        return ArtifactDecision(artifact.path, "blocked", "binary file is not copied automatically")
    if artifact.secret_risk:
        return ArtifactDecision(
            artifact.path,
            "pending",
            "file may contain secrets and requires confirmation",
            destination=artifact.path,
        )
    if destination_path.exists() and source_path.read_bytes() != destination_path.read_bytes():
        return ArtifactDecision(
            artifact.path,
            "pending",
            "destination already exists with different content",
            destination=artifact.path,
        )
    if destination_path.exists():
        return ArtifactDecision(artifact.path, "skip", "destination already has identical content")
    return None


def _inspect_artifact(root: Path, rel_path: str, git_status: str) -> LocalArtifact:
    path = _safe_join(root, rel_path)
    if path.is_symlink():
        kind = "symlink"
        size = None
        is_text = False
        secret_risk = _path_has_secret_risk(rel_path)
    elif path.is_dir():
        kind = "directory"
        size = None
        is_text = False
        secret_risk = _path_has_secret_risk(rel_path)
    elif path.is_file():
        kind = "file"
        size = path.stat().st_size
        text = _read_text_sample(path)
        is_text = text is not None
        secret_risk = _path_has_secret_risk(rel_path) or (text is not None and _text_has_secret_risk(text))
    elif path.exists():
        kind = "other"
        size = None
        is_text = False
        secret_risk = _path_has_secret_risk(rel_path)
    else:
        kind = "missing"
        size = None
        is_text = False
        secret_risk = _path_has_secret_risk(rel_path)
    return LocalArtifact(
        path=rel_path,
        kind=kind,
        size_bytes=size,
        git_status=git_status,
        is_text=is_text,
        secret_risk=secret_risk,
    )


def _expand_artifact_path(root: Path, rel_path: str) -> tuple[str, ...]:
    path = _safe_join(root, rel_path)
    if (
        path.is_dir()
        and not path.is_symlink()
        and not _is_generated_path(rel_path)
        and not _is_git_or_ait_path(rel_path)
    ):
        expanded: list[str] = []
        for child in sorted(path.rglob("*")):
            if child.is_file() or child.is_symlink():
                expanded.append(child.relative_to(root).as_posix())
        return tuple(expanded) or (rel_path,)
    return (rel_path,)


def _copy_artifact(source_root: Path, destination_root: Path, rel_path: str) -> None:
    source = _safe_join(source_root, rel_path)
    destination = _safe_join(destination_root, rel_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _safe_join(root: Path, rel_path: str) -> Path:
    normalized = _normalize_relative_path(rel_path)
    if normalized is None:
        raise ValueError(f"unsafe artifact path: {rel_path}")
    target = (root / normalized).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"artifact path escapes repository: {rel_path}")
    return target


def _normalize_relative_path(path: str) -> str | None:
    cleaned = path.replace("\\", "/").strip("/")
    if not cleaned or cleaned.startswith("../") or "/../" in f"/{cleaned}/":
        return None
    if cleaned in {".", ".."}:
        return None
    return cleaned


def _is_git_or_ait_path(path: str) -> bool:
    first = path.split("/", 1)[0]
    return first in {".git", ".ait"}


def _is_generated_path(path: str) -> bool:
    return any(part in _GENERATED_DIR_NAMES for part in path.split("/"))


def _path_has_secret_risk(path: str) -> bool:
    lowered = path.lower()
    name = Path(path).name.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    return any(part in lowered for part in _SECRET_PATH_PARTS)


def _text_has_secret_risk(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip().lower()
        if any(part in key for part in _SECRET_KEY_PARTS):
            return True
    return False


def _read_text_sample(path: Path, *, limit: int = 8192) -> str | None:
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _read_env_keys(path: Path) -> tuple[str, ...]:
    text = _read_text_sample(path)
    if text is None:
        return ()
    keys: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.append(stripped.split("=", 1)[0].strip())
    return tuple(keys)
