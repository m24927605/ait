"""CLI dispatch for `ait self-update`."""
from __future__ import annotations

import argparse
import sys
import urllib.request
import urllib.error
import json
import datetime as dt

from ait.cli_installation import package_version
from ait.self_update import (
    install_method,
    compare_versions,
    refuse_with_message,
    check_install_path_writable,
    download_and_verify,
    atomic_replace,
    load_cache,
    save_cache,
    is_cache_fresh,
    InstallPathNotWritable,
    ChecksumMismatch,
)


REPO = "m24927605/ait"
_API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def fetch_latest() -> dict:
    """Return the latest release JSON. Honors the 1h cache."""
    now = dt.datetime.now(dt.timezone.utc)
    if is_cache_fresh(now=now):
        cached = load_cache()
        if cached is not None:
            return cached["latest"]
    with urllib.request.urlopen(_API_LATEST, timeout=15) as fh:
        data = json.loads(fh.read().decode("utf-8"))
    latest = {
        "tag_name": data.get("tag_name", ""),
        "published_at": data.get("published_at", ""),
    }
    save_cache(latest, now=now)
    return latest


def handle(args: argparse.Namespace, repo_root=None, parser=None) -> int:
    method = install_method()
    if method in ("pip", "brew", "unknown"):
        return refuse_with_message(method)

    current = package_version()
    try:
        latest = fetch_latest()
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"could not check for updates: {exc}", file=sys.stderr)
        return 1
    latest_tag = latest.get("tag_name", "")
    if not latest_tag:
        print("could not determine latest tag", file=sys.stderr)
        return 1

    cmp = compare_versions(current, latest_tag)
    if cmp >= 0 and not args.force:
        print(f"already at the latest version ({current}).")
        return 0

    print(f"Update available: {current} -> {latest_tag}")
    if args.check:
        return 0

    # Confirmation
    if not args.yes:
        prompt = f"Update ait from {current} to {latest_tag}? [Y/n]: "
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("", "y", "yes"):
            print("aborted.")
            return 0

    # Target path & permission check
    from pathlib import Path
    target = Path(sys.executable).resolve()
    try:
        check_install_path_writable(target)
    except InstallPathNotWritable as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    # Resolve target binary URL + sha256 for the running platform
    import platform
    sys_platform = platform.system().lower()
    arch = platform.machine().lower()
    if sys_platform == "darwin" and arch == "arm64":
        target_name = "macos-arm64"
    elif sys_platform == "darwin" and arch in ("x86_64", "amd64"):
        target_name = "macos-x86_64"
    elif sys_platform == "linux" and arch in ("x86_64", "amd64"):
        target_name = "linux-x86_64"
    elif sys_platform == "linux" and arch in ("aarch64", "arm64"):
        target_name = "linux-arm64"
    else:
        print(f"no binary available for {sys_platform}/{arch}",
              file=sys.stderr)
        return 1

    binary_url = (
        f"https://github.com/{REPO}/releases/download/{latest_tag}/"
        f"ait-{latest_tag}-{target_name}"
    )
    checksums_url = (
        f"https://github.com/{REPO}/releases/download/{latest_tag}/"
        f"ait-{latest_tag}-checksums.txt"
    )

    # Download checksums, find ours
    try:
        with urllib.request.urlopen(checksums_url, timeout=15) as fh:
            sums = fh.read().decode("utf-8")
    except urllib.error.URLError as exc:
        print(f"could not fetch checksums: {exc}", file=sys.stderr)
        return 1
    expected_sha = ""
    for line in sums.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1] == f"ait-{latest_tag}-{target_name}":
            expected_sha = parts[0]
            break
    if not expected_sha:
        print(f"no checksum for ait-{latest_tag}-{target_name}", file=sys.stderr)
        return 1

    # Download binary + verify
    print("Downloading new binary...")
    try:
        content = download_and_verify(binary_url, expected_sha256=expected_sha)
    except (urllib.error.URLError, ChecksumMismatch) as exc:
        print(f"download/verify failed: {exc}", file=sys.stderr)
        return 1

    # Atomic replace
    atomic_replace(target, content)
    print(f"Updated to {latest_tag}. Run `ait --version` to verify.")
    return 0
