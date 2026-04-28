from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.memory import add_memory_note, list_memory_notes


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
            _git_commit_initial(repo_root)
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
            _git_commit_initial(repo_root)
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
            _git_commit_initial(repo_root)
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

    def test_init_text_initializes_repo_and_detected_agent_wrappers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "init"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            text = stdout.getvalue()

            self.assertEqual(0, exit_code)
            self.assertIn("AIT initialized", text)
            self.assertIn("- claude-code", text)
            self.assertIn("- codex", text)
            self.assertIn("Current shell:", text)
            self.assertTrue("direnv allow" in text or 'eval "$(ait init --shell)"' in text)
            self.assertTrue((repo_root / ".ait" / "config.json").exists())
            self.assertTrue((repo_root / ".ait" / "bin" / "claude").exists())
            self.assertTrue((repo_root / ".ait" / "bin" / "codex").exists())
            self.assertTrue((repo_root / ".ait" / "memory-policy.json").exists())
            self.assertIn("PATH_add .ait/bin", (repo_root / ".envrc").read_text(encoding="utf-8"))

    def test_init_json_can_limit_adapter_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "init", "--adapter", "codex", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())

            self.assertEqual(0, exit_code)
            self.assertEqual(["codex"], payload["installed_adapters"])
            self.assertTrue(payload["shell_snippet"].startswith("export PATH="))
            self.assertTrue(payload["memory_policy"]["created"])
            self.assertTrue((repo_root / ".ait" / "bin" / "codex").exists())
            self.assertFalse((repo_root / ".ait" / "bin" / "claude").exists())

    def test_init_imports_detected_agent_memory_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            (repo_root / "CLAUDE.md").write_text("Run repair before release.\n", encoding="utf-8")
            stdout = io.StringIO()
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = "/usr/bin:/bin"
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "init", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())
            notes = list_memory_notes(repo_root, topic="agent-memory")

            self.assertEqual(0, exit_code)
            self.assertEqual(["agent-memory:claude:CLAUDE.md"], [
                item["source"] for item in payload["memory_import"]["imported"]
            ])
            self.assertEqual(1, len(notes))
            self.assertIn("Run repair before release.", notes[0].body)

    def test_path_claude_invocation_hits_wrapper_and_self_repairs_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text(
                "#!/bin/sh\n"
                "printf 'real claude reached\\n'\n"
                "printf 'agent wrote through PATH claude\\n' > path-claude-output.txt\n",
                encoding="utf-8",
            )
            real_claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            init_stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "init", "--adapter", "claude-code", "--format", "json"]):
                        with redirect_stdout(init_stdout):
                            init_exit_code = cli.main()
                    (repo_root / ".ait" / "memory-policy.json").unlink()
                    (repo_root / "CLAUDE.md").write_text(
                        "Prefer direct PATH claude use.\n",
                        encoding="utf-8",
                    )
                    env = {
                        **os.environ,
                        "PATH": (
                            str(repo_root / ".ait" / "bin")
                            + os.pathsep
                            + str(bin_dir)
                            + os.pathsep
                            + old_path
                        ),
                    }
                    completed = subprocess.run(
                        ["claude", "--fake-prompt"],
                        cwd=repo_root,
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
            finally:
                os.environ["PATH"] = old_path

            init_payload = json.loads(init_stdout.getvalue())
            wrapper_payload = json.loads(completed.stdout)
            notes = list_memory_notes(repo_root)

            self.assertEqual(0, init_exit_code)
            self.assertEqual(["claude-code"], init_payload["installed_adapters"])
            self.assertEqual(0, completed.returncode)
            self.assertEqual(0, wrapper_payload["exit_code"])
            self.assertTrue((repo_root / ".ait" / "memory-policy.json").exists())
            self.assertTrue(Path(wrapper_payload["workspace_ref"], "path-claude-output.txt").exists())
            self.assertTrue(wrapper_payload["attempt"]["commits"])
            sources = {note.source for note in notes}
            self.assertIn("agent-memory:claude:CLAUDE.md", sources)
            self.assertTrue(any(source.startswith("attempt-memory:") for source in sources))

    def test_path_fixed_binary_invocations_hit_wrappers_and_self_repair_memory(self) -> None:
        for adapter_name, command_name in (
            ("codex", "codex"),
            ("aider", "aider"),
            ("gemini", "gemini"),
            ("cursor", "cursor"),
        ):
            with self.subTest(adapter=adapter_name):
                with tempfile.TemporaryDirectory() as tmp:
                    repo_root = Path(tmp) / "repo"
                    repo_root.mkdir()
                    _git_init(repo_root)
                    _git_commit_initial(repo_root)
                    bin_dir = Path(tmp) / "bin"
                    bin_dir.mkdir()
                    real_agent = bin_dir / command_name
                    real_agent.write_text(
                        "#!/bin/sh\n"
                        f"printf 'real {command_name} reached\\n'\n"
                        f"printf 'agent wrote through PATH {command_name}\\n' > path-{command_name}-output.txt\n",
                        encoding="utf-8",
                    )
                    real_agent.chmod(0o755)
                    old_path = os.environ.get("PATH", "")
                    init_stdout = io.StringIO()
                    os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
                    try:
                        with chdir(repo_root):
                            with patch("sys.argv", ["ait", "init", "--adapter", adapter_name, "--format", "json"]):
                                with redirect_stdout(init_stdout):
                                    init_exit_code = cli.main()
                            (repo_root / ".ait" / "memory-policy.json").unlink()
                            (repo_root / "AGENTS.md").write_text(
                                f"Prefer direct PATH {command_name} use.\n",
                                encoding="utf-8",
                            )
                            env = {
                                **os.environ,
                                "PATH": (
                                    str(repo_root / ".ait" / "bin")
                                    + os.pathsep
                                    + str(bin_dir)
                                    + os.pathsep
                                    + old_path
                                ),
                            }
                            completed = subprocess.run(
                                [command_name, "--fake-prompt"],
                                cwd=repo_root,
                                env=env,
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                    finally:
                        os.environ["PATH"] = old_path

                    init_payload = json.loads(init_stdout.getvalue())
                    wrapper_payload = json.loads(completed.stdout)
                    notes = list_memory_notes(repo_root)

                    self.assertEqual(0, init_exit_code)
                    self.assertEqual([adapter_name], init_payload["installed_adapters"])
                    self.assertEqual(0, completed.returncode)
                    self.assertEqual(0, wrapper_payload["exit_code"])
                    self.assertTrue((repo_root / ".ait" / "memory-policy.json").exists())
                    self.assertTrue(Path(wrapper_payload["workspace_ref"], f"path-{command_name}-output.txt").exists())
                    self.assertTrue(wrapper_payload["attempt"]["commits"])
                    sources = {note.source for note in notes}
                    self.assertIn("agent-memory:codex:AGENTS.md", sources)
                    self.assertTrue(any(source.startswith("attempt-memory:") for source in sources))

    def test_init_shell_outputs_eval_safe_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            (repo_root / "CLAUDE.md").write_text("Do not import from shell mode.\n", encoding="utf-8")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "init", "--adapter", "codex", "--shell"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            wrapper_dir = (repo_root / ".ait" / "bin").resolve()

            self.assertEqual(0, exit_code)
            self.assertEqual(f'export PATH={wrapper_dir}:"$PATH"\n', stdout.getvalue())
            self.assertTrue((wrapper_dir / "codex").exists())
            self.assertEqual((), list_memory_notes(repo_root, topic="agent-memory"))

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
            self.assertIn('eval "$(ait init --shell)"', text)

    def test_doctor_fix_outputs_eval_safe_shell_snippet_for_detected_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
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
            self.assertTrue((wrapper_dir / "codex").exists())
            self.assertTrue((repo_root / ".ait" / "memory-policy.json").exists())

    def test_doctor_fix_json_initializes_memory_policy_and_imports_agent_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            (repo_root / "CLAUDE.md").write_text("Prefer low-interruption agent CLI use.\n", encoding="utf-8")
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
                    with patch("sys.argv", ["ait", "doctor", "claude-code", "--fix", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())
            notes = list_memory_notes(repo_root, topic="agent-memory")

            self.assertEqual(0, exit_code)
            self.assertEqual(["claude-code"], payload["installed_adapters"])
            self.assertTrue(payload["memory_policy"]["created"])
            self.assertEqual(["agent-memory:claude:CLAUDE.md"], [
                item["source"] for item in payload["memory_import"]["imported"]
            ])
            self.assertEqual(1, len(notes))
            self.assertTrue((repo_root / ".ait" / "memory-policy.json").exists())

    def test_doctor_fix_named_adapter_limits_enable_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text("#!/bin/sh\nprintf 'real claude\\n'\n", encoding="utf-8")
            real_claude.chmod(0o755)
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "doctor", "codex", "--fix"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            wrapper_dir = (repo_root / ".ait" / "bin").resolve()

            self.assertEqual(0, exit_code)
            self.assertEqual(f'export PATH={wrapper_dir}:"$PATH"\n', stdout.getvalue())
            self.assertTrue((wrapper_dir / "codex").exists())
            self.assertFalse((wrapper_dir / "claude").exists())

    def test_status_json_reports_next_steps_without_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            (repo_root / "CLAUDE.md").write_text("Import me later.\n", encoding="utf-8")
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
            self.assertFalse(payload["agent_cli_ready"])
            self.assertIn("run ait init --adapter claude-code", payload["agent_cli_message"])
            self.assertFalse(payload["memory"]["initialized"])
            self.assertEqual("uninitialized", payload["memory"]["health"])
            self.assertEqual(["CLAUDE.md"], payload["memory"]["pending_paths"])
            self.assertIn("ait init --adapter claude-code", payload["next_steps"])
            self.assertFalse((repo_root / ".ait").exists())

    def test_status_json_reports_memory_health_when_state_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            add_memory_note(
                repo_root,
                topic="attempt-memory",
                source="attempt-memory:secret",
                body="Billing retry path stores GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456 confidence=high",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "status", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())

            self.assertEqual(0, exit_code)
            self.assertEqual("error", payload["memory"]["health"])
            self.assertEqual(1, payload["memory"]["lint_error_count"])
            self.assertGreaterEqual(payload["memory"]["lint_issue_count"], 1)

    def test_status_text_emits_one_time_automation_hint_to_stderr(self) -> None:
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
            stderr = io.StringIO()
            second_stderr = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "status"]):
                        with redirect_stdout(stdout), redirect_stderr(stderr):
                            exit_code = cli.main()
                    with patch("sys.argv", ["ait", "status"]):
                        with redirect_stdout(io.StringIO()), redirect_stderr(second_stderr):
                            second_exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            hints = json.loads((repo_root / ".ait" / "hints.json").read_text(encoding="utf-8"))

            self.assertEqual(0, exit_code)
            self.assertEqual(0, second_exit_code)
            self.assertTrue(stdout.getvalue().startswith("Agent CLI: run ait init --adapter claude-code\n"))
            self.assertIn("Wrapper installed: False", stdout.getvalue())
            self.assertIn("Agent CLI ready: False", stdout.getvalue())
            self.assertIn("Agent CLI detail: not ready: run ait init --adapter claude-code", stdout.getvalue())
            self.assertIn("run ait init once", stderr.getvalue())
            self.assertEqual("", second_stderr.getvalue())
            self.assertTrue(hints["claude_code_automation_hint_v1"])

    def test_status_all_json_reports_every_fixed_binary_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "status", "--all", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())
            by_adapter = {item["adapter"]: item for item in payload}

            self.assertEqual(0, exit_code)
            self.assertEqual({"aider", "claude-code", "codex", "cursor", "gemini"}, set(by_adapter))
            self.assertTrue(by_adapter["codex"]["real_agent_binary"])
            self.assertFalse(by_adapter["codex"]["wrapper_installed"])
            self.assertIn("ait init --adapter codex", by_adapter["codex"]["next_steps"])

    def test_status_all_text_emits_enable_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_aider = bin_dir / "aider"
            real_aider.write_text("#!/bin/sh\nprintf 'real aider\\n'\n", encoding="utf-8")
            real_aider.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            stderr = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + "/usr/bin:/bin"
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "status", "--all"]):
                        with redirect_stdout(stdout), redirect_stderr(stderr):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(0, exit_code)
            text = stdout.getvalue()
            self.assertIn("AIT Agent CLI Readiness", text)
            self.assertIn("- aider: run ait init --adapter aider", text)
            self.assertIn("- codex: install codex", text)
            self.assertIn("- cursor: install cursor", text)
            self.assertIn("- gemini: install gemini", text)
            self.assertIn("details: adapter=aider", text)
            self.assertIn("run ait init once", stderr.getvalue())

    def test_repair_named_adapter_rebuilds_damaged_wrapper_and_envrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "init", "--adapter", "codex", "--format", "json"]):
                        with redirect_stdout(io.StringIO()):
                            self.assertEqual(0, cli.main())
                    wrapper_path = repo_root / ".ait" / "bin" / "codex"
                    wrapper_path.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
                    wrapper_path.chmod(0o755)
                    (repo_root / ".envrc").unlink()
                    stdout = io.StringIO()
                    with patch("sys.argv", ["ait", "repair", "codex", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())
            repaired_wrapper = (repo_root / ".ait" / "bin" / "codex").read_text(encoding="utf-8")

            self.assertEqual(0, exit_code)
            self.assertEqual(["codex"], payload["installed_adapters"])
            self.assertIn("run --adapter codex --format json", repaired_wrapper)
            self.assertIn(str(real_codex.resolve()), repaired_wrapper)
            self.assertIn("PATH_add .ait/bin", (repo_root / ".envrc").read_text(encoding="utf-8"))

    def test_repair_all_text_reports_before_after_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            (repo_root / "AGENTS.md").write_text("Keep wrappers current.\n", encoding="utf-8")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_aider = bin_dir / "aider"
            real_aider.write_text("#!/bin/sh\nprintf 'real aider\\n'\n", encoding="utf-8")
            real_aider.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "repair"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            text = stdout.getvalue()

            self.assertEqual(0, exit_code)
            self.assertIn("AIT repair", text)
            self.assertIn("Repaired:", text)
            self.assertIn("- aider", text)
            self.assertIn("Status changes:", text)
            self.assertIn("wrapper_installed: False -> True", text)
            self.assertIn("Imported memory:", text)
            self.assertIn("agent-memory:codex:AGENTS.md", text)
            self.assertIn("Current shell:", text)
            self.assertTrue((repo_root / ".ait" / "bin" / "aider").exists())

    def test_repair_without_real_binary_reports_skipped_without_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            (repo_root / "CLAUDE.md").write_text("Repair should still import memory.\n", encoding="utf-8")
            stdout = io.StringIO()
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = "/usr/bin:/bin"
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "repair", "codex", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())

            self.assertEqual(2, exit_code)
            self.assertEqual([], payload["installed_adapters"])
            self.assertEqual(["codex"], [item["name"] for item in payload["skipped_adapters"]])
            self.assertEqual(
                ["agent-memory:claude:CLAUDE.md"],
                [item["source"] for item in payload["memory_import"]["imported"]],
            )
            self.assertFalse((repo_root / ".ait" / "bin" / "codex").exists())
            self.assertFalse((repo_root / ".envrc").exists())

    def test_repair_json_runs_memory_lint_fix_even_without_agent_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            _git_commit_initial(repo_root)
            add_memory_note(repo_root, topic="release", source="manual", body="Run tests before release.")
            add_memory_note(repo_root, topic="release", source="manual", body="Run tests before release.")
            add_memory_note(
                repo_root,
                topic="attempt-memory",
                source="attempt-memory:secret",
                body="Do not keep GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456 confidence=high",
            )
            stdout = io.StringIO()
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = "/usr/bin:/bin"
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "repair", "codex", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())
            notes_text = "\n".join(note.body for note in list_memory_notes(repo_root, limit=20))

            self.assertEqual(0, exit_code)
            self.assertEqual([], payload["installed_adapters"])
            self.assertGreaterEqual(payload["memory_lint"]["fix_count"], 2)
            self.assertEqual(0, payload["memory_health"]["error_count"])
            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", notes_text)

    def test_enable_json_installs_all_detected_agent_wrappers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "enable", "--adapter", "codex", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            payload = json.loads(stdout.getvalue())

            self.assertEqual(0, exit_code)
            self.assertEqual(["codex"], [item["adapter"]["name"] for item in payload["installed"]])
            self.assertTrue(payload["shell_snippet"].startswith("export PATH="))
            self.assertTrue((repo_root / ".ait" / "bin" / "codex").exists())
            self.assertFalse((repo_root / ".ait" / "bin" / "aider").exists())

    def test_enable_text_outputs_agent_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'real codex\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "enable", "--adapter", "codex"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            text = stdout.getvalue()

            self.assertEqual(0, exit_code)
            self.assertIn("Next:", text)
            self.assertIn("- codex ...", text)

    def test_enable_shell_outputs_eval_safe_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _git_init(repo_root)
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_aider = bin_dir / "aider"
            real_aider.write_text("#!/bin/sh\nprintf 'real aider\\n'\n", encoding="utf-8")
            real_aider.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "enable", "--adapter", "aider", "--shell"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            wrapper_dir = (repo_root / ".ait" / "bin").resolve()

            self.assertEqual(0, exit_code)
            self.assertEqual(f'export PATH={wrapper_dir}:"$PATH"\n', stdout.getvalue())
            self.assertTrue((wrapper_dir / "aider").exists())

    def test_no_hints_suppresses_status_hint_and_hint_file(self) -> None:
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
            stderr = io.StringIO()
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            try:
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "--no-hints", "status"]):
                        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                            exit_code = cli.main()
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(0, exit_code)
            self.assertEqual("", stderr.getvalue())
            self.assertFalse((repo_root / ".ait" / "hints.json").exists())


if __name__ == "__main__":
    unittest.main()


def _git_init(repo_root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)


def _git_commit_initial(repo_root: Path) -> None:
    import subprocess

    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True)
