#!/bin/sh
# install.sh — Install ait from GitHub Releases.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh -s -- --version v1.5.1
#   curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh -s -- --prefix ~/.local
#
# Options:
#   --version <tag>   Install a specific tag (default: latest from GitHub Releases)
#   --prefix <dir>    Install directory (default: /usr/local/bin if writable, else ~/.local/bin)
#   --no-checksum     Skip SHA256 verification (NOT recommended)

set -eu

REPO="m24927605/ait"
DEFAULT_PREFIX_SYS="/usr/local/bin"
DEFAULT_PREFIX_USER="$HOME/.local/bin"

VERSION="latest"
PREFIX=""
SKIP_CHECKSUM=0

# --- argparse ---
while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            [ $# -ge 2 ] || { echo "--version requires a value" >&2; exit 2; }
            VERSION="$2"; shift 2 ;;
        --prefix)
            [ $# -ge 2 ] || { echo "--prefix requires a value" >&2; exit 2; }
            PREFIX="$2"; shift 2 ;;
        --no-checksum)
            SKIP_CHECKSUM=1; shift ;;
        -h|--help)
            sed -n '2,12p' "$0"; exit 0 ;;
        *)
            printf 'unknown arg: %s\n' "$1" >&2; exit 2 ;;
    esac
done

# --- platform detection ---
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "$os/$arch" in
    darwin/arm64)               target="macos-arm64" ;;
    darwin/x86_64)              target="macos-x86_64" ;;
    linux/x86_64|linux/amd64)   target="linux-x86_64" ;;
    linux/aarch64|linux/arm64)  target="linux-arm64" ;;
    test/PLATFORM)              target="PLATFORM" ;;   # for tests
    *) printf 'unsupported platform: %s/%s\n' "$os" "$arch" >&2; exit 1 ;;
esac

# --- resolve version ---
if [ "$VERSION" = "latest" ]; then
    VERSION="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
        | grep -o '"tag_name": *"[^"]*"' | cut -d'"' -f4)"
    [ -n "$VERSION" ] || { echo "could not resolve latest version" >&2; exit 1; }
fi

# --- pick install dir ---
if [ -z "$PREFIX" ]; then
    if [ -w "$DEFAULT_PREFIX_SYS" ] 2>/dev/null; then
        PREFIX="$DEFAULT_PREFIX_SYS"
    else
        PREFIX="$DEFAULT_PREFIX_USER"
    fi
fi
mkdir -p "$PREFIX"

# --- download binary + checksums ---
binary_name="ait-${VERSION}-${target}"
binary_url="https://github.com/${REPO}/releases/download/${VERSION}/${binary_name}"
checksum_url="https://github.com/${REPO}/releases/download/${VERSION}/ait-${VERSION}-checksums.txt"

tmp="$(mktemp -d -t ait-install.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT

printf 'Downloading %s ...\n' "$binary_name"
curl -fSL --progress-bar "$binary_url" -o "$tmp/ait"

if [ "$SKIP_CHECKSUM" -eq 0 ]; then
    printf 'Verifying checksum ...\n'
    curl -fsSL "$checksum_url" -o "$tmp/checksums.txt"
    expected="$(grep " ${binary_name}\$" "$tmp/checksums.txt" | awk '{print $1}')"
    [ -n "$expected" ] || { echo "no checksum entry for ${binary_name}" >&2; exit 1; }
    if command -v shasum >/dev/null 2>&1; then
        actual="$(shasum -a 256 "$tmp/ait" | awk '{print $1}')"
    elif command -v sha256sum >/dev/null 2>&1; then
        actual="$(sha256sum "$tmp/ait" | awk '{print $1}')"
    else
        echo "neither shasum nor sha256sum is available; rerun with --no-checksum to bypass" >&2
        exit 1
    fi
    [ "$expected" = "$actual" ] || {
        printf 'checksum mismatch: expected %s, got %s\n' "$expected" "$actual" >&2
        exit 1
    }
fi

# --- macOS: drop quarantine attribute ---
if [ "$os" = "darwin" ]; then
    xattr -d com.apple.quarantine "$tmp/ait" 2>/dev/null || true
fi

# --- install ---
chmod +x "$tmp/ait"
install_path="$PREFIX/ait"
mv "$tmp/ait" "$install_path"

printf 'Installed: %s\n' "$install_path"

# --- PATH check ---
case ":$PATH:" in
    *":$PREFIX:"*) ;;
    *) printf '\nNOTE: %s is not in your PATH. Add this to your shell profile:\n  export PATH="%s:$PATH"\n' "$PREFIX" "$PREFIX" ;;
esac

# --- verify ---
if command -v ait >/dev/null 2>&1; then
    ait --version
fi
