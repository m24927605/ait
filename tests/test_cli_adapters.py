from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ait import cli


class CliAdapterTests(unittest.TestCase):
    def test_adapter_list_json_outputs_registry(self) -> None:
        stdout = io.StringIO()

        with patch("sys.argv", ["ait", "adapter", "list", "--format", "json"]):
            with redirect_stdout(stdout):
                exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertIn("claude-code", {item["name"] for item in payload})

    def test_adapter_show_text_outputs_capabilities(self) -> None:
        stdout = io.StringIO()

        with patch("sys.argv", ["ait", "adapter", "show", "claude-code"]):
            with redirect_stdout(stdout):
                exit_code = cli.main()

        text = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("Adapter: claude-code", text)
        self.assertIn("Default context: True", text)
        self.assertIn("Native hooks: True", text)

    def test_adapter_doctor_json_outputs_checks(self) -> None:
        stdout = io.StringIO()

        with patch("sys.argv", ["ait", "adapter", "doctor", "claude-code", "--format", "json"]):
            with redirect_stdout(stdout):
                exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("claude-code", payload["adapter"]["name"])
        self.assertIn("git_repo", {item["name"] for item in payload["checks"]})
        self.assertIn("claude_hook_resource", {item["name"] for item in payload["checks"]})


if __name__ == "__main__":
    unittest.main()
