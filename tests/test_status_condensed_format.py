from __future__ import annotations

import unittest


class CondensedStatusFormatTests(unittest.TestCase):
    def _payload(self, *, inside_attempt: bool = False, **overrides) -> dict:
        detected = {
            "repo_root": "/repo/x",
            "is_primary_worktree": not inside_attempt,
            "is_ait_workspace": inside_attempt,
            "attempt_id": "repo:01HZX9TYE5K" if inside_attempt else None,
            "target_branch": "main",
            "current_branch": None if inside_attempt else "main",
            "workspace_ref": (
                ".ait/workspaces/attempt-0001-01hzx9tye5k" if inside_attempt else None
            ),
            "dirty": False,
            "dirty_tracked_files": [],
        }
        base = {
            "adapter": "claude-code",
            "ok": True,
            "git_repo": True,
            "wrapper_installed": True,
            "path_wrapper_active": True,
            "real_agent_binary": True,
            "real_claude_binary": True,
            "direnv_available": False,
            "direnv_loaded": False,
            "memory": {
                "initialized": True, "health": "ok",
                "lint_issue_count": 0, "lint_error_count": 0,
                "lint_warning_count": 0, "lint_info_count": 0,
            },
            "daemon": {"running": True, "pid": 12345},
            "wrap_behavior": {
                "current": "wrapped (claude in this shell enters AIT)",
                "disable_once": "AIT_BYPASS=1 claude ...",
                "disable_shell": "ait off    (re-enable: ait on)",
            },
            "agent_cli_ready": True,
            "agent_cli_message": "ok",
            "ait_health": {"status": "ok"},
            "recovery": {"status": "ok", "active_count": 0, "archived_count": 0},
            "agent_state": {"detected_context": detected},
        }
        base.update(overrides)
        return base

    def test_condensed_default_is_under_20_lines(self) -> None:
        from ait.cli.status_helpers import _format_status_condensed

        out = _format_status_condensed(self._payload())
        lines = out.splitlines()
        # Spec target is ~13 lines; allow some slack. Hard ceiling 20.
        self.assertLessEqual(len(lines), 20, f"too verbose:\n{out}")

    def test_condensed_contains_three_named_blocks(self) -> None:
        from ait.cli.status_helpers import _format_status_condensed

        out = _format_status_condensed(self._payload())
        self.assertIn("Repo", out)
        self.assertIn("Workspace", out)
        self.assertIn("Wrap behavior", out)

    def test_condensed_ends_with_OK_on_healthy_state(self) -> None:
        from ait.cli.status_helpers import _format_status_condensed

        out = _format_status_condensed(self._payload())
        self.assertTrue(
            out.rstrip().endswith("OK"),
            f"missing trailing OK:\n{out!r}",
        )

    def test_inside_attempt_workspace_block_shows_attempt(self) -> None:
        from ait.cli.status_helpers import _format_status_condensed

        out = _format_status_condensed(self._payload(inside_attempt=True))
        self.assertIn("attempt", out.lower())
        self.assertIn("01HZX9TYE", out)
        self.assertIn("you are here", out)

    def test_outside_attempt_workspace_block_shows_primary(self) -> None:
        from ait.cli.status_helpers import _format_status_condensed

        out = _format_status_condensed(self._payload(inside_attempt=False))
        self.assertIn("primary checkout", out)

    def test_verbose_preserves_legacy_dump(self) -> None:
        # The pre-1.7 `_format_status` becomes the verbose path; it
        # must still be reachable and still produce the long output.
        from ait.cli.status_helpers import _format_status

        out = _format_status(self._payload(), debug=False)
        # Legacy dump emits 20+ lines for a fully populated payload.
        self.assertGreater(len(out.splitlines()), 15)


if __name__ == "__main__":
    unittest.main()
