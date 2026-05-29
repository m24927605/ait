from __future__ import annotations

import unittest


class WhereamiFormatTests(unittest.TestCase):
    def _payload_inside_attempt(self) -> dict:
        return {
            "current_state": "inside_attempt",
            "repo_root": "/repo/x",
            "detected_context": {
                "is_primary_worktree": False,
                "is_ait_workspace": True,
                "attempt_id": "repo:01HZX9TYE5K",
                "current_branch": None,
                "target_branch": "main",
                "ahead_by": 0,
                "dirty": True,
                "dirty_tracked_files": ["src/foo.py"],
                "workspace_ref": ".ait/workspaces/attempt-0001-01hzx9tye5k",
            },
            "next_action": {},
        }

    def _payload_outside_attempt(self) -> dict:
        return {
            "current_state": "primary_checkout",
            "repo_root": "/repo/x",
            "detected_context": {
                "is_primary_worktree": True,
                "is_ait_workspace": False,
                "attempt_id": None,
                "current_branch": "main",
                "target_branch": None,
                "ahead_by": 0,
                "dirty": False,
                "dirty_tracked_files": [],
                "workspace_ref": None,
            },
            "next_action": {},
        }

    def test_inside_attempt_is_six_lines(self) -> None:
        from ait.cli.whereami import _format_whereami

        out = _format_whereami(self._payload_inside_attempt())
        self.assertEqual(6, len(out.splitlines()), out)
        self.assertTrue(out.startswith("Inside AIT attempt"))
        self.assertIn("01HZX9TYE", out)
        self.assertIn("target", out)
        self.assertIn("HEAD", out)
        self.assertIn("dirty", out)
        self.assertIn("workspace", out)
        self.assertIn("repo", out)

    def test_outside_attempt_is_two_lines(self) -> None:
        from ait.cli.whereami import _format_whereami

        out = _format_whereami(self._payload_outside_attempt())
        self.assertEqual(2, len(out.splitlines()), out)
        self.assertTrue(out.startswith("Not in an AIT attempt"))
        self.assertIn("primary checkout", out)

    def test_does_not_emit_internal_keys(self) -> None:
        from ait.cli.whereami import _format_whereami

        out = _format_whereami(self._payload_inside_attempt())
        for noise in ("is_primary_worktree", "is_ait_workspace", "ahead_by"):
            self.assertNotIn(noise, out, f"leaked internal key {noise!r}")


if __name__ == "__main__":
    unittest.main()
