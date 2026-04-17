from __future__ import annotations

from typing import Any

from learn_core.quality_review import (
    apply_quality_envelope,
    build_traceability_entry,
    collect_quality_issues,
    normalize_confidence,
    normalize_quality_review,
)
from learn_core.text_utils import normalize_string_list

from .state_machine import diagnostic_metadata_is_valid


STAGE_REVIEWER_NAME = "stage-reviewer"
REVIEW_CONFIDENCE_THRESHOLD = {
    "clarification": 0.35,
    "research": 0.45,
    "diagnostic": 0.5,
    "approval": 0.4,
    "planning": 0.45,
}


def _normalize_candidate_for_review(stage: str, candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return candidate
    normalized_stage = str(stage or "").strip().lower()
    normalized = dict(candidate)
    if normalized_stage == "approval":
        approval_state = normalized.get("approval_state") if isinstance(normalized.get("approval_state"), dict) else {}
        if approval_state:
            normalized_approval_state = dict(approval_state)
            approval_status = str(normalized_approval_state.get("approval_status") or "").strip()
            legacy_status = str(normalized_approval_state.get("status") or "").strip()
            if not approval_status and legacy_status:
                normalized_approval_state["approval_status"] = legacy_status
            normalized["approval_state"] = normalized_approval_state
    return normalized


def _stage_specific_issues(stage: str, candidate: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage == "clarification":
        questionnaire = candidate.get("questionnaire") if isinstance(candidate.get("questionnaire"), dict) else {}
        clarification_state = candidate.get("clarification_state") if isinstance(candidate.get("clarification_state"), dict) else {}
        preference_state = candidate.get("preference_state") if isinstance(candidate.get("preference_state"), dict) else {}
        mastery_preferences = questionnaire.get("mastery_preferences") if isinstance(questionnaire.get("mastery_preferences"), dict) else {}
        assessment_depth_preference = str(
            mastery_preferences.get("assessment_depth_preference")
            or questionnaire.get("assessment_depth_preference")
            or preference_state.get("assessment_depth_preference")
            or ""
        ).strip().lower()
        assessment_depth_preference = {
            "简单": "simple",
            "简单测评": "simple",
            "深度": "deep",
            "深度测评": "deep",
        }.get(assessment_depth_preference, assessment_depth_preference)
        if not normalize_string_list(questionnaire.get("success_criteria")):
            issues.append("success_criteria_missing")
        if not str(questionnaire.get("current_level_self_report") or "").strip():
            issues.append("current_level_self_report_missing")
        if not preference_state:
            issues.append("preference_state_missing")
        if not clarification_state:
            issues.append("clarification_state_missing")
        if assessment_depth_preference not in {"simple", "deep"}:
            issues.append("assessment_depth_preference_missing")
    elif normalized_stage == "research":
        report = candidate.get("research_report") if isinstance(candidate.get("research_report"), dict) else {}
        metrics = report.get("capability_metrics") if isinstance(report.get("capability_metrics"), list) else []
        evidence_summary = normalize_string_list(report.get("evidence_summary") or report.get("source_evidence"))
        if not metrics:
            issues.append("capability_metrics_missing")
        if not evidence_summary:
            issues.append("evidence_summary_missing")
        if not normalize_string_list(report.get("selection_rationale")):
            issues.append("selection_rationale_missing")
    elif normalized_stage == "diagnostic":
        diagnostic_plan = candidate.get("diagnostic_plan") if isinstance(candidate.get("diagnostic_plan"), dict) else {}
        items = candidate.get("diagnostic_items") if isinstance(candidate.get("diagnostic_items"), list) else []
        result = candidate.get("diagnostic_result") if isinstance(candidate.get("diagnostic_result"), dict) else {}
        profile = candidate.get("diagnostic_profile") if isinstance(candidate.get("diagnostic_profile"), dict) else {}
        assessment_depth = str(diagnostic_plan.get("assessment_depth") or profile.get("assessment_depth") or "").strip()
        delivery = str(diagnostic_plan.get("delivery") or diagnostic_plan.get("diagnostic_delivery") or "").strip()
        assessment_kind = str(diagnostic_plan.get("assessment_kind") or profile.get("assessment_kind") or "").strip()
        session_intent = str(diagnostic_plan.get("session_intent") or profile.get("session_intent") or "").strip()
        plan_execution_mode = str(diagnostic_plan.get("plan_execution_mode") or profile.get("plan_execution_mode") or "").strip()
        round_index = diagnostic_plan.get("round_index") if "round_index" in diagnostic_plan else profile.get("round_index")
        max_rounds = diagnostic_plan.get("max_rounds") if "max_rounds" in diagnostic_plan else profile.get("max_rounds")
        if not items:
            issues.append("diagnostic_items_missing")
        if assessment_depth not in {"simple", "deep"}:
            issues.append("assessment_depth_missing")
        if delivery != "web-session":
            issues.append("diagnostic_delivery_missing")
        if not diagnostic_metadata_is_valid(assessment_kind, session_intent, plan_execution_mode):
            issues.append("diagnostic_assessment_kind_invalid")
            issues.append("diagnostic_session_intent_invalid")
        try:
            round_index_value = int(round_index)
        except (TypeError, ValueError):
            round_index_value = 0
        try:
            max_rounds_value = int(max_rounds)
        except (TypeError, ValueError):
            max_rounds_value = 0
        if round_index_value < 1:
            issues.append("round_index_missing")
        if max_rounds_value < max(1, round_index_value):
            issues.append("max_rounds_invalid")
        if not str(result.get("recommended_entry_level") or profile.get("recommended_entry_level") or "").strip():
            issues.append("recommended_entry_level_missing")
        confidence = result.get("confidence") if "confidence" in result else profile.get("confidence")
        if normalize_confidence(confidence, default=-1.0) < 0:
            issues.append("confidence_missing")
        if assessment_depth == "deep":
            if "follow_up_needed" not in result:
                issues.append("follow_up_needed_missing")
            if not str(result.get("stop_reason") or "").strip():
                issues.append("stop_reason_missing")
    elif normalized_stage == "approval":
        approval_state = candidate.get("approval_state") if isinstance(candidate.get("approval_state"), dict) else {}
        if not approval_state:
            issues.append("approval_state_missing")
        if not str(approval_state.get("approval_status") or "").strip():
            issues.append("approval_status_missing")
    elif normalized_stage == "planning":
        plan_candidate = candidate.get("plan_candidate") if isinstance(candidate.get("plan_candidate"), dict) else {}
        if not plan_candidate:
            issues.append("plan_candidate_missing")
        if not normalize_string_list(plan_candidate.get("stage_goals")):
            issues.append("stage_goals_missing")
        if not normalize_string_list(plan_candidate.get("mastery_checks")):
            issues.append("mastery_checks_missing")
    return issues


def review_stage_candidate(stage: str, candidate: dict[str, Any] | None) -> dict[str, Any]:
    normalized_stage = str(stage or "").strip().lower()
    normalized_candidate = _normalize_candidate_for_review(normalized_stage, candidate)
    issues = collect_quality_issues(
        normalized_candidate,
        prefix=normalized_stage,
        require_evidence=True,
        require_traceability=True,
        require_generation_trace=True,
        require_review=False,
        min_confidence=REVIEW_CONFIDENCE_THRESHOLD.get(normalized_stage, 0.0),
    )
    if isinstance(normalized_candidate, dict):
        issues.extend(f"{normalized_stage}.{item}" for item in _stage_specific_issues(normalized_stage, normalized_candidate))
    issue_texts = normalize_string_list(issues)
    valid = not issue_texts
    review = normalize_quality_review(
        None,
        reviewer=STAGE_REVIEWER_NAME,
        valid=valid,
        issues=issue_texts,
        warnings=[],
        confidence=(normalized_candidate or {}).get("confidence") if isinstance(normalized_candidate, dict) else 0.0,
        evidence_adequacy="sufficient" if valid else "partial",
        verdict="ready" if valid else "needs-revision",
    )
    payload = apply_quality_envelope(
        normalized_candidate,
        stage=normalized_stage,
        generator=f"stage-candidate:{normalized_stage}",
        evidence=(normalized_candidate or {}).get("evidence") if isinstance(normalized_candidate, dict) else [],
        confidence=(normalized_candidate or {}).get("confidence") if isinstance(normalized_candidate, dict) else 0.0,
        quality_review=review,
        generation_trace=(normalized_candidate or {}).get("generation_trace") if isinstance(normalized_candidate, dict) else {},
        traceability=(normalized_candidate or {}).get("traceability") if isinstance(normalized_candidate, dict) else [],
    )
    payload["quality_review"] = review
    if not payload.get("traceability"):
        payload["traceability"] = [
            build_traceability_entry(
                kind="stage-review",
                ref=normalized_stage,
                title=f"{normalized_stage} review",
                stage=normalized_stage,
                status=review.get("verdict"),
            )
        ]
    return payload


__all__ = [
    "REVIEW_CONFIDENCE_THRESHOLD",
    "STAGE_REVIEWER_NAME",
    "review_stage_candidate",
]
