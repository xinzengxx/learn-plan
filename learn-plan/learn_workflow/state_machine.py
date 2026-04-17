from __future__ import annotations

from typing import Any

from learn_core.quality_review import collect_quality_issues, normalize_confidence
from learn_core.text_utils import normalize_string_list

from .contracts import CONTRACT_VERSION, NEXT_ACTION_ENTER_TODAY, WORKFLOW_STATE_QUALITY_PREFIXES, next_action_for_mode


RESEARCH_KEYWORDS = (
    "工作",
    "就业",
    "转岗",
    "面试",
    "岗位",
    "求职",
    "职业",
    "大模型",
    "llm",
    "agent",
    "rag",
    "langchain",
    "langgraph",
    "模型应用",
    "应用开发",
)
LEVEL_UNCERTAIN_KEYWORDS = (
    "不确定",
    "说不清",
    "不清楚",
    "不会判断",
    "不知道自己什么水平",
)
QUALITY_CONFIDENCE_THRESHOLD = {
    "clarification": 0.35,
    "research": 0.45,
    "diagnostic": 0.5,
    "approval": 0.4,
    "planning": 0.45,
}
ASSESSMENT_DEPTH_CHOICES = {"simple", "deep"}
LEGACY_DIAGNOSTIC_ASSESSMENT_KIND = "plan-diagnostic"
INITIAL_TEST_ASSESSMENT_KIND = "initial-test"
LEGACY_DIAGNOSTIC_SESSION_INTENT = "plan-diagnostic"
INITIAL_TEST_SESSION_INTENT = "assessment"
ASSESSMENT_DEPTH_ALIASES = {
    "simple": "simple",
    "简单": "simple",
    "简单测评": "simple",
    "deep": "deep",
    "深度": "deep",
    "深度测评": "deep",
}


def normalize_assessment_depth(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return ASSESSMENT_DEPTH_ALIASES.get(normalized, normalized if normalized in ASSESSMENT_DEPTH_CHOICES else "undecided")


def resolve_assessment_depth_preference(
    clarification: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> str:
    clarification = clarification if isinstance(clarification, dict) else {}
    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    mastery_preferences = questionnaire.get("mastery_preferences") if isinstance(questionnaire.get("mastery_preferences"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    user_model = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    for value in (
        mastery_preferences.get("assessment_depth_preference"),
        questionnaire.get("assessment_depth_preference"),
        preference_state.get("assessment_depth_preference"),
        user_model.get("assessment_depth_preference"),
        diagnostic_plan.get("assessment_depth"),
        diagnostic_profile.get("assessment_depth"),
    ):
        depth = normalize_assessment_depth(value)
        if depth in ASSESSMENT_DEPTH_CHOICES:
            return depth
    return "undecided"


def diagnostic_metadata_is_valid(assessment_kind: Any, session_intent: Any, plan_execution_mode: Any | None = None) -> bool:
    normalized_kind = str(assessment_kind or "").strip()
    normalized_intent = str(session_intent or "").strip()
    normalized_execution_mode = str(plan_execution_mode or "").strip()
    if normalized_kind == LEGACY_DIAGNOSTIC_ASSESSMENT_KIND and normalized_intent == LEGACY_DIAGNOSTIC_SESSION_INTENT:
        return True
    return (
        normalized_kind == INITIAL_TEST_ASSESSMENT_KIND
        and normalized_intent == INITIAL_TEST_SESSION_INTENT
        and normalized_execution_mode == "diagnostic"
    )


def _normalized_goal_text(topic: str, goal: str) -> str:
    return f"{topic} {goal}".lower()


def needs_research(topic: str, goal: str) -> bool:
    normalized_goal = _normalized_goal_text(topic, goal)
    return any(keyword in normalized_goal for keyword in RESEARCH_KEYWORDS)


def level_uncertain(topic: str, goal: str, diagnostic: dict[str, Any] | None = None) -> bool:
    normalized_goal = _normalized_goal_text(topic, goal)
    if any(keyword in normalized_goal for keyword in LEVEL_UNCERTAIN_KEYWORDS):
        return True
    return not bool(diagnostic)


def infer_workflow_type(topic: str, goal: str, diagnostic: dict[str, Any] | None = None) -> str:
    research_needed = needs_research(topic, goal)
    diagnostic_needed = level_uncertain(topic, goal, diagnostic)
    if research_needed and diagnostic_needed:
        return "mixed"
    if research_needed:
        return "research-first"
    if diagnostic_needed:
        return "diagnostic-first"
    return "light"


def _artifact_has_quality_signal(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "quality_review",
            "generation_trace",
            "traceability",
            "evidence",
            "confidence",
            "candidate_version",
            "stage",
        )
    )



def _collect_stage_quality(
    *,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    planning: dict[str, Any] | None = None,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    artifacts = {
        "clarification": clarification or {},
        "research": research or {},
        "diagnostic": diagnostic or {},
        "approval": approval or {},
        "planning": planning or {},
    }
    issues_by_stage: dict[str, list[str]] = {}
    quality_summary: dict[str, dict[str, Any]] = {}
    for stage, payload in artifacts.items():
        artifact = payload if isinstance(payload, dict) else {}
        review = artifact.get("quality_review") if isinstance(artifact.get("quality_review"), dict) else {}
        if not artifact:
            issues_by_stage[stage] = []
            quality_summary[stage] = {
                "present": False,
                "valid": False,
                "verdict": "missing",
                "confidence": 0.0,
                "reviewer": "",
                "issues": [],
            }
            continue
        if not _artifact_has_quality_signal(artifact):
            issues_by_stage[stage] = []
            quality_summary[stage] = {
                "present": True,
                "evaluated": False,
                "valid": True,
                "verdict": "legacy-unreviewed",
                "confidence": normalize_confidence(artifact.get("confidence"), default=0.0),
                "reviewer": "",
                "issues": [],
            }
            continue
        issues = normalize_string_list(
            collect_quality_issues(
                artifact,
                prefix=WORKFLOW_STATE_QUALITY_PREFIXES.get(stage, stage),
                require_evidence=True,
                require_traceability=True,
                require_generation_trace=True,
                require_review=True,
                require_valid_review=True,
                min_confidence=QUALITY_CONFIDENCE_THRESHOLD.get(stage),
            )
        )
        issues_by_stage[stage] = issues
        quality_summary[stage] = {
            "present": True,
            "evaluated": True,
            "valid": (not issues) and (bool(review.get("valid")) if review else True),
            "verdict": str(review.get("verdict") or ("ready" if not issues else "needs-revision")).strip() or ("ready" if not issues else "needs-revision"),
            "confidence": normalize_confidence(artifact.get("confidence"), default=0.0),
            "reviewer": str(review.get("reviewer") or "").strip(),
            "issues": issues,
        }
    return issues_by_stage, quality_summary


def collect_missing_requirements(
    *,
    topic: str,
    goal: str,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    clarification = clarification or {}
    research = research or {}
    diagnostic = diagnostic or {}
    approval = approval or {}

    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    clarification_state = clarification.get("clarification_state") if isinstance(clarification.get("clarification_state"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    user_model = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    goal_model = clarification.get("goal_model") if isinstance(clarification.get("goal_model"), dict) else {}

    success_criteria = list(
        questionnaire.get("success_criteria")
        or goal_model.get("supporting_capabilities")
        or ([goal_model.get("mainline_goal")] if goal_model.get("mainline_goal") else [])
    )
    current_level_self_report = str(
        questionnaire.get("current_level_self_report")
        or user_model.get("profile")
        or ""
    ).strip()
    time_constraints = questionnaire.get("time_constraints") if isinstance(questionnaire.get("time_constraints"), dict) else {}
    legacy_constraints = list(user_model.get("constraints") or clarification_state.get("constraints_confirmed") or [])
    assessment_depth_preference = resolve_assessment_depth_preference(clarification, diagnostic)

    clarification_missing: list[str] = []
    if not (str(topic or "").strip() or str(questionnaire.get("topic") or "").strip()):
        clarification_missing.append("clarification.topic")
    if not (str(goal or "").strip() or str(questionnaire.get("goal") or "").strip()):
        clarification_missing.append("clarification.goal")
    if not success_criteria:
        clarification_missing.append("clarification.success_criteria")
    if not current_level_self_report:
        clarification_missing.append("clarification.current_level_self_report")
    if not str(time_constraints.get("frequency") or "").strip() and not str(time_constraints.get("session_length") or "").strip() and not legacy_constraints:
        clarification_missing.append("clarification.time_constraints")
    if list(clarification_state.get("open_questions") or []):
        clarification_missing.append("clarification.open_questions")
    if not preference_state or list(preference_state.get("pending_items") or []):
        clarification_missing.append("clarification.preference_state")
    if assessment_depth_preference not in ASSESSMENT_DEPTH_CHOICES:
        clarification_missing.append("clarification.assessment_depth_preference")

    research_missing: list[str] = []
    if needs_research(topic, goal):
        research_plan = research.get("research_plan") if isinstance(research.get("research_plan"), dict) else {}
        research_report = research.get("research_report") if isinstance(research.get("research_report"), dict) else {}
        report_status = str(research_report.get("report_status") or ("completed" if research_report else "missing"))
        capability_metrics = list(research_report.get("capability_metrics") or [])
        visible_capabilities = list(research_report.get("must_master_capabilities") or research_report.get("must_master") or research_report.get("mainline_capabilities") or [])
        evidence_summary = list(research_report.get("evidence_summary") or research_report.get("source_evidence") or [])
        if not research:
            research_missing.append("research.report")
        plan_status = str(research_plan.get("status") or ("completed" if research_report else "")).strip().lower()
        if research_plan and plan_status not in {"approved", "completed"}:
            research_missing.append("research.plan_status")
        if report_status != "completed":
            research_missing.append("research.report_status")
        if not capability_metrics and not visible_capabilities:
            research_missing.append("research.capability_metrics")
        if not evidence_summary:
            research_missing.append("research.evidence")

    diagnostic_missing: list[str] = []
    if level_uncertain(topic, goal, diagnostic):
        diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
        diagnostic_result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}
        diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
        result_status = str(diagnostic_result.get("status") or "")
        profile_status = str(diagnostic_profile.get("status") or "")
        assessment_depth = str(diagnostic_plan.get("assessment_depth") or diagnostic_profile.get("assessment_depth") or "").strip()
        diagnostic_delivery = str(diagnostic_plan.get("delivery") or diagnostic_plan.get("diagnostic_delivery") or "").strip()
        diagnostic_assessment_kind = str(diagnostic_plan.get("assessment_kind") or diagnostic_profile.get("assessment_kind") or "").strip()
        diagnostic_session_intent = str(diagnostic_plan.get("session_intent") or diagnostic_profile.get("session_intent") or "").strip()
        diagnostic_execution_mode = str(diagnostic_plan.get("plan_execution_mode") or diagnostic_profile.get("plan_execution_mode") or "").strip()
        round_index = diagnostic_plan.get("round_index") if "round_index" in diagnostic_plan else diagnostic_profile.get("round_index")
        max_rounds = diagnostic_plan.get("max_rounds") if "max_rounds" in diagnostic_plan else diagnostic_profile.get("max_rounds")
        if not diagnostic:
            diagnostic_missing.append("diagnostic.result")
        if result_status and result_status != "evaluated" and profile_status != "validated":
            diagnostic_missing.append("diagnostic.result_status")
        if not diagnostic_result and profile_status != "validated":
            diagnostic_missing.append("diagnostic.result_status")
        if not list(diagnostic_result.get("capability_assessment") or []) and not list(diagnostic_profile.get("dimensions") or []):
            diagnostic_missing.append("diagnostic.capability_assessment")
        if assessment_depth not in {"simple", "deep"}:
            diagnostic_missing.append("diagnostic.assessment_depth")
        if diagnostic_delivery != "web-session":
            diagnostic_missing.append("diagnostic.delivery")
        if not diagnostic_metadata_is_valid(
            diagnostic_assessment_kind,
            diagnostic_session_intent,
            diagnostic_execution_mode,
        ):
            diagnostic_missing.append("diagnostic.assessment_kind")
            diagnostic_missing.append("diagnostic.session_intent")
        try:
            round_index_value = int(round_index)
        except (TypeError, ValueError):
            round_index_value = 0
        try:
            max_rounds_value = int(max_rounds)
        except (TypeError, ValueError):
            max_rounds_value = 0
        if round_index_value < 1:
            diagnostic_missing.append("diagnostic.round_index")
        if max_rounds_value < max(1, round_index_value):
            diagnostic_missing.append("diagnostic.max_rounds")
        if not str(diagnostic_result.get("recommended_entry_level") or diagnostic_profile.get("recommended_entry_level") or "").strip():
            diagnostic_missing.append("diagnostic.recommended_entry_level")
        if not str(diagnostic_profile.get("confidence") or "").strip():
            diagnostic_missing.append("diagnostic.confidence")
        if assessment_depth == "deep":
            if "follow_up_needed" not in diagnostic_result:
                diagnostic_missing.append("diagnostic.follow_up_needed")
            if not str(diagnostic_result.get("stop_reason") or "").strip():
                diagnostic_missing.append("diagnostic.stop_reason")

    approval_missing: list[str] = []
    approval_state = approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {}
    if not bool(approval_state.get("ready_for_execution")):
        approval_missing.append("approval.ready_for_execution")
    if list(approval_state.get("pending_decisions") or []):
        approval_missing.append("approval.pending_decisions")
    for field in (
        "confirmed_material_strategy",
        "confirmed_daily_execution_style",
        "confirmed_mastery_checks",
    ):
        if field in approval_state and not approval_state.get(field):
            approval_missing.append(f"approval.{field}")

    return {
        "clarification": clarification_missing,
        "research": research_missing,
        "diagnostic": diagnostic_missing,
        "approval": approval_missing,
    }


def build_workflow_state(
    *,
    topic: str,
    goal: str,
    requested_mode: str,
    current_mode: str,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    planning: dict[str, Any] | None = None,
    quality_issues: list[str] | None = None,
    artifacts: dict[str, str] | None = None,
) -> dict[str, Any]:
    missing_by_stage = collect_missing_requirements(
        topic=topic,
        goal=goal,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
    )
    stage_quality_issues, stage_quality = _collect_stage_quality(
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning=planning,
    )
    planning = planning or {}
    planning_candidate = planning.get("plan_candidate") if isinstance(planning.get("plan_candidate"), dict) else {}
    planning_missing: list[str] = []
    if str(current_mode or "").strip() == "finalize" and not planning_candidate:
        planning_missing.append("planning.plan_candidate")

    routing_reasons: list[str] = []
    blocking_stage = "ready"
    recommended_mode = "finalize"

    if missing_by_stage["clarification"]:
        blocking_stage = "clarification"
        recommended_mode = "draft"
        if "clarification.assessment_depth_preference" in missing_by_stage["clarification"]:
            routing_reasons.append("起始测评深度尚未确认，应先让用户明确选择 simple 或 deep，再进入网页诊断 session")
        else:
            routing_reasons.append("仍存在待澄清问题，应优先补齐顾问式澄清")
    elif stage_quality_issues["clarification"]:
        blocking_stage = "clarification"
        recommended_mode = "draft"
        routing_reasons.append("clarification candidate 尚未通过质量评审，应先补齐证据、追踪信息与未决项")
    elif missing_by_stage["research"]:
        blocking_stage = "research"
        recommended_mode = "research-report"
        routing_reasons.append("目标需要 research 支撑，应优先补齐能力要求与材料取舍依据")
    elif stage_quality_issues["research"]:
        blocking_stage = "research"
        recommended_mode = "research-report"
        routing_reasons.append("research candidate 尚未通过质量评审，应先补齐 evidence/source grounding 与取舍理由")
    elif missing_by_stage["diagnostic"]:
        blocking_stage = "diagnostic"
        recommended_mode = "diagnostic"
        routing_reasons.append("当前水平仍不可靠，应优先完成最小水平诊断")
    elif stage_quality_issues["diagnostic"]:
        blocking_stage = "diagnostic"
        recommended_mode = "diagnostic"
        routing_reasons.append("diagnostic candidate 尚未通过质量评审，应先补齐 confidence、推荐起点与能力覆盖")
    elif missing_by_stage["approval"]:
        blocking_stage = "approval"
        recommended_mode = "draft"
        routing_reasons.append("计划尚未通过 approval gate，应先完成确认与关键决策")
    elif stage_quality_issues["approval"]:
        blocking_stage = "approval"
        recommended_mode = "draft"
        routing_reasons.append("approval candidate 尚未通过质量评审，应先明确 ready 状态与待决策项")
    elif planning_missing:
        blocking_stage = "planning"
        recommended_mode = "finalize"
        routing_reasons.append("finalize 前仍缺少结构化 plan candidate，应先生成规划候选态")
    elif stage_quality_issues["planning"]:
        blocking_stage = "planning"
        recommended_mode = "finalize"
        routing_reasons.append("planning candidate 尚未通过质量评审，应先补齐阶段目标、掌握标准与执行逻辑")
    else:
        routing_reasons.append("主要 workflow gate 已满足，可进入 finalize / 执行阶段")

    external_quality_issues = normalize_string_list(quality_issues or [])
    combined_quality_issues = normalize_string_list(
        [
            *stage_quality_issues["clarification"],
            *stage_quality_issues["research"],
            *stage_quality_issues["diagnostic"],
            *stage_quality_issues["approval"],
            *stage_quality_issues["planning"],
            *external_quality_issues,
        ]
    )
    ready_for_entry = blocking_stage == "ready" and current_mode == "finalize" and not combined_quality_issues
    next_action = NEXT_ACTION_ENTER_TODAY if ready_for_entry else next_action_for_mode(recommended_mode)

    return {
        "contract_version": CONTRACT_VERSION,
        "workflow_type": infer_workflow_type(topic, goal, diagnostic),
        "requested_mode": requested_mode,
        "current_mode": current_mode,
        "recommended_mode": recommended_mode,
        "blocking_stage": blocking_stage,
        "should_continue_workflow": not ready_for_entry,
        "is_intermediate_product": not ready_for_entry,
        "next_action": next_action,
        "missing_requirements": [
            *missing_by_stage["clarification"],
            *missing_by_stage["research"],
            *missing_by_stage["diagnostic"],
            *missing_by_stage["approval"],
            *planning_missing,
        ],
        "routing_reasons": routing_reasons,
        "quality_issues": combined_quality_issues,
        "stage_quality": stage_quality,
        "artifacts": dict(artifacts or {}),
    }
