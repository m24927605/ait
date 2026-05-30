from __future__ import annotations

import io
import os
import unittest
from unittest import mock


class NestedWrapWarningTests(unittest.TestCase):
    def test_emit_helper_warns_for_operator_manual_nested(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _maybe_warn_nested_wrap

        adapter = get_adapter("claude-code")
        stream = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"AIT_ATTEMPT_ID": "repo:01HZX9TYE5K"},
            clear=False,
        ):
            os.environ.pop("AIT_SHIM_REENTRY", None)
            _maybe_warn_nested_wrap(adapter, stream=stream)
        out = stream.getvalue()
        self.assertIn("nested wrapped claude-code", out)
        self.assertIn("AIT_BYPASS=1", out)
        self.assertIn("ait off", out)
        self.assertIn("01HZX9TYE5K", out)

    def test_emit_helper_silent_when_shim_marker_present(self) -> None:
        # When the shim itself re-execs ait run, it sets
        # AIT_SHIM_REENTRY=1 to suppress this warning — the
        # recursion is by design in that path.
        from ait.adapter_registry import get_adapter
        from ait.runner import _maybe_warn_nested_wrap

        adapter = get_adapter("claude-code")
        stream = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"AIT_ATTEMPT_ID": "repo:01H", "AIT_SHIM_REENTRY": "1"},
            clear=False,
        ):
            _maybe_warn_nested_wrap(adapter, stream=stream)
        self.assertEqual("", stream.getvalue())

    def test_emit_helper_silent_when_no_parent_attempt(self) -> None:
        from ait.adapter_registry import get_adapter
        from ait.runner import _maybe_warn_nested_wrap

        adapter = get_adapter("claude-code")
        stream = io.StringIO()
        env_without = {
            k: v for k, v in os.environ.items()
            if k not in ("AIT_ATTEMPT_ID", "AIT_SHIM_REENTRY")
        }
        with mock.patch.dict(os.environ, env_without, clear=True):
            _maybe_warn_nested_wrap(adapter, stream=stream)
        self.assertEqual("", stream.getvalue())

    def test_emit_helper_silent_for_shell_adapter(self) -> None:
        # Shell adapter has no OAuth/session auth context to lose;
        # nested-wrap warning would just be noise.
        from ait.adapter_registry import get_adapter
        from ait.runner import _maybe_warn_nested_wrap

        adapter = get_adapter("shell")
        stream = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"AIT_ATTEMPT_ID": "repo:01H"},
            clear=False,
        ):
            os.environ.pop("AIT_SHIM_REENTRY", None)
            _maybe_warn_nested_wrap(adapter, stream=stream)
        self.assertEqual("", stream.getvalue())


class ShimEmitsReentryMarkerTests(unittest.TestCase):
    def test_wrapper_script_sets_ait_shim_reentry_before_reexec(self) -> None:
        from ait.adapter_wrapper import _adapter_wrapper_script
        from ait.adapter_registry import get_adapter

        adapter = get_adapter("claude-code")
        script = _adapter_wrapper_script(adapter, real_binary="/usr/bin/true")
        # The shim re-execs `ait run` near the end of its body. Right
        # before that exec, it must set AIT_SHIM_REENTRY=1 so the
        # nested-wrap warning stays silent in this by-design recursion.
        self.assertIn("AIT_SHIM_REENTRY=1", script)
        self.assertIn("export AIT_SHIM_REENTRY", script)


if __name__ == "__main__":
    unittest.main()
