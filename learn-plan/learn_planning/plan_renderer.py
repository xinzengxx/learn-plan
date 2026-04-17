from __future__ import annotations

from pathlib import Path
from typing import Any


def render_planning_profile(profile: dict[str, Any]) -> str:
    user_model = profile.get("user_model") or {}
    goal_model = profile.get("goal_model") or {}
    planning_state = profile.get("planning_state") or {}
    clarification_state = profile.get("clarification_state") or {}
    preference_state = profile.get("preference_state") or {}
    diagnostic_profile = profile.get("diagnostic_profile") or {}
    approval_state = profile.get("approval_state") or {}
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
        "- 目标层级：",
        f"  - 主线目标：{goal_model.get('mainline_goal')}",
        *[f"  - 支撑能力：{item}" for item in goal_model.get("supporting_capabilities", [])],
        *[f"  - 增强模块：{item}" for item in goal_model.get("enhancement_modules", [])],
        "- planning state：",
        f"  - 澄清状态：{planning_state.get('clarification_status')}",
        f"  - deepsearch 状态：{planning_state.get('deepsearch_status')}",
        f"  - 诊断状态：{planning_state.get('diagnostic_status')}",
        f"  - 测评深度：{planning_state.get('assessment_depth')}",
        f"  - 诊断轮次：{planning_state.get('diagnostic_round_index')} / {planning_state.get('diagnostic_max_rounds')}",
        f"  - 是否需要追问轮次：{planning_state.get('diagnostic_follow_up_needed')}",
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
        *([f"  - 测评深度：{diagnostic_profile.get('assessment_depth')}"] if diagnostic_profile.get("assessment_depth") else []),
        *([f"  - 诊断轮次：{diagnostic_profile.get('round_index')} / {diagnostic_profile.get('max_rounds')}"] if diagnostic_profile.get("round_index") else []),
        *([f"  - 是否需要追问轮次：{diagnostic_profile.get('follow_up_needed')}"] if diagnostic_profile.get("follow_up_needed") is not None else []),
        *([f"  - 结束原因：{diagnostic_profile.get('stop_reason')}"] if diagnostic_profile.get("stop_reason") else []),
        *([f"  - 推荐起步层级：{diagnostic_profile.get('recommended_entry_level')}"] if diagnostic_profile.get("recommended_entry_level") else []),
        "- 计划确认状态：",
        f"  - 审批状态：{approval_state.get('approval_status')}",
        *[f"  - 待确认决策：{item}" for item in approval_state.get("pending_decisions", [])],
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
    preference_state = profile.get("preference_state") or {}
    return {
        "summary": mode_summary.get(mode, mode_summary["draft"]),
        "must_master": list(research_report.get("must_master_capabilities") or [stage["focus"] for stage in curriculum["stages"]]),
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
        "research_questions": list(research_plan.get("research_questions") or []),
        "candidate_paths": list(research_report.get("candidate_paths") or []),
        "selection_rationale": list(research_report.get("selection_rationale") or []),
        "evidence_summary": list(research_report.get("evidence_summary") or []),
        "open_risks": list(research_report.get("open_risks") or []),
        "diagnostic_summary": {
            "assessment_depth": diagnostic_profile.get("assessment_depth"),
            "round_index": diagnostic_profile.get("round_index"),
            "max_rounds": diagnostic_profile.get("max_rounds"),
            "follow_up_needed": diagnostic_profile.get("follow_up_needed"),
            "stop_reason": diagnostic_profile.get("stop_reason"),
            "baseline_level": diagnostic_profile.get("baseline_level"),
            "recommended_entry_level": diagnostic_profile.get("recommended_entry_level"),
            "confidence": diagnostic_profile.get("confidence"),
        },
        "preference_summary": {
            "status": preference_state.get("status"),
            "learning_style": list(preference_state.get("learning_style") or []),
            "practice_style": list(preference_state.get("practice_style") or []),
            "delivery_preference": list(preference_state.get("delivery_preference") or []),
            "pending_items": list(preference_state.get("pending_items") or []),
        },
        "approval_state": approval_state,
    }


def render_plan_report(report: dict[str, Any]) -> str:
    lines = [
        f"- 结论摘要：{report['summary']}",
        "- 为达到目标需要掌握：",
        *[f"  - {item}" for item in report.get("must_master", [])],
        "- 当前采用的资料策略：",
        f"  - {report['material_policy']}",
        "- 计划质量门槛：",
        *[f"  - {item}" for item in report.get("quality_gates", [])],
    ]
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
    diagnostic_summary = report.get("diagnostic_summary") or {}
    if diagnostic_summary:
        lines.extend([
            "- 诊断摘要：",
            *([f"  - 测评深度：{diagnostic_summary.get('assessment_depth')}"] if diagnostic_summary.get("assessment_depth") else []),
            *([f"  - 诊断轮次：{diagnostic_summary.get('round_index')} / {diagnostic_summary.get('max_rounds')}"] if diagnostic_summary.get("round_index") else []),
            *([f"  - 是否需要追问轮次：{diagnostic_summary.get('follow_up_needed')}"] if diagnostic_summary.get("follow_up_needed") is not None else []),
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
    if approval_state:
        lines.extend([
            "- 计划确认状态：",
            *([f"  - 审批状态：{approval_state.get('approval_status')}"] if approval_state.get("approval_status") else []),
            *[f"  - 待确认：{item}" for item in approval_state.get("pending_decisions", [])],
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


def render_stage_overview(curriculum: dict[str, Any]) -> str:
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


def render_learning_route(curriculum: dict[str, Any]) -> str:
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
            "- /learn-today-update 应把下次复习重点、下次新学习建议与推进判断写回学习记录。",
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
    blocks = [
        "# Learn Plan",
        "",
        f"- 学习主题：{topic}",
        f"- 学习目的：{goal}",
        f"- 当前水平：{level}",
        f"- 时间/频率约束：{schedule}",
        f"- 学习偏好：{preference}",
        "",
    ]

    ordered_headings = [
        "学习画像",
        "规划假设与约束",
        "能力指标与起点判断",
        "检索结论与取舍",
        "阶段总览",
        "阶段路线图",
        "资料清单与阅读定位",
        "掌握度检验设计",
        "今日生成规则",
        "每日推进表",
        "学习记录",
        "测试记录",
    ]
    for heading in ordered_headings:
        content = sections.get(heading)
        if content is None:
            continue
        blocks.append(f"## {heading}")
        blocks.append("")
        content = content.strip()
        if content:
            blocks.append(content)
            blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"
