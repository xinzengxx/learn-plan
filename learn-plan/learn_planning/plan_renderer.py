from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from learn_core.text_utils import normalize_string_list


def _planning_candidate(plan_candidate: dict[str, Any] | None) -> dict[str, Any]:
    return plan_candidate if isinstance(plan_candidate, dict) else {}


PUBLIC_PLAN_HEADINGS = ("学习目标", "用户画像", "学习路线", "学习安排")
PUBLIC_PLAN_FORBIDDEN_TOKENS = (
    "workflow mode",
    "planning state",
    "blocking_stage",
    "deepsearch_status",
    "deepsearch 状态",
    "generation_trace",
    "quality_review",
    "traceability",
    "missing_artifact",
    "semantic diagnostic",
    "research questions",
    "candidate path",
    "candidate_paths",
    "quality gates",
)



def _public_list(values: Any) -> list[str]:
    if isinstance(values, list):
        result: list[str] = []
        for item in values:
            if isinstance(item, dict):
                text = str(item.get("summary") or item.get("title") or item.get("name") or item.get("point") or item.get("capability") or "").strip()
            else:
                text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result
    return normalize_string_list(values)



def _strip_internal_lines(text: Any) -> str:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        lowered = raw_line.lower()
        if any(token.lower() in lowered for token in PUBLIC_PLAN_FORBIDDEN_TOKENS):
            continue
        if "{'" in raw_line or '{"' in raw_line or "[{'" in raw_line:
            continue
        lines.append(raw_line.rstrip())
    return "\n".join(lines).strip()



def _extract_prefixed_values(text: str, prefixes: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        for prefix in prefixes:
            if stripped.startswith(prefix):
                value = stripped[len(prefix):].strip()
                if value and value not in values:
                    values.append(value)
                break
    return values



def _section_or_fallback(sections: dict[str, str], *headings: str) -> str:
    for heading in headings:
        if sections.get(heading):
            return _strip_internal_lines(sections.get(heading))
    return ""



def review_public_plan_markdown(markdown: str) -> list[str]:
    issues: list[str] = []
    for heading in PUBLIC_PLAN_HEADINGS:
        if f"## {heading}" not in markdown:
            issues.append("public-plan.required-heading-missing")
            break
    lowered = markdown.lower()
    if any(token.lower() in lowered for token in PUBLIC_PLAN_FORBIDDEN_TOKENS):
        issues.append("public-plan.internal-token")
    if "{'" in markdown or '{"' in markdown or "[{'" in markdown:
        issues.append("public-plan.raw-python-repr")
    if any(f"## {heading}" in markdown for heading in ("学习画像", "规划假设与约束", "检索结论与取舍", "每日推进表")):
        issues.append("public-plan.legacy-debug-heading")
    bullet_chars = [line.strip()[2:] for line in markdown.splitlines() if line.strip().startswith("- ")]
    if len(bullet_chars) >= 4 and sum(1 for item in bullet_chars if len(item) == 1) >= 4:
        issues.append("public-plan.character-bullets")
    return issues



def _planning_stage_entries(plan_candidate: dict[str, Any] | None) -> list[dict[str, Any]]:
    candidate = _planning_candidate(plan_candidate)
    stage_plan = candidate.get("stage_plan") if isinstance(candidate.get("stage_plan"), list) else []
    if stage_plan:
        return [item for item in stage_plan if isinstance(item, dict)]
    stages = candidate.get("stages") if isinstance(candidate.get("stages"), list) else []
    return [item for item in stages if isinstance(item, dict)]



def _planning_material_entries(plan_candidate: dict[str, Any] | None) -> list[dict[str, Any]]:
    candidate = _planning_candidate(plan_candidate)
    materials = candidate.get("materials") if isinstance(candidate.get("materials"), list) else []
    return [item for item in materials if isinstance(item, dict)]



def _planning_entry_level(plan_candidate: dict[str, Any] | None) -> str | None:
    candidate = _planning_candidate(plan_candidate)
    current_context = candidate.get("current_context") if isinstance(candidate.get("current_context"), dict) else {}
    return candidate.get("entry_level") or current_context.get("entry_point")



def _planning_tradeoffs(plan_candidate: dict[str, Any] | None) -> list[str]:
    candidate = _planning_candidate(plan_candidate)
    return list(candidate.get("tradeoffs") or candidate.get("open_risks") or [])



def _planning_material_role_lines(plan_candidate: dict[str, Any] | None) -> list[str]:
    candidate = _planning_candidate(plan_candidate)
    explicit = list(candidate.get("material_roles") or [])
    if explicit:
        return explicit
    lines: list[str] = []
    for item in _planning_material_entries(candidate):
        name = str(item.get("name") or item.get("title") or "").strip()
        role = str(item.get("role") or item.get("why_this_material") or "").strip()
        use_when = str(item.get("use_when") or item.get("when_to_use") or "").strip()
        priority = str(item.get("priority") or "").strip()
        parts = [part for part in [role, use_when, (f"priority={priority}" if priority else "")] if part]
        if name:
            lines.append(f"{name}：{'；'.join(parts)}" if parts else name)
    if lines:
        return lines
    for stage in _planning_stage_entries(candidate):
        for item in (stage.get("materials_used") or stage.get("selected_materials") or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("title") or "").strip()
            role = str(item.get("role") or item.get("why_this_material") or "").strip()
            use_when = str(item.get("use_when") or item.get("when_to_use") or "").strip()
            parts = [part for part in [role, use_when] if part]
            if name:
                lines.append(f"{name}：{'；'.join(parts)}" if parts else name)
    return lines



def _planning_daily_execution_lines(plan_candidate: dict[str, Any] | None) -> list[str]:
    candidate = _planning_candidate(plan_candidate)
    explicit = list(candidate.get("daily_execution_logic") or [])
    if explicit:
        return explicit
    strategy = candidate.get("execution_strategy") if isinstance(candidate.get("execution_strategy"), dict) else {}
    lines = list(strategy.get("recommended_unit_structure") or [])
    review_strategy = str(strategy.get("review_strategy") or "").strip()
    if review_strategy:
        lines.append(f"复习策略：{review_strategy}")
    return lines



def _planning_mastery_check_lines(plan_candidate: dict[str, Any] | None) -> list[str]:
    candidate = _planning_candidate(plan_candidate)
    explicit = list(candidate.get("mastery_checks") or [])
    if explicit:
        return explicit
    framework = candidate.get("mastery_framework") if isinstance(candidate.get("mastery_framework"), dict) else {}
    lines = list(framework.get("must_master_core") or [])
    final_signal = str(framework.get("final_mastery_signal") or "").strip()
    if final_signal:
        lines.append(f"最终信号：{final_signal}")
    return lines



def render_planning_profile(profile: dict[str, Any]) -> str:
    user_model = profile.get("user_model") or {}
    goal_model = profile.get("goal_model") or {}
    planning_state = profile.get("planning_state") or {}
    clarification_state = profile.get("clarification_state") or {}
    preference_state = profile.get("preference_state") or {}
    diagnostic_profile = profile.get("diagnostic_profile") or {}
    approval_state = profile.get("approval_state") or {}
    patch_queue = profile.get("curriculum_patch_queue") or {}
    lines = [
        f"- 学习主题：{profile['topic']}",
        f"- 学习目的：{profile['goal']}",
        f"- 当前水平：{profile['level']}",
        f"- 时间/频率约束：{profile['schedule']}",
        f"- 学习偏好：{profile['preference']}",
        f"- 主题 family：{profile['family']}",
        f"- 当前 workflow mode：{profile.get('mode')}",
        "- 用户模型：",
        f"  - 画像：{user_model.get('profile')}",
        *[f"  - 约束：{item}" for item in user_model.get("constraints", [])],
        *[f"  - 偏好：{item}" for item in user_model.get("preferences", [])],
        *[f"  - 已知优势：{item}" for item in user_model.get("strengths", [])],
        *[f"  - 已知薄弱点：{item}" for item in user_model.get("weaknesses", [])],
        *[f"  - 复习债：{item}" for item in user_model.get("review_debt", [])],
        *[f"  - 已掌握范围：{item}" for item in user_model.get("mastered_scope", [])],
        "- 目标层级：",
        f"  - 主线目标：{goal_model.get('mainline_goal')}",
        *[f"  - 支撑能力：{item}" for item in goal_model.get("supporting_capabilities", [])],
        *[f"  - 增强模块：{item}" for item in goal_model.get("enhancement_modules", [])],
        "- planning state：",
        f"  - 澄清状态：{planning_state.get('clarification_status')}",
        f"  - deepsearch 状态：{planning_state.get('deepsearch_status')}",
        f"  - 诊断状态：{planning_state.get('diagnostic_status')}",
        f"  - 最多轮次：{planning_state.get('diagnostic_max_rounds')}",
        f"  - 每轮题量：{planning_state.get('questions_per_round')}",
        f"  - 当前轮次：第 {planning_state.get('diagnostic_round_index')} 轮 / 共 {planning_state.get('diagnostic_max_rounds')} 轮",
        f"  - 是否需要下一轮：{planning_state.get('diagnostic_follow_up_needed')}",
        f"  - 偏好确认状态：{planning_state.get('preference_status')}",
        f"  - 计划状态：{planning_state.get('plan_status')}",
        "- 顾问式澄清状态：",
        *[f"  - 已确认：{item}" for item in clarification_state.get("resolved_items", [])],
        *[f"  - 待确认：{item}" for item in clarification_state.get("open_questions", [])],
        *[f"  - 假设：{item}" for item in clarification_state.get("assumptions", [])],
        *[f"  - 非目标：{item}" for item in clarification_state.get("non_goals", [])],
        "- 学习风格与练习方式：",
        *[f"  - 学习风格：{item}" for item in preference_state.get("learning_style", [])],
        *[f"  - 练习方式：{item}" for item in preference_state.get("practice_style", [])],
        *[f"  - 交付偏好：{item}" for item in preference_state.get("delivery_preference", [])],
        *[f"  - 待确认偏好：{item}" for item in preference_state.get("pending_items", [])],
        "- 诊断摘要：",
        *[f"  - 诊断维度：{item}" for item in diagnostic_profile.get("dimensions", [])],
        *[f"  - 观察到的优势：{item}" for item in diagnostic_profile.get("observed_strengths", [])],
        *[f"  - 观察到的薄弱点：{item}" for item in diagnostic_profile.get("observed_weaknesses", [])],
        *([f"  - 最多轮次：{diagnostic_profile.get('max_rounds')}"] if diagnostic_profile.get("max_rounds") else []),
        *([f"  - 每轮题量：{diagnostic_profile.get('questions_per_round')}"] if diagnostic_profile.get("questions_per_round") else []),
        *([f"  - 当前轮次：第 {diagnostic_profile.get('round_index')} 轮 / 共 {diagnostic_profile.get('max_rounds')} 轮"] if diagnostic_profile.get("round_index") else []),
        *([f"  - 是否需要下一轮：{diagnostic_profile.get('follow_up_needed')}"] if diagnostic_profile.get("follow_up_needed") is not None else []),
        *([f"  - 结束原因：{diagnostic_profile.get('stop_reason')}"] if diagnostic_profile.get("stop_reason") else []),
        *([f"  - 推荐起步层级：{diagnostic_profile.get('recommended_entry_level')}"] if diagnostic_profile.get("recommended_entry_level") else []),
        "- 计划确认状态：",
        f"  - 审批状态：{approval_state.get('approval_status')}",
        *[f"  - 待确认决策：{item}" for item in approval_state.get("pending_decisions", [])],
        *[f"  - 已批准 patch：{item}" for item in patch_queue.get("approved_summaries", [])],
        *([f"  - 已应用 patch：{'；'.join(patch_queue.get('applied_patch_topics') or [])}"] if patch_queue.get("applied_patch_topics") else []),
        *([f"  - 已拒绝 patch：{'；'.join(patch_queue.get('rejected_patch_topics') or [])}"] if patch_queue.get("rejected_patch_topics") else []),
        *([f"  - 可进入执行：{approval_state.get('ready_for_execution')}"] if approval_state else []),
        "- 当前规划要求：",
        *[f"  - {item}" for item in profile.get("needs", [])],
    ]
    return "\n".join(lines)


def render_planning_constraints(profile: dict[str, Any]) -> str:
    lines = [
        "- 主线资料必须优先可落地到本地；无法本地化的在线材料只能作为候选或备注。",
        "- 学习路线必须从当前水平出发，不能直接套用零基础模板。",
        "- 每个阶段必须细化到可执行阅读定位：至少到章节；若资料存在稳定页码信息，则进一步细到页码。",
        "- 每个阶段必须明确掌握标准，并能被 /learn-today 精确拆成当天计划。",
        f"- 当前主题将以 `{profile['family']}` family 为默认 seed；若后续检索结论与默认模板冲突，应以检索结论为准。",
    ]
    return "\n".join(lines)


def build_plan_report(profile: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    goal_model = profile.get("goal_model") or {}
    planning_state = profile.get("planning_state") or {}
    research_plan = profile.get("research_plan") or {}
    research_report = profile.get("research_report") or {}
    diagnostic_profile = profile.get("diagnostic_profile") or {}
    approval_state = profile.get("approval_state") or {}
    mode = str(profile.get("mode") or "draft")
    mode_summary = {
        "draft": "当前输出的是候选规划草案，用于继续澄清、补研究或补诊断，不应直接视为正式主线计划。",
        "research-report": "当前输出的是研究摘要，用于确认要查什么、为什么查、查完后如何影响学习路线。",
        "diagnostic": "当前输出的是诊断摘要或最小验证方案，用于确认真实起点和薄弱点，而不是直接推进正式主线。",
        "finalize": "当前输出的是正式规划摘要；只有在顾问式澄清、研究决策、诊断与计划确认通过后，才应视为正式主线计划。",
    }
    preference_state = profile.get("preference_state") or {}
    plan_candidate = _planning_candidate(profile.get("plan_candidate") or {})
    candidate_stage_entries = _planning_stage_entries(plan_candidate)
    if candidate_stage_entries:
        stage_summaries = []
        for index, stage in enumerate(candidate_stage_entries):
            role_in_plan = "mainline" if index == 0 else ("supporting" if index == 1 else "optional")
            reading = [
                item.get("name") or item.get("title")
                for item in (stage.get("materials_used") or stage.get("selected_materials") or [])
                if isinstance(item, dict) and (item.get("name") or item.get("title"))
            ]
            exercise_types = _public_list(stage.get("practice_modes") or stage.get("practice") or [])
            stage_summaries.append(
                {
                    "name": stage.get("name") or stage.get("stage_name") or stage.get("title"),
                    "focus": stage.get("focus"),
                    "goal": stage.get("stage_goal") or stage.get("goal"),
                    "reading": reading,
                    "exercise_types": exercise_types,
                    "test_gate": stage.get("exit_standard"),
                    "role_in_plan": role_in_plan,
                    "goal_alignment": goal_model.get("mainline_goal"),
                    "capability_alignment": (goal_model.get("supporting_capabilities") or [])[:2],
                }
            )
    else:
        stage_summaries = []
        for index, stage in enumerate(curriculum["stages"]):
            role_in_plan = "mainline" if index == 0 else ("supporting" if index == 1 else "optional")
            stage_summaries.append(
                {
                    "name": stage["name"],
                    "focus": stage["focus"],
                    "goal": stage["goal"],
                    "reading": stage.get("reading", []),
                    "exercise_types": stage.get("exercise_types", []),
                    "test_gate": stage.get("test_gate"),
                    "role_in_plan": role_in_plan,
                    "goal_alignment": goal_model.get("mainline_goal"),
                    "capability_alignment": (goal_model.get("supporting_capabilities") or [])[:2],
                }
            )
    return {
        "summary": mode_summary.get(mode, mode_summary["draft"]),
        "research_core_summary": {
            "goal_target_band": research_report.get("goal_target_band"),
            "must_master_core": _public_list(research_report.get("must_master_core") or []),
            "evidence_expectations": _public_list(research_report.get("evidence_expectations") or []),
            "research_brief": research_report.get("research_brief"),
        },
        "must_master": _public_list(research_report.get("must_master_capabilities") or [stage["focus"] for stage in curriculum["stages"]]),
        "mainline_capabilities": _public_list(research_report.get("mainline_capabilities") or []),
        "supporting_capabilities": _public_list(research_report.get("supporting_capabilities") or []),
        "deferred_capabilities": _public_list(research_report.get("deferred_capabilities") or []),
        "stage_summaries": stage_summaries,
        "quality_gates": [
            "完成顾问式澄清",
            "必要时完成 deepsearch 并确认",
            "完成能力要求报告，并向用户清晰告知为达到目标需要掌握哪些能力",
            "完成最小水平诊断或明确跳过理由",
            "完成学习风格与练习方式确认",
            "主线资料可本地获得",
            "阶段资料可定位到章节/页码/小节",
            "每阶段存在掌握度检验方式",
            "长期路线可拆成 /learn-today 当日计划",
            "计划已通过确认 gate",
        ],
        "material_policy": "仅将可本地化资料作为正式主线；在线不可缓存资料仅作候选或备注。",
        "planning_state": planning_state,
        "research_questions": _public_list(research_plan.get("research_questions") or []),
        "source_types": _public_list(research_plan.get("source_types") or []),
        "candidate_directions": _public_list(research_plan.get("candidate_directions") or []),
        "selection_criteria": _public_list(research_plan.get("selection_criteria") or []),
        "candidate_paths": _public_list(research_report.get("candidate_paths") or []),
        "selection_rationale": _public_list(research_report.get("selection_rationale") or []),
        "evidence_summary": _public_list(research_report.get("evidence_summary") or []),
        "open_risks": _public_list(research_report.get("open_risks") or []),
        "diagnostic_summary": {
            "round_index": diagnostic_profile.get("round_index"),
            "max_rounds": diagnostic_profile.get("max_rounds"),
            "questions_per_round": diagnostic_profile.get("questions_per_round"),
            "follow_up_needed": diagnostic_profile.get("follow_up_needed"),
            "stop_reason": diagnostic_profile.get("stop_reason"),
            "baseline_level": diagnostic_profile.get("baseline_level"),
            "recommended_entry_level": diagnostic_profile.get("recommended_entry_level"),
            "confidence": diagnostic_profile.get("confidence"),
        },
        "preference_summary": {
            "status": preference_state.get("status"),
            "learning_style": _public_list(preference_state.get("learning_style") or []),
            "practice_style": _public_list(preference_state.get("practice_style") or []),
            "delivery_preference": _public_list(preference_state.get("delivery_preference") or []),
            "pending_items": _public_list(preference_state.get("pending_items") or []),
        },
        "approval_state": approval_state,
        "curriculum_patch_queue": profile.get("curriculum_patch_queue") or {},
        "plan_candidate_summary": {
            "entry_level": _planning_entry_level(plan_candidate),
            "stage_goals": _public_list(
                plan_candidate.get("stage_goals")
                or [
                    stage.get("stage_goal") or stage.get("goal")
                    for stage in candidate_stage_entries
                    if isinstance(stage, dict) and (stage.get("stage_goal") or stage.get("goal"))
                ]
            ),
            "material_roles": _planning_material_role_lines(plan_candidate),
            "daily_execution_logic": _planning_daily_execution_lines(plan_candidate),
            "mastery_checks": _planning_mastery_check_lines(plan_candidate),
            "tradeoffs": _planning_tradeoffs(plan_candidate),
        },
    }


def render_plan_report(report: dict[str, Any]) -> str:
    lines = [
        f"- 结论摘要：{report['summary']}",
    ]
    research_core_summary = report.get("research_core_summary") or {}
    if research_core_summary and any(research_core_summary.values()):
        lines.extend([
            "- 核心分析：",
            *([f"  - {research_core_summary.get('research_brief')}"] if research_core_summary.get("research_brief") else []),
            *([f"  - 目标层级：{research_core_summary.get('goal_target_band')}"] if research_core_summary.get("goal_target_band") else []),
            *([f"  - 核心能力：{'；'.join(research_core_summary.get('must_master_core') or [])}"] if research_core_summary.get("must_master_core") else []),
            *([f"  - 常见证据：{'；'.join(research_core_summary.get('evidence_expectations') or [])}"] if research_core_summary.get("evidence_expectations") else []),
        ])
    lines.extend([
        "- 为达到目标需要掌握：",
        *[f"  - {item}" for item in report.get("must_master", [])],
        "- 当前采用的资料策略：",
        f"  - {report['material_policy']}",
        "- 计划质量门槛：",
        *[f"  - {item}" for item in report.get("quality_gates", [])],
    ])
    if report.get("research_questions"):
        lines.extend([
            "- 当前 research questions：",
            *[f"  - {item}" for item in report.get("research_questions", [])],
        ])
    if report.get("summary") and "研究摘要" in str(report.get("summary")):
        lines.extend([
            "- 当前交付类型：",
            "  - 这是研究阶段的中间产物，用于确认要查什么、为什么查以及查完如何影响规划。",
            "  - 在完成研究确认与后续诊断前，不应直接进入正式执行。",
        ])
    if report.get("must_master"):
        lines.extend([
            "- 能力要求报告：",
            "  - 这一阶段应明确回答：为达到该学习目的，必须掌握哪些能力。",
        ])
    if report.get("mainline_capabilities"):
        lines.extend([
            "- 主线能力：",
            *[f"  - {item}" for item in report.get("mainline_capabilities", [])],
        ])
    if report.get("supporting_capabilities"):
        lines.extend([
            "- 支撑能力：",
            *[f"  - {item}" for item in report.get("supporting_capabilities", [])],
        ])
    if report.get("deferred_capabilities"):
        lines.extend([
            "- 可后置能力：",
            *[f"  - {item}" for item in report.get("deferred_capabilities", [])],
        ])
    if report.get("candidate_paths"):
        lines.extend([
            "- 候选路径：",
            *[f"  - {item}" for item in report.get("candidate_paths", [])],
        ])
    if report.get("selection_rationale"):
        lines.extend([
            "- 取舍理由：",
            *[f"  - {item}" for item in report.get("selection_rationale", [])],
        ])
    if report.get("evidence_summary"):
        lines.extend([
            "- 证据摘要：",
            *[f"  - {item}" for item in report.get("evidence_summary", [])],
        ])
    if report.get("open_risks"):
        lines.extend([
            "- 当前风险：",
            *[f"  - {item}" for item in report.get("open_risks", [])],
        ])
    plan_candidate_summary = report.get("plan_candidate_summary") or {}
    if any(plan_candidate_summary.values()):
        diagnostic_summary = report.get("diagnostic_summary") or {}
        has_confirmed_entry_level = bool(diagnostic_summary.get("recommended_entry_level"))
        lines.extend([
            "- 个性化执行策略：",
            *([f"  - {'建议' if has_confirmed_entry_level else '暂定'}起步层级：{plan_candidate_summary.get('entry_level')}" ] if plan_candidate_summary.get("entry_level") else []),
            *(["  - 阶段目标：", *[f"    - {item}" for item in plan_candidate_summary.get("stage_goals", [])]] if plan_candidate_summary.get("stage_goals") else []),
            *(["  - 材料角色：", *[f"    - {item}" for item in plan_candidate_summary.get("material_roles", [])]] if plan_candidate_summary.get("material_roles") else []),
            *(["  - 日常执行风格：", *[f"    - {item}" for item in plan_candidate_summary.get("daily_execution_logic", [])]] if plan_candidate_summary.get("daily_execution_logic") else []),
            *(["  - 掌握标准：", *[f"    - {item}" for item in plan_candidate_summary.get("mastery_checks", [])]] if plan_candidate_summary.get("mastery_checks") else []),
            *(["  - 当前取舍：", *[f"    - {item}" for item in plan_candidate_summary.get("tradeoffs", [])]] if plan_candidate_summary.get("tradeoffs") else []),
        ])
    diagnostic_summary = report.get("diagnostic_summary") or {}
    if diagnostic_summary:
        lines.extend([
            "- 诊断摘要：",
            *([f"  - 最多轮次：{diagnostic_summary.get('max_rounds')}"] if diagnostic_summary.get("max_rounds") else []),
            *([f"  - 每轮题量：{diagnostic_summary.get('questions_per_round')}"] if diagnostic_summary.get("questions_per_round") else []),
            *([f"  - 当前轮次：第 {diagnostic_summary.get('round_index')} 轮"] if diagnostic_summary.get("round_index") else []),
            *([f"  - 是否需要下一轮：{diagnostic_summary.get('follow_up_needed')}"] if diagnostic_summary.get("follow_up_needed") is not None else []),
            *([f"  - 结束原因：{diagnostic_summary.get('stop_reason')}"] if diagnostic_summary.get("stop_reason") else []),
            *([f"  - 基线水平：{diagnostic_summary.get('baseline_level')}"] if diagnostic_summary.get("baseline_level") else []),
            *([f"  - 推荐起步层级：{diagnostic_summary.get('recommended_entry_level')}"] if diagnostic_summary.get("recommended_entry_level") else []),
            *([f"  - 诊断置信度：{diagnostic_summary.get('confidence')}"] if diagnostic_summary.get("confidence") is not None else []),
        ])
        if report.get("summary") and "诊断摘要" in str(report.get("summary")):
            lines.extend([
                "- 当前交付类型：",
                "  - 这是诊断阶段的中间产物，用于确认真实起点、薄弱点和建议起步层级。",
                "  - 在完成确认 gate 前，不应直接把它当成正式执行计划。",
            ])
    preference_summary = report.get("preference_summary") or {}
    if preference_summary:
        lines.extend([
            "- 学习风格与练习方式确认：",
            *([f"  - 偏好确认状态：{preference_summary.get('status')}"] if preference_summary.get("status") else []),
            *[f"  - 学习风格：{item}" for item in preference_summary.get("learning_style", [])],
            *[f"  - 练习方式：{item}" for item in preference_summary.get("practice_style", [])],
            *[f"  - 交付偏好：{item}" for item in preference_summary.get("delivery_preference", [])],
            *[f"  - 待确认偏好：{item}" for item in preference_summary.get("pending_items", [])],
        ])
    approval_state = report.get("approval_state") or {}
    patch_queue = report.get("curriculum_patch_queue") or {}
    if approval_state or patch_queue:
        lines.extend([
            "- 计划确认状态：",
            *([f"  - 审批状态：{approval_state.get('approval_status')}"] if approval_state.get("approval_status") else []),
            *[f"  - 待确认：{item}" for item in approval_state.get("pending_decisions", [])],
            *[f"  - 已批准 patch：{item}" for item in patch_queue.get("approved_summaries", [])],
            *([f"  - 已应用 patch：{'；'.join(patch_queue.get('applied_patch_topics') or [])}"] if patch_queue.get("applied_patch_topics") else []),
            *([f"  - 已拒绝 patch：{'；'.join(patch_queue.get('rejected_patch_topics') or [])}"] if patch_queue.get("rejected_patch_topics") else []),
        ])
    lines.append("- 阶段候选路线：")
    for stage in report.get("stage_summaries", []):
        lines.extend(
            [
                f"  - {stage['name']}：{stage['focus']}",
                f"    - 阶段目标：{stage['goal']}",
                f"    - 角色：{stage.get('role_in_plan')}",
                f"    - 目标对齐：{stage.get('goal_alignment')}",
                f"    - 支撑能力对齐：{'；'.join(stage.get('capability_alignment', []))}",
                f"    - 主线阅读：{'；'.join(stage.get('reading', []))}",
                f"    - 练习方式：{'；'.join(stage.get('exercise_types', []))}",
                f"    - 通过标准：{stage.get('test_gate')}",
            ]
        )
    return "\n".join(lines)


def render_research_plan(report: dict[str, Any]) -> str:
    lines = ["- research plan："]
    if report.get("research_questions"):
        lines.extend([*[f"  - 研究问题：{item}" for item in report.get("research_questions", [])]])
    if report.get("source_types"):
        lines.extend([*[f"  - 证据来源：{item}" for item in report.get("source_types", [])]])
    if report.get("candidate_directions"):
        lines.extend([*[f"  - 候选方向：{item}" for item in report.get("candidate_directions", [])]])
    if report.get("selection_criteria"):
        lines.extend([*[f"  - 取舍标准：{item}" for item in report.get("selection_criteria", [])]])
    if len(lines) == 1:
        lines.append("  - 当前尚未形成稳定的 research plan。")
    return "\n".join(lines)


def render_capability_report(report: dict[str, Any]) -> str:
    core = report.get("research_core_summary") or {}
    lines = ["- 目标层级："]
    if core.get("research_brief"):
        lines.append(f"  - {core.get('research_brief')}")
    if core.get("goal_target_band"):
        lines.append(f"  - 目标要求：{core.get('goal_target_band')}")
    if len(lines) == 1:
        lines.append("  - 当前尚未形成稳定的目标层级判断。")

    must_master = list(report.get("must_master") or [])
    mainline = list(report.get("mainline_capabilities") or [])
    supporting = list(report.get("supporting_capabilities") or [])
    lines.extend([
        "- 必备能力：",
        *[f"  - {item}" for item in (must_master or core.get("must_master_core") or [])],
        *( ["  - 重点主线：", *[f"    - {item}" for item in mainline]] if mainline else []),
        *( ["  - 相关支撑：", *[f"    - {item}" for item in supporting]] if supporting else []),
    ])
    if not (must_master or core.get("must_master_core") or mainline or supporting):
        lines.append("  - 当前尚未形成稳定的能力要求列表。")

    evidence = list(core.get("evidence_expectations") or [])
    lines.extend([
        "- 常见验证方式：",
        *[f"  - {item}" for item in evidence],
    ])
    if not evidence:
        lines.append("  - 当前尚未形成稳定的验证方式判断。")

    deferred = list(report.get("deferred_capabilities") or [])
    risks = list(report.get("open_risks") or [])
    lines.extend([
        "- 非优先项 / 边界：",
        *[f"  - 暂不优先：{item}" for item in deferred],
        *[f"  - 边界提醒：{item}" for item in risks],
    ])
    if not (deferred or risks):
        lines.append("  - 当前未显式识别出额外的边界条件。")
    return "\n".join(lines)


def _html_list(items: list[Any]) -> str:
    normalized = [str(item).strip() for item in items if str(item or "").strip()]
    if not normalized:
        return "<p class=\"muted\">暂无明确条目。</p>"
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in normalized) + "</ul>"


def _capability_metric_html(metric: dict[str, Any]) -> str:
    title = str(metric.get("name") or metric.get("title") or metric.get("capability") or metric.get("id") or "未命名能力").strip()
    target_level = str(metric.get("target_level") or metric.get("level") or metric.get("required_level") or "").strip()
    role = str(metric.get("role") or metric.get("capability_role") or "").strip()
    sections = [f"<h3>{escape(title)}</h3>"]
    meta = [item for item in [f"目标水平：{target_level}" if target_level else "", f"能力角色：{role}" if role else ""] if item]
    if meta:
        sections.append("<p class=\"meta\">" + escape("；".join(meta)) + "</p>")
    for label, keys in (
        ("可观察行为", ("observable_behaviors", "observed_behaviors")),
        ("量化指标", ("quantitative_indicators", "metrics", "measurement_indicators")),
        ("诊断方法", ("diagnostic_methods", "assessment_methods")),
        ("学习证据", ("learning_evidence", "evidence_expectations")),
        ("来源证据", ("source_evidence", "evidence_summary")),
    ):
        values: list[Any] = []
        for key in keys:
            candidate = metric.get(key)
            if isinstance(candidate, list):
                values = candidate
                break
            if isinstance(candidate, str) and candidate.strip():
                values = [candidate]
                break
        if values:
            sections.append(f"<h4>{escape(label)}</h4>{_html_list(values)}")
    return "<article class=\"capability-card\">" + "".join(sections) + "</article>"


def render_capability_report_html(report: dict[str, Any]) -> str:
    user_facing = report.get("user_facing_report") if isinstance(report.get("user_facing_report"), dict) else {}
    supplied_html = str(user_facing.get("html") or "").strip()
    if supplied_html:
        return supplied_html

    title = str(user_facing.get("title") or report.get("title") or report.get("research_brief") or "能力要求与达标水平报告").strip()
    summary = list(user_facing.get("summary") or [])
    goal_target_band = str(report.get("goal_target_band") or "").strip()
    required_level_definition = str(report.get("required_level_definition") or "").strip()
    must_master_core = list(report.get("must_master_core") or report.get("must_master_capabilities") or [])
    evidence_expectations = list(report.get("evidence_expectations") or [])
    capability_metrics = [item for item in report.get("capability_metrics") or [] if isinstance(item, dict)]
    diagnostic_scope = report.get("diagnostic_scope") if isinstance(report.get("diagnostic_scope"), dict) else {}
    evidence_summary = list(report.get("evidence_summary") or report.get("source_evidence") or [])
    open_risks = list(report.get("open_risks") or [])
    language_policy = report.get("language_policy") if isinstance(report.get("language_policy"), dict) else {}
    language = str(language_policy.get("user_facing_language") or user_facing.get("language") or "zh-CN")

    capability_cards = "".join(_capability_metric_html(metric) for metric in capability_metrics)
    if not capability_cards:
        capability_cards = "<p class=\"muted\">当前尚未形成可渲染的 capability_metrics。</p>"
    diagnostic_items = []
    for key in ("target_capabilities", "scope_rationale", "evidence_expectations", "scoring_dimensions", "gap_judgement_basis", "non_priority_items"):
        values = diagnostic_scope.get(key)
        if isinstance(values, list) and values:
            diagnostic_items.append(f"<h4>{escape(key)}</h4>{_html_list(values)}")
    diagnostic_html = "".join(diagnostic_items) or "<p class=\"muted\">当前尚未形成稳定诊断范围。</p>"

    return f"""<!doctype html>
<html lang=\"{escape(language)}\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #172033; background: #f7f4ef; line-height: 1.65; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 48px 24px 72px; }}
    header {{ padding: 32px; background: #fffaf2; border: 1px solid #eadfce; border-radius: 24px; box-shadow: 0 16px 45px rgba(37, 28, 12, 0.08); }}
    h1 {{ margin: 0 0 16px; font-size: 34px; line-height: 1.2; }}
    h2 {{ margin-top: 36px; padding-top: 12px; border-top: 1px solid #e3d8c6; }}
    h3 {{ margin-bottom: 8px; }}
    section, .capability-card {{ margin-top: 20px; padding: 24px; background: #fff; border: 1px solid #ebe2d6; border-radius: 18px; }}
    .summary {{ display: grid; gap: 8px; margin-top: 20px; }}
    .summary li, li {{ margin: 6px 0; }}
    .meta {{ color: #6a5438; font-weight: 600; }}
    .muted {{ color: #7d776e; }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>{escape(title)}</h1>
    <p class=\"meta\">这是 research 阶段的能力要求与达标水平报告，不是学习路线或正式计划。</p>
    {_html_list(summary)}
  </header>
  <section><h2>目标达标带</h2><p>{escape(goal_target_band or '暂无明确目标达标带。')}</p></section>
  <section><h2>达标水平定义</h2><p>{escape(required_level_definition or '暂无明确达标水平定义。')}</p></section>
  <section><h2>必须掌握的核心能力</h2>{_html_list(must_master_core)}</section>
  <section><h2>能力指标明细</h2>{capability_cards}</section>
  <section><h2>证据与判断方式</h2>{_html_list(evidence_expectations)}</section>
  <section><h2>后续诊断范围</h2>{diagnostic_html}</section>
  <section><h2>来源证据与开放风险</h2><h3>来源证据</h3>{_html_list(evidence_summary)}<h3>开放风险</h3>{_html_list(open_risks)}</section>
</main>
</body>
</html>
"""


def render_diagnostic_scope_preview(report: dict[str, Any]) -> str:
    scope = report.get("diagnostic_scope") if isinstance(report.get("diagnostic_scope"), dict) else {}
    target_goal_band = str(scope.get("target_goal_band") or "").strip()
    target_capabilities = list(scope.get("target_capabilities") or [])
    target_capability_ids = list(scope.get("target_capability_ids") or [])
    scope_rationale = list(scope.get("scope_rationale") or [])
    evidence_expectations = list(scope.get("evidence_expectations") or [])
    scoring_dimensions = list(scope.get("scoring_dimensions") or [])
    gap_judgement_basis = list(scope.get("gap_judgement_basis") or [])
    non_priority_items = list(scope.get("non_priority_items") or report.get("deferred_capabilities") or [])
    lines = ["- 能力测试范围 / 诊断蓝图预览："]
    if target_goal_band:
        lines.append(f"  - 对齐目标：{target_goal_band}")
    if target_capabilities:
        lines.extend(["  - 接下来会测什么：", *[f"    - {item}" for item in target_capabilities]])
    elif target_capability_ids:
        lines.extend(["  - 接下来会测什么：", *[f"    - {item}" for item in target_capability_ids]])
    else:
        lines.append("  - 当前尚未形成稳定的测试范围。")
    if scope_rationale:
        lines.extend(["  - 为什么这样测：", *[f"    - {item}" for item in scope_rationale]])
    if evidence_expectations:
        lines.extend(["  - 重点观察信号：", *[f"    - {item}" for item in evidence_expectations]])
    if scoring_dimensions:
        lines.extend(["  - 评分维度：", *[f"    - {item}" for item in scoring_dimensions]])
    if gap_judgement_basis:
        lines.extend(["  - 如何判断离目标还差多少：", *[f"    - {item}" for item in gap_judgement_basis]])
    if non_priority_items:
        lines.extend(["  - 本轮暂不重点测：", *[f"    - {item}" for item in non_priority_items]])
    return "\n".join(lines)


def render_stage_overview(curriculum: dict[str, Any], planning_artifact: dict[str, Any] | None = None) -> str:
    plan_candidate = _planning_candidate((planning_artifact or {}).get("plan_candidate"))
    candidate_stages = _planning_stage_entries(plan_candidate)
    if candidate_stages:
        blocks: list[str] = []
        for stage in candidate_stages:
            lesson_units = [item for item in (stage.get("lesson_units") or []) if isinstance(item, dict)]
            selected_materials = [item for item in (stage.get("materials_used") or stage.get("selected_materials") or stage.get("materials") or []) if isinstance(item, dict)]
            material_titles = [
                item.get("name") or item.get("title")
                for item in selected_materials
                if item.get("name") or item.get("title")
            ]
            focus_items = [
                item.get("title") or item.get("focus") or item.get("name")
                for item in lesson_units
                if item.get("title") or item.get("focus") or item.get("name")
            ]
            if not focus_items:
                focus_items = list(stage.get("focus") or [])
            mastery_items = list(stage.get("completion_evidence") or stage.get("mastery_check") or [])
            blocks.extend(
                [
                    f"### {stage.get('name') or stage.get('stage_name') or stage.get('title')}",
                    *([f"- 阶段摘要：{stage.get('stage_goal') or stage.get('goal')}"] if stage.get("stage_goal") or stage.get("goal") else []),
                    *([f"- 为什么现在学：{stage.get('why_this_stage_now') or stage.get('why_now')}"] if stage.get("why_this_stage_now") or stage.get("why_now") else []),
                    *([f"- 重点内容：{'；'.join(focus_items)}"] if focus_items else []),
                    *([f"- 具体阅读：{'；'.join(material_titles)}"] if material_titles else []),
                    *( ["- 掌握检查：", *[f"  - {item}" for item in mastery_items]] if mastery_items else []),
                    *([f"- 阶段门槛：{stage.get('exit_standard')}"] if stage.get("exit_standard") else []),
                    "",
                ]
            )
        return "\n".join(blocks).strip()
    blocks: list[str] = []
    for stage in curriculum["stages"]:
        blocks.extend(
            [
                f"### {stage['name']}：{stage['focus']}",
                f"- 阶段摘要：{stage['goal']}",
                f"- 具体阅读：{'；'.join(stage['reading'])}",
                f"- 练习类型：{'；'.join(stage['exercise_types']) or stage['practice']}",
                f"- 未来用途：{stage['future_use']}",
                f"- 阶段门槛：{stage['test_gate']}",
                "",
            ]
        )
    return "\n".join(blocks).strip()


def render_learning_route(curriculum: dict[str, Any], planning_artifact: dict[str, Any] | None = None) -> str:
    plan_candidate = _planning_candidate((planning_artifact or {}).get("plan_candidate"))
    candidate_stages = _planning_stage_entries(plan_candidate)
    if candidate_stages:
        blocks: list[str] = []
        for stage in candidate_stages:
            lesson_units = [item for item in (stage.get("lesson_units") or []) if isinstance(item, dict)]
            selected_materials = [item for item in (stage.get("materials_used") or stage.get("selected_materials") or stage.get("materials") or []) if isinstance(item, dict)]
            practice_items = list(stage.get("practice_modes") or stage.get("practice") or stage.get("practice_blocks") or [])
            blockers = list(stage.get("common_blockers") or [])
            mastery_items = list(stage.get("completion_evidence") or stage.get("mastery_check") or stage.get("mastery_checks") or [])
            lesson_lines = [
                item.get("title") or item.get("focus") or item.get("name")
                for item in lesson_units
                if item.get("title") or item.get("focus") or item.get("name")
            ]
            material_lines = []
            for item in selected_materials:
                title = item.get("name") or item.get("title")
                role = item.get("role") or item.get("why_this_material") or item.get("use_when")
                if title and role:
                    material_lines.append(f"  - {title}：{role}")
                elif title:
                    material_lines.append(f"  - {title}")
            blocks.extend(
                [
                    f"### {stage.get('name')}",
                    *([f"- 阶段目标：{stage.get('stage_goal') or stage.get('goal')}"] if stage.get("stage_goal") or stage.get("goal") else []),
                    *( ["- 具体阅读：", *material_lines] if material_lines else []),
                    *( ["- 重点小节：", *[f"  - {item}" for item in lesson_lines]] if lesson_lines else []),
                    *( ["- 练习类型：", *[f"  - {item}" for item in practice_items]] if practice_items else []),
                    *( ["- 常见卡点：", *[f"  - {item}" for item in blockers]] if blockers else []),
                    *( ["- 阶段通过标准：", *[f"  - {item}" for item in mastery_items]] if mastery_items else []),
                    *([f"- 推荐练习方式：{stage.get('practice_guidance')}" ] if stage.get("practice_guidance") else []),
                    "",
                ]
            )
        return "\n".join(blocks).strip()
    blocks: list[str] = []
    for stage in curriculum["stages"]:
        blocks.extend(
            [
                f"### {stage['name']}：{stage['focus']}",
                "- 具体阅读：",
                *[f"  - {item}" for item in stage["reading"]],
                "- 练习类型：",
                *[f"  - {item}" for item in stage["exercise_types"]],
                f"- 阶段目标：{stage['goal']}",
                f"- 推荐练习方式：{stage['practice']}",
                f"- 阶段通过标准：{stage['test_gate']}",
                "",
            ]
        )
    return "\n".join(blocks).strip()


def render_daily_roadmap(curriculum: dict[str, Any]) -> str:
    blocks: list[str] = []
    for day in curriculum["daily_templates"]:
        blocks.extend(
            [
                f"### {day['day']}",
                f"- 当前阶段：{day['当前阶段']}",
                f"- 今日主题：{day['今日主题']}",
                f"- 复习点：{day['复习点']}",
                f"- 新学习点：{day['新学习点']}",
                f"- 练习重点：{day['练习重点']}",
                f"- 推荐材料：{day['推荐材料']}",
                f"- 难度目标：{day['难度目标']}",
                "",
            ]
        )
    blocks.extend(
        [
            "### 使用规则",
            "- /learn-today 默认优先读取最新一个 Day 区块作为当日计划。",
            "- /learn-today Step 6 应把下次复习重点、下次新学习建议与推进判断写回学习记录。",
            "- 若阶段测试结果显示需要回退，应优先回到最近相关 Day 区块继续巩固。",
        ]
    )
    return "\n".join(blocks).strip()


def render_materials_section(curriculum: dict[str, Any], materials_dir: Path, materials_index: Path, *, family_configs: dict[str, dict[str, Any]]) -> str:
    material_titles = []
    for item in family_configs.get(curriculum["family"], family_configs["general-cs"]).get("materials", []):
        title = item.get("title")
        use = item.get("use")
        if title and use:
            material_titles.append(f"  - {title}：{use}")
    lines = [
        f"- 本地目录：`{materials_dir}`",
        f"- 索引文件：`{materials_index}`",
        "- 主线材料：",
        *(material_titles or ["  - 暂无预置主线材料"]),
        "- 说明：当前版本会把材料摘要、聚焦主题、推荐阶段、推荐日与练习类型写入索引，供 session 使用。",
    ]
    return "\n".join(lines)


def render_mastery_checks(curriculum: dict[str, Any]) -> str:
    lines = [
        "### 阅读掌握清单",
        "- 每阶段至少列出 3 个“学完后应能解释/区分/实现”的检查点。",
        "- 若阅读材料有章节/页码，则检查点应能定位回具体段落。",
        "",
        "### session 练习/测试",
        "- 每阶段都应有对应的概念题、代码题或阶段测试。",
        "- 正确率只能作为证据之一，不能单独代表真正掌握。",
        "",
        "### 小项目 / 实作",
        "- 关键阶段至少安排 1 个小项目或真实任务，用于验证能否迁移应用。",
        "- 若项目未完成，不应直接判定为阶段完全掌握。",
        "",
        "### 口头 / 书面复盘",
        "- 每阶段结束后，需用自己的话解释核心概念、易错点与实际用途。",
        "- 若无法完成清楚复盘，应将相关内容加入后续复习池。",
        "",
        "### 质量判断规则",
        "- 阅读掌握清单 + session 表现 + 项目/实作 + 复盘，需要综合判断。",
        "- 只有做题表现，没有阅读理解与项目证据，不应判定为完全掌握。",
    ]
    return "\n".join(lines)


def render_today_generation_rules(curriculum: dict[str, Any]) -> str:
    lines = [
        "- /learn-today 默认先询问真实进度，再决定今日计划。",
        "- 若上次指定章节/页码/segment 未完成，优先补读与复习，不推进新内容。",
        "- 若阅读掌握清单未达标，应减少新知识比例，优先解释、复盘与巩固。",
        "- 若最近两次 session 与复盘稳定，才允许进入下一阶段。",
        "- 今日计划必须同时给出：复习内容、新学习内容、对应资料定位、练习重点、掌握标准。",
    ]
    if curriculum.get("daily_templates"):
        lines.append("- 当前默认 day 模板可作为 fallback，但不能替代真实进度 check-in。")
    return "\n".join(lines)


def render_plan(topic: str, goal: str, level: str, schedule: str, preference: str, sections: dict[str, str]) -> str:
    profile_text = _section_or_fallback(sections, "用户画像", "学习画像")
    goal_text = _section_or_fallback(sections, "学习目标", "能力指标与起点判断", "检索结论与取舍")
    route_text = _section_or_fallback(sections, "学习路线", "阶段路线图", "阶段总览")
    arrangement_text = _section_or_fallback(sections, "学习安排", "每日推进表", "阶段总览")
    learning_log = _section_or_fallback(sections, "学习记录")
    test_log = _section_or_fallback(sections, "测试记录")

    goal_items = _extract_prefixed_values(goal_text, ("目标要求：", "核心能力：", "能力要求报告："))
    profile_items = _extract_prefixed_values(profile_text, ("画像：", "已知优势：", "已知薄弱点：", "已掌握范围：", "推荐起步层级："))
    if not profile_items:
        profile_items = [line.strip()[2:].strip() for line in profile_text.splitlines() if line.strip().startswith("- ")][:8]

    blocks = [
        "# Learn Plan",
        "",
        f"- 学习主题：{topic}",
        f"- 学习目的：{goal}",
        f"- 当前水平：{level}",
        f"- 时间/频率约束：{schedule}",
        f"- 学习偏好：{preference}",
        "",
        "## 学习目标",
        "",
        f"- 目标：{goal}",
        f"- 当前计划要解决的问题：从“{level}”出发，按“{schedule}”的节奏，把学习推进到可验证、可迁移的水平。",
        *( ["- 达标能力：", *[f"  - {item}" for item in goal_items]] if goal_items else []),
        "",
        "## 用户画像",
        "",
        *( [*[f"- {item}" for item in profile_items]] if profile_items else [f"- 当前起点：{level}"] ),
        *( ["- 学习记录：", *[f"  {line.strip()}" for line in learning_log.splitlines() if line.strip()][:8]] if learning_log else []),
        *( ["- 测试记录：", *[f"  {line.strip()}" for line in test_log.splitlines() if line.strip()][:8]] if test_log else []),
        "",
        "## 学习路线",
        "",
        route_text or "- 当前路线将围绕学习目标拆成可验证的阶段推进。",
        "",
        "## 学习安排",
        "",
        arrangement_text or "- 当前安排会由 /learn-today 根据学习路线和最新进度生成。",
        "",
    ]
    markdown = "\n".join(str(item) for item in blocks if item is not None).rstrip() + "\n"
    cleaned = _strip_internal_lines(markdown).rstrip() + "\n"
    return cleaned
