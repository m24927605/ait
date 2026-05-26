from __future__ import annotations

import json
import re
import shlex
import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.cli_parser import build_parser

ROOT = Path(__file__).resolve().parents[1]

PINNED_TAG_DOCS = (
    ROOT / "README.md",
    ROOT / "README.zh-TW.md",
    ROOT / "site-docs" / "getting-started.md",
    ROOT / "site-docs" / "zh-TW" / "getting-started.md",
)
QUICKSTART_DOCS = (
    ROOT / "README.md",
    ROOT / "README.zh-TW.md",
    ROOT / "site-docs" / "getting-started.md",
    ROOT / "site-docs" / "zh-TW" / "getting-started.md",
)
PUBLIC_CLAIM_DOCS = (
    ROOT / "README.md",
    ROOT / "README.zh-TW.md",
    ROOT / "site-docs" / "index.md",
    ROOT / "site-docs" / "zh-TW" / "index.md",
    ROOT / "site-docs" / "facts.md",
    ROOT / "site-docs" / "why-ait.md",
    ROOT / "site-docs" / "zh-TW" / "why-ait.md",
    ROOT / "site-docs" / "reference" / "adversarial-code-review.md",
    ROOT / "site-docs" / "zh-TW" / "reference" / "adversarial-code-review.md",
)


class DocsDriftTests(unittest.TestCase):
    def test_docs_versions_match_package_versions(self) -> None:
        version = _python_package_version()
        npm_version = json.loads(
            (ROOT / "npm" / "ait-vcs" / "package.json").read_text(encoding="utf-8")
        )["version"]
        facts = (ROOT / "site-docs" / "facts.md").read_text(encoding="utf-8")

        self.assertEqual(version, npm_version)
        self.assertIn(f"Current package version: `{version}`.", facts)
        self.assertIn(f"current package version is `{version}`", facts)
        self.assertIn(f"current package version is {version}", facts)
        self.assertNotRegex(facts, r"\b1\.1(?:\.x|\.\d+)?\b|\b1\.2\.0\b")

    def test_docs_pinned_github_tags_match_version(self) -> None:
        version = _python_package_version()
        tag_pattern = re.compile(r"github\.com/m24927605/ait\.git@v(\d+\.\d+\.\d+)")

        for path in PINNED_TAG_DOCS:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                tags = tag_pattern.findall(text)
                self.assertTrue(tags, f"missing pinned GitHub install tag in {path}")
                self.assertEqual({version}, set(tags))

    def test_quickstart_ait_commands_exist(self) -> None:
        parser = build_parser()
        commands = {
            (path.relative_to(ROOT), command)
            for path in QUICKSTART_DOCS
            for command in _ait_commands_from_markdown(path.read_text(encoding="utf-8"))
        }
        self.assertTrue(commands)

        for path, command in sorted(commands):
            with self.subTest(path=path, command=command):
                argv = shlex.split(command)[1:]
                try:
                    parser.parse_args(argv)
                except SystemExit as exc:
                    self.assertEqual(0, exc.code)

    def test_public_claims_do_not_overstate_review_or_production_readiness(self) -> None:
        unsupported = re.compile(
            r"production[- ]ready|ready for production|guaranteed|guarantee|catches every bug|catches all bugs",
            flags=re.IGNORECASE,
        )
        allowed_context = (
            "not ",
            "no ",
            "do not",
            "does not",
            "without ",
            "not yet",
            "不是",
            "不代表",
            "不保證",
            "沒有",
            "尚未",
            "不得",
        )

        failures: list[str] = []
        for path in PUBLIC_CLAIM_DOCS:
            text = path.read_text(encoding="utf-8")
            for match in unsupported.finditer(text):
                context = text[max(0, match.start() - 140) : match.end() + 140].lower()
                if any(marker in context for marker in allowed_context):
                    continue
                failures.append(
                    f"{path.relative_to(ROOT)}: unsupported claim {match.group(0)!r}"
                )

        self.assertEqual([], failures)


def _python_package_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _ait_commands_from_markdown(text: str) -> list[str]:
    commands: list[str] = []
    for block in re.findall(r"```(?:bash|sh)\n(.*?)```", text, flags=re.DOTALL):
        pending = ""
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "#" in line:
                line = re.split(r"\s+#", line, maxsplit=1)[0].rstrip()
            if line.endswith("\\"):
                pending += line[:-1].rstrip() + " "
                continue
            command = (pending + line).strip()
            pending = ""
            if command.startswith("ait "):
                commands.append(command)
    return commands


if __name__ == "__main__":
    unittest.main()
