from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from learn_core.markdown_sections import extract_markdown_section
from learn_core.plan_parser import (
    extract_numbered_subsection,
    extract_plain_bullets,
    extract_recent_bullet_values,
    split_semicolon_values,
    summarize_plan_bullets,
)
from learn_core.text_utils import normalize_string_list
from learn_core.topic_family import detect_topic_family
from learn_runtime.session_history import load_latest_structured_state

EXECUTABLE_PLAN_STATUSES = {
    "approved",
    "plan-confirmed",
    "confirmed",
    "accepted",
    "complete",
    "completed",
}

DEFAULT_TOPIC_FAMILIES = {
    "english": ["英语", "词汇", "语法", "阅读", "写作", "英文", "English", "english"],
    "math": ["数学", "线代", "高数", "概率", "离散", "微积分"],
    "algorithm": ["算法", "数据结构", "刷题", "LeetCode", "leetcode", "双指针", "二分", "DFS", "BFS", "动态规划"],
    "linux": ["Linux", "linux", "GNU/Linux", "shell", "Shell", "bash", "zsh", "命令行", "终端", "操作系统", "系统管理", "系统运维", "服务器"],
    "llm-app": ["LangChain", "langchain", "LangGraph", "langgraph", "RAG", "rag", "Agent", "agent", "提示工程", "大模型", "LLM", "llm", "向量数据库", "embedding", "embeddings", "prompt", "Claude API", "Anthropic API", "模型应用"],
    "backend": ["后端", "backend", "API", "api", "Flask", "Django", "FastAPI", "Spring", "Node.js", "服务端", "微服务"],
    "frontend": ["前端", "frontend", "React", "react", "Vue", "vue", "Next.js", "next.js", "HTML", "CSS", "JavaScript", "TypeScript", "浏览器"],
    "database": ["数据库", "database", "SQL", "sql", "MySQL", "PostgreSQL", "postgres", "Redis", "索引", "事务"],
    "git": ["Git", "git", "版本控制", "仓库", "暂存区", "提交", "commit", "branch", "分支", "merge", "remote", "HEAD"],
    "python": ["Python", "python", "pandas", "Pandas", "numpy", "NumPy", "pythonic", "Jupyter", "jupyter", "数据分析"],
}


def extract_section(plan_text: str, heading: str) -> str:
    return extract_markdown_section(plan_text, heading)


def extract_today_checkin(plan_text: str) -> dict[str, Any]:
    checkin_section = extract_section(plan_text, "今日生成规则")
    requested_focus = extract_plain_bullets(checkin_section, limit=5) if checkin_section else []
    return {
        "reported_completion": [],
        "blocked_items": [],
        "self_assessed_mastery": None,
        "time_budget_today": None,
        "requested_focus": requested_focus,
    }


def normalize_day_key(value: Any) -> str:
    text = str(value or "").strip().lower().replace("：", ":")
    text = re.sub(r"第\s*(\d+)\s*天", r"day \1", text)
    day_match = re.search(r"day\s*(\d+)", text)
    label = text.split(":", 1)[1] if ":" in text else text
    label = re.sub(r"[\s:：，,；;、/()（）\[\]\-]+", "", label)
    if day_match:
        return f"day{day_match.group(1)}:{label}"
    return label


def day_matches(target: Any, candidate: Any) -> bool:
    target_key = normalize_day_key(target)
    candidate_key = normalize_day_key(candidate)
    if not target_key or not candidate_key:
        return False
    if target_key == candidate_key:
        return True
    target_day = re.match(r"day(\d+)", target_key)
    candidate_day = re.match(r"day(\d+)", candidate_key)
    return bool(target_day and candidate_day and target_day.group(1) == candidate_day.group(1))


def make_plan_source_from_progress_state(topic: str, session_type: str, test_mode: str | None, state: dict[str, Any]) -> dict[str, Any]:
    context = state.get("context") or {}
    snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
    learning_state = state.get("learning_state") or {}
    progression = state.get("progression") or {}
    difficulty = context.get("difficulty_target") or {}
    difficulty_raw = difficulty.get("raw") if isinstance(difficulty, dict) else None
    review_focus = normalize_string_list(learning_state.get("review_focus") or context.get("review_focus"))
    next_learning = normalize_string_list(learning_state.get("next_learning") or context.get("new_learning_focus"))
    review_debt = normalize_string_list(progression.get("review_debt"))
    weaknesses = normalize_string_list(learning_state.get("weaknesses"))
    recommended_materials = normalize_string_list(context.get("recommended_materials") or snapshot.get("recommended_materials"))
    exercise_focus = normalize_string_list(context.get("exercise_focus") or snapshot.get("exercise_focus"))
    current_stage = context.get("current_stage") or snapshot.get("current_stage")
    current_day = context.get("current_day") or snapshot.get("day")
    topic_cluster = context.get("topic_cluster") or snapshot.get("today_topic") or context.get("current_day") or topic
    user_model = dict(context.get("user_model") or {})
    goal_model = dict(context.get("goal_model") or {})
    planning_state = dict(context.get("planning_state") or {})
    time_budget = context.get("checkin", {}).get("time_budget_today") if isinstance(context.get("checkin"), dict) else None
    lesson_path = context.get("lesson_path")
    diagnostic_profile = dict(context.get("diagnostic_profile") or snapshot.get("diagnostic_profile") or {})
    assessment_depth = context.get("assessment_depth") or snapshot.get("assessment_depth") or planning_state.get("assessment_depth") or diagnostic_profile.get("assessment_depth")
    round_index = context.get("round_index") or snapshot.get("round_index") or planning_state.get("diagnostic_round_index") or diagnostic_profile.get("round_index")
    max_rounds = context.get("max_rounds") or snapshot.get("max_rounds") or planning_state.get("diagnostic_max_rounds") or diagnostic_profile.get("max_rounds")
    follow_up_needed = context.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = snapshot.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = planning_state.get("diagnostic_follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = diagnostic_profile.get("follow_up_needed")
    stop_reason = context.get("stop_reason") or snapshot.get("stop_reason") or diagnostic_profile.get("stop_reason")

    base_payload = {
        "basis": "progress-state",
        "source_kind": "progress-state",
        "state_anchor": state.get("progress_path"),
        "current_stage": current_stage,
        "today_topic": topic_cluster,
        "recommended_materials": recommended_materials,
        "difficulty_target": difficulty_raw,
        "day": current_day,
        "user_model": user_model,
        "goal_model": goal_model,
        "planning_state": planning_state,
        "preference_state": {
            "status": planning_state.get("preference_status"),
            "learning_style": normalize_string_list(user_model.get("learning_style")),
            "practice_style": normalize_string_list(user_model.get("practice_style")),
            "delivery_preference": normalize_string_list(user_model.get("delivery_preference")),
            "pending_items": [],
        },
        "mainline_goal": goal_model.get("mainline_goal"),
        "supporting_capabilities": normalize_string_list(goal_model.get("supporting_capabilities")),
        "enhancement_modules": normalize_string_list(goal_model.get("enhancement_modules")),
        "diagnostic_profile": diagnostic_profile,
        "assessment_depth": assessment_depth,
        "round_index": round_index,
        "max_rounds": max_rounds,
        "follow_up_needed": follow_up_needed,
        "stop_reason": stop_reason,
        "time_budget_today": time_budget,
        "lesson_path": lesson_path,
        "selected_segments": context.get("selected_segments") or snapshot.get("selected_segments") or [],
        "mastery_targets": context.get("mastery_targets") or snapshot.get("mastery_targets") or {},
        "target_segment_ids": normalize_string_list(
            context.get("target_segment_ids")
            or snapshot.get("target_segment_ids")
            or [segment.get("segment_id") for segment in (context.get("selected_segments") or snapshot.get("selected_segments") or []) if isinstance(segment, dict)]
        ),
        "material_alignment": state.get("material_alignment") or context.get("material_alignment") or snapshot.get("material_alignment") or {},
    }

    if session_type == "test":
        if test_mode == "weakness-focused":
            weakness_focus = weaknesses or review_debt or review_focus or [f"{topic} 最近薄弱点"]
        elif test_mode == "mixed":
            weakness_focus = normalize_string_list((weaknesses or review_debt or review_focus)[:2])
        else:
            weakness_focus = normalize_string_list((review_focus or weaknesses or [])[:2])
        covered = normalize_string_list(progression.get("mastered_clusters") or [topic_cluster, current_stage])
        return {
            **base_payload,
            "test_mode": test_mode,
            "covered": covered or [f"{topic} 已学核心概念"],
            "weakness_focus": weakness_focus or [f"{topic} 最近薄弱点"],
            "deferred_enhancement": normalize_string_list(progression.get("deferred_clusters")),
        }

    return {
        **base_payload,
        "review": review_focus or review_debt or [f"{topic} 旧知识回顾"],
        "new_learning": next_learning or [f"{topic} 新知识推进"],
        "exercise_focus": exercise_focus,
        "should_review": bool(learning_state.get("should_review")),
        "can_advance": bool(learning_state.get("can_advance")),
        "active_clusters": normalize_string_list(progression.get("active_clusters")),
        "deferred_enhancement": normalize_string_list(progression.get("deferred_clusters")),
    }


def extract_prefixed_values(section_text: str, prefixes: list[str]) -> dict[str, list[str]]:
    result = {prefix: [] for prefix in prefixes}
    if not section_text:
        return result
    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:].strip()
        for prefix in prefixes:
            if content.startswith(prefix):
                value = content[len(prefix):].strip()
                if value:
                    result[prefix].append(value)
                break
    return result


def extract_nested_bullet_block(section_text: str, heading: str) -> str:
    if not section_text:
        return ""
    lines = section_text.splitlines()
    start = None
    target = f"- {heading}："
    for idx, raw_line in enumerate(lines):
        if raw_line.strip() == target:
            start = idx + 1
            break
    if start is None:
        return ""
    collected: list[str] = []
    for idx in range(start, len(lines)):
        raw_line = lines[idx]
        stripped = raw_line.strip()
        if not stripped:
            continue
        if raw_line.startswith("- "):
            break
        if stripped.startswith("- "):
            collected.append(stripped)
    return "\n".join(collected)


def _parse_optional_bool(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y", "是", "需要"}:
        return True
    if text in {"false", "0", "no", "n", "否", "不需要"}:
        return False
    return None


def _parse_round_tuple(value: Any) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    if text.isdigit():
        return int(text), None
    return None, None


def parse_learning_profile_section(section_text: str, topic: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    user_block = extract_nested_bullet_block(section_text, "用户模型")
    goal_block = extract_nested_bullet_block(section_text, "目标层级")
    planning_block = extract_nested_bullet_block(section_text, "planning state")
    preference_block = extract_nested_bullet_block(section_text, "学习风格与练习方式")
    diagnostic_block = extract_nested_bullet_block(section_text, "诊断摘要")

    user_values = extract_prefixed_values(user_block, ["画像：", "约束：", "偏好：", "已知优势：", "已知薄弱点："])
    goal_values = extract_prefixed_values(goal_block, ["主线目标：", "支撑能力：", "增强模块："])
    planning_values = extract_prefixed_values(planning_block, ["澄清状态：", "deepsearch 状态：", "诊断状态：", "测评深度：", "诊断轮次：", "是否需要追问轮次：", "偏好确认状态：", "计划状态："])
    preference_values = extract_prefixed_values(preference_block, ["学习风格：", "练习方式：", "交付偏好：", "待确认偏好："])
    diagnostic_values = extract_prefixed_values(diagnostic_block, ["诊断维度：", "观察到的优势：", "观察到的薄弱点：", "测评深度：", "诊断轮次：", "是否需要追问轮次：", "结束原因：", "推荐起步层级："])

    planning_round_index, planning_max_rounds = _parse_round_tuple((planning_values.get("诊断轮次：") or [None])[0])
    diagnostic_round_index, diagnostic_max_rounds = _parse_round_tuple((diagnostic_values.get("诊断轮次：") or [None])[0])
    planning_follow_up_needed = _parse_optional_bool((planning_values.get("是否需要追问轮次：") or [None])[0])
    diagnostic_follow_up_needed = _parse_optional_bool((diagnostic_values.get("是否需要追问轮次：") or [None])[0])

    assessment_depth = (planning_values.get("测评深度：") or diagnostic_values.get("测评深度：") or [None])[0]
    round_index = planning_round_index or diagnostic_round_index
    max_rounds = planning_max_rounds or diagnostic_max_rounds or round_index
    follow_up_needed = planning_follow_up_needed if planning_follow_up_needed is not None else diagnostic_follow_up_needed

    user_model = {
        "profile": (user_values.get("画像：") or [None])[0],
        "constraints": user_values.get("约束：") or [],
        "preferences": user_values.get("偏好：") or [],
        "strengths": user_values.get("已知优势：") or [],
        "weaknesses": user_values.get("已知薄弱点：") or [],
        "learning_style": preference_values.get("学习风格：") or [],
        "practice_style": preference_values.get("练习方式：") or [],
        "delivery_preference": preference_values.get("交付偏好：") or [],
    }
    goal_model = {
        "mainline_goal": (goal_values.get("主线目标：") or [topic])[0],
        "supporting_capabilities": goal_values.get("支撑能力：") or [],
        "enhancement_modules": goal_values.get("增强模块：") or [],
    }
    planning_state = {
        "clarification_status": (planning_values.get("澄清状态：") or ["fallback"])[0],
        "deepsearch_status": (planning_values.get("deepsearch 状态：") or ["unknown"])[0],
        "diagnostic_status": (planning_values.get("诊断状态：") or ["fallback"])[0],
        "assessment_depth": assessment_depth,
        "diagnostic_round_index": round_index,
        "diagnostic_max_rounds": max_rounds,
        "diagnostic_follow_up_needed": follow_up_needed,
        "preference_status": (planning_values.get("偏好确认状态：") or ["not-started"])[0],
        "plan_status": (planning_values.get("计划状态：") or ["fallback"])[0],
    }
    preference_state = {
        "status": planning_state.get("preference_status"),
        "learning_style": preference_values.get("学习风格：") or [],
        "practice_style": preference_values.get("练习方式：") or [],
        "delivery_preference": preference_values.get("交付偏好：") or [],
        "pending_items": preference_values.get("待确认偏好：") or [],
    }
    diagnostic_profile = {
        "status": planning_state.get("diagnostic_status"),
        "assessment_depth": (diagnostic_values.get("测评深度：") or [assessment_depth])[0],
        "round_index": diagnostic_round_index or planning_round_index,
        "max_rounds": diagnostic_max_rounds or planning_max_rounds or diagnostic_round_index or planning_round_index,
        "follow_up_needed": diagnostic_follow_up_needed if diagnostic_follow_up_needed is not None else planning_follow_up_needed,
        "stop_reason": (diagnostic_values.get("结束原因：") or [None])[0],
        "dimensions": diagnostic_values.get("诊断维度：") or [],
        "observed_strengths": diagnostic_values.get("观察到的优势：") or [],
        "observed_weaknesses": diagnostic_values.get("观察到的薄弱点：") or [],
        "recommended_entry_level": (diagnostic_values.get("推荐起步层级：") or [None])[0],
    }
    return user_model, goal_model, planning_state, preference_state, diagnostic_profile


def normalize_python_day_material_anchor(
    topic: str,
    active_day: dict[str, Any],
    *,
    family_keywords: dict[str, list[str]] | None = None,
    allow_material_anchor: bool = True,
) -> dict[str, Any]:
    if not allow_material_anchor:
        return active_day
    families = family_keywords or DEFAULT_TOPIC_FAMILIES
    if detect_topic_family(topic, families, fallback_text="") != "python" or not day_matches(active_day.get("day"), "Day 2"):
        return active_day
    normalized = dict(active_day)
    normalized.update(
        {
            "今日主题": "pathlib.Path 文本读写、异常与 JSON",
            "复习点": "路径字符串与 Path 对象；基础异常类型；字典/列表与 JSON 的关系",
            "新学习点": "Path.read_text()；Path.write_text()；try-except；json.dumps()；json.loads()",
            "练习重点": "Path 读写文本 + 文件/JSON 异常处理 + JSON 序列化/反序列化",
            "推荐材料": "Python编程：从入门到实践（第3版）第 10 章",
            "target_segment_ids": "python-crash-course-3e-day-2-ch10-files-exceptions-json；python-crash-course-3e-segment-3",
        }
    )
    return normalized


def make_plan_source_from_markdown_fallback(
    topic: str,
    session_type: str,
    test_mode: str | None,
    plan_text: str,
    target_day: str | None = None,
    *,
    family_keywords: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    summary = summarize_plan_bullets(plan_text)
    learning_profile = extract_section(plan_text, "学习画像")
    learning_log = extract_section(plan_text, "学习记录")
    test_log = extract_section(plan_text, "测试记录")
    daily_plan = extract_section(plan_text, "每日推进表")
    stage_start = extract_section(plan_text, "第一阶段的起步顺序")
    user_model, goal_model, planning_state, preference_state, diagnostic_profile = parse_learning_profile_section(learning_profile, topic)

    review_focus = extract_recent_bullet_values(learning_log, ["下次复习重点：", "高频错误点："])
    new_learning = extract_recent_bullet_values(learning_log, ["下次新学习建议："])
    covered_scope = extract_recent_bullet_values(test_log, ["本次测试覆盖范围："])
    weakness_focus = extract_recent_bullet_values(test_log, ["薄弱项：", "后续建议："])

    day_blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in daily_plan.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("### Day "):
            if current:
                day_blocks.append(current)
            current = {"day": stripped.lstrip("# ").strip()}
            continue
        if current is None or not stripped.startswith("- "):
            continue
        content = stripped[2:].strip()
        if "：" not in content:
            continue
        key, value = content.split("：", 1)
        current[key.strip()] = value.strip()
    if current:
        day_blocks.append(current)

    active_day = {}
    if target_day and day_blocks:
        active_day = next((day for day in day_blocks if day_matches(target_day, day.get("day"))), {})
    if not active_day and review_focus and day_blocks:
        active_day = next((day for day in day_blocks if any(str(value or "").strip() and str(value or "").strip() in " ".join(str(item or "") for item in day.values()) for value in review_focus)), {})
    if not active_day and new_learning and day_blocks:
        active_day = next((day for day in day_blocks if any(str(value or "").strip() and str(value or "").strip() in " ".join(str(item or "") for item in day.values()) for value in new_learning)), {})
    if not active_day and day_blocks:
        active_day = day_blocks[0]
    if not active_day and stage_start:
        review_section = extract_numbered_subsection(stage_start, "复习")
        new_section = extract_numbered_subsection(stage_start, "新学习")
        practice_section = extract_numbered_subsection(stage_start, "起步练习方向")
        review_seed = extract_plain_bullets(review_section, limit=3)
        new_seed = extract_plain_bullets(new_section, limit=4)
        practice_seed = extract_plain_bullets(practice_section, limit=4)
        active_day = {
            "day": "阶段 1 起步",
            "当前阶段": "阶段 1",
            "今日主题": "函数 / 文件 / 异常 / 调试入门",
            "复习点": "；".join(review_seed[:3]),
            "新学习点": "；".join(new_seed[:4]),
            "练习重点": "；".join(practice_seed[:4]),
            "推荐材料": "Python编程：从入门到实践（第3版）；The Python Tutorial",
            "难度目标": "concept easy/medium，code easy",
        }

    diagnostic_status = normalize_status_token(planning_state.get("diagnostic_status"))
    allow_material_anchor = not (session_type == "test" and diagnostic_status in {"in-progress", "not-started"})
    active_day = normalize_python_day_material_anchor(
        topic,
        active_day,
        family_keywords=family_keywords,
        allow_material_anchor=allow_material_anchor,
    ) if active_day else active_day
    if review_focus and active_day:
        active_day = dict(active_day)
        active_day["历史复习建议"] = "；".join(review_focus)
    if new_learning and active_day:
        active_day = dict(active_day)
        active_day["历史新学习建议"] = "；".join(new_learning)

    shared_payload = {
        "basis": "plan-and-history",
        "source_kind": "plan-markdown-fallback",
        "day": active_day.get("day"),
        "user_model": user_model,
        "goal_model": goal_model,
        "planning_state": planning_state,
        "preference_state": preference_state,
        "diagnostic_profile": diagnostic_profile,
        "mainline_goal": goal_model.get("mainline_goal") or topic,
        "supporting_capabilities": goal_model.get("supporting_capabilities") or [],
        "enhancement_modules": goal_model.get("enhancement_modules") or [],
        "target_segment_ids": split_semicolon_values(active_day.get("target_segment_ids")),
    }

    if session_type == "test":
        if test_mode == "weakness-focused":
            weakness_focus = weakness_focus or review_focus or [f"{topic} 最近薄弱点"]
        elif test_mode == "mixed":
            weakness_focus = weakness_focus or review_focus[:2]
        else:
            weakness_focus = weakness_focus[:2]

        return {
            **shared_payload,
            "test_mode": test_mode,
            "current_stage": active_day.get("当前阶段"),
            "today_topic": active_day.get("今日主题"),
            "covered": covered_scope or [active_day.get("复习点") or active_day.get("今日主题") or f"{topic} 已学核心概念"],
            "weakness_focus": weakness_focus or [active_day.get("练习重点") or f"{topic} 最近薄弱点"],
            "recommended_materials": split_semicolon_values(active_day.get("推荐材料")),
            "difficulty_target": active_day.get("难度目标"),
        }

    return {
        **shared_payload,
        "current_stage": active_day.get("当前阶段"),
        "today_topic": active_day.get("今日主题"),
        "review": split_semicolon_values(active_day.get("复习点")) or review_focus or summary[:3] or [f"{topic} 旧知识回顾"],
        "new_learning": split_semicolon_values(active_day.get("新学习点")) or new_learning or summary[3:6] or [f"{topic} 新知识推进"],
        "exercise_focus": split_semicolon_values(active_day.get("练习重点")),
        "recommended_materials": split_semicolon_values(active_day.get("推荐材料")),
        "difficulty_target": active_day.get("难度目标"),
    }


def normalize_status_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def plan_status_is_executable(value: Any) -> bool:
    return normalize_status_token(value) in EXECUTABLE_PLAN_STATUSES


def resolve_plan_execution_mode(plan_source: dict[str, Any], session_type: str) -> tuple[str, list[str]]:
    planning_state = plan_source.get("planning_state") if isinstance(plan_source.get("planning_state"), dict) else {}
    clarification_status = normalize_status_token(planning_state.get("clarification_status"))
    deepsearch_status = normalize_status_token(planning_state.get("deepsearch_status"))
    diagnostic_status = normalize_status_token(planning_state.get("diagnostic_status"))
    plan_status = normalize_status_token(planning_state.get("plan_status"))

    blockers: list[str] = []
    if clarification_status not in {"confirmed", "captured"}:
        blockers.append("顾问式澄清尚未完成")
    if deepsearch_status in {"needed-pending-plan", "approved-running"}:
        blockers.append("deepsearch 尚未完成或尚未确认")
    if diagnostic_status in {"in-progress", "not-started"}:
        blockers.append("诊断尚未完成或缺少最小水平验证")
    if not plan_status_is_executable(plan_status):
        blockers.append("计划尚未通过确认 gate")

    if blockers:
        if clarification_status not in {"confirmed", "captured"}:
            return "clarification", blockers
        if deepsearch_status in {"needed-pending-plan", "approved-running"}:
            return "research", blockers
        if diagnostic_status in {"in-progress", "not-started"}:
            return "diagnostic", blockers
        return ("test-diagnostic" if session_type == "test" else "prestudy"), blockers
    return "normal", []


def apply_plan_gates(plan_source: dict[str, Any], session_type: str) -> dict[str, Any]:
    enriched = json.loads(json.dumps(plan_source))
    execution_mode, blockers = resolve_plan_execution_mode(enriched, session_type)
    enriched["plan_execution_mode"] = execution_mode
    enriched["plan_blockers"] = blockers
    if execution_mode == "clarification":
        enriched["review"] = ["先补齐目标、约束、已有经验与非目标范围"]
        enriched["new_learning"] = ["整理并确认学习主题、最终目标、成功标准与时间约束"]
        enriched["exercise_focus"] = ["回答顾问式澄清问题，并确认哪些内容暂不进入主线"]
    elif execution_mode == "research":
        enriched["review"] = ["先确认当前目标是否需要外部能力标准与资料取舍依据"]
        enriched["new_learning"] = ["阅读研究计划、确认检索问题与候选资料方向"]
        enriched["exercise_focus"] = ["完成 deepsearch 计划确认，而不是直接进入正式主线学习"]
    elif execution_mode in {"diagnostic", "test-diagnostic"}:
        enriched["review"] = ["先确认当前水平与真实薄弱点，不直接推进新主线"]
        enriched["new_learning"] = ["完成最小诊断验证：解释题、小测试或小代码题"]
        enriched["exercise_focus"] = ["本次 session 以诊断为主，用来决定起步阶段和推进节奏"]
    elif execution_mode == "prestudy":
        enriched.setdefault("review", [])
        enriched.setdefault("new_learning", [])
        enriched.setdefault("exercise_focus", [])
        if not normalize_string_list(enriched.get("review") or []):
            enriched["review"] = ["当前计划仍待确认，先阅读主线候选材料并补齐待确认项"]
        if not normalize_string_list(enriched.get("new_learning") or []):
            enriched["new_learning"] = ["完成资料预读、主线选择和确认 gate"]
        if not normalize_string_list(enriched.get("exercise_focus") or []):
            enriched["exercise_focus"] = ["本次 session 以预读/补资料为主，不直接进入正式推进"]
    return enriched


def apply_cli_overrides(plan_source: dict[str, Any], args: Any) -> dict[str, Any]:
    overridden = json.loads(json.dumps(plan_source))
    if getattr(args, "current_stage", None):
        overridden["current_stage"] = args.current_stage
    if getattr(args, "current_day", None):
        overridden["day"] = args.current_day
    if getattr(args, "today_topic", None):
        overridden["today_topic"] = args.today_topic
    if getattr(args, "review", None):
        overridden["review"] = normalize_string_list(args.review)
    if getattr(args, "new_learning", None):
        overridden["new_learning"] = normalize_string_list(args.new_learning)
    if getattr(args, "exercise_focus", None):
        overridden["exercise_focus"] = normalize_string_list(args.exercise_focus)
    if getattr(args, "time_budget", None):
        overridden["time_budget_today"] = args.time_budget
        checkin = overridden.get("today_progress_checkin") if isinstance(overridden.get("today_progress_checkin"), dict) else {}
        checkin["time_budget_today"] = args.time_budget
        overridden["today_progress_checkin"] = checkin
    if getattr(args, "assessment_depth", None):
        overridden["assessment_depth"] = str(args.assessment_depth).strip()
    if getattr(args, "round_index", None) is not None:
        overridden["round_index"] = args.round_index
    if getattr(args, "max_rounds", None) is not None:
        overridden["max_rounds"] = args.max_rounds
    if getattr(args, "follow_up_needed", None) is not None:
        overridden["follow_up_needed"] = bool(args.follow_up_needed)
    if getattr(args, "stop_reason", None):
        overridden["stop_reason"] = str(args.stop_reason).strip()
    if any([
        getattr(args, "current_stage", None),
        getattr(args, "current_day", None),
        getattr(args, "today_topic", None),
        getattr(args, "review", None),
        getattr(args, "new_learning", None),
        getattr(args, "exercise_focus", None),
        getattr(args, "time_budget", None),
        getattr(args, "assessment_depth", None),
        getattr(args, "round_index", None) is not None,
        getattr(args, "max_rounds", None) is not None,
        getattr(args, "follow_up_needed", None) is not None,
        getattr(args, "stop_reason", None),
    ]):
        overridden["basis"] = "cli-override"
        overridden["source_kind"] = "cli-override"
    return overridden


def make_plan_source(
    topic: str,
    session_type: str,
    test_mode: str | None,
    plan_text: str,
    plan_path: Path | None = None,
    args: Any | None = None,
    *,
    family_keywords: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    base_checkin = extract_today_checkin(plan_text)
    explicit_day = getattr(args, "current_day", None) if args is not None else None
    markdown_source = make_plan_source_from_markdown_fallback(
        topic,
        session_type,
        test_mode,
        plan_text,
        explicit_day,
        family_keywords=family_keywords,
    )
    plan_source = markdown_source
    markdown_target_segments = normalize_string_list(markdown_source.get("target_segment_ids") or [])
    has_explicit_segment_targets = bool(markdown_target_segments)
    if plan_path is not None:
        latest_state = load_latest_structured_state(plan_path, topic)
        if latest_state:
            progress_source = make_plan_source_from_progress_state(topic, session_type, test_mode, latest_state)
            same_day = day_matches(markdown_source.get("day"), progress_source.get("day"))
            should_repeat = bool(progress_source.get("should_review")) and not progress_source.get("can_advance")
            if session_type == "test" or (same_day and not has_explicit_segment_targets):
                plan_source = progress_source
            else:
                plan_source = json.loads(json.dumps(markdown_source))
                plan_source["basis"] = "plan-markdown-with-progress-review"
                plan_source["source_kind"] = "plan-markdown-with-progress-review"
                if should_repeat:
                    plan_source["review"] = normalize_string_list(progress_source.get("review") or []) or plan_source.get("review")
                    plan_source["progress_review_debt"] = normalize_string_list(progress_source.get("review") or [])
                    plan_source["should_review"] = True
                    plan_source["can_advance"] = False
                plan_source["progress_state_anchor"] = progress_source.get("state_anchor")
                plan_source["progress_state_day"] = progress_source.get("day")
    plan_source["today_progress_checkin"] = base_checkin
    if args is not None:
        plan_source = apply_cli_overrides(plan_source, args)
    return apply_plan_gates(plan_source, session_type)
