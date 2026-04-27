from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli


class CliAdapterTests(unittest.TestCase):
    def test_version_outputs_installed_distribution_version(self) -> None:
        stdout = io.StringIO()

        with patch("sys.argv", ["ait", "--version"]):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    cli.main()

        self.assertEqual(0, raised.exception.code)
        self.assertRegex(stdout.getvalue(), r"^ait \d+\.\d+\.\d+\n$")

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

    def test_adapter_setup_print_outputs_claude_settings(self) -> None:
        stdout = io.StringIO()

        with patch("sys.argv", ["ait", "adapter", "setup", "claude-code", "--print"]):
            with redirect_stdout(stdout):
                exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertIn("SessionStart", payload["hooks"])
        self.assertIn(".ait/adapters/claude-code/claude_code_hook.py", stdout.getvalue())

    def test_adapter_setup_unsupported_adapter_returns_error(self) -> None:
        with patch("sys.argv", ["ait", "adapter", "setup", "shell", "--print"]):
            exit_code = cli.main()

        self.assertEqual(2, exit_code)

    def test_adapter_setup_install_wrapper_outputs_wrapper_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch(
                        "sys.argv",
                        ["ait", "adapter", "setup", "claude-code", "--install-wrapper"],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertTrue(payload["wrapper_path"].endswith(".ait/bin/claude"))
        self.assertIn(payload["wrapper_path"], payload["wrote_files"])

    def test_adapter_setup_install_direnv_outputs_envrc_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch(
                        "sys.argv",
                        [
                            "ait",
                            "adapter",
                            "setup",
                            "claude-code",
                            "--install-wrapper",
                            "--install-direnv",
                        ],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())
            envrc = Path(payload["direnv_path"]).read_text(encoding="utf-8")

            self.assertEqual(0, exit_code)
            self.assertTrue(payload["direnv_path"].endswith(".envrc"))
            self.assertIn(payload["direnv_path"], payload["wrote_files"])
            self.assertIn("PATH_add .ait/bin", envrc)

    def test_bootstrap_claude_code_json_outputs_setup_and_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "bootstrap", "claude-code"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())

            self.assertEqual(0, exit_code)
            self.assertEqual("claude-code", payload["adapter"]["name"])
            self.assertTrue(payload["setup"]["wrapper_path"].endswith(".ait/bin/claude"))
            self.assertTrue(payload["setup"]["direnv_path"].endswith(".envrc"))
            self.assertIn("PATH_add .ait/bin", (repo_root / ".envrc").read_text(encoding="utf-8"))

    def test_bootstrap_defaults_to_claude_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "bootstrap"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())

            self.assertEqual(0, exit_code)
            self.assertEqual("claude-code", payload["adapter"]["name"])
            self.assertTrue((repo_root / ".ait" / "bin" / "claude").exists())

    def test_doctor_claude_code_json_reports_automation_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "bootstrap", "claude-code"]):
                        with redirect_stdout(io.StringIO()):
                            cli.main()
                    os.environ["PATH"] = (
                        str(repo_root / ".ait" / "bin")
                        + os.pathsep
                        + str(bin_dir)
                        + os.pathsep
                        + old_path
                    )
                    with patch("sys.argv", ["ait", "doctor", "claude-code", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())
            checks = {item["name"]: item for item in payload["checks"]}

            self.assertEqual(0, exit_code)
            self.assertTrue(checks["wrapper_file"]["ok"])
            self.assertTrue(checks["path_wrapper_active"]["ok"])
            self.assertTrue(checks["real_claude_binary"]["ok"])

    def test_bootstrap_shell_outputs_eval_safe_path_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "bootstrap", "claude-code", "--shell"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            wrapper_dir = (repo_root / ".ait" / "bin").resolve()

            self.assertEqual(0, exit_code)
            self.assertEqual(f'export PATH={wrapper_dir}:"$PATH"\n', stdout.getvalue())
            self.assertTrue((wrapper_dir / "claude").exists())

    def test_bootstrap_check_reports_without_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch(
                        "sys.argv",
                        ["ait", "bootstrap", "claude-code", "--check", "--format", "json"],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())
            checks = {item["name"]: item for item in payload["checks"]}

            self.assertEqual(2, exit_code)
            self.assertFalse(checks["wrapper_file"]["ok"])
            self.assertFalse((repo_root / ".ait").exists())
            self.assertFalse((repo_root / ".envrc").exists())

    def test_doctor_text_outputs_next_step_for_inactive_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "bootstrap", "claude-code"]):
                        with redirect_stdout(io.StringIO()):
                            cli.main()
                    with patch("sys.argv", ["ait", "doctor", "claude-code"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            text = stdout.getvalue()

            self.assertEqual(2, exit_code)
            self.assertIn("Next steps:", text)
            self.assertIn('eval "$(ait bootstrap claude-code --shell)"', text)

    def test_doctor_fix_outputs_eval_safe_shell_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "doctor", "--fix"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            wrapper_dir = (repo_root / ".ait" / "bin").resolve()

            self.assertEqual(0, exit_code)
            self.assertEqual(f'export PATH={wrapper_dir}:"$PATH"\n', stdout.getvalue())
            self.assertTrue((wrapper_dir / "claude").exists())

    def test_status_json_reports_next_steps_without_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "status", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())

            self.assertEqual(0, exit_code)
            self.assertEqual("claude-code", payload["adapter"])
            self.assertFalse(payload["wrapper_installed"])
            self.assertIn("ait bootstrap claude-code", payload["next_steps"])
            self.assertFalse((repo_root / ".ait").exists())


if __name__ == "__main__":
    unittest.main()


def _git_init(repo_root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
