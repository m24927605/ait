# homebrew-ait

Homebrew tap for [`ait`](https://github.com/m24927605/ait).

## Install

```bash
brew tap m24927605/ait
brew install ait
```

## Update

```bash
brew upgrade ait
```

## Notes

This tap is auto-updated on every `ait` release by the
[release-binary.yml](https://github.com/m24927605/ait/blob/main/.github/workflows/release-binary.yml)
workflow in the main repo. Do not hand-edit `Formula/ait.rb`; it will
be overwritten on the next release.

The formula points at signed (ad-hoc) binaries hosted on the main
repo's GitHub Releases. Homebrew strips `com.apple.quarantine` on
install so Gatekeeper does not prompt.
