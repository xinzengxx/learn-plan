from __future__ import annotations

import json
from typing import Any


REQUIRED_SECTIONS = [
    "学习画像",
    "规划假设与约束",
    "能力指标与起点判断",
    "检索结论与取舍",
    "阶段总览",
    "阶段路线图",
    "资料清单与阅读定位",
    "掌握度检验设计",
    "今日生成规则",
]


def validate_plan_quality(sections: dict[str, str], materials_data: dict[str, Any], *, profile: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for heading in REQUIRED_SECTIONS:
        if not sections.get(heading, "").strip():
            issues.append(f"缺少关键区块：{heading}")

    current_mode = str(profile.get("mode") or "draft")
    planning_state = profile.get("planning_state") or {}
    approval_state = profile.get("approval_state") or {}
    planning_artifact = profile.get("planning_artifact") or {}
    planning_quality_review = profile.get("planning_quality_review") or {}
    plan_candidate = profile.get("plan_candidate") or {}
    clarification_status = str(planning_state.get("clarification_status") or "")
    deepsearch_status = str(planning_state.get("deepsearch_status") or "")
    diagnostic_status = str(planning_state.get("diagnostic_status") or "")
    plan_status = str(planning_state.get("plan_status") or "")
    if clarification_status not in {"confirmed", "captured"}:
        issues.append("顾问式澄清尚未完成")
    if deepsearch_status in {"needed-pending-plan", "approved-running"}:
        issues.append("deepsearch 尚未完成或尚未确认")
    research_report = profile.get("research_report") or {}
    research_has_capabilities = bool(research_report.get("must_master_capabilities") or research_report.get("mainline_capabilities") or research_report.get("capability_layers"))
    research_has_evidence = bool(research_report.get("evidence_summary") or research_report.get("selection_rationale"))
    if deepsearch_status == "completed" and not research_has_capabilities:
        issues.append("research 阶段尚未形成对用户可见的能力要求报告")
    if deepsearch_status == "completed" and not research_has_evidence:
        issues.append("research 阶段缺少 evidence_summary / selection_rationale，不能支撑正式计划")
    if diagnostic_status in {"in-progress", "not-started"}:
        issues.append("诊断尚未完成或缺少最小水平验证")
    diagnostic_profile = profile.get("diagnostic_profile") or {}
    if current_mode == "finalize" and diagnostic_status == "validated":
        if not diagnostic_profile.get("evidence"):
            issues.append("diagnostic 阶段缺少 evidence，不能支撑起点判断")
        confidence = diagnostic_profile.get("confidence")
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.0
        if confidence_value <= 0:
            issues.append("diagnostic 阶段缺少有效 confidence")
        elif confidence_value < 0.5:
            issues.append("diagnostic confidence 低于 0.5，建议补诊断而不是 finalize")
    preference_status = str(planning_state.get("preference_status") or "")
    if preference_status in {"needs-confirmation", "not-started"}:
        issues.append("学习风格与练习方式尚未确认")
    if current_mode != "finalize":
        issues.append("当前仍处于非 finalize workflow mode，不能视为正式主线计划")
    if plan_status != "approved" and not approval_state.get("ready_for_execution"):
        issues.append("计划尚未通过确认 gate")
    if not plan_candidate:
        issues.append("planning 阶段缺少 plan_candidate，不能支撑正式计划")
    if planning_artifact and not planning_quality_review:
        issues.append("planning 阶段缺少 quality_review")
    if planning_quality_review and not planning_quality_review.get("valid"):
        issues.append("planning 阶段未通过质量评审")
    if planning_quality_review and list(planning_quality_review.get("issues") or []):
        issues.extend([f"planning review issue: {item}" for item in planning_quality_review.get("issues") or []])

    entries = materials_data.get("entries") or []
    confirmed = [item for item in entries if item.get("selection_status") == "confirmed" and item.get("role_in_plan") == "mainline"]
    if not confirmed:
        issues.append("没有正式主线资料（selection_status=confirmed）")

    for item in confirmed:
        segments = item.get("reading_segments") or []
        if not segments:
            issues.append(f"主线资料缺少 reading_segments：{item.get('title') or item.get('id')}")
            continue
        has_locator = False
        for segment in segments:
            locator = segment.get("locator") if isinstance(segment, dict) else {}
            if isinstance(locator, dict) and (locator.get("chapter") or locator.get("pages") or locator.get("sections")):
                has_locator = True
                break
        if not has_locator:
            issues.append(f"主线资料缺少章节/页码/小节定位：{item.get('title') or item.get('id')}")
        mastery_checks = item.get("mastery_checks") or {}
        if not mastery_checks:
            issues.append(f"主线资料缺少掌握度检验设计：{item.get('title') or item.get('id')}")

    if any(str(item.get("id") or "") == "python-crash-course-3e" for item in confirmed):
        crash_course = next((item for item in confirmed if str(item.get("id") or "") == "python-crash-course-3e"), {})
        day2_blob = json.dumps(crash_course.get("reading_segments") or [], ensure_ascii=False)
        required_day2_terms = ["Day 2", "pathlib", "read_text", "write_text", "try-except", "json.dumps", "json.loads"]
        if not all(term in day2_blob for term in required_day2_terms):
            issues.append("Python Day 2 主线资料缺少第 10 章 pathlib / read_text / write_text / try-except / json.dumps / json.loads 精确覆盖")

    capability_section = sections.get("能力指标与起点判断", "")
    if capability_section and "待补充区块" in capability_section and current_mode == "finalize":
        issues.append("能力指标与起点判断仍未形成稳定内容")
    if current_mode == "finalize" and capability_section:
        required_terms = ["必须掌握", "起点判断"]
        missing_terms = [term for term in required_terms if term not in capability_section]
        if missing_terms:
            issues.append(f"能力指标与起点判断缺少关键内容：{'、'.join(missing_terms)}")

    return issues
