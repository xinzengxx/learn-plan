from __future__ import annotations

from typing import Any

from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_string_list


PLAN_CANDIDATE_VERSION = "learn-plan.plan-candidate.v1"


def build_plan_candidate(profile: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    research_report = profile.get("research_report") if isinstance(profile.get("research_report"), dict) else {}
    diagnostic_profile = profile.get("diagnostic_profile") if isinstance(profile.get("diagnostic_profile"), dict) else {}
    approval_state = profile.get("approval_state") if isinstance(profile.get("approval_state"), dict) else {}
    stages = curriculum.get("stages") if isinstance(curriculum.get("stages"), list) else []

    stage_goals = [
        f"{stage.get('name')}: {stage.get('goal')}"
        for stage in stages
        if isinstance(stage, dict) and stage.get("name") and stage.get("goal")
    ]
    material_roles = [
        f"{index + 1}. {stage.get('name')} 以 {', '.join(normalize_string_list(stage.get('reading'))[:2])} 为主线输入"
        for index, stage in enumerate(stages)
        if isinstance(stage, dict)
    ]
    mastery_checks = [
        f"{stage.get('name')}: {stage.get('test_gate')}"
        for stage in stages
        if isinstance(stage, dict) and stage.get("test_gate")
    ]
    daily_execution_logic = [
        f"当天先围绕 {stage.get('focus')} 讲解，再做 {', '.join(normalize_string_list(stage.get('exercise_types'))[:2])}。"
        for stage in stages
        if isinstance(stage, dict) and stage.get("focus")
    ]
    evidence = normalize_string_list(
        [
            f"goal={profile.get('goal')}",
            f"recommended_entry_level={diagnostic_profile.get('recommended_entry_level') or profile.get('level')}",
            *(research_report.get("evidence_summary") or []),
        ]
    )
    candidate = {
        "plan_candidate": {
            "topic": profile.get("topic"),
            "goal": profile.get("goal"),
            "entry_level": diagnostic_profile.get("recommended_entry_level") or profile.get("level"),
            "stage_goals": stage_goals,
            "material_roles": material_roles,
            "mastery_checks": mastery_checks,
            "daily_execution_logic": daily_execution_logic,
            "tradeoffs": normalize_string_list(approval_state.get("pending_decisions") or approval_state.get("accepted_tradeoffs")),
        }
    }
    traceability = [
        build_traceability_entry(kind="profile", ref=str(profile.get("topic") or "plan-profile"), title=str(profile.get("goal") or ""), stage="planning"),
        build_traceability_entry(kind="curriculum", ref=str(curriculum.get("family") or profile.get("family") or "curriculum"), title="curriculum seed", stage="planning"),
    ]
    return apply_quality_envelope(
        candidate,
        stage="planning",
        generator="plan-candidate-builder",
        evidence=evidence,
        confidence=diagnostic_profile.get("confidence") or 0.5,
        quality_review={
            "reviewer": "plan-candidate-builder",
            "valid": bool(stage_goals and mastery_checks),
            "issues": ([] if stage_goals and mastery_checks else ["planning.plan_candidate_incomplete"]),
            "warnings": [],
            "confidence": diagnostic_profile.get("confidence") or 0.5,
            "verdict": "ready" if stage_goals and mastery_checks else "needs-revision",
            "evidence_adequacy": "sufficient" if evidence else "partial",
        },
        generation_trace={
            "prompt_version": PLAN_CANDIDATE_VERSION,
            "generator": "plan-candidate-builder",
            "status": "deterministic",
        },
        traceability=traceability,
    )


__all__ = ["PLAN_CANDIDATE_VERSION", "build_plan_candidate"]
