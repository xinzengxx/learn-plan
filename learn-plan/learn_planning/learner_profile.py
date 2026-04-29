from __future__ import annotations

from typing import Any

from learn_core.text_utils import normalize_string_list
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
    learner_model: dict[str, Any] | None = None,
    curriculum_patch_queue: dict[str, Any] | None = None,
    mode: str = "draft",
) -> dict[str, Any]:
    clarification = clarification or {}
    research = research or {}
    diagnostic = diagnostic or {}
    approval = approval or {}
    planning = planning or {}
    learner_model = learner_model or {}
    curriculum_patch_queue = curriculum_patch_queue or {}

    family = detect_topic_family_from_configs(topic, family_configs)
    clarification_state = clarification.get("clarification_state") if isinstance(clarification.get("clarification_state"), dict) else {}
    research_plan = research.get("research_plan") if isinstance(research.get("research_plan"), dict) else {}
    research_report = research.get("research_report") if isinstance(research.get("research_report"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    approval_state = approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {}
    material_curation = approval.get("material_curation") if isinstance(approval.get("material_curation"), dict) else {}
    planning_candidate = planning.get("plan_candidate") if isinstance(planning.get("plan_candidate"), dict) else {}
    planning_quality_review = planning.get("quality_review") if isinstance(planning.get("quality_review"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
    diagnostic_result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}

    learner_strengths = normalize_string_list(learner_model.get("strengths") or [])
    learner_weaknesses = normalize_string_list(learner_model.get("weaknesses") or [])
    learner_review_debt = normalize_string_list(learner_model.get("review_debt") or [])
    learner_mastered_scope = normalize_string_list(learner_model.get("mastered_scope") or [])
    patches = [item for item in (curriculum_patch_queue.get("patches") or []) if isinstance(item, dict)]
    pending_patches = [
        item for item in patches
        if str(item.get("status") or "").strip() in {"proposed", "pending", "pending-evidence"}
    ]
    approved_patches = [
        item for item in patches
        if str(item.get("status") or "").strip() == "approved"
    ]
    applied_patches = [
        item for item in patches
        if str(item.get("status") or "").strip() == "applied"
    ]
    rejected_patches = [
        item for item in patches
        if str(item.get("status") or "").strip() == "rejected"
    ]
    pending_patch_decisions = [
        f"patch[{item.get('patch_type') or 'unknown'}] {item.get('topic') or topic}: {item.get('rationale') or '待确认是否吸收进正式计划'}"
        for item in pending_patches
    ]
    patch_review_focus = normalize_string_list(
        decision
        for item in pending_patches
        for decision in (
            ((item.get("proposal") or {}).get("review_focus") if isinstance(item.get("proposal"), dict) else []) or []
        )
    )
    patch_next_actions = normalize_string_list(
        action
        for item in pending_patches
        for action in (
            ((item.get("proposal") or {}).get("next_actions") if isinstance(item.get("proposal"), dict) else []) or []
        )
    )
    user_model_seed = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    goal_model_seed = clarification.get("goal_model") if isinstance(clarification.get("goal_model"), dict) else {}
    user_model = {
        "profile": user_model_seed.get("profile") or f"当前围绕 {topic} 建立长期学习路线，当前水平为：{level}。",
        "constraints": list(user_model_seed.get("constraints") or [schedule or "未指定时间约束"]),
        "preferences": list(user_model_seed.get("preferences") or [preference]),
        "strengths": list(user_model_seed.get("strengths") or learner_strengths or ["已有一定基础，需要从当前水平继续推进而非回到纯模板入门"]),
        "weaknesses": list(user_model_seed.get("weaknesses") or learner_weaknesses or ["仍需通过诊断、session 和复盘持续校准真实薄弱点"]),
        "learning_style": list(preference_state.get("learning_style") or []),
        "practice_style": list(preference_state.get("practice_style") or []),
        "delivery_preference": list(preference_state.get("delivery_preference") or []),
        "review_debt": learner_review_debt,
        "mastered_scope": learner_mastered_scope,
    }
    goal_model = {
        "mainline_goal": goal_model_seed.get("mainline_goal") or goal,
        "supporting_capabilities": list(goal_model_seed.get("supporting_capabilities") or patch_review_focus or [
            f"支撑 {topic} 主线推进的基础表达与概念稳定性",
            "阅读、练习、复盘三类证据闭环",
        ]),
        "enhancement_modules": list(goal_model_seed.get("enhancement_modules") or patch_next_actions or [f"围绕 {family} family 的进阶专题与应用扩展"]),
    }
    research_needed = needs_research(topic, goal)
    diagnostic_result_status = str(diagnostic_result.get("status") or "").strip().lower()
    diagnostic_profile_status = str(diagnostic_profile.get("status") or "").strip().lower()
    diagnostic_evaluated = diagnostic_result_status == "evaluated" or diagnostic_profile_status == "validated"
    pending_decisions = normalize_string_list(approval_state.get("pending_decisions") or [])
    effective_pending_decisions = normalize_string_list([*pending_decisions, *pending_patch_decisions])
    planning_state = {
        "clarification_status": clarification_state.get("status") or ("confirmed" if clarification else ("captured" if mode != "draft" else "needs-more")),
        "deepsearch_status": research.get("deepsearch_status") or ("completed" if research_report else ("needed-pending-plan" if research_needed else "not-needed")),
        "diagnostic_status": diagnostic_profile.get("status") or diagnostic_result.get("status") or ("in-progress" if diagnostic or mode == "diagnostic" else "not-started"),
        "preference_status": preference_state.get("status") or ("confirmed" if preference_state else ("needs-confirmation" if mode == "finalize" else "not-started")),
        "plan_status": approval_state.get("approval_status") or ("approved" if mode == "finalize" and approval_state.get("ready_for_execution") and not effective_pending_decisions else ("pending-confirmation" if mode == "finalize" or effective_pending_decisions else "draft")),
        "diagnostic_round_index": diagnostic_plan.get("round_index") or diagnostic_profile.get("round_index") or 1,
        "diagnostic_max_rounds": diagnostic_plan.get("max_rounds") or diagnostic_profile.get("max_rounds") or 1,
        "questions_per_round": diagnostic_plan.get("questions_per_round") or diagnostic_profile.get("questions_per_round"),
        "diagnostic_follow_up_needed": diagnostic_result.get("follow_up_needed") if "follow_up_needed" in diagnostic_result else diagnostic_profile.get("follow_up_needed"),
        "learner_model_confidence": learner_model.get("confidence"),
        "pending_patch_count": len(pending_patches),
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
            "goal_target_band": research_report.get("goal_target_band"),
            "must_master_core": list(research_report.get("must_master_core") or []),
            "evidence_expectations": list(research_report.get("evidence_expectations") or []),
            "research_brief": research_report.get("research_brief"),
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
            "round_index": diagnostic_plan.get("round_index") or diagnostic_profile.get("round_index") or 1,
            "max_rounds": diagnostic_plan.get("max_rounds") or diagnostic_profile.get("max_rounds") or 1,
            "questions_per_round": diagnostic_plan.get("questions_per_round") or diagnostic_profile.get("questions_per_round"),
            "follow_up_needed": diagnostic_result.get("follow_up_needed") if "follow_up_needed" in diagnostic_result else diagnostic_profile.get("follow_up_needed"),
            "stop_reason": diagnostic_result.get("stop_reason") or diagnostic_profile.get("stop_reason"),
            "baseline_level": diagnostic_profile.get("baseline_level") or level,
            "dimensions": list(diagnostic_profile.get("dimensions") or []),
            "observed_strengths": list(diagnostic_profile.get("observed_strengths") or []),
            "observed_weaknesses": list(diagnostic_profile.get("observed_weaknesses") or []),
            "evidence": list(diagnostic_profile.get("evidence") or []),
            "recommended_entry_level": (diagnostic_result.get("recommended_entry_level") or diagnostic_profile.get("recommended_entry_level")) if diagnostic_evaluated else None,
            "confidence": (diagnostic_result.get("confidence") if "confidence" in diagnostic_result else diagnostic_profile.get("confidence")) if diagnostic_evaluated else None,
            "status": diagnostic_profile.get("status") or diagnostic_result.get("status") or planning_state["diagnostic_status"],
        },
        "approval_state": {
            "approval_status": approval_state.get("approval_status") or planning_state["plan_status"],
            "pending_decisions": effective_pending_decisions,
            "approved_scope": list(approval_state.get("approved_scope") or []),
            "approved_patch_ids": normalize_string_list(approval_state.get("approved_patch_ids") or []),
            "rejected_patch_ids": normalize_string_list(approval_state.get("rejected_patch_ids") or []),
            "ready_for_execution": bool(approval_state.get("ready_for_execution")) and not effective_pending_decisions,
        },
        "material_curation": material_curation,
        "plan_candidate": planning_candidate,
        "planning_artifact": planning,
        "planning_quality_review": planning_quality_review,
        "learner_model": {
            "strengths": learner_strengths,
            "weaknesses": learner_weaknesses,
            "review_debt": learner_review_debt,
            "mastered_scope": learner_mastered_scope,
            "confidence": learner_model.get("confidence"),
            "last_updated": learner_model.get("last_updated"),
        },
        "curriculum_patch_queue": {
            "pending_patch_count": len(pending_patches),
            "pending_patch_ids": normalize_string_list(item.get("id") for item in pending_patches),
            "pending_patch_topics": normalize_string_list(item.get("topic") for item in pending_patches),
            "pending_decisions": pending_patch_decisions,
            "approved_patch_ids": normalize_string_list(item.get("id") for item in approved_patches),
            "approved_patch_topics": normalize_string_list(item.get("topic") for item in approved_patches),
            "approved_summaries": normalize_string_list(
                f"patch[{item.get('patch_type') or 'unknown'}] {item.get('topic') or topic}: {item.get('rationale') or '已批准，等待写入正式计划'}"
                for item in approved_patches
            ),
            "applied_patch_ids": normalize_string_list(item.get("id") for item in applied_patches),
            "applied_patch_topics": normalize_string_list(item.get("topic") for item in applied_patches),
            "rejected_patch_ids": normalize_string_list(item.get("id") for item in rejected_patches),
            "rejected_patch_topics": normalize_string_list(item.get("topic") for item in rejected_patches),
        },
        "needs": [
            "顾问式澄清",
            "深度检索报告确认",
            "主线资料本地可得",
            "章节/页码级学习定位",
            "阅读/练习/项目/复盘联合检验",
            "待审批 patch 只能在 approval/finalize 后吸收进正式计划",
        ],
    }
