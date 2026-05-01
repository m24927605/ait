from __future__ import annotations

import unittest

from ait.outcome import classify_attempt_outcome


class OutcomeTests(unittest.TestCase):
    def test_python_traceback_is_not_infra_by_itself(self) -> None:
        outcome = classify_attempt_outcome(
            reported_status="finished",
            verified_status="failed",
            result_exit_code=1,
            changed_files=(),
            commit_oids=(),
            observed_tool_calls=0,
            observed_file_writes=0,
            observed_tests_run=0,
            observed_tests_failed=0,
            raw_trace_text="Traceback (most recent call last):\nAssertionError\n",
        )

        self.assertEqual("failed", outcome.outcome_class)

    def test_literal_caret_c_text_is_not_interrupted(self) -> None:
        outcome = classify_attempt_outcome(
            reported_status="finished",
            verified_status="failed",
            result_exit_code=1,
            changed_files=(),
            commit_oids=(),
            observed_tool_calls=0,
            observed_file_writes=0,
            observed_tests_run=0,
            observed_tests_failed=0,
            raw_trace_text="The token ^cdef is invalid.\n",
        )

        self.assertEqual("failed", outcome.outcome_class)

    def test_sigint_text_is_interrupted(self) -> None:
        outcome = classify_attempt_outcome(
            reported_status="finished",
            verified_status="failed",
            result_exit_code=1,
            changed_files=(),
            commit_oids=(),
            observed_tool_calls=0,
            observed_file_writes=0,
            observed_tests_run=0,
            observed_tests_failed=0,
            raw_trace_text="received SIGINT",
        )

        self.assertEqual("failed_interrupted", outcome.outcome_class)


if __name__ == "__main__":
    unittest.main()
