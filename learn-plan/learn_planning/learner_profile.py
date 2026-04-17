from __future__ import annotations

from typing import Any

from learn_core.topic_family import detect_topic_family_from_configs
from learn_workflow import needs_research


def build_planning_profile(
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    *,
    family_configs: dict[str, dict[str, Any]],
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    planning: dict[str, Any] | None = None,
    mode: str = "draft",
) -> dict[str, Any]:
    clarification = clarification or {}
    research = research or {}
    diagnostic = diagnostic or {}
    approval = approval or {}
    planning = planning or {}

    family = detect_topic_family_from_configs(topic, family_configs)
    clarification_state = clarification.get("clarification_state") if isinstance(clarification.get("clarification_state"), dict) else {}
    research_plan = research.get("research_plan") if isinstance(research.get("research_plan"), dict) else {}
    research_report = research.get("research_report") if isinstance(research.get("research_report"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    approval_state = approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {}
    planning_candidate = planning.get("plan_candidate") if isinstance(planning.get("plan_candidate"), dict) else {}
    planning_quality_review = planning.get("quality_review") if isinstance(planning.get("quality_review"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
    diagnostic_result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}

    user_model_seed = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    goal_model_seed = clarification.get("goal_model") if isinstance(clarification.get("goal_model"), dict) else {}
    user_model = {
        "profile": user_model_seed.get("profile") or f"当前围绕 {topic} 建立长期学习路线，当前水平为：{level}。",
        "constraints": list(user_model_seed.get("constraints") or [schedule or "未指定时间约束"]),
        "preferences": list(user_model_seed.get("preferences") or [preference]),
        "strengths": list(user_model_seed.get("strengths") or ["已有一定基础，需要从当前水平继续推进而非回到纯模板入门"]),
        "weaknesses": list(user_model_seed.get("weaknesses") or ["仍需通过诊断、session 和复盘持续校准真实薄弱点"]),
        "learning_style": list(preference_state.get("learning_style") or []),
        "practice_style": list(preference_state.get("practice_style") or []),
        "delivery_preference": list(preference_state.get("delivery_preference") or []),
    }
    goal_model = {
        "mainline_goal": goal_model_seed.get("mainline_goal") or goal,
        "supporting_capabilities": list(goal_model_seed.get("supporting_capabilities") or [
            f"支撑 {topic} 主线推进的基础表达与概念稳定性",
            "阅读、练习、复盘三类证据闭环",
        ]),
        "enhancement_modules": list(goal_model_seed.get("enhancement_modules") or [f"围绕 {family} family 的进阶专题与应用扩展"]),
    }
    research_needed = needs_research(topic, goal)
    planning_state = {
        "clarification_status": clarification_state.get("status") or ("confirmed" if clarification else ("captured" if mode != "draft" else "needs-more")),
        "deepsearch_status": research.get("deepsearch_status") or ("completed" if research_report else ("needed-pending-plan" if research_needed else "not-needed")),
        "diagnostic_status": diagnostic_profile.get("status") or ("validated" if diagnostic_profile else ("in-progress" if mode == "diagnostic" else "not-started")),
        "preference_status": preference_state.get("status") or ("confirmed" if preference_state else ("needs-confirmation" if mode == "finalize" else "not-started")),
        "plan_status": approval_state.get("approval_status") or ("approved" if mode == "finalize" and approval_state.get("ready_for_execution") else ("pending-confirmation" if mode == "finalize" else "draft")),
        "assessment_depth": diagnostic_plan.get("assessment_depth") or diagnostic_profile.get("assessment_depth") or user_model_seed.get("assessment_depth_preference") or "undecided",
        "diagnostic_round_index": diagnostic_plan.get("round_index") or diagnostic_profile.get("round_index") or 1,
        "diagnostic_max_rounds": diagnostic_plan.get("max_rounds") or diagnostic_profile.get("max_rounds") or 1,
        "diagnostic_follow_up_needed": diagnostic_result.get("follow_up_needed") if "follow_up_needed" in diagnostic_result else None,
    }
    return {
        "topic": topic,
        "goal": goal,
        "level": level,
        "schedule": schedule,
        "preference": preference,
        "family": family,
        "mode": mode,
        "user_model": user_model,
        "goal_model": goal_model,
        "planning_state": planning_state,
        "clarification_state": {
            "questions": list(clarification_state.get("questions") or []),
            "resolved_items": list(clarification_state.get("resolved_items") or []),
            "open_questions": list(clarification_state.get("open_questions") or []),
            "assumptions": list(clarification_state.get("assumptions") or []),
            "constraints_confirmed": list(clarification_state.get("constraints_confirmed") or user_model["constraints"]),
            "non_goals": list(clarification_state.get("non_goals") or []),
        },
        "preference_state": {
            "status": preference_state.get("status") or planning_state["preference_status"],
            "learning_style": list(preference_state.get("learning_style") or user_model.get("learning_style") or []),
            "practice_style": list(preference_state.get("practice_style") or user_model.get("practice_style") or []),
            "delivery_preference": list(preference_state.get("delivery_preference") or user_model.get("delivery_preference") or []),
            "pending_items": list(preference_state.get("pending_items") or []),
        },
        "research_plan": {
            "research_questions": list(research_plan.get("research_questions") or research_plan.get("questions") or []),
            "source_types": list(research_plan.get("source_types") or []),
            "candidate_directions": list(research_plan.get("candidate_directions") or []),
            "selection_criteria": list(research_plan.get("selection_criteria") or []),
        },
        "research_report": {
            "must_master_capabilities": list(research_report.get("must_master_capabilities") or research_report.get("must_master") or []),
            "capability_layers": list(research_report.get("capability_layers") or []),
            "mainline_capabilities": list(research_report.get("mainline_capabilities") or []),
            "supporting_capabilities": list(research_report.get("supporting_capabilities") or []),
            "deferred_capabilities": list(research_report.get("deferred_capabilities") or []),
            "candidate_paths": list(research_report.get("candidate_paths") or []),
            "candidate_materials": list(research_report.get("candidate_materials") or []),
            "selection_rationale": list(research_report.get("selection_rationale") or []),
            "evidence_summary": list(research_report.get("evidence_summary") or []),
            "report_status": research_report.get("report_status") or ("completed" if research_report else "missing"),
            "open_risks": list(research_report.get("open_risks") or []),
        },
        "diagnostic_profile": {
            "assessment_depth": diagnostic_plan.get("assessment_depth") or diagnostic_profile.get("assessment_depth") or user_model_seed.get("assessment_depth_preference") or "undecided",
            "round_index": diagnostic_plan.get("round_index") or diagnostic_profile.get("round_index") or 1,
            "max_rounds": diagnostic_plan.get("max_rounds") or diagnostic_profile.get("max_rounds") or 1,
            "follow_up_needed": diagnostic_result.get("follow_up_needed") if "follow_up_needed" in diagnostic_result else diagnostic_profile.get("follow_up_needed"),
            "stop_reason": diagnostic_result.get("stop_reason") or diagnostic_profile.get("stop_reason"),
            "baseline_level": diagnostic_profile.get("baseline_level") or level,
            "dimensions": list(diagnostic_profile.get("dimensions") or []),
            "observed_strengths": list(diagnostic_profile.get("observed_strengths") or []),
            "observed_weaknesses": list(diagnostic_profile.get("observed_weaknesses") or []),
            "evidence": list(diagnostic_profile.get("evidence") or []),
            "recommended_entry_level": diagnostic_profile.get("recommended_entry_level") or level,
            "confidence": diagnostic_profile.get("confidence"),
            "status": diagnostic_profile.get("status") or planning_state["diagnostic_status"],
        },
        "approval_state": {
            "approval_status": approval_state.get("approval_status") or planning_state["plan_status"],
            "pending_decisions": list(approval_state.get("pending_decisions") or []),
            "approved_scope": list(approval_state.get("approved_scope") or []),
            "ready_for_execution": bool(approval_state.get("ready_for_execution")),
        },
        "plan_candidate": planning_candidate,
        "planning_artifact": planning,
        "planning_quality_review": planning_quality_review,
        "needs": [
            "顾问式澄清",
            "深度检索报告确认",
            "主线资料本地可得",
            "章节/页码级学习定位",
            "阅读/练习/项目/复盘联合检验",
        ],
    }
