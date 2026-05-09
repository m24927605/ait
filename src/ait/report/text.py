from __future__ import annotations



def render_work_graph_text(graph: dict[str, object]) -> str:
    lines = [
        "AIT Work Graph",
        f"Repo: {graph.get('repo_root')}",
        f"State: {'initialized' if graph.get('initialized') else 'not initialized'}",
        (
            "Summary: "
            f"intents={graph.get('intent_count', 0)} "
            f"attempts={graph.get('attempt_count', 0)} "
            f"matched_intents={graph.get('matched_intent_count', len(graph.get('intents', [])))} "
            f"matched_attempts={graph.get('matched_attempt_count', 0)} "
            f"memory_notes={graph.get('memory_note_count', 0)}"
        ),
    ]
    filters = graph.get("filters", {})
    if isinstance(filters, dict) and filters:
        lines.append(
            "Filters: "
            + ", ".join(f"{key}={value}" for key, value in sorted(filters.items()))
        )
    memory_topics = graph.get("memory_topics", {})
    if isinstance(memory_topics, dict) and memory_topics:
        topics = ", ".join(f"{topic or 'general'}={count}" for topic, count in sorted(memory_topics.items()))
        lines.append(f"Memory topics: {topics}")
    lines.append("Tree:")
    intents = [item for item in graph.get("intents", []) if isinstance(item, dict)]
    if not intents:
        lines.append("`-- no intents recorded")
        return "\n".join(lines)
    for intent_index, intent in enumerate(intents):
        intent_last = intent_index == len(intents) - 1
        intent_prefix = "`-- " if intent_last else "|-- "
        child_prefix = "    " if intent_last else "|   "
        lines.append(
            intent_prefix
            + f"Intent {intent.get('short_id')}: {intent.get('title')} "
            + f"[status={intent.get('status')}]"
        )
        attempts = [item for item in intent.get("attempts", []) if isinstance(item, dict)]
        if not attempts:
            lines.append(child_prefix + "`-- attempts: none")
            continue
        for attempt_index, attempt in enumerate(attempts):
            attempt_last = attempt_index == len(attempts) - 1
            attempt_prefix = child_prefix + ("`-- " if attempt_last else "|-- ")
            detail_prefix = child_prefix + ("    " if attempt_last else "|   ")
            lines.append(
                attempt_prefix
                + f"Attempt {attempt.get('ordinal')} {attempt.get('short_id')} "
                + f"agent={attempt.get('agent_id')} "
                + f"status={attempt.get('verified_status')}/{attempt.get('reported_status')}"
                + f" outcome={attempt.get('outcome_class') or 'unclassified'}"
            )
            files = attempt.get("files", {})
            changed = files.get("changed", []) if isinstance(files, dict) else []
            touched = files.get("touched", []) if isinstance(files, dict) else []
            file_list = changed or touched
            if file_list:
                lines.append(detail_prefix + "Files:")
                for file_path in file_list[:8]:
                    lines.append(detail_prefix + f"- {file_path}")
                if len(file_list) > 8:
                    lines.append(detail_prefix + f"- ... {len(file_list) - 8} more")
            commits = [item for item in attempt.get("commits", []) if isinstance(item, dict)]
            if commits:
                lines.append(detail_prefix + "Commits:")
                for commit in commits[:5]:
                    lines.append(detail_prefix + f"- {str(commit.get('commit_oid', ''))[:12]}")
                if len(commits) > 5:
                    lines.append(detail_prefix + f"- ... {len(commits) - 5} more")
            retrievals = [item for item in attempt.get("memory_retrievals", []) if isinstance(item, dict)]
            if retrievals:
                lines.append(detail_prefix + "Memory Used:")
                for retrieval in retrievals[:5]:
                    lines.append(
                        detail_prefix
                        + f"- facts={len(retrieval.get('selected_facts', []))} "
                        + f"ranker={retrieval.get('ranker_version')} "
                        + f"query={retrieval.get('query')}"
                    )
                if len(retrievals) > 5:
                    lines.append(detail_prefix + f"- ... {len(retrievals) - 5} more")
            memory_eval = attempt.get("memory_eval", {})
            if isinstance(memory_eval, dict) and int(memory_eval.get("event_count", 0) or 0):
                lines.append(
                    detail_prefix
                    + "Memory Eval: "
                    + f"{memory_eval.get('status')} "
                    + f"score={memory_eval.get('average_score')} "
                    + f"events={memory_eval.get('event_count')}"
                )
            review = attempt.get("review", {})
            if isinstance(review, dict) and review:
                review_line = (
                    f"Review: {review.get('status', 'unknown')} "
                    f"risk={review.get('risk_level', 'unknown')} "
                    f"score={review.get('risk_score', 0)} "
                    f"findings={review.get('finding_count', 0)}"
                )
                if review.get("overridden"):
                    review_line += " overridden=true"
                if review.get("freshness_status"):
                    review_line += f" fresh={review.get('freshness_status')}"
                lines.append(detail_prefix + review_line)
                if review.get("fresh") is False and review.get("freshness_reason"):
                    lines.append(detail_prefix + f"Review freshness: {review.get('freshness_reason')}")
                if review.get("status") in {"queued", "running", "blocked", "failed"}:
                    lines.append(detail_prefix + "Review next: ait review status")
                profiles = review.get("profiles", [])
                if profiles:
                    lines.append(detail_prefix + "Review profiles: " + ", ".join(str(item) for item in profiles))
                if review.get("summary"):
                    lines.append(detail_prefix + f"Review summary: {review.get('summary')}")
                if review.get("accepted_risk_finding_count"):
                    lines.append(detail_prefix + f"Review accepted risk: {review.get('accepted_risk_finding_count')}")
                baseline_ref = review.get("baseline_ref")
                if baseline_ref:
                    lines.append(detail_prefix + f"Review baseline: {baseline_ref}")
    return "\n".join(lines)



__all__ = ["render_work_graph_text"]
