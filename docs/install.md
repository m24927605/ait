# Installing `ait`

`ait` ships through three channels. Pick whichever fits.

## Homebrew (macOS, recommended)

```bash
brew tap m24927605/ait
brew install ait
ait --version
```

Updates: `brew upgrade ait`.

Brew strips `com.apple.quarantine` on install, so the ad-hoc-signed
binary runs without Gatekeeper prompts.

## curl install script (macOS + Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh
```

Behind the scenes the script:

1. Detects your OS and CPU from `uname`.
2. Resolves the latest tag from `api.github.com/repos/m24927605/ait/releases/latest`.
3. Picks `/usr/local/bin` if writable, else `~/.local/bin`.
4. Downloads the binary and the release's `checksums.txt`.
5. Verifies SHA256.
6. On macOS, removes `com.apple.quarantine`.
7. `chmod +x`, mv into place.

Options:

```bash
curl -fsSL https://... | sh -s -- --version v1.5.1
curl -fsSL https://... | sh -s -- --prefix ~/.local
curl -fsSL https://... | sh -s -- --no-checksum   # not recommended
```

Updates: re-run the install command (downloads the latest tag and
overwrites). Or use `ait self-update` (see below).

## pip / pipx

```bash
pip install ait-vcs          # in a venv
pipx install ait-vcs         # isolated install
```

Requires Python ≥ 3.11.

Updates: `pip install --upgrade ait-vcs` (or `pipx upgrade ait-vcs`).

## Offline install (binary)

Download the binary and checksums for your platform from
<https://github.com/m24927605/ait/releases>:

```bash
sha256sum -c <(grep ait-v1.5.1-linux-x86_64 ait-v1.5.1-checksums.txt)
chmod +x ait-v1.5.1-linux-x86_64
sudo mv ait-v1.5.1-linux-x86_64 /usr/local/bin/ait
ait --version
```

## Verifying a binary

Every release publishes `ait-<tag>-checksums.txt` next to the binaries.

```bash
curl -LO https://github.com/m24927605/ait/releases/download/v1.5.1/ait-v1.5.1-checksums.txt
curl -LO https://github.com/m24927605/ait/releases/download/v1.5.1/ait-v1.5.1-linux-x86_64
sha256sum -c <(grep ait-v1.5.1-linux-x86_64 ait-v1.5.1-checksums.txt)
```

## Uninstall

- **Brew:** `brew uninstall ait && brew untap m24927605/ait`
- **curl install:** `rm <prefix>/ait` (default `/usr/local/bin/ait`
  or `~/.local/bin/ait`). State under `~/.config/ait` and
  `~/.local/state/ait` is left in place — remove manually if desired.
- **pip:** `pip uninstall ait-vcs`

## Platforms

| Target | Binary name | Built on |
|---|---|---|
| macOS arm64 (Apple Silicon) | `ait-<tag>-macos-arm64` | macos-latest |
| macOS x86_64 (Intel) | `ait-<tag>-macos-x86_64` | macos-13 |
| Linux x86_64 | `ait-<tag>-linux-x86_64` | ubuntu-latest |
| Linux arm64 | `ait-<tag>-linux-arm64` | ubuntu-24.04-arm |

Windows: not supported in v1; use the pip path under WSL or native
Python 3.11+.
