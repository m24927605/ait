from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"


class InstallSshellSmokeTests(unittest.TestCase):
    """Smoke install.sh end-to-end with curl/sha mocked out.

    Build a PATH-only directory of fake `curl`, `sha256sum`, `shasum`
    that emit deterministic content, then run install.sh with --prefix
    pointing into a tmpdir and assert the resulting `ait` file is
    present.
    """

    def test_install_sh_detects_platform_and_places_binary(self):
        with tempfile.TemporaryDirectory() as td_str:
            td = Path(td_str)
            fake_bin = td / "fake_bin"
            fake_bin.mkdir()
            prefix = td / "prefix"

            # Fake curl: writes deterministic content.
            (fake_bin / "curl").write_text(textwrap.dedent("""\
                #!/bin/sh
                # Capture last arg as output file; emit different things based on URL.
                out=""
                last=""
                while [ $# -gt 0 ]; do
                    case "$1" in
                        -o) out="$2"; shift 2 ;;
                        *) last="$1"; shift ;;
                    esac
                done
                emit() {
                    if [ -n "$out" ]; then
                        printf '%s' "$1" > "$out"
                    else
                        printf '%s' "$1"
                    fi
                }
                case "$last" in
                    *checksums.txt)
                        # 64 'a's -> matches what we make sha256sum print
                        emit 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  ait-vTEST-PLATFORM\\n'
                        ;;
                    *latest)
                        emit '{"tag_name": "vTEST"}\\n'
                        ;;
                    *ait-vTEST-*)
                        emit 'fakebinary'
                        ;;
                    *)
                        echo "FAKE_CURL: unknown URL $last" >&2; exit 1 ;;
                esac
            """))
            (fake_bin / "curl").chmod(0o755)

            # Fake shasum -a 256: print 'a'*64 deterministically.
            (fake_bin / "shasum").write_text(textwrap.dedent("""\
                #!/bin/sh
                printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  -\\n'
            """))
            (fake_bin / "shasum").chmod(0o755)
            # And sha256sum as a fallback on Linux:
            (fake_bin / "sha256sum").write_text(textwrap.dedent("""\
                #!/bin/sh
                printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  -\\n'
            """))
            (fake_bin / "sha256sum").chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env.get('PATH','')}"

            # Patch the target tuple to match what fake checksums say.
            # install.sh derives target from uname, so we also patch uname.
            (fake_bin / "uname").write_text(textwrap.dedent("""\
                #!/bin/sh
                case "$1" in
                    -s) echo "Test" ;;
                    -m) echo "PLATFORM" ;;
                    *) echo "Test" ;;
                esac
            """))
            (fake_bin / "uname").chmod(0o755)

            r = subprocess.run(
                ["sh", str(INSTALL_SH), "--prefix", str(prefix),
                 "--no-checksum"],   # we don't need to chase the checksum logic in this test
                capture_output=True, env=env, text=True, timeout=15,
            )
            if r.returncode != 0:
                self.fail(
                    f"install.sh failed rc={r.returncode}\n"
                    f"stdout:\n{r.stdout}\n"
                    f"stderr:\n{r.stderr}"
                )
            self.assertTrue((prefix / "ait").exists(),
                            f"expected {prefix}/ait to exist after install")


if __name__ == "__main__":
    unittest.main()
