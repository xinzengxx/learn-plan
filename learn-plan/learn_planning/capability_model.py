from __future__ import annotations

from typing import Any


def _bullet_lines(title: str, values: list[str]) -> list[str]:
    if not values:
        return []
    return [f"- {title}：", *[f"  - {item}" for item in values]]


def render_capability_model_section(profile: dict[str, Any]) -> str:
    research_report = profile.get("research_report") or {}
    diagnostic_profile = profile.get("diagnostic_profile") or {}
    planning_state = profile.get("planning_state") or {}

    must_master = list(research_report.get("must_master_capabilities") or [])
    mainline = list(research_report.get("mainline_capabilities") or [])
    supporting = list(research_report.get("supporting_capabilities") or [])
    deferred = list(research_report.get("deferred_capabilities") or [])
    evidence = list(research_report.get("evidence_summary") or [])
    dimensions = list(diagnostic_profile.get("dimensions") or [])
    strengths = list(diagnostic_profile.get("observed_strengths") or [])
    weaknesses = list(diagnostic_profile.get("observed_weaknesses") or [])
    baseline = diagnostic_profile.get("baseline_level")
    entry_level = diagnostic_profile.get("recommended_entry_level") or profile.get("level")
    confidence = diagnostic_profile.get("confidence")
    assessment_depth = diagnostic_profile.get("assessment_depth")
    round_index = diagnostic_profile.get("round_index")
    max_rounds = diagnostic_profile.get("max_rounds")
    follow_up_needed = diagnostic_profile.get("follow_up_needed")
    stop_reason = diagnostic_profile.get("stop_reason")

    lines = [
        f"- 当前 workflow 状态：{planning_state.get('plan_status')}",
        f"- 起点判断：建议从 {entry_level} 开始",
    ]
    if assessment_depth:
        lines.append(f"- 测评深度：{assessment_depth}")
    if round_index:
        lines.append(f"- 诊断轮次：{round_index} / {max_rounds}")
    if follow_up_needed is not None:
        lines.append(f"- 是否需要追问轮次：{follow_up_needed}")
    if stop_reason:
        lines.append(f"- 结束原因：{stop_reason}")
    if baseline:
        lines.append(f"- 当前基线水平：{baseline}")
    if confidence is not None:
        lines.append(f"- 起点判断置信度：{confidence}")

    lines.extend(_bullet_lines("必须掌握", must_master))
    lines.extend(_bullet_lines("主线能力", mainline))
    lines.extend(_bullet_lines("支撑能力", supporting))
    lines.extend(_bullet_lines("可后置能力", deferred))
    lines.extend(_bullet_lines("诊断维度", dimensions))
    lines.extend(_bullet_lines("已观察到的优势", strengths))
    lines.extend(_bullet_lines("已观察到的薄弱点", weaknesses))
    lines.extend(_bullet_lines("证据摘要", evidence))

    if not any([must_master, mainline, supporting, deferred, dimensions, strengths, weaknesses, evidence]):
        lines.append("- 当前尚未形成稳定的能力指标与起点判断；在完成 research / diagnostic 前，这一节只能视为待补充区块。")

    return "\n".join(lines)
