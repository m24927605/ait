from __future__ import annotations

import io
import os
import re
import unittest
from unittest import mock

from ait.banner import print_attempt_banner, render_attempt_banner


class RenderAttemptBannerTests(unittest.TestCase):
    def test_includes_attempt_id_workspace_head_apply_lines(self) -> None:
        text = render_attempt_banner(
            attempt_id="repo:01HZX9TYE",
            workspace_rel=".ait/workspaces/attempt-0001-01hzx9tye",
            head="detached",
            target="main",
        )
        self.assertIn("01HZX9TYE", text)
        self.assertIn(".ait/workspaces/attempt-0001-01hzx9tye", text)
        self.assertIn("HEAD: detached", text)
        self.assertIn("target: main", text)
        self.assertIn("ait apply", text)

    def test_each_line_no_longer_than_60_chars_visible(self) -> None:
        text = render_attempt_banner(
            attempt_id="repo:01HZX9TYE",
            workspace_rel=".ait/workspaces/attempt-0001-01hzx9tye",
            head="detached",
            target="main",
            use_color=True,
        )
        ansi = re.compile(r"\x1b\[[0-9;]*m")
        for line in text.splitlines():
            visible = ansi.sub("", line)
            self.assertLessEqual(
                len(visible), 60,
                f"line wider than 60: {visible!r}",
            )

    def test_short_attempt_id_renders_full_when_below_9_chars(self) -> None:
        text = render_attempt_banner(
            attempt_id="01HZ",
            workspace_rel=".ait/workspaces/attempt-0001-01hz",
            head="detached",
            target="main",
        )
        self.assertIn("01HZ", text)


class PrintAttemptBannerTests(unittest.TestCase):
    def _make_fake_tty(self) -> io.StringIO:
        class _FakeTTY(io.StringIO):
            def isatty(self) -> bool:
                return True
        return _FakeTTY()

    def _make_fake_pipe(self) -> io.StringIO:
        class _FakePipe(io.StringIO):
            def isatty(self) -> bool:
                return False
        return _FakePipe()

    def test_prints_when_stderr_is_tty_and_env_unset(self) -> None:
        stream = self._make_fake_tty()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIT_NO_BANNER", None)
            print_attempt_banner(
                stream=stream,
                attempt_id="01HZX9TYE",
                workspace_rel=".ait/workspaces/attempt-0001-01hzx9tye",
                head="detached",
                target="main",
            )
        out = stream.getvalue()
        self.assertIn("01HZX9TYE", out)

    def test_skips_when_stderr_not_tty(self) -> None:
        stream = self._make_fake_pipe()
        print_attempt_banner(
            stream=stream,
            attempt_id="01HZX9TYE",
            workspace_rel=".ait/workspaces/attempt-0001-01hzx9tye",
            head="detached",
            target="main",
        )
        self.assertEqual("", stream.getvalue())

    def test_skips_when_ait_no_banner_env_set(self) -> None:
        stream = self._make_fake_tty()
        with mock.patch.dict(os.environ, {"AIT_NO_BANNER": "1"}):
            print_attempt_banner(
                stream=stream,
                attempt_id="01HZX9TYE",
                workspace_rel=".ait/workspaces/attempt-0001-01hzx9tye",
                head="detached",
                target="main",
            )
        self.assertEqual("", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
