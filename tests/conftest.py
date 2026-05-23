from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_ait_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AIT_STATE_DIR", str(tmp_path / "ait-state"))


_FILE_MARKS: dict[str, tuple[str, ...]] = {
    "tests/test_agent_first_workflow.py": ("slow", "integration", "subprocess", "serial"),
    "tests/test_concurrency.py": ("slow", "integration", "subprocess", "serial"),
    "tests/test_daemon_concurrency.py": ("daemon", "integration", "serial"),
    "tests/test_daemon_e2e.py": ("slow", "daemon", "integration", "subprocess", "serial"),
    "tests/test_daemon_lifecycle.py": ("daemon", "integration", "subprocess", "serial"),
    "tests/test_daemon_reaper.py": ("daemon", "serial"),
    "tests/test_daemon_verifier_threads.py": ("daemon", "serial"),
    "tests/test_integration.py": ("integration", "subprocess"),
    "tests/test_refactor_smoke.py": ("slow", "integration", "subprocess"),
    "tests/test_review_adapter_config.py": ("integration", "subprocess"),
    "tests/test_review_gate.py": ("release", "integration", "subprocess"),
    "tests/test_workspace.py": ("integration", "subprocess"),
}

_NODE_MARKS: dict[str, tuple[str, ...]] = {
    "tests/test_cleanup.py::CleanupTests::test_cleanup_retains_failed_and_crashed_attempts_inside_retention_window": (
        "slow",
        "integration",
    ),
    "tests/test_cleanup.py::CleanupTests::test_cleanup_apply_is_idempotent_when_run_twice": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_adapters.py::CliAdapterTests::test_init_text_initializes_every_detected_agent_cli_wrapper": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_adapters.py::CliAdapterTests::test_doctor_fix_outputs_eval_safe_shell_snippet_for_detected_agents": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_adapters.py::CliAdapterTests::test_doctor_reports_daemon_stale_reason": (
        "slow",
        "daemon",
        "integration",
        "subprocess",
        "serial",
    ),
    "tests/test_cli_adapters.py::CliAdapterTests::test_status_reports_last_background_report_paths": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_adapters.py::CliAdapterTests::test_status_reports_memory_eval_failure": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_adapters.py::CliAdapterTests::test_path_claude_invocation_hits_wrapper_without_importing_agent_memory": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_adapters.py::CliAdapterTests::test_path_fixed_binary_invocations_hit_wrappers_without_importing_agent_memory": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_run.py::CliRunTests::test_memory_retrievals_cli_and_graph_show_context_memory_use": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_run.py::CliRunTests::test_work_graph_filters_by_status_agent_and_file": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_run_review.py::CliRunReviewTests::test_high_risk_auto_apply_holds_when_required_review_is_queued": (
        "slow",
        "release",
        "integration",
        "subprocess",
    ),
    "tests/test_cli_session.py::CliSessionTests::test_split_implementation_disjoint_and_overlap_behaviors": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_federated_recall.py::FederatedRecallTests::test_policy_blocked_live_source_is_not_in_context_and_redaction_runs_first": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_integration.py::IntegrationTests::test_cleanup_gates_integration_workspace_with_durable_artifact_and_dev_server": (
        "slow",
        "release",
    ),
    "tests/test_integration.py::IntegrationTests::test_untracked_and_binary_overlap_hold_without_modifying_root": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_landing.py::LandingTests::test_status_reports_conflict_missing_and_applied_recovery_states": (
        "slow",
        "release",
        "integration",
        "subprocess",
    ),
    "tests/test_landing.py::LandingTests::test_status_all_includes_repo_recovery_summary_without_text_workspace_noise": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_runner.py::RunnerTests::test_agent_adapters_capture_transcript_for_memory_search": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_runner.py::RunnerTests::test_aider_and_codex_adapters_default_to_context_and_env": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_runner.py::RunnerTests::test_failed_attempt_memory_is_not_injected_into_default_context": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_runner.py::RunnerTests::test_finish_attempt_locally_does_not_dedupe_repeated_fallbacks": (
        "slow",
        "daemon",
        "integration",
        "serial",
    ),
    "tests/test_runner.py::RunnerTests::test_next_context_includes_relevant_attempt_memory": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_runner.py::RunnerTests::test_run_agent_command_caps_context_file_total_budget": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_runner.py::RunnerTests::test_run_agent_command_finalizes_locally_if_finish_is_interrupted": (
        "slow",
        "daemon",
        "integration",
        "serial",
    ),
    "tests/test_runner.py::RunnerTests::test_run_agent_command_finalizes_locally_if_record_tool_loses_harness": (
        "slow",
        "daemon",
        "integration",
        "serial",
    ),
    "tests/test_runner.py::RunnerTests::test_run_agent_command_reads_live_agent_memory_before_context": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_runner.py::RunnerTests::test_run_agent_command_records_memory_retrieval_events_for_context": (
        "slow",
        "integration",
        "subprocess",
    ),
    "tests/test_transcript_summarizer.py::RecallIntegrationTests::test_transcript_summary_note_is_surfaced_by_default_recall_policy": (
        "slow",
        "integration",
        "subprocess",
    ),
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    mark_by_name = {
        "slow": pytest.mark.slow,
        "integration": pytest.mark.integration,
        "daemon": pytest.mark.daemon,
        "subprocess": pytest.mark.subprocess,
        "release": pytest.mark.release,
        "serial": pytest.mark.serial,
    }
    for item in items:
        marks = set(_FILE_MARKS.get(item.nodeid.split("::", 1)[0], ()))
        marks.update(_NODE_MARKS.get(item.nodeid, ()))
        for name in sorted(marks):
            item.add_marker(mark_by_name[name])
