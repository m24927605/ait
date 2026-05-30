from __future__ import annotations

import unittest


class LooksLikeIntentIdTests(unittest.TestCase):
    def test_bare_26_char_ulid_recognized(self) -> None:
        from ait.cli.run import _looks_like_intent_id

        self.assertTrue(_looks_like_intent_id("01HZX9TYE5K2NRMW6QVTESTAB1"))

    def test_prefixed_intent_id_recognized(self) -> None:
        from ait.cli.run import _looks_like_intent_id

        self.assertTrue(_looks_like_intent_id("intent:01HZX9TYE5K2NRMW6QVTESTAB1"))

    def test_prose_title_rejected(self) -> None:
        from ait.cli.run import _looks_like_intent_id

        self.assertFalse(_looks_like_intent_id("SLICE_01 canonical_events migration"))
        self.assertFalse(_looks_like_intent_id("Add feature X"))
        self.assertFalse(_looks_like_intent_id(""))
        self.assertFalse(_looks_like_intent_id(None))

    def test_short_alphanumeric_rejected(self) -> None:
        # 25 chars — too short to be a ULID, treat as title
        from ait.cli.run import _looks_like_intent_id

        self.assertFalse(_looks_like_intent_id("01HZX9TYE5K2NRMW6QVTESTAB"))

    def test_repo_prefix_namespace_recognized(self) -> None:
        # Real intent IDs in storage have form "<repo_id>:<ulid>"
        # e.g. "abc123def456:01HZX9TYE5K2NRMW6QVTESTAB1"
        from ait.cli.run import _looks_like_intent_id

        self.assertTrue(_looks_like_intent_id("abc123def456:01HZX9TYE5K2NRMW6QVTESTAB1"))


class RunnerHonoursExistingIntentTests(unittest.TestCase):
    def test_run_agent_command_accepts_intent_id_kwarg(self) -> None:
        # The signature contract: runner.run_agent_command must accept
        # an `intent_id` kwarg. When provided, it must NOT call
        # create_intent — instead it resolves and uses the existing one.
        import inspect

        from ait.runner import run_agent_command

        sig = inspect.signature(run_agent_command)
        self.assertIn("intent_id", sig.parameters)

    def test_runner_exports_ait_intent_env_for_shim_recursion(self) -> None:
        # The adapter_wrapper.py shim reads $AIT_INTENT (NOT $AIT_INTENT_ID)
        # to forward intent through wrapper re-exec. The runner must
        # export both names so the shim's recursion path stays bound to
        # the parent attempt's intent.
        import inspect

        from ait import runner

        source = inspect.getsource(runner.run_agent_command)
        self.assertIn('"AIT_INTENT"', source)


if __name__ == "__main__":
    unittest.main()
