from __future__ import annotations

import unittest

from ait.adapter_wrapper import _adapter_wrapper_script
from ait.adapters import get_adapter
from ait.shell_integration import shell_snippet


class WrapperBypassTests(unittest.TestCase):
    def test_wrapper_script_honours_ait_bypass_env(self) -> None:
        adapter = get_adapter("claude-code")
        script = _adapter_wrapper_script(adapter, real_binary="/usr/bin/true")
        # Must check both the legacy AIT_WRAPPER_BYPASS *and* the new
        # spec-blessed AIT_BYPASS name. Legacy stays for backward
        # compatibility; AIT_BYPASS is the documented entry-point.
        self.assertIn("AIT_BYPASS", script)
        self.assertIn("AIT_WRAPPER_BYPASS", script)


class ShellOffOnInterceptTests(unittest.TestCase):
    def test_zsh_wrapper_intercepts_off_and_on(self) -> None:
        snippet = shell_snippet("zsh")
        # The ait() shell function must intercept `ait off` and
        # `ait on` like it does `ait continue`, eval'ing the script
        # the binary prints so AIT_BYPASS can be set/unset in the
        # parent shell.
        self.assertIn("off|on", snippet)

    def test_bash_wrapper_intercepts_off_and_on(self) -> None:
        snippet = shell_snippet("bash")
        self.assertIn("off|on", snippet)


class OffOnCommandTests(unittest.TestCase):
    def test_off_emits_export_ait_bypass(self) -> None:
        from ait.cli.off_on import build_off_script

        self.assertIn("export AIT_BYPASS=1", build_off_script())

    def test_on_emits_unset_ait_bypass(self) -> None:
        from ait.cli.off_on import build_on_script

        self.assertIn("unset AIT_BYPASS", build_on_script())

    def test_off_includes_acknowledgement_line(self) -> None:
        from ait.cli.off_on import build_off_script

        self.assertIn("AIT auto-wrap disabled", build_off_script())


class WrapBehaviorPayloadTests(unittest.TestCase):
    def test_wrap_behavior_payload_wrapped_state(self) -> None:
        from ait.cli.status_helpers import _wrap_behavior_payload

        wb = _wrap_behavior_payload({
            "adapter": "claude-code",
            "wrapper_installed": True,
            "path_wrapper_active": True,
        })
        self.assertIn("wrapped", wb["current"])
        self.assertIn("claude", wb["current"])
        self.assertIn("AIT_BYPASS=1", wb["disable_once"])
        self.assertIn("ait off", wb["disable_shell"])
        self.assertIn("ait on", wb["disable_shell"])

    def test_wrap_behavior_payload_unwrapped_state(self) -> None:
        from ait.cli.status_helpers import _wrap_behavior_payload

        wb = _wrap_behavior_payload({
            "adapter": "claude-code",
            "wrapper_installed": True,
            "path_wrapper_active": False,
        })
        self.assertIn("unwrapped", wb["current"])

    def test_wrap_behavior_added_to_status_payload(self) -> None:
        # The _status_payload builder must emit a "wrap_behavior" key.
        # The presence is what we care about — content is validated by
        # the two tests above.
        import inspect

        from ait.cli.status_helpers import _status_payload

        source = inspect.getsource(_status_payload)
        self.assertIn('wrap_behavior', source)


if __name__ == "__main__":
    unittest.main()
