from __future__ import annotations


class ApplyCode:
    ALREADY_APPLIED = "apply.already_applied"
    APPLIED = "apply.applied"
    ATTEMPT_NOT_SUCCESSFUL = "apply.attempt_not_successful"
    CONFLICT = "apply.conflict"
    CONFLICT_MARKERS = "apply.conflict_markers"
    CURRENT_BRANCH_UPDATE_FAILED = "apply.current_branch_update_failed"
    DIRTY_OVERLAP = "apply.dirty_overlap"
    DIRTY_PATCH_APPLIED = "apply.dirty_patch_applied"
    DIRTY_POLICY_HOLD = "apply.dirty_policy_hold"
    EMPTY_RESULT = "apply.empty_result"
    HELD = "apply.held"
    MISSING_RECOVERY_STATE = "apply.missing_recovery_state"
    MODE_NONE = "apply.mode_none"
    PATCH_CHECK_FAILED = "apply.patch_check_failed"
    REVIEW_GATE = "apply.review_gate"
    TARGET_BRANCH_UPDATE_FAILED = "apply.target_branch_update_failed"
    TARGET_CURRENT_BRANCH = "apply.target_current_branch"
    TARGET_MOVED = "apply.target_moved"
    TARGET_MOVED_UNCOMMITTED_RESULT = "apply.target_moved_uncommitted_result"
    UNTRACKED_OVERWRITE = "apply.untracked_overwrite"
    UNSAFE_PATCH_STATUS = "apply.unsafe_patch_status"


class CleanupCode:
    PREFIX = "cleanup."


class IntegrationCode:
    BINARY_OVERLAP = "integration.binary_overlap"
    DELETE_OVERLAP = "integration.delete_overlap"
    MERGE_FILE_CONFLICT = "integration.merge_file_conflict"
    NO_AGENT_PATCH = "integration.no_agent_patch"
    RENAME_OVERLAP = "integration.rename_overlap"
    REPLAY_AGENT_FAILED = "integration.replay_agent_failed"
    REPLAY_USER_FAILED = "integration.replay_user_failed"
    SAFE_NON_OVERLAP = "integration.safe_non_overlap"
    SEMANTIC_MERGE_FAILED = "integration.semantic_merge_failed"
    SUCCEEDED = "integration.succeeded"
    TEXT_OVERLAP = "integration.text_overlap"
    UNTRACKED_CONFLICT = "integration.untracked_conflict"
    UNSAFE_STATUS = "integration.unsafe_status"


class RecoverCode:
    ACTIVE = "recover.active"
    ALREADY_APPLIED = "recover.already_applied"
    DISCARDED = "recover.discarded"
    FAILED = "recover.failed"
    HELD = "recover.held"
    INTEGRATION_CREATED = "recover.integration_created"
    MISSING_STATE = "recover.missing_state"
    READY_TO_APPLY = "recover.ready_to_apply"
    CONFLICT = "recover.conflict"


class StatusCode:
    ACTIVE = "status.active"
    CONFLICT = "status.conflict"
    FAILED = "status.failed"
    LATEST_APPLIED = "status.latest_applied"
    LATEST_DISCARDED = "status.latest_discarded"
    MISSING_RECOVERY_STATE = "status.missing_recovery_state"
    NO_ATTEMPTS = "status.no_attempts"
    NOT_INITIALIZED = "status.not_initialized"
    READY_TO_APPLY = "status.ready_to_apply"
    REVIEWABLE = "status.reviewable"


def cleanup_reason_code(reason: str) -> str:
    return f"{CleanupCode.PREFIX}{reason}"
