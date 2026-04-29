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

from .state_machine import diagnostic_blueprint_missing_fields, diagnostic_metadata_is_valid, normalize_clarification_artifact, resolve_assessment_budget_preference


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
    if normalized_stage == "clarification":
        normalized = normalize_clarification_artifact(normalized)
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
        consultation_model_enabled = bool(candidate.get("consultation_model_enabled")) if "consultation_model_enabled" in candidate else isinstance(candidate.get("consultation_state"), dict)
        candidate = normalize_clarification_artifact(candidate)
        questionnaire = candidate.get("questionnaire") if isinstance(candidate.get("questionnaire"), dict) else {}
        clarification_state = candidate.get("clarification_state") if isinstance(candidate.get("clarification_state"), dict) else {}
        preference_state = candidate.get("preference_state") if isinstance(candidate.get("preference_state"), dict) else {}
        consultation_state = candidate.get("consultation_state") if isinstance(candidate.get("consultation_state"), dict) else {}
        assessment_budget = resolve_assessment_budget_preference(candidate, None)
        if consultation_model_enabled:
            if not consultation_state:
                issues.append("consultation_state_missing")
            else:
                current_topic_id = str(consultation_state.get("current_topic_id") or "").strip()
                topics = consultation_state.get("topics") if isinstance(consultation_state.get("topics"), list) else []
                if not current_topic_id:
                    issues.append("consultation_state.current_topic_id_missing")
                if not topics:
                    issues.append("consultation_state.topics_missing")
                active_topic_ids = []
                for topic in topics:
                    if not isinstance(topic, dict):
                        continue
                    topic_id = str(topic.get("id") or "").strip()
                    status = str(topic.get("status") or "").strip().lower()
                    if topic.get("required") and status not in {"resolved", "deferred", "in-progress", "not-started"}:
                        issues.append(f"consultation_topic.{topic_id}.status_invalid")
                    if topic.get("required") and not normalize_string_list(topic.get("exit_criteria") or []):
                        issues.append(f"consultation_topic.{topic_id}.exit_criteria_missing")
                    if status == "resolved" and topic.get("ambiguities") and not topic.get("assumptions"):
                        issues.append(f"consultation_topic.{topic_id}.resolved_with_ambiguities")
                    if status == "in-progress":
                        active_topic_ids.append(topic_id)
                if len([topic_id for topic_id in active_topic_ids if topic_id]) > 1:
                    issues.append("consultation_state.multiple_active_topics")
        if not normalize_string_list(questionnaire.get("success_criteria")):
            issues.append("success_criteria_missing")
        current_level_deferred = False
        for topic in consultation_state.get("topics") if isinstance(consultation_state.get("topics"), list) else []:
            if isinstance(topic, dict) and str(topic.get("id") or "").strip() == "current_level":
                current_level_deferred = str(topic.get("status") or "").strip().lower() == "deferred"
        if not str(questionnaire.get("current_level_self_report") or "").strip() and not current_level_deferred:
            issues.append("current_level_self_report_missing")
        if list(preference_state.get("pending_items") or []):
            issues.append("preference_state_pending")
        if not clarification_state:
            issues.append("clarification_state_missing")
        if assessment_budget.get("max_assessment_rounds_preference") is None:
            issues.append("max_assessment_rounds_preference_missing")
        if assessment_budget.get("questions_per_round_preference") is None:
            issues.append("questions_per_round_preference_missing")
        if not normalize_string_list(candidate.get("theme_inventory") or []):
            issues.append("theme_inventory_missing")
        learner_profile = candidate.get("learner_profile") if isinstance(candidate.get("learner_profile"), dict) else {}
        if not learner_profile:
            issues.append("learner_profile_missing")
            issues.append("learner_profile_confirmation_missing")
        else:
            confirmation_status = str(learner_profile.get("confirmation_status") or "").strip().lower()
            if confirmation_status not in {"pending_user_confirmation", "confirmed", "needs_revision"}:
                issues.append("learner_profile_confirmation_missing")
            elif confirmation_status == "pending_user_confirmation" and not str(learner_profile.get("confirmation_prompt") or "").strip():
                issues.append("learner_profile_confirmation_missing")
    elif normalized_stage == "research":
        report = candidate.get("research_report") if isinstance(candidate.get("research_report"), dict) else {}
        metrics = report.get("capability_metrics") if isinstance(report.get("capability_metrics"), list) else []
        evidence_summary = normalize_string_list(report.get("evidence_summary") or report.get("source_evidence"))
        diagnostic_scope = report.get("diagnostic_scope") if isinstance(report.get("diagnostic_scope"), dict) else {}
        user_facing_report = report.get("user_facing_report") if isinstance(report.get("user_facing_report"), dict) else {}
        if not str(report.get("goal_target_band") or "").strip():
            issues.append("goal_target_band_missing")
        if not str(report.get("required_level_definition") or "").strip():
            issues.append("required_level_definition_missing")
        if str(user_facing_report.get("format") or "").strip().lower() != "html":
            issues.append("user_facing_report.format_missing")
        if not str(user_facing_report.get("html") or user_facing_report.get("path") or "").strip():
            issues.append("user_facing_report.html_missing")
        if not normalize_string_list(user_facing_report.get("summary") or []):
            issues.append("user_facing_report.summary_missing")
        if not normalize_string_list(report.get("must_master_core")):
            issues.append("must_master_core_missing")
        if not normalize_string_list(report.get("evidence_expectations")):
            issues.append("evidence_expectations_missing")
        if not str(report.get("research_brief") or "").strip():
            issues.append("research_brief_missing")
        if not normalize_string_list(report.get("evaluator_roles") or []):
            issues.append("evaluator_roles_missing")
        if not normalize_string_list(report.get("source_categories") or []):
            issues.append("source_categories_missing")
        web_source_evidence = report.get("web_source_evidence") if isinstance(report.get("web_source_evidence"), list) else []
        if not web_source_evidence:
            issues.append("web_source_evidence_missing")
        if not metrics:
            issues.append("capability_metrics_missing")
        for index, metric in enumerate(metrics):
            if not isinstance(metric, dict):
                continue
            for field in ("observable_behaviors", "quantitative_indicators", "diagnostic_methods", "learning_evidence", "source_evidence"):
                if not normalize_string_list(metric.get(field) or []):
                    issues.append(f"capability_metrics.{index}.{field}_missing")
        if not evidence_summary:
            issues.append("evidence_summary_missing")
        if not normalize_string_list(report.get("selection_rationale")):
            issues.append("selection_rationale_missing")
        if not diagnostic_scope:
            issues.append("diagnostic_scope_missing")
        else:
            if not normalize_string_list(diagnostic_scope.get("target_capability_ids") or []):
                issues.append("diagnostic_scope.target_capability_ids_missing")
            if not normalize_string_list(diagnostic_scope.get("scoring_dimensions") or []):
                issues.append("diagnostic_scope.scoring_dimensions_missing")
            if not normalize_string_list(diagnostic_scope.get("gap_judgement_basis") or []):
                issues.append("diagnostic_scope.gap_judgement_basis_missing")
    elif normalized_stage == "diagnostic":
        diagnostic_plan = candidate.get("diagnostic_plan") if isinstance(candidate.get("diagnostic_plan"), dict) else {}
        items = candidate.get("diagnostic_items") if isinstance(candidate.get("diagnostic_items"), list) else []
        result = candidate.get("diagnostic_result") if isinstance(candidate.get("diagnostic_result"), dict) else {}
        profile = candidate.get("diagnostic_profile") if isinstance(candidate.get("diagnostic_profile"), dict) else {}
        research_report = candidate.get("research_report") if isinstance(candidate.get("research_report"), dict) else {}
        diagnostic_scope = research_report.get("diagnostic_scope") if isinstance(research_report.get("diagnostic_scope"), dict) else {}
        delivery = str(diagnostic_plan.get("delivery") or diagnostic_plan.get("diagnostic_delivery") or "").strip()
        assessment_kind = str(diagnostic_plan.get("assessment_kind") or profile.get("assessment_kind") or "").strip()
        session_intent = str(diagnostic_plan.get("session_intent") or profile.get("session_intent") or "").strip()
        plan_execution_mode = str(diagnostic_plan.get("plan_execution_mode") or profile.get("plan_execution_mode") or "").strip()
        round_index = diagnostic_plan.get("round_index") if "round_index" in diagnostic_plan else profile.get("round_index")
        max_rounds = diagnostic_plan.get("max_rounds") if "max_rounds" in diagnostic_plan else profile.get("max_rounds")
        questions_per_round = diagnostic_plan.get("questions_per_round") if "questions_per_round" in diagnostic_plan else profile.get("questions_per_round")
        result_status = str(result.get("status") or "").strip().lower()
        profile_status = str(profile.get("status") or "").strip().lower()
        evaluated = result_status == "evaluated" or profile_status == "validated"
        target_capability_ids = normalize_string_list(diagnostic_plan.get("target_capability_ids") or [])
        scoring_rubric = diagnostic_plan.get("scoring_rubric") if isinstance(diagnostic_plan.get("scoring_rubric"), list) else []
        blueprint_missing_fields = diagnostic_blueprint_missing_fields(target_capability_ids, scoring_rubric, items)
        if "target_capability_ids" in blueprint_missing_fields:
            issues.append("target_capability_ids_missing")
        if "scoring_rubric" in blueprint_missing_fields:
            issues.append("scoring_rubric_missing")
        if "diagnostic_items" in blueprint_missing_fields:
            issues.append("diagnostic_items_missing")
        if "diagnostic_items_blueprint" in blueprint_missing_fields:
            issues.append("diagnostic_items_blueprint_missing")
        if diagnostic_scope:
            scope_capability_ids = normalize_string_list(diagnostic_scope.get("target_capability_ids") or [])
            if scope_capability_ids and not set(scope_capability_ids).issubset(set(target_capability_ids)):
                issues.append("research_scope_alignment_missing")
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
        try:
            questions_per_round_value = int(questions_per_round)
        except (TypeError, ValueError):
            questions_per_round_value = 0
        if round_index_value < 1:
            issues.append("round_index_missing")
        if max_rounds_value < max(1, round_index_value):
            issues.append("max_rounds_invalid")
        if questions_per_round_value < 1:
            issues.append("questions_per_round_missing")
        if "follow_up_needed" not in result and "follow_up_needed" not in profile and "follow_up_needed" not in diagnostic_plan:
            issues.append("follow_up_needed_missing")
        if not str(result.get("stop_reason") or profile.get("stop_reason") or diagnostic_plan.get("stop_reason") or "").strip():
            issues.append("stop_reason_missing")
        if not str(diagnostic_plan.get("start_difficulty") or profile.get("start_difficulty") or "").strip():
            issues.append("start_difficulty_missing")
        if not normalize_string_list(diagnostic_plan.get("difficulty_ladder") or profile.get("difficulty_ladder") or []):
            issues.append("difficulty_ladder_missing")
        adjustment_policy = diagnostic_plan.get("difficulty_adjustment_policy") or profile.get("difficulty_adjustment_policy")
        if not isinstance(adjustment_policy, dict) or not adjustment_policy:
            issues.append("difficulty_adjustment_policy_missing")
        if evaluated:
            capability_assessment = result.get("capability_assessment") if isinstance(result.get("capability_assessment"), list) else []
            if capability_assessment and not any(
                isinstance(item, dict)
                and str(item.get("capability_id") or item.get("dimension") or "").strip()
                and str(item.get("current_level") or item.get("status") or "").strip()
                and "confidence" in item
                for item in capability_assessment
            ):
                issues.append("capability_assessment_invalid")
            if not str(result.get("recommended_entry_level") or profile.get("recommended_entry_level") or "").strip():
                issues.append("recommended_entry_level_missing")
            confidence = result.get("confidence") if "confidence" in result else profile.get("confidence")
            if normalize_confidence(confidence, default=-1.0) < 0:
                issues.append("confidence_missing")
    elif normalized_stage == "approval":
        approval_state = candidate.get("approval_state") if isinstance(candidate.get("approval_state"), dict) else {}
        if not approval_state:
            issues.append("approval_state_missing")
        approval_status = str(approval_state.get("approval_status") or "").strip().lower()
        if approval_status not in {"approved", "accepted", "confirmed"}:
            issues.append("approval_status_missing")
        if not bool(approval_state.get("ready_for_execution")):
            issues.append("ready_for_execution_missing")
        if list(approval_state.get("pending_decisions") or []):
            issues.append("pending_decisions")
        for field in (
            "confirmed_material_strategy",
            "confirmed_daily_execution_style",
            "confirmed_mastery_checks",
        ):
            if not approval_state.get(field):
                issues.append(f"{field}_missing")
        material_curation = candidate.get("material_curation") if isinstance(candidate.get("material_curation"), dict) else {}
        if not material_curation:
            issues.append("material_curation_missing")
        else:
            if str(material_curation.get("status") or "").strip().lower() != "confirmed":
                issues.append("material_curation_not_confirmed")
            user_confirmation = material_curation.get("user_confirmation") if isinstance(material_curation.get("user_confirmation"), dict) else {}
            if not bool(user_confirmation.get("confirmed")):
                issues.append("material_curation_user_confirmation_missing")
            mainline_items = [
                item for item in (material_curation.get("materials") or [])
                if isinstance(item, dict) and item.get("role") == "mainline" and item.get("selection_status") == "confirmed"
            ]
            if not mainline_items and not str(material_curation.get("mainline_unavailable_reason") or "").strip():
                issues.append("material_curation_no_mainline")
            for item in mainline_items:
                if not list(item.get("excerpt_briefs") or []):
                    issues.append("material_curation_missing_excerpts")
                    break
            if list(user_confirmation.get("pending_questions") or []):
                issues.append("material_curation_unresolved_risks")
            invalid_mainline = [
                item for item in mainline_items
                if str(item.get("cache_status") or "") in {"download-failed", "validation-failed"}
            ]
            if mainline_items and len(invalid_mainline) == len(mainline_items) and not list(material_curation.get("open_risks") or []):
                issues.append("material_curation_cache_validation_missing")
    elif normalized_stage == "planning":
        plan_candidate = candidate.get("plan_candidate") if isinstance(candidate.get("plan_candidate"), dict) else {}
        if not plan_candidate:
            issues.append("plan_candidate_missing")
        if not normalize_string_list(plan_candidate.get("stage_goals")):
            issues.append("stage_goals_missing")
        if not normalize_string_list(plan_candidate.get("mastery_checks")):
            issues.append("mastery_checks_missing")
        if not normalize_string_list(plan_candidate.get("problem_definition") if isinstance(plan_candidate.get("problem_definition"), list) else [plan_candidate.get("problem_definition")]):
            issues.append("problem_definition_missing")
        plan_stages = plan_candidate.get("stages") if isinstance(plan_candidate.get("stages"), list) else []
        for index, stage_item in enumerate(plan_stages):
            if not isinstance(stage_item, dict):
                continue
            for field in ("target_gap", "capability_metric", "evidence_requirement", "approx_time_range"):
                if not normalize_string_list(stage_item.get(field) if isinstance(stage_item.get(field), list) else [stage_item.get(field)]):
                    issues.append(f"stages.{index}.{field}_missing")
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
