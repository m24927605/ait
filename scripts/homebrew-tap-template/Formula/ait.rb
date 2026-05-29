# This is the initial formula seed for m24927605/homebrew-ait.
# Replaced on every release by render_brew_formula.py via CI.
class Ait < Formula
  desc "AI-agent-native VCS layer that turns AI coding into reviewable attempts"
  homepage "https://github.com/m24927605/ait"
  version "1.5.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-macos-arm64"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-macos-x86_64"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-linux-arm64"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-linux-x86_64"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
  end

  def install
    bin.install Dir["ait-*"][0] => "ait"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/ait --version")
  end
end
