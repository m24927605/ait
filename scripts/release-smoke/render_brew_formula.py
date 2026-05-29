"""Render a Homebrew Formula from a version tag + a sha256 checksums file.

Usage:
    python scripts/release-smoke/render_brew_formula.py \
        --version v1.5.1 \
        --checksums checksums.txt \
        --output Formula/ait.rb
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


TARGETS = ("macos-arm64", "linux-x86_64", "linux-arm64")

_TEMPLATE = """\
class Ait < Formula
  desc "AI-agent-native VCS layer that turns AI coding into reviewable attempts"
  homepage "https://github.com/m24927605/ait"
  version "{version_no_v}"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/{version_tag}/ait-{version_tag}-macos-arm64"
      sha256 "{macos_arm64}"
    end
    # macos-x86_64 not produced — Intel Mac users install via pip.
  end

  on_linux do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/{version_tag}/ait-{version_tag}-linux-arm64"
      sha256 "{linux_arm64}"
    end
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/{version_tag}/ait-{version_tag}-linux-x86_64"
      sha256 "{linux_x86_64}"
    end
  end

  def install
    bin.install Dir["ait-*"][0] => "ait"
  end

  test do
    assert_match version.to_s, shell_output("#{{bin}}/ait --version")
  end
end
"""


def parse_checksums(content: str, *, version: str) -> dict[str, str]:
    """Parse `sha256  ait-<version>-<target>` lines into {target: sha}."""
    out: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, name = parts
        prefix = f"ait-{version}-"
        if not name.startswith(prefix):
            continue
        target = name[len(prefix):]
        out[target] = sha
    missing = [t for t in TARGETS if t not in out]
    if missing:
        raise ValueError(f"checksums missing entries for: {missing}")
    return out


def render_formula(*, version: str, checksums: dict[str, str]) -> str:
    version_no_v = version.lstrip("v")
    return _TEMPLATE.format(
        version_tag=version,
        version_no_v=version_no_v,
        macos_arm64=checksums["macos-arm64"],
        linux_x86_64=checksums["linux-x86_64"],
        linux_arm64=checksums["linux-arm64"],
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True, help="version tag, e.g. v1.5.1")
    p.add_argument("--checksums", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    content = args.checksums.read_text(encoding="utf-8")
    sums = parse_checksums(content, version=args.version)
    formula = render_formula(version=args.version, checksums=sums)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(formula, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
