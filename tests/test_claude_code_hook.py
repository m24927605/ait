from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_hook_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "claude_code_hook.py"
    spec = importlib.util.spec_from_file_location("claude_code_hook", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load claude_code_hook.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


class ClaudeCodeHookTests(unittest.TestCase):
    def test_tool_category_maps_claude_tools_to_ait_categories(self) -> None:
        self.assertEqual("read", hook.tool_category("Read"))
        self.assertEqual("read", hook.tool_category("Grep"))
        self.assertEqual("write", hook.tool_category("Edit"))
        self.assertEqual("write", hook.tool_category("MultiEdit"))
        self.assertEqual("command", hook.tool_category("Bash"))
        self.assertEqual("other", hook.tool_category("TodoWrite"))

    def test_tool_files_extracts_known_path_fields(self) -> None:
        payload = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/app.py",
                "path": "src/app.py",
                "notebook_path": "notes.ipynb",
            },
        }

        self.assertEqual(
            [
                {"path": "notes.ipynb", "access": "write"},
                {"path": "src/app.py", "access": "write"},
            ],
            hook.tool_files(payload),
        )

    def test_state_round_trips_with_sanitized_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            state = {"session_id": "abc/123", "attempt_id": "repo:attempt"}

            hook.write_state(repo_root, "abc/123", state)

            self.assertTrue((repo_root / ".ait" / "claude-code-hooks" / "abc_123.json").exists())
            self.assertEqual(state, hook.read_state(repo_root, "abc/123"))

    def test_append_env_file_quotes_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "claude.env"

            hook.append_env_file(
                {"CLAUDE_ENV_FILE": str(env_file)},
                {"AIT_ATTEMPT_ID": "repo:attempt with space"},
            )

            self.assertEqual(
                "export AIT_ATTEMPT_ID='repo:attempt with space'\n",
                env_file.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
