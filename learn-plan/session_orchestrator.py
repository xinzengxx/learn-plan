#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent
BOOTSTRAP = SKILL_DIR / "session_bootstrap.py"
VALID_TEST_MODES = {"general", "weakness-focused", "mixed"}

TOPIC_FAMILIES = {
    "english": ["英语", "词汇", "语法", "阅读", "写作", "英文", "English", "english"],
    "math": ["数学", "线代", "高数", "概率", "离散", "微积分"],
    "algorithm": ["算法", "数据结构", "刷题", "LeetCode", "leetcode", "双指针", "二分", "DFS", "BFS", "动态规划"],
    "linux": ["Linux", "linux", "GNU/Linux", "shell", "Shell", "bash", "zsh", "命令行", "终端", "操作系统", "系统管理", "系统运维", "服务器"],
    "llm-app": ["LangChain", "langchain", "LangGraph", "langgraph", "RAG", "rag", "Agent", "agent", "提示工程", "大模型", "LLM", "llm", "向量数据库", "embedding", "embeddings", "prompt", "Claude API", "Anthropic API", "模型应用"],
    "backend": ["后端", "backend", "API", "api", "Flask", "Django", "FastAPI", "Spring", "Node.js", "服务端", "微服务"],
    "frontend": ["前端", "frontend", "React", "react", "Vue", "vue", "Next.js", "next.js", "HTML", "CSS", "JavaScript", "TypeScript", "浏览器"],
    "database": ["数据库", "database", "SQL", "sql", "MySQL", "PostgreSQL", "postgres", "Redis", "索引", "事务"],
    "python": ["Python", "python", "pandas", "Pandas", "numpy", "NumPy", "pythonic", "Jupyter", "jupyter", "数据分析"],
    "git": ["Git", "git", "版本控制", "version control", "commit", "branch", "merge", "rebase", "GitHub", "github", "pull request", "PR"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a minimal learn-plan session and bootstrap it")
    parser.add_argument("--session-dir", required=True, help="目标 session 目录")
    parser.add_argument("--topic", help="学习主题；未提供时尝试从 plan 中提取")
    parser.add_argument("--plan-path", default="learn-plan.md", help="学习计划文件路径")
    parser.add_argument("--session-type", choices=["today", "test"], default="today")
    parser.add_argument("--test-mode", choices=["general", "weakness-focused", "mixed"], help="test session 的模式")
    parser.add_argument("--date", default=time.strftime("%Y-%m-%d"), help="写入 questions.json 的日期")
    parser.add_argument("--force-generate", action="store_true", help="即使 questions.json 已存在也重生成")
    parser.add_argument("--force-bootstrap", action="store_true", help="透传给 bootstrap 的 --force")
    parser.add_argument("--no-start", action="store_true", help="透传给 bootstrap 的 --no-start")
    parser.add_argument("--no-open", action="store_true", help="透传给 bootstrap 的 --no-open")
    parser.add_argument("--current-stage", help="显式指定当前阶段，优先级高于自动推断")
    parser.add_argument("--current-day", help="显式指定当前 Day，优先级高于自动推断")
    parser.add_argument("--today-topic", help="显式指定今日主题，优先级高于自动推断")
    parser.add_argument("--review", action="append", help="显式指定复习点，可重复传入")
    parser.add_argument("--new-learning", action="append", help="显式指定新学习点，可重复传入")
    parser.add_argument("--exercise-focus", action="append", help="显式指定练习重点，可重复传入")
    parser.add_argument("--time-budget", help="显式指定今日时间预算")
    return parser.parse_args()


def read_text_if_exists(path: Path) -> str:
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if path.exists() and path.is_file():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def extract_topic_from_plan(plan_text: str) -> str | None:
    for line in plan_text.splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if not stripped:
            continue
        if stripped.startswith("学习主题"):
            parts = stripped.split(":", 1) if ":" in stripped else stripped.split("：", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            value = stripped.lstrip("#").strip()
            if value and value.lower() != "learn plan":
                return value
    return None


def detect_topic_family(topic: str, plan_text: str) -> str:
    topic_text = (topic or "").strip()
    for family, keywords in TOPIC_FAMILIES.items():
        for keyword in keywords:
            if keyword and keyword in topic_text:
                return family

    if topic_text:
        return "general-cs"

    text = plan_text.strip()
    for family, keywords in TOPIC_FAMILIES.items():
        for keyword in keywords:
            if keyword and keyword in text:
                return family
    return "general-cs"


def infer_domain(topic: str, plan_text: str) -> str:
    return detect_topic_family(topic, plan_text)


def load_topic_profile(plan_path: Path, topic: str) -> dict[str, Any]:
    for name in (".learn-plan-topic-profile.json", "topic-profile.json"):
        candidate = plan_path.parent / name
        data = read_json_if_exists(candidate)
        if not data:
            continue
        explicit = str(data.get("domain") or data.get("family") or "").strip()
        if explicit:
            data["domain"] = explicit
            data["family"] = explicit
        data["topic"] = str(data.get("topic") or topic).strip() or topic
        return data
    return {}


def resolve_topic_domain(topic: str, plan_text: str, topic_profile: dict[str, Any] | None = None) -> str:
    if isinstance(topic_profile, dict):
        explicit = str(topic_profile.get("domain") or topic_profile.get("family") or "").strip()
        if explicit:
            return explicit
    return infer_domain(topic, plan_text)


def resolve_question_bank_domain(domain: str) -> str:
    if domain == "git":
        return "general-cs"
    return domain


def extract_section(plan_text: str, heading: str) -> str:
    lines = plan_text.splitlines()
    target = heading.strip()
    start = None
    heading_pattern = re.compile(r"^##\s+(?:\d+\.\s*)?(?P<title>.+?)\s*$")
    for idx, line in enumerate(lines):
        match = heading_pattern.match(line.strip())
        if match and match.group("title").strip() == target:
            start = idx + 1
            break
    if start is None:
        return ""
    while start < len(lines) and not lines[start].strip():
        start += 1
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def extract_recent_bullet_values(section_text: str, prefixes: list[str], *, limit: int = 3) -> list[str]:
    values: list[str] = []
    for raw_line in reversed(section_text.splitlines()):
        stripped = raw_line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:].strip()
        for prefix in prefixes:
            if content.startswith(prefix):
                value = content[len(prefix):].strip()
                parts = [item.strip() for item in value.replace("；", ";").split(";") if item.strip()]
                for item in parts:
                    if item not in values:
                        values.append(item)
                        if len(values) >= limit:
                            return values
    return values


def extract_plain_bullets(section_text: str, *, limit: int = 4) -> list[str]:
    values: list[str] = []
    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if value and value not in values:
            values.append(value)
            if len(values) >= limit:
                break
    return values


def extract_numbered_subsection(section_text: str, heading: str) -> str:
    lines = section_text.splitlines()
    start = None
    target = heading.strip()
    pattern = re.compile(r"^\d+\.\s+(?P<title>.+?)\s*$")
    for idx, raw_line in enumerate(lines):
        match = pattern.match(raw_line.strip())
        if match and match.group("title").strip() == target:
            start = idx + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start, len(lines)):
        if pattern.match(lines[idx].strip()):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def summarize_plan_bullets(plan_text: str, *, limit: int = 6) -> list[str]:
    summary = []
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            value = stripped[2:].strip()
            if value and value not in summary:
                summary.append(value)
        if len(summary) >= limit:
            break
    return summary


def split_semicolon_values(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").replace("；", ";").split(";") if item.strip()]



def normalize_string_list(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result



def load_latest_structured_state(plan_path: Path, topic: str) -> dict[str, Any] | None:
    sessions_dir = plan_path.parent / "sessions"
    if not sessions_dir.exists() or not sessions_dir.is_dir():
        return None

    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for progress_path in sessions_dir.glob("*/progress.json"):
        progress = read_json_if_exists(progress_path)
        if not progress:
            continue
        if str(progress.get("topic") or "").strip() != topic:
            continue
        session = progress.get("session") or {}
        context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
        learning_state = progress.get("learning_state") if isinstance(progress.get("learning_state"), dict) else {}
        progression = progress.get("progression") if isinstance(progress.get("progression"), dict) else {}
        if not context and not learning_state and not progression:
            continue
        status = str(session.get("status") or "")
        if status not in {"finished", "active"}:
            continue
        if status == "active" and not (learning_state or progression):
            continue
        current_stage = str(context.get("current_stage") or "").strip()
        current_day = str(context.get("current_day") or "").strip()
        topic_cluster = str(context.get("topic_cluster") or "").strip()
        anchor_score = 1 if (current_stage and (current_day or topic_cluster)) else 0
        status_score = 2 if status == "active" else 1
        try:
            sort_ts = progress_path.stat().st_mtime
        except OSError:
            continue
        candidates.append(
            (
                sort_ts,
                anchor_score * 10 + status_score,
                {
                    "progress_path": str(progress_path),
                    "session": session,
                    "context": context,
                    "learning_state": learning_state,
                    "progression": progression,
                },
            )
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[1], item[0]), reverse=True)
    return candidates[0][2]



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



def select_material_segments(materials: list[dict[str, Any]], plan_source: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    review_terms = normalize_string_list(plan_source.get("review") or plan_source.get("weakness_focus"))
    new_terms = normalize_string_list(plan_source.get("new_learning"))
    supporting_terms = normalize_string_list(plan_source.get("supporting_capabilities"))
    enhancement_terms = normalize_string_list(plan_source.get("enhancement_modules"))
    preferred_stage = str(plan_source.get("current_stage") or "")
    selected_segments: list[dict[str, Any]] = []
    mastery_targets = {
        "reading_checklist": [],
        "session_exercises": normalize_string_list(plan_source.get("exercise_focus") or []),
        "applied_project": [],
        "reflection": [],
    }

    def segment_blob(segment: dict[str, Any], material: dict[str, Any]) -> str:
        locator = segment.get("locator") if isinstance(segment, dict) else {}
        return " ".join(
            [
                str(segment.get("label") or material.get("title") or ""),
                str(locator.get("chapter") or "") if isinstance(locator, dict) else "",
                " ".join(str(item) for item in (locator.get("sections") or [])) if isinstance(locator, dict) else "",
                " ".join(str(item) for item in segment.get("checkpoints") or []),
                str(material.get("goal_alignment") or ""),
                " ".join(str(item) for item in material.get("capability_alignment") or []),
            ]
        )

    prioritized: dict[str, list[dict[str, Any]]] = {"mainline": [], "supporting": [], "optional": []}
    for material in materials:
        if material.get("selection_status") not in {None, "confirmed"}:
            continue
        role = str(material.get("role_in_plan") or "optional")
        for segment in material.get("reading_segments") or []:
            blob = segment_blob(segment, material)
            enriched_segment = {
                **segment,
                "material_title": material.get("title"),
                "material_summary": material.get("summary") or material.get("use"),
                "material_source_type": material.get("source_type"),
                "material_kind": material.get("kind"),
                "material_teaching_style": material.get("teaching_style"),
                "role_in_plan": role,
                "goal_alignment": material.get("goal_alignment"),
                "capability_alignment": material.get("capability_alignment") or [],
            }
            matched = False
            if preferred_stage and preferred_stage in blob:
                matched = True
            elif any(term and term in blob for term in review_terms + new_terms):
                matched = True
            elif role == "supporting" and any(term and term in blob for term in supporting_terms):
                matched = True
            elif role == "optional" and any(term and term in blob for term in enhancement_terms):
                matched = True
            if matched:
                prioritized.setdefault(role, []).append(enriched_segment)

    fallback_segments = [
        {**seg, "role_in_plan": material.get("role_in_plan") or "optional", "goal_alignment": material.get("goal_alignment"), "capability_alignment": material.get("capability_alignment") or [], "material_title": material.get("title"), "material_summary": material.get("summary") or material.get("use"), "material_source_type": material.get("source_type"), "material_kind": material.get("kind"), "material_teaching_style": material.get("teaching_style")}
        for material in materials[:3]
        for seg in (material.get("reading_segments") or [])[:1]
    ]

    target_order = [
        ("mainline", 2),
        ("supporting", 1),
        ("optional", 1 if enhancement_terms else 0),
    ]
    seen_segment_ids: set[str] = set()
    for role, limit in target_order:
        count = 0
        for segment in prioritized.get(role, []):
            segment_id = str(segment.get("segment_id") or "")
            if not segment_id or segment_id in seen_segment_ids:
                continue
            seen_segment_ids.add(segment_id)
            selected_segments.append(segment)
            count += 1
            for checkpoint in segment.get("checkpoints") or []:
                if checkpoint not in mastery_targets["reading_checklist"]:
                    mastery_targets["reading_checklist"].append(checkpoint)
            mastery_targets["reflection"].append(f"解释 {segment.get('label') or segment_id} 的关键概念与实际用途")
            mastery_targets["applied_project"].append(f"基于 {segment.get('label') or segment_id} 做 1 个小练习或小项目")
            if count >= limit:
                break

    if not selected_segments:
        for segment in fallback_segments:
            segment_id = str(segment.get("segment_id") or "")
            if not segment_id or segment_id in seen_segment_ids:
                continue
            seen_segment_ids.add(segment_id)
            selected_segments.append(segment)
            for checkpoint in segment.get("checkpoints") or []:
                if checkpoint not in mastery_targets["reading_checklist"]:
                    mastery_targets["reading_checklist"].append(checkpoint)
            mastery_targets["reflection"].append(f"解释 {segment.get('label') or segment_id} 的关键概念与实际用途")
            mastery_targets["applied_project"].append(f"基于 {segment.get('label') or segment_id} 做 1 个小练习或小项目")
            if len(selected_segments) >= 3:
                break

    return selected_segments[:4], mastery_targets



def make_plan_source_from_progress_state(topic: str, session_type: str, test_mode: str | None, state: dict[str, Any]) -> dict[str, Any]:
    context = state.get("context") or {}
    learning_state = state.get("learning_state") or {}
    progression = state.get("progression") or {}
    difficulty = context.get("difficulty_target") or {}
    difficulty_raw = difficulty.get("raw") if isinstance(difficulty, dict) else None
    review_focus = normalize_string_list(learning_state.get("review_focus") or context.get("review_focus"))
    next_learning = normalize_string_list(learning_state.get("next_learning") or context.get("new_learning_focus"))
    review_debt = normalize_string_list(progression.get("review_debt"))
    weaknesses = normalize_string_list(learning_state.get("weaknesses"))
    recommended_materials = normalize_string_list(context.get("recommended_materials"))
    exercise_focus = normalize_string_list(context.get("exercise_focus"))
    current_stage = context.get("current_stage")
    current_day = context.get("current_day")
    topic_cluster = context.get("topic_cluster") or context.get("current_day") or topic
    user_model = dict(context.get("user_model") or {})
    goal_model = dict(context.get("goal_model") or {})
    planning_state = dict(context.get("planning_state") or {})
    time_budget = context.get("checkin", {}).get("time_budget_today") if isinstance(context.get("checkin"), dict) else None
    lesson_path = context.get("lesson_path")

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
        "time_budget_today": time_budget,
        "lesson_path": lesson_path,
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



def parse_learning_profile_section(section_text: str, topic: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    user_block = extract_nested_bullet_block(section_text, "用户模型")
    goal_block = extract_nested_bullet_block(section_text, "目标层级")
    planning_block = extract_nested_bullet_block(section_text, "planning state")
    preference_block = extract_nested_bullet_block(section_text, "学习风格与练习方式")

    user_values = extract_prefixed_values(user_block, ["画像：", "约束：", "偏好：", "已知优势：", "已知薄弱点："])
    goal_values = extract_prefixed_values(goal_block, ["主线目标：", "支撑能力：", "增强模块："])
    planning_values = extract_prefixed_values(planning_block, ["澄清状态：", "deepsearch 状态：", "诊断状态：", "偏好确认状态：", "计划状态："])
    preference_values = extract_prefixed_values(preference_block, ["学习风格：", "练习方式：", "交付偏好：", "待确认偏好："])

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
    return user_model, goal_model, planning_state, preference_state



def make_plan_source_from_markdown_fallback(topic: str, session_type: str, test_mode: str | None, plan_text: str) -> dict[str, Any]:
    summary = summarize_plan_bullets(plan_text)
    learning_profile = extract_section(plan_text, "学习画像")
    learning_log = extract_section(plan_text, "学习记录")
    test_log = extract_section(plan_text, "测试记录")
    daily_plan = extract_section(plan_text, "每日推进表")
    stage_start = extract_section(plan_text, "第一阶段的起步顺序")
    user_model, goal_model, planning_state, preference_state = parse_learning_profile_section(learning_profile, topic)

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

    active_day = day_blocks[0] if day_blocks else {}
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

    if review_focus and active_day:
        active_day = dict(active_day)
        active_day["复习点"] = "；".join(review_focus)
    if new_learning and active_day:
        active_day = dict(active_day)
        active_day["新学习点"] = "；".join(new_learning)

    if session_type == "test":
        if test_mode == "weakness-focused":
            weakness_focus = weakness_focus or review_focus or [f"{topic} 最近薄弱点"]
        elif test_mode == "mixed":
            weakness_focus = weakness_focus or review_focus[:2]
        else:
            weakness_focus = weakness_focus[:2]

        return {
            "basis": "plan-and-history",
            "source_kind": "plan-markdown-fallback",
            "test_mode": test_mode,
            "current_stage": active_day.get("当前阶段"),
            "today_topic": active_day.get("今日主题"),
            "covered": covered_scope or [active_day.get("复习点") or active_day.get("今日主题") or f"{topic} 已学核心概念"],
            "weakness_focus": weakness_focus or [active_day.get("练习重点") or f"{topic} 最近薄弱点"],
            "recommended_materials": split_semicolon_values(active_day.get("推荐材料")),
            "difficulty_target": active_day.get("难度目标"),
            "day": active_day.get("day"),
            "user_model": user_model,
            "goal_model": goal_model,
            "planning_state": planning_state,
            "preference_state": preference_state,
            "mainline_goal": goal_model.get("mainline_goal") or topic,
            "supporting_capabilities": goal_model.get("supporting_capabilities") or [],
            "enhancement_modules": goal_model.get("enhancement_modules") or [],
        }

    return {
        "basis": "plan-and-history",
        "source_kind": "plan-markdown-fallback",
        "current_stage": active_day.get("当前阶段"),
        "today_topic": active_day.get("今日主题"),
        "review": review_focus or (split_semicolon_values(active_day.get("复习点")) or summary[:3] or [f"{topic} 旧知识回顾"]),
        "new_learning": new_learning or (split_semicolon_values(active_day.get("新学习点")) or summary[3:6] or [f"{topic} 新知识推进"]),
        "exercise_focus": split_semicolon_values(active_day.get("练习重点")),
        "recommended_materials": split_semicolon_values(active_day.get("推荐材料")),
        "difficulty_target": active_day.get("难度目标"),
        "day": active_day.get("day"),
        "user_model": user_model,
        "goal_model": goal_model,
        "planning_state": planning_state,
        "preference_state": preference_state,
        "mainline_goal": goal_model.get("mainline_goal") or topic,
        "supporting_capabilities": goal_model.get("supporting_capabilities") or [],
        "enhancement_modules": goal_model.get("enhancement_modules") or [],
    }



def resolve_plan_execution_mode(plan_source: dict[str, Any], session_type: str) -> tuple[str, list[str]]:
    planning_state = plan_source.get("planning_state") if isinstance(plan_source.get("planning_state"), dict) else {}
    clarification_status = str(planning_state.get("clarification_status") or "")
    deepsearch_status = str(planning_state.get("deepsearch_status") or "")
    diagnostic_status = str(planning_state.get("diagnostic_status") or "")
    plan_status = str(planning_state.get("plan_status") or "")

    blockers: list[str] = []
    if clarification_status not in {"confirmed", "captured"}:
        blockers.append("顾问式澄清尚未完成")
    if deepsearch_status in {"needed-pending-plan", "approved-running"}:
        blockers.append("deepsearch 尚未完成或尚未确认")
    if diagnostic_status in {"in-progress", "not-started"}:
        blockers.append("诊断尚未完成或缺少最小水平验证")
    if plan_status != "approved":
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
        enriched["review"] = ["当前计划仍待确认，先阅读主线候选材料并补齐待确认项"]
        enriched["new_learning"] = ["完成资料预读、主线选择和确认 gate"]
        enriched["exercise_focus"] = ["本次 session 以预读/补资料为主，不直接进入正式推进"]
    return enriched


def apply_cli_overrides(plan_source: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    overridden = json.loads(json.dumps(plan_source))
    if args.current_stage:
        overridden["current_stage"] = args.current_stage
    if args.current_day:
        overridden["day"] = args.current_day
    if args.today_topic:
        overridden["today_topic"] = args.today_topic
    if args.review:
        overridden["review"] = normalize_string_list(args.review)
    if args.new_learning:
        overridden["new_learning"] = normalize_string_list(args.new_learning)
    if args.exercise_focus:
        overridden["exercise_focus"] = normalize_string_list(args.exercise_focus)
    if args.time_budget:
        overridden["time_budget_today"] = args.time_budget
        checkin = overridden.get("today_progress_checkin") if isinstance(overridden.get("today_progress_checkin"), dict) else {}
        checkin["time_budget_today"] = args.time_budget
        overridden["today_progress_checkin"] = checkin
    if any([
        args.current_stage,
        args.current_day,
        args.today_topic,
        args.review,
        args.new_learning,
        args.exercise_focus,
        args.time_budget,
    ]):
        overridden["basis"] = "cli-override"
        overridden["source_kind"] = "cli-override"
    return overridden


def make_plan_source(topic: str, session_type: str, test_mode: str | None, plan_text: str, plan_path: Path | None = None, args: argparse.Namespace | None = None, topic_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    base_checkin = extract_today_checkin(plan_text)
    if plan_path is not None:
        latest_state = load_latest_structured_state(plan_path, topic)
        if latest_state:
            plan_source = make_plan_source_from_progress_state(topic, session_type, test_mode, latest_state)
            plan_source["today_progress_checkin"] = base_checkin
            if args is not None:
                plan_source = apply_cli_overrides(plan_source, args)
            return apply_plan_gates(plan_source, session_type)
    plan_source = make_plan_source_from_markdown_fallback(topic, session_type, test_mode, plan_text)
    plan_source["today_progress_checkin"] = base_checkin
    if args is not None:
        plan_source = apply_cli_overrides(plan_source, args)
    return apply_plan_gates(plan_source, session_type)



def normalize_material_item(item: dict[str, Any], topic: str) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("title") or "material",
        "title": item.get("title") or item.get("id") or "未命名材料",
        "topic": item.get("topic") or topic,
        "domain": item.get("domain"),
        "kind": item.get("kind") or "reference",
        "use": item.get("use") or "配合当前 session 学习",
        "source_name": item.get("source_name"),
        "source_type": item.get("source_type"),
        "url": item.get("url"),
        "local_path": item.get("local_path"),
        "cache_status": item.get("cache_status") or ("cached" if item.get("exists_locally") else "metadata-only"),
        "cache_note": item.get("cache_note"),
        "tags": item.get("tags") or [],
        "exists_locally": bool(item.get("exists_locally")),
        "selection_status": item.get("selection_status"),
        "availability": item.get("availability"),
        "role_in_plan": item.get("role_in_plan") or "optional",
        "goal_alignment": item.get("goal_alignment") or topic,
        "capability_alignment": item.get("capability_alignment") or [],
        "reading_segments": item.get("reading_segments") or [],
        "mastery_checks": item.get("mastery_checks") or {},
    }


def load_materials(plan_path: Path, topic: str) -> list[dict[str, Any]]:
    candidate_indexes: list[Path] = []
    plan_text = read_text_if_exists(plan_path)
    material_dir_match = re.search(r"^- 本地目录：`(?P<path>[^`]+)`", plan_text, re.MULTILINE)
    if material_dir_match:
        candidate_indexes.append(Path(material_dir_match.group("path")).expanduser() / "index.json")
    if plan_path.stem.startswith("learn-plan-"):
        suffix = plan_path.stem[len("learn-plan-"):]
        candidate_indexes.append(plan_path.parent / f"materials-{suffix}" / "index.json")
    candidate_indexes.append(plan_path.parent / "materials" / "index.json")

    seen_paths: set[str] = set()
    data: dict[str, Any] = {}
    for materials_index in candidate_indexes:
        key = str(materials_index)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        loaded = read_json_if_exists(materials_index)
        if loaded:
            data = loaded
            break

    entries = data.get("entries") or data.get("materials") or []
    if not isinstance(entries, list):
        return []

    result = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        item_topic = str(item.get("topic") or "").strip()
        if item_topic and item_topic != topic:
            continue
        result.append(normalize_material_item(item, topic))
    return result


def build_algorithm_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "在算法分析里，通常用什么方式描述输入规模足够大时的渐进增长趋势？",
            "options": ["Big-O 记号", "Markdown 记号", "ASCII 记号", "HTTP 状态码"],
            "answer": 0,
            "explanation": "Big-O 用来描述增长趋势，是算法复杂度分析中的常用工具。",
            "tags": ["复杂度", "基础概念"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些数据结构常用于加速查找或去重？",
            "options": ["哈希表", "集合", "数组顺序扫描", "平衡搜索树"],
            "answer": [0, 1, 3],
            "explanation": "哈希表、集合、平衡搜索树都可以用于高效查找；单纯顺序扫描通常更慢。",
            "tags": ["数据结构"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "二分查找只适用于有序序列。",
            "answer": True,
            "explanation": "二分查找依赖有序性，否则无法依据中点结果缩小区间。",
            "tags": ["二分查找"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "如果一个问题天然能拆成若干相似子问题，并且子问题之间互不依赖，最常见的思路是什么？",
            "options": ["递归 / 分治", "直接忽略边界", "只打印调试信息", "固定返回 0"],
            "answer": 0,
            "explanation": "递归和分治常用于把大问题拆成结构相似的小问题。",
            "tags": ["递归", "分治"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "关于双指针技巧，下面哪些说法更常见？",
            "options": ["常用于数组和字符串", "经常配合有序条件", "只适用于树结构", "可用于滑动窗口问题"],
            "answer": [0, 1, 3],
            "explanation": "双指针常见于数组、字符串、滑动窗口等场景，不只限于树。",
            "tags": ["双指针"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "动态规划通常要求你先明确状态、状态转移和边界条件。",
            "answer": True,
            "explanation": "这三部分是动态规划建模的核心。",
            "tags": ["动态规划"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "遍历图时，如果你想按层扩展节点，通常优先考虑哪种方法？",
            "options": ["BFS", "DFS", "排序", "哈希"],
            "answer": 0,
            "explanation": "BFS 天然按层推进。",
            "tags": ["图", "BFS"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "数组求和", "sum_list", ["nums"],
                           "请实现函数 sum_list(nums)，返回整数列表的元素和。",
                           "def sum_list(nums):\n    pass",
                           "def sum_list(nums):\n    return sum(nums)",
                           [
                               {"input": [[1, 2, 3]], "expected": 6},
                               {"input": [[0, 0]], "expected": 0},
                               {"input": [[-1, 1]], "expected": 0},
                           ], ["数组", "遍历"]),
        make_code_question("code2", "easy", "查找最大值", "max_value", ["nums"],
                           "请实现函数 max_value(nums)，返回列表中的最大值。",
                           "def max_value(nums):\n    pass",
                           "def max_value(nums):\n    return max(nums)",
                           [
                               {"input": [[3, 1, 5]], "expected": 5},
                               {"input": [[-3, -7]], "expected": -3},
                               {"input": [[8]], "expected": 8},
                           ], ["数组"]),
        make_code_question("code3", "medium", "判断回文串", "is_palindrome", ["s"],
                           "请实现函数 is_palindrome(s)，判断字符串是否为回文串。",
                           "def is_palindrome(s):\n    pass",
                           "def is_palindrome(s):\n    return s == s[::-1]",
                           [
                               {"input": ["level"], "expected": True},
                               {"input": ["algo"], "expected": False},
                               {"input": ["a"], "expected": True},
                           ], ["字符串", "双指针"]),
        make_code_question("code4", "medium", "二分查找", "binary_search", ["nums", "target"],
                           "请实现函数 binary_search(nums, target)，若 target 存在则返回其下标，否则返回 -1。nums 保证有序。",
                           "def binary_search(nums, target):\n    pass",
                           "def binary_search(nums, target):\n    left, right = 0, len(nums) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if nums[mid] == target:\n            return mid\n        if nums[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1",
                           [
                               {"input": [[1, 3, 5, 7], 5], "expected": 2},
                               {"input": [[2, 4, 6], 1], "expected": -1},
                               {"input": [[9], 9], "expected": 0},
                           ], ["二分查找"]),
        make_code_question("code5", "medium", "统计唯一元素", "count_unique", ["nums"],
                           "请实现函数 count_unique(nums)，返回列表中不同元素的个数。",
                           "def count_unique(nums):\n    pass",
                           "def count_unique(nums):\n    return len(set(nums))",
                           [
                               {"input": [[1, 1, 2, 3]], "expected": 3},
                               {"input": [[5, 5, 5]], "expected": 1},
                               {"input": [[]], "expected": 0},
                           ], ["哈希", "去重"]),
        make_code_question("code6", "medium", "括号有效性", "is_valid_parentheses", ["s"],
                           "请实现函数 is_valid_parentheses(s)，判断括号字符串是否有效。只包含 ()[]{}。",
                           "def is_valid_parentheses(s):\n    pass",
                           "def is_valid_parentheses(s):\n    pairs = {')': '(', ']': '[', '}': '{'}\n    stack = []\n    for ch in s:\n        if ch in '([{':\n            stack.append(ch)\n        else:\n            if not stack or stack.pop() != pairs[ch]:\n                return False\n    return not stack",
                           [
                               {"input": ["()[]{}"], "expected": True},
                               {"input": ["(]"], "expected": False},
                               {"input": ["([{}])"], "expected": True},
                           ], ["栈"]),
        make_code_question("code7", "project", "两数之和", "two_sum", ["nums", "target"],
                           "请实现函数 two_sum(nums, target)，返回和为 target 的两个下标。保证存在唯一答案。",
                           "def two_sum(nums, target):\n    pass",
                           "def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target - n], i]\n        seen[n] = i",
                           [
                               {"input": [[2, 7, 11, 15], 9], "expected": [0, 1]},
                               {"input": [[3, 2, 4], 6], "expected": [1, 2]},
                               {"input": [[3, 3], 6], "expected": [0, 1]},
                           ], ["哈希", "经典题"]),
    ]
    return concept, code


def build_math_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "如果两个事件互斥，那么它们可以同时发生吗？",
            "options": ["可以", "不可以", "只在样本很大时可以", "取决于是否独立"],
            "answer": 1,
            "explanation": "互斥表示不能同时发生。",
            "tags": ["概率"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些量能衡量一组数据的集中趋势？",
            "options": ["平均数", "中位数", "众数", "极差"],
            "answer": [0, 1, 2],
            "explanation": "平均数、中位数、众数都描述集中趋势；极差更偏离散程度。",
            "tags": ["统计"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "如果函数在某点处可导，那么它在该点一定连续。",
            "answer": True,
            "explanation": "可导蕴含连续。",
            "tags": ["微积分"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "在线性代数里，矩阵乘法一般要求什么条件？",
            "options": ["两个矩阵行数相等", "两个矩阵列数相等", "前一个矩阵列数等于后一个矩阵行数", "两个矩阵完全同型"],
            "answer": 2,
            "explanation": "矩阵乘法要求前者列数等于后者行数。",
            "tags": ["线性代数"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "下面哪些属于常见离散数学对象？",
            "options": ["集合", "命题", "图", "导数"],
            "answer": [0, 1, 2],
            "explanation": "集合、命题、图都属于离散数学常见对象。",
            "tags": ["离散数学"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "标准差越大，通常表示数据波动越大。",
            "answer": True,
            "explanation": "标准差刻画离散程度。",
            "tags": ["统计"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "若命题“如果 A 则 B”为真，而 A 为真，那么根据哪种推理可得 B 为真？",
            "options": ["归纳法", "反证法", "肯定前件", "枚举法"],
            "answer": 2,
            "explanation": "这对应常见的肯定前件推理。",
            "tags": ["逻辑"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "计算平均数", "mean_value", ["nums"],
                           "请实现函数 mean_value(nums)，返回列表平均数。保证 nums 非空。",
                           "def mean_value(nums):\n    pass",
                           "def mean_value(nums):\n    return sum(nums) / len(nums)",
                           [
                               {"input": [[1, 2, 3]], "expected": 2.0},
                               {"input": [[5, 5]], "expected": 5.0},
                               {"input": [[-2, 2]], "expected": 0.0},
                           ], ["统计"]),
        make_code_question("code2", "easy", "最大公约数", "gcd_value", ["a", "b"],
                           "请实现函数 gcd_value(a, b)，返回两个正整数的最大公约数。",
                           "def gcd_value(a, b):\n    pass",
                           "def gcd_value(a, b):\n    while b:\n        a, b = b, a % b\n    return a",
                           [
                               {"input": [12, 18], "expected": 6},
                               {"input": [7, 3], "expected": 1},
                               {"input": [9, 6], "expected": 3},
                           ], ["数论"]),
        make_code_question("code3", "medium", "判断素数", "is_prime", ["n"],
                           "请实现函数 is_prime(n)，判断 n 是否是素数。",
                           "def is_prime(n):\n    pass",
                           "def is_prime(n):\n    if n < 2:\n        return False\n    i = 2\n    while i * i <= n:\n        if n % i == 0:\n            return False\n        i += 1\n    return True",
                           [
                               {"input": [2], "expected": True},
                               {"input": [9], "expected": False},
                               {"input": [17], "expected": True},
                           ], ["数论"]),
        make_code_question("code4", "medium", "方差", "variance", ["nums"],
                           "请实现函数 variance(nums)，返回总体方差。保证 nums 非空。",
                           "def variance(nums):\n    pass",
                           "def variance(nums):\n    mean = sum(nums) / len(nums)\n    return sum((x - mean) ** 2 for x in nums) / len(nums)",
                           [
                               {"input": [[1, 2, 3]], "expected": 2 / 3},
                               {"input": [[5, 5]], "expected": 0.0},
                               {"input": [[0, 2]], "expected": 1.0},
                           ], ["统计"]),
        make_code_question("code5", "medium", "矩阵每行求和", "row_sums", ["matrix"],
                           "请实现函数 row_sums(matrix)，返回矩阵每一行元素和组成的列表。",
                           "def row_sums(matrix):\n    pass",
                           "def row_sums(matrix):\n    return [sum(row) for row in matrix]",
                           [
                               {"input": [[[1, 2], [3, 4]]], "expected": [3, 7]},
                               {"input": [[[5], [6], [7]]], "expected": [5, 6, 7]},
                               {"input": [[[]]], "expected": [0]},
                           ], ["矩阵"]),
        make_code_question("code6", "medium", "集合交集大小", "intersection_size", ["a", "b"],
                           "请实现函数 intersection_size(a, b)，返回两个列表交集元素的个数（按去重后集合计算）。",
                           "def intersection_size(a, b):\n    pass",
                           "def intersection_size(a, b):\n    return len(set(a) & set(b))",
                           [
                               {"input": [[1, 2, 3], [2, 3, 4]], "expected": 2},
                               {"input": [[1, 1], [1]], "expected": 1},
                               {"input": [[5], [6]], "expected": 0},
                           ], ["集合"]),
        make_code_question("code7", "project", "统计命题真值个数", "count_true", ["values"],
                           "请实现函数 count_true(values)，返回布尔列表中 True 的个数。",
                           "def count_true(values):\n    pass",
                           "def count_true(values):\n    return sum(1 for v in values if v)",
                           [
                               {"input": [[True, False, True]], "expected": 2},
                               {"input": [[False, False]], "expected": 0},
                               {"input": [[True]], "expected": 1},
                           ], ["逻辑", "统计"]),
    ]
    return concept, code


def build_english_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "下面哪一项最适合用来描述一个已经完成、且与现在有关的动作？",
            "options": ["一般现在时", "现在完成时", "一般将来时", "过去将来时"],
            "answer": 1,
            "explanation": "现在完成时常表示过去发生、对现在有影响。",
            "tags": ["英语", "时态"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些通常属于提升英语词汇记忆效果的策略？",
            "options": ["结合语境记忆", "按词根词缀归类", "只机械抄写不理解", "间隔复习"],
            "answer": [0, 1, 3],
            "explanation": "语境、词根词缀、间隔复习都更有助于长期记忆。",
            "tags": ["词汇"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "英语中的主谓一致要求主语和谓语在人称与数上保持协调。",
            "answer": True,
            "explanation": "主谓一致是英语语法基础规则之一。",
            "tags": ["语法"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "如果一句话强调“正在进行的动作”，通常优先考虑哪个时态？",
            "options": ["现在进行时", "一般过去时", "一般现在时", "现在完成时"],
            "answer": 0,
            "explanation": "现在进行时强调当前正在发生。",
            "tags": ["时态"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "下面哪些属于常见的英语从句类型？",
            "options": ["定语从句", "名词性从句", "状语从句", "矩阵从句"],
            "answer": [0, 1, 2],
            "explanation": "前三者都是常见英语从句类型。",
            "tags": ["从句"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "只背单词表而完全不接触例句，通常不利于真正掌握词语用法。",
            "answer": True,
            "explanation": "词汇最好结合真实语境理解搭配和用法。",
            "tags": ["词汇"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "在阅读长句时，先定位主干成分通常有什么作用？",
            "options": ["让句子自动变短", "帮助理解句子核心结构", "替代所有词汇学习", "避免分析从句"],
            "answer": 1,
            "explanation": "先找主干可以帮助把握句子的核心语义。",
            "tags": ["阅读", "长难句"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "统计单词数", "count_words", ["text"],
                           "请实现函数 count_words(text)，按空白分词后返回单词数量。",
                           "def count_words(text):\n    pass",
                           "def count_words(text):\n    return len(text.split()) if text.split() else 0",
                           [
                               {"input": ["hello world"], "expected": 2},
                               {"input": ["one"], "expected": 1},
                               {"input": [""], "expected": 0},
                           ], ["字符串", "词汇"]),
        make_code_question("code2", "easy", "小写归一化", "normalize_lower", ["word"],
                           "请实现函数 normalize_lower(word)，返回转成小写后的字符串。",
                           "def normalize_lower(word):\n    pass",
                           "def normalize_lower(word):\n    return word.lower()",
                           [
                               {"input": ["Apple"], "expected": "apple"},
                               {"input": ["USA"], "expected": "usa"},
                               {"input": ["mixEd"], "expected": "mixed"},
                           ], ["字符串"]),
        make_code_question("code3", "medium", "去除标点", "remove_punctuation", ["text"],
                           "请实现函数 remove_punctuation(text)，删除字符串中的逗号、句号、感叹号和问号。",
                           "def remove_punctuation(text):\n    pass",
                           "def remove_punctuation(text):\n    for ch in ',.!?':\n        text = text.replace(ch, '')\n    return text",
                           [
                               {"input": ["Hi, Tom!"], "expected": "Hi Tom"},
                               {"input": ["What?"], "expected": "What"},
                               {"input": ["No.change"], "expected": "Nochange"},
                           ], ["字符串"]),
        make_code_question("code4", "medium", "统计元音字母", "count_vowels", ["text"],
                           "请实现函数 count_vowels(text)，返回字符串中元音字母 aeiou 的个数，不区分大小写。",
                           "def count_vowels(text):\n    pass",
                           "def count_vowels(text):\n    return sum(1 for ch in text.lower() if ch in 'aeiou')",
                           [
                               {"input": ["apple"], "expected": 2},
                               {"input": ["Sky"], "expected": 0},
                               {"input": ["Education"], "expected": 5},
                           ], ["词汇", "字符串"]),
        make_code_question("code5", "medium", "首字母大写", "capitalize_words", ["text"],
                           "请实现函数 capitalize_words(text)，将每个单词首字母变为大写。",
                           "def capitalize_words(text):\n    pass",
                           "def capitalize_words(text):\n    return ' '.join(word.capitalize() for word in text.split())",
                           [
                               {"input": ["hello world"], "expected": "Hello World"},
                               {"input": ["python code"], "expected": "Python Code"},
                               {"input": ["a"], "expected": "A"},
                           ], ["字符串"]),
        make_code_question("code6", "medium", "统计后缀词", "count_suffix_words", ["words", "suffix"],
                           "请实现函数 count_suffix_words(words, suffix)，返回列表中以 suffix 结尾的单词数量。",
                           "def count_suffix_words(words, suffix):\n    pass",
                           "def count_suffix_words(words, suffix):\n    return sum(1 for word in words if word.endswith(suffix))",
                           [
                               {"input": [["reading", "coding", "play"], "ing"], "expected": 2},
                               {"input": [["cat", "dog"], "g"], "expected": 1},
                               {"input": [["one"], "ed"], "expected": 0},
                           ], ["词汇"]),
        make_code_question("code7", "project", "去重保序词表", "dedupe_words", ["words"],
                           "请实现函数 dedupe_words(words)，返回去重后仍保持原始出现顺序的新列表。",
                           "def dedupe_words(words):\n    pass",
                           "def dedupe_words(words):\n    seen = set()\n    result = []\n    for word in words:\n        if word not in seen:\n            seen.add(word)\n            result.append(word)\n    return result",
                           [
                               {"input": [["the", "cat", "the"]], "expected": ["the", "cat"]},
                               {"input": [["a", "a", "a"]], "expected": ["a"]},
                               {"input": [["go", "home"]], "expected": ["go", "home"]},
                           ], ["词汇", "去重"]),
    ]
    return concept, code


def build_linux_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "查看当前工作目录的最常用命令通常是哪一个？",
            "options": ["pwd", "ps", "chmod", "tar"],
            "answer": 0,
            "explanation": "pwd 用于输出当前工作目录。",
            "tags": ["linux", "命令行"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些命令常用于查看文件内容？",
            "options": ["cat", "less", "head", "mkdir"],
            "answer": [0, 1, 2],
            "explanation": "cat、less、head 都常用于查看文件内容，mkdir 用于建目录。",
            "tags": ["linux", "文件"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "chmod 用来修改文件或目录权限。",
            "answer": True,
            "explanation": "chmod 是 Linux 中修改权限的常用命令。",
            "tags": ["linux", "权限"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "如果想按名称搜索进程，下面哪个命令最直接？",
            "options": ["pgrep", "touch", "mv", "uname"],
            "answer": 0,
            "explanation": "pgrep 常用于按名称匹配进程。",
            "tags": ["linux", "进程"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "下面哪些属于常见 Linux 排障信息来源？",
            "options": ["日志文件", "systemctl status", "ss/netstat", "幻灯片动画"],
            "answer": [0, 1, 2],
            "explanation": "日志、服务状态和网络监听信息都很常见。",
            "tags": ["linux", "排障"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "环境变量 PATH 会影响 shell 查找可执行文件的路径。",
            "answer": True,
            "explanation": "PATH 决定了命令查找顺序。",
            "tags": ["linux", "环境变量"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "查看某个端口是否被监听，下面哪个方向最合理？",
            "options": ["ss -ltnp", "rm -rf", "whoami", "date"],
            "answer": 0,
            "explanation": "ss -ltnp 常用于查看 TCP 监听端口和进程。",
            "tags": ["linux", "网络"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "拼接路径", "join_home_path", ["name"],
                           "请实现函数 join_home_path(name)，返回 '/home/' 与 name 拼接后的路径字符串。",
                           "def join_home_path(name):\n    pass",
                           "def join_home_path(name):\n    return f'/home/{name}'",
                           [
                               {"input": ["alice"], "expected": "/home/alice"},
                               {"input": ["bob"], "expected": "/home/bob"},
                               {"input": ["tmp"], "expected": "/home/tmp"},
                           ], ["linux", "路径"]),
        make_code_question("code2", "easy", "提取文件扩展名", "file_extension", ["filename"],
                           "请实现函数 file_extension(filename)，返回最后一个点号后的扩展名；若没有点号则返回空字符串。",
                           "def file_extension(filename):\n    pass",
                           "def file_extension(filename):\n    return filename.rsplit('.', 1)[1] if '.' in filename else ''",
                           [
                               {"input": ["notes.txt"], "expected": "txt"},
                               {"input": ["archive.tar.gz"], "expected": "gz"},
                               {"input": ["README"], "expected": ""},
                           ], ["linux", "文件"]),
        make_code_question("code3", "medium", "统计隐藏文件", "count_hidden_files", ["names"],
                           "请实现函数 count_hidden_files(names)，返回以 '.' 开头的文件名数量。",
                           "def count_hidden_files(names):\n    pass",
                           "def count_hidden_files(names):\n    return sum(1 for name in names if name.startswith('.'))",
                           [
                               {"input": [[".bashrc", "notes.txt", ".gitignore"]], "expected": 2},
                               {"input": [["file1", "file2"]], "expected": 0},
                               {"input": [[".env"]], "expected": 1},
                           ], ["linux", "文件"]),
        make_code_question("code4", "medium", "筛选可执行权限", "filter_executable", ["permissions"],
                           "请实现函数 filter_executable(permissions)，输入权限字符串列表，返回其中 owner 位可执行（第 3 位为 x）的项数。",
                           "def filter_executable(permissions):\n    pass",
                           "def filter_executable(permissions):\n    return sum(1 for item in permissions if len(item) >= 3 and item[2] == 'x')",
                           [
                               {"input": [["rwxr-xr-x", "rw-r--r--", "r-x------"]], "expected": 2},
                               {"input": [["rw-------"]], "expected": 0},
                               {"input": [["--x------"]], "expected": 1},
                           ], ["linux", "权限"]),
        make_code_question("code5", "medium", "提取日志级别", "extract_log_levels", ["lines"],
                           "请实现函数 extract_log_levels(lines)，从形如 'INFO service started' 的日志行中提取每行第一个单词，返回列表。",
                           "def extract_log_levels(lines):\n    pass",
                           "def extract_log_levels(lines):\n    return [line.split()[0] for line in lines if line.split()]",
                           [
                               {"input": [["INFO started", "ERROR failed"]], "expected": ["INFO", "ERROR"]},
                               {"input": [["WARN low disk"]], "expected": ["WARN"]},
                               {"input": [[""]], "expected": []},
                           ], ["linux", "日志"]),
        make_code_question("code6", "medium", "统计监听端口", "count_listening_ports", ["ports"],
                           "请实现函数 count_listening_ports(ports)，输入端口状态布尔列表，返回 True 的数量。",
                           "def count_listening_ports(ports):\n    pass",
                           "def count_listening_ports(ports):\n    return sum(1 for port in ports if port)",
                           [
                               {"input": [[True, False, True]], "expected": 2},
                               {"input": [[False, False]], "expected": 0},
                               {"input": [[True]], "expected": 1},
                           ], ["linux", "网络"]),
        make_code_question("code7", "project", "统计命令使用频率", "command_frequency", ["commands"],
                           "请实现函数 command_frequency(commands)，返回一个字典，统计每个命令字符串出现的次数。",
                           "def command_frequency(commands):\n    pass",
                           "def command_frequency(commands):\n    result = {}\n    for command in commands:\n        result[command] = result.get(command, 0) + 1\n    return result",
                           [
                               {"input": [["ls", "cd", "ls"]], "expected": {"ls": 2, "cd": 1}},
                               {"input": [["pwd"]], "expected": {"pwd": 1}},
                               {"input": [[]], "expected": {}},
                           ], ["linux", "命令行", "统计"]),
    ]
    return concept, code


def build_llm_app_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "如果你希望模型稳定输出固定 JSON 字段，最直接的做法通常是什么？",
            "options": ["明确给出 schema 或字段示例", "只说“回答详细一点”", "缩短用户问题", "把 temperature 改成 0.9"],
            "answer": 0,
            "explanation": "结构化输出首先依赖明确的格式约束，而不是只靠模糊提示。",
            "tags": ["llm-app", "structured-output"],
        },
        {
            "id": "c2", "category": "concept", "type": "single",
            "question": "一个最典型的 RAG 基础链路通常是哪个顺序？",
            "options": ["用户问题 -> 检索相关资料 -> 把资料连同问题交给模型生成", "用户问题 -> 直接让模型猜 -> 最后再检索", "先微调整个模型 -> 再决定要不要回答", "先删除上下文 -> 再调用工具"],
            "answer": 0,
            "explanation": "RAG 的核心是 retrieval + generation，先检索再生成。",
            "tags": ["llm-app", "rag"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "提示词写得再长，也不能稳定替代外部检索到的真实知识。",
            "answer": True,
            "explanation": "Prompt 可以改善表达和约束，但不能凭空补足系统没有提供的事实来源。",
            "tags": ["llm-app", "prompting", "rag"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "LangChain 在 LLM 应用里更常见的定位是什么？",
            "options": ["用于组织 prompts、models、retrievers、tools 等组件工作流", "替代操作系统内核", "直接存储 GPU 显存", "把 Python 自动编译成 C"],
            "answer": 0,
            "explanation": "LangChain 更像应用编排层，帮助把常见组件串起来。",
            "tags": ["llm-app", "langchain", "workflow"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "设计 tool calling 时，哪些做法通常更合理？",
            "options": ["工具输入输出结构尽量清晰", "把每个工具职责定义得尽量单一", "让模型自己猜工具参数字段", "为工具返回结果保留可解析结构"],
            "answer": [0, 1, 3],
            "explanation": "工具设计应强调清晰 schema、单一职责和可解析返回，而不是依赖模型盲猜。",
            "tags": ["llm-app", "tools"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "Agent workflow 通常意味着模型会在多步过程中决定下一步动作，并可能调用不同工具。",
            "answer": True,
            "explanation": "这是 agent 的常见特征：按状态推进、做决策、可能调用工具。",
            "tags": ["llm-app", "agent"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "下面哪一项最不属于 LLM 应用 eval 的常见指标？",
            "options": ["回答正确性", "检索相关性", "延迟与成本", "显示器刷新率"],
            "answer": 3,
            "explanation": "Eval 常关注质量、相关性、延迟、成本等，显示器刷新率与应用评测无关。",
            "tags": ["llm-app", "eval"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "构造 messages 列表", "build_messages", ["system_prompt", "user_question"],
                           "请实现函数 build_messages(system_prompt, user_question)，返回 Claude/OpenAI 风格的 messages 列表，格式为 [{'role': 'system', 'content': ...}, {'role': 'user', 'content': ...}]。",
                           "def build_messages(system_prompt, user_question):\n    pass",
                           "def build_messages(system_prompt, user_question):\n    return [\n        {'role': 'system', 'content': system_prompt},\n        {'role': 'user', 'content': user_question},\n    ]",
                           [
                               {"input": ["你是助手", "总结这段文本"], "expected": [{"role": "system", "content": "你是助手"}, {"role": "user", "content": "总结这段文本"}]},
                               {"input": ["只返回 JSON", "给我结果"], "expected": [{"role": "system", "content": "只返回 JSON"}, {"role": "user", "content": "给我结果"}]},
                               {"input": ["", "hello"], "expected": [{"role": "system", "content": ""}, {"role": "user", "content": "hello"}]},
                           ], ["llm-app", "messages", "prompting"]),
        make_code_question("code2", "easy", "提取结构化字段", "extract_answer_field", ["payload", "field"],
                           "请实现函数 extract_answer_field(payload, field)，当 payload 是字典且包含 field 时返回对应值，否则返回 None。",
                           "def extract_answer_field(payload, field):\n    pass",
                           "def extract_answer_field(payload, field):\n    if not isinstance(payload, dict):\n        return None\n    return payload.get(field)",
                           [
                               {"input": [{"answer": "42", "confidence": 0.8}, "answer"], "expected": "42"},
                               {"input": [{"answer": "ok"}, "confidence"], "expected": None},
                               {"input": [None, "answer"], "expected": None},
                           ], ["llm-app", "structured-output"]),
        make_code_question("code3", "medium", "筛选检索结果", "select_retrieved_docs", ["docs", "min_score"],
                           "请实现函数 select_retrieved_docs(docs, min_score)，输入形如 {'text': ..., 'score': ...} 的字典列表，返回 score 大于等于 min_score 的文档列表。",
                           "def select_retrieved_docs(docs, min_score):\n    pass",
                           "def select_retrieved_docs(docs, min_score):\n    return [doc for doc in docs if doc.get('score', 0) >= min_score]",
                           [
                               {"input": [[{"text": "A", "score": 0.91}, {"text": "B", "score": 0.4}], 0.8], "expected": [{"text": "A", "score": 0.91}]},
                               {"input": [[{"text": "A", "score": 0.5}, {"text": "B", "score": 0.7}], 0.7], "expected": [{"text": "B", "score": 0.7}]},
                               {"input": [[], 0.6], "expected": []},
                           ], ["llm-app", "rag", "retrieval"]),
        make_code_question("code4", "medium", "格式化 RAG 上下文", "format_rag_context", ["chunks"],
                           "请实现函数 format_rag_context(chunks)，把若干文本片段按 '【片段1】...\n\n【片段2】...' 的形式拼接；空列表返回空字符串。",
                           "def format_rag_context(chunks):\n    pass",
                           "def format_rag_context(chunks):\n    parts = []\n    for index, chunk in enumerate(chunks, start=1):\n        parts.append(f'【片段{index}】{chunk}')\n    return '\\n\\n'.join(parts)",
                           [
                               {"input": [["文档A", "文档B"]], "expected": "【片段1】文档A\n\n【片段2】文档B"},
                               {"input": [["Only one"]], "expected": "【片段1】Only one"},
                               {"input": [[]], "expected": ""},
                           ], ["llm-app", "rag", "context"]),
        make_code_question("code5", "medium", "收集工具调用名", "collect_tool_call_names", ["tool_calls"],
                           "请实现函数 collect_tool_call_names(tool_calls)，输入形如 {'name': ...} 的工具调用列表，返回其中所有 name 值组成的列表，缺少 name 的项跳过。",
                           "def collect_tool_call_names(tool_calls):\n    pass",
                           "def collect_tool_call_names(tool_calls):\n    return [call['name'] for call in tool_calls if 'name' in call]",
                           [
                               {"input": [[{"name": "search"}, {"name": "calculator"}]], "expected": ["search", "calculator"]},
                               {"input": [[{"name": "browser"}, {}]], "expected": ["browser"]},
                               {"input": [[]], "expected": []},
                           ], ["llm-app", "tools", "agent"]),
        make_code_question("code6", "medium", "计算回答准确率", "compute_accuracy", ["results"],
                           "请实现函数 compute_accuracy(results)，输入布尔列表，返回 True 所占比例；空列表返回 0。",
                           "def compute_accuracy(results):\n    pass",
                           "def compute_accuracy(results):\n    return sum(1 for item in results if item) / len(results) if results else 0",
                           [
                               {"input": [[True, True, False]], "expected": 2 / 3},
                               {"input": [[False, False]], "expected": 0.0},
                               {"input": [[]], "expected": 0},
                           ], ["llm-app", "eval"]),
        make_code_question("code7", "project", "统计文档来源分布", "count_docs_by_source", ["docs"],
                           "请实现函数 count_docs_by_source(docs)，输入含 source 字段的字典列表，返回 source 到数量的映射；缺少 source 时归到 'unknown'。",
                           "def count_docs_by_source(docs):\n    pass",
                           "def count_docs_by_source(docs):\n    result = {}\n    for doc in docs:\n        source = doc.get('source', 'unknown')\n        result[source] = result.get(source, 0) + 1\n    return result",
                           [
                               {"input": [[{"source": "faq"}, {"source": "faq"}, {"source": "wiki"}]], "expected": {"faq": 2, "wiki": 1}},
                               {"input": [[{"title": "x"}]], "expected": {"unknown": 1}},
                               {"input": [[]], "expected": {}},
                           ], ["llm-app", "rag", "project"]),
    ]
    return concept, code


def build_general_cs_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "HTTP 404 通常表示什么？",
            "options": ["资源未找到", "鉴权成功", "服务启动完成", "数据库已备份"],
            "answer": 0,
            "explanation": "404 表示请求的资源不存在或未找到。",
            "tags": ["general-cs", "http"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些属于常见工程调试手段？",
            "options": ["日志", "断点", "最小复现", "随意删除代码"],
            "answer": [0, 1, 2],
            "explanation": "前三者都属于常见且合理的调试手段。",
            "tags": ["general-cs", "debug"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "JSON 是一种常见的数据交换格式。",
            "answer": True,
            "explanation": "JSON 在接口与配置中很常见。",
            "tags": ["general-cs", "json"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "git commit 的主要作用是什么？",
            "options": ["保存一份版本快照到本地历史", "直接上线到生产", "删除仓库", "自动修复 bug"],
            "answer": 0,
            "explanation": "commit 用于记录当前版本历史。",
            "tags": ["general-cs", "git"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "一个典型 Web 应用常见包含哪些部分？",
            "options": ["前端", "后端接口", "数据库", "机械键盘灯效"],
            "answer": [0, 1, 2],
            "explanation": "前三项都很常见。",
            "tags": ["general-cs", "architecture"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "自动化测试的一个重要价值是帮助更早发现回归问题。",
            "answer": True,
            "explanation": "测试可以降低回归风险。",
            "tags": ["general-cs", "testing"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "部署后发现接口异常，通常第一步更合理的是？",
            "options": ["查看日志和错误信息", "直接删库", "马上重装系统", "忽略报警"],
            "answer": 0,
            "explanation": "先看日志和报错信息最基本。",
            "tags": ["general-cs", "ops"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "统计状态码", "count_status", ["codes", "target"],
                           "请实现函数 count_status(codes, target)，返回列表中等于 target 的状态码数量。",
                           "def count_status(codes, target):\n    pass",
                           "def count_status(codes, target):\n    return sum(1 for code in codes if code == target)",
                           [
                               {"input": [[200, 404, 200], 200], "expected": 2},
                               {"input": [[500, 500], 404], "expected": 0},
                               {"input": [[201], 201], "expected": 1},
                           ], ["general-cs", "http"]),
        make_code_question("code2", "easy", "提取 JSON 键", "json_keys", ["obj"],
                           "请实现函数 json_keys(obj)，返回字典所有键组成的列表。",
                           "def json_keys(obj):\n    pass",
                           "def json_keys(obj):\n    return list(obj.keys())",
                           [
                               {"input": [{"a": 1, "b": 2}], "expected": ["a", "b"]},
                               {"input": [{"name": "x"}], "expected": ["name"]},
                               {"input": [{}], "expected": []},
                           ], ["general-cs", "json"]),
        make_code_question("code3", "medium", "筛选错误日志", "filter_error_logs", ["logs"],
                           "请实现函数 filter_error_logs(logs)，返回包含 'ERROR' 子串的日志行列表。",
                           "def filter_error_logs(logs):\n    pass",
                           "def filter_error_logs(logs):\n    return [log for log in logs if 'ERROR' in log]",
                           [
                               {"input": [["INFO ok", "ERROR failed"]], "expected": ["ERROR failed"]},
                               {"input": [["WARN a", "WARN b"]], "expected": []},
                               {"input": [["ERROR x", "ERROR y"]], "expected": ["ERROR x", "ERROR y"]},
                           ], ["general-cs", "logs"]),
        make_code_question("code4", "medium", "统计分支名", "branch_frequency", ["branches"],
                           "请实现函数 branch_frequency(branches)，返回每个分支名出现次数的字典。",
                           "def branch_frequency(branches):\n    pass",
                           "def branch_frequency(branches):\n    result = {}\n    for branch in branches:\n        result[branch] = result.get(branch, 0) + 1\n    return result",
                           [
                               {"input": [["main", "dev", "main"]], "expected": {"main": 2, "dev": 1}},
                               {"input": [["feature"]], "expected": {"feature": 1}},
                               {"input": [[]], "expected": {}},
                           ], ["general-cs", "git"]),
        make_code_question("code5", "medium", "查找慢请求", "count_slow_requests", ["durations", "threshold"],
                           "请实现函数 count_slow_requests(durations, threshold)，返回耗时大于阈值的请求数。",
                           "def count_slow_requests(durations, threshold):\n    pass",
                           "def count_slow_requests(durations, threshold):\n    return sum(1 for duration in durations if duration > threshold)",
                           [
                               {"input": [[120, 80, 300], 100], "expected": 2},
                               {"input": [[10, 20], 50], "expected": 0},
                               {"input": [[51], 50], "expected": 1},
                           ], ["general-cs", "performance"]),
        make_code_question("code6", "medium", "统计通过测试", "passed_tests", ["results"],
                           "请实现函数 passed_tests(results)，输入布尔列表，返回通过数量。",
                           "def passed_tests(results):\n    pass",
                           "def passed_tests(results):\n    return sum(1 for result in results if result)",
                           [
                               {"input": [[True, False, True]], "expected": 2},
                               {"input": [[False]], "expected": 0},
                               {"input": [[]], "expected": 0},
                           ], ["general-cs", "testing"]),
        make_code_question("code7", "project", "按环境统计配置项", "count_env_keys", ["configs"],
                           "请实现函数 count_env_keys(configs)，输入环境到配置字典的映射，返回环境到键数量的映射。",
                           "def count_env_keys(configs):\n    pass",
                           "def count_env_keys(configs):\n    return {env: len(values) for env, values in configs.items()}",
                           [
                               {"input": [{"dev": {"DEBUG": True, "PORT": 8000}, "prod": {"PORT": 80}}], "expected": {"dev": 2, "prod": 1}},
                               {"input": [{"test": {}}], "expected": {"test": 0}},
                               {"input": [{}], "expected": {}},
                           ], ["general-cs", "config"]),
    ]
    return concept, code


def make_python_metadata(
    stage: str,
    cluster: str,
    subskills: list[str],
    question_role: str,
    prerequisites: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "family": "python",
        "stage": stage,
        "cluster": cluster,
        "subskills": subskills,
        "question_role": question_role,
        "prerequisites": prerequisites or [],
    }


def make_python_concept_question(
    qid: str,
    qtype: str,
    difficulty: str,
    question: str,
    explanation: str,
    tags: list[str],
    *,
    answer: Any,
    options: list[str] | None = None,
    stage: str,
    cluster: str,
    subskills: list[str],
    question_role: str,
    prerequisites: list[str] | None = None,
) -> dict[str, Any]:
    item = {
        "id": qid,
        "category": "concept",
        "type": qtype,
        "difficulty": difficulty,
        "question": question,
        "answer": answer,
        "explanation": explanation,
        "tags": tags,
    }
    if options is not None:
        item["options"] = options
    item.update(make_python_metadata(stage, cluster, subskills, question_role, prerequisites))
    return item


def make_code_question(
    qid: str,
    difficulty: str,
    title: str,
    function_name: str,
    params: list[str],
    prompt: str,
    starter_code: str,
    solution_code: str,
    test_cases: list[dict[str, Any]],
    tags: list[str],
    *,
    stage: str | None = None,
    cluster: str | None = None,
    subskills: list[str] | None = None,
    question_role: str | None = None,
    prerequisites: list[str] | None = None,
) -> dict[str, Any]:
    item = {
        "id": qid,
        "category": "code",
        "type": "function",
        "difficulty": difficulty,
        "title": title,
        "prompt": prompt,
        "description": prompt,
        "function_name": function_name,
        "params": params,
        "starter_code": starter_code,
        "solution_code": solution_code,
        "test_cases": test_cases,
        "tags": tags,
        "editor_language": "python",
        "language_label": "Python",
    }
    if stage and cluster and subskills is not None and question_role:
        item.update(make_python_metadata(stage, cluster, subskills, question_role, prerequisites))
    return item


def build_python_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        make_python_concept_question(
            "py-c1", "single", "easy",
            "在 Python 中，如果一个函数没有显式写 return，调用结果默认是什么？",
            "Python 函数未显式 return 时会默认返回 None。",
            ["python", "函数", "返回值", "stage1"],
            answer=2,
            options=["0", "False", "None", "空字符串"],
            stage="stage1",
            cluster="functions-foundations",
            subskills=["函数返回值", "None", "基础函数语义"],
            question_role="review",
        ),
        make_python_concept_question(
            "py-c2", "multi", "medium",
            "关于 Python 函数参数，下面哪些说法是正确的？",
            "可变默认参数会复用同一个对象；关键字参数常能提升可读性。位置参数应先于关键字参数；关键字调用依赖参数名。",
            ["python", "函数", "参数", "默认参数", "stage1"],
            answer=[0, 1],
            options=["可变默认参数可能带来跨调用共享状态", "关键字参数可以提升调用可读性", "位置参数必须写在关键字参数后面", "形参名只影响函数定义，不影响关键字调用"],
            stage="stage1",
            cluster="functions-foundations",
            subskills=["函数参数", "默认参数", "关键字参数"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c3", "judge", "easy",
            "使用 with open(...) as f: 可以在代码块结束后自动关闭文件。",
            "with 会配合上下文管理协议在离开代码块时释放资源。",
            ["python", "文件读写", "with", "上下文管理器", "stage1", "stage3"],
            answer=True,
            stage="stage1",
            cluster="files-and-io",
            subskills=["文件读写", "with", "资源释放"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c4", "single", "medium",
            "处理 Python 报错时，先看 traceback 的核心价值通常是什么？",
            "traceback 最直接的作用是告诉你错误类型、调用链和具体行号。",
            ["python", "异常处理", "调试", "traceback", "stage1"],
            answer=1,
            options=["自动修复代码", "定位异常类型与触发位置", "替代单元测试", "判断代码风格是否 Pythonic"],
            stage="stage1",
            cluster="exceptions-and-debugging",
            subskills=["traceback", "异常定位", "调试"],
            question_role="review",
        ),
        make_python_concept_question(
            "py-c5", "multi", "medium",
            "关于 try-except 的使用，下面哪些做法更合理？",
            "异常处理应尽量精确，关注边界操作，并保留足够上下文；无条件吞异常会降低可调试性。",
            ["python", "异常处理", "调试", "stage1"],
            answer=[0, 2, 3],
            options=["只捕获你预期会发生的异常类型", "在 except 里吞掉所有异常且不处理", "把可能失败的边界操作包进 try", "必要时记录上下文信息帮助排查"],
            stage="stage1",
            cluster="exceptions-and-debugging",
            subskills=["try-except", "异常边界", "错误上下文"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c6", "single", "medium",
            "在 pandas 中，如果你想按条件筛选行，最常见的写法是哪一种？",
            "按条件筛选最常见的是布尔条件配合 loc 或直接 df[mask]。",
            ["python", "pandas", "筛选", "DataFrame", "stage2"],
            answer=0,
            options=["df.loc[df['score'] > 60]", "df.groupby('score')", "df.merge(df2)", "df.pivot_table(index='score')"],
            stage="stage2",
            cluster="pandas-filtering",
            subskills=["布尔筛选", "DataFrame", "loc"],
            question_role="learn",
            prerequisites=["函数基础", "列表与字典", "基本数据读取"],
        ),
        make_python_concept_question(
            "py-c7", "multi", "hard",
            "关于 groupby、merge、pivot/reshape，下面哪些理解更准确？",
            "groupby、merge、pivot 分别对应聚合、连接、重塑，不等同于简单过滤。",
            ["python", "pandas", "groupby", "merge", "pivot", "reshape", "stage2"],
            answer=[0, 1, 2],
            options=["groupby 常用于分组后聚合统计", "merge 常用于按键连接多张表", "pivot/reshape 主要用于重塑表结构", "它们本质上都只是在做按行过滤"],
            stage="stage2",
            cluster="pandas-groupby-merge-reshape",
            subskills=["groupby", "merge", "pivot", "reshape"],
            question_role="bridge",
            prerequisites=["pandas 基础筛选", "DataFrame 结构理解"],
        ),
        make_python_concept_question(
            "py-c8", "judge", "medium",
            "NumPy / pandas 的很多操作之所以高效，和向量化思维有关。",
            "向量化意味着尽量让底层批量处理数据，而不是在 Python 层面逐元素循环。",
            ["python", "numpy", "pandas", "向量化", "stage2"],
            answer=True,
            stage="stage2",
            cluster="data-cleaning-and-vectorization",
            subskills=["向量化", "NumPy", "pandas 性能思维"],
            question_role="bridge",
            prerequisites=["数组与 DataFrame 基础"],
        ),
        make_python_concept_question(
            "py-c9", "single", "medium",
            "下面哪种写法通常更符合 Pythonic 风格？",
            "简单映射和过滤场景下，列表推导式通常更清晰简洁。",
            ["python", "pythonic", "列表推导式", "stage3"],
            answer=1,
            options=["先创建空列表，再在 10 行循环里 append 简单映射结果", "在表达简单映射时使用列表推导式", "所有逻辑都写进一个超长函数", "为了显得高级到处手写迭代器协议"],
            stage="stage3",
            cluster="pythonic-expressions",
            subskills=["列表推导式", "Pythonic 表达", "代码简洁性"],
            question_role="learn",
            prerequisites=["循环", "条件表达式", "函数基础"],
        ),
        make_python_concept_question(
            "py-c10", "multi", "hard",
            "关于生成器与上下文管理器，下面哪些说法更准确？",
            "生成器适合惰性迭代；上下文管理器用于成对资源管理；with 依赖上下文管理协议。生成器并非所有场景都优于列表。",
            ["python", "pythonic", "生成器", "上下文管理器", "stage3"],
            answer=[0, 1, 3],
            options=["生成器适合按需产出数据，减少一次性占用内存", "上下文管理器常用于资源申请与释放配对", "生成器一定比列表推导式更快且总是更适合", "with 语句背后依赖上下文管理协议"],
            stage="stage3",
            cluster="generators-and-context-managers",
            subskills=["生成器", "上下文管理器", "惰性迭代"],
            question_role="bridge",
            prerequisites=["迭代器基础", "函数基础"],
        ),
    ]

    code = [
        make_code_question("py-code1", "easy", "提取偶数", "extract_even_numbers", ["nums"],
                           "请实现函数 extract_even_numbers(nums)，返回列表中所有偶数组成的新列表，保持原顺序。",
                           "def extract_even_numbers(nums):\n    pass",
                           "def extract_even_numbers(nums):\n    return [num for num in nums if num % 2 == 0]",
                           [
                               {"input": [[1, 2, 3, 4]], "expected": [2, 4]},
                               {"input": [[1, 3, 5]], "expected": []},
                               {"input": [[0, -2, 7]], "expected": [0, -2]},
                           ], ["python", "函数", "列表处理", "stage1"],
                           stage="stage1", cluster="functions-foundations", subskills=["函数定义", "列表遍历", "条件过滤"], question_role="review"),
        make_code_question("py-code2", "easy", "规范化姓名", "normalize_names", ["names"],
                           "请实现函数 normalize_names(names)，去掉每个姓名首尾空白并转成 title case，返回新列表。",
                           "def normalize_names(names):\n    pass",
                           "def normalize_names(names):\n    return [name.strip().title() for name in names]",
                           [
                               {"input": [[" alice ", "BOB"]], "expected": ["Alice", "Bob"]},
                               {"input": [["tom"]], "expected": ["Tom"]},
                               {"input": [["  mary jane  "]], "expected": ["Mary Jane"]},
                           ], ["python", "字符串", "函数", "stage1"],
                           stage="stage1", cluster="functions-foundations", subskills=["字符串方法", "列表构造", "函数返回值"], question_role="learn"),
        make_code_question("py-code3", "easy", "安全除法", "safe_divide", ["a", "b"],
                           "请实现函数 safe_divide(a, b)：若 b 为 0 返回 None，否则返回 a / b。",
                           "def safe_divide(a, b):\n    pass",
                           "def safe_divide(a, b):\n    if b == 0:\n        return None\n    return a / b",
                           [
                               {"input": [6, 3], "expected": 2.0},
                               {"input": [5, 0], "expected": None},
                               {"input": [7, 2], "expected": 3.5},
                           ], ["python", "异常处理", "函数", "stage1"],
                           stage="stage1", cluster="exceptions-and-debugging", subskills=["边界判断", "返回值设计", "安全处理"], question_role="learn"),
        make_code_question("py-code4", "medium", "解析 CSV 行", "parse_csv_row", ["row"],
                           "请实现函数 parse_csv_row(row)，按逗号切分字符串，并去掉每个字段首尾空白。",
                           "def parse_csv_row(row):\n    pass",
                           "def parse_csv_row(row):\n    return [part.strip() for part in row.split(',')]",
                           [
                               {"input": ["alice, 18, Chongqing"], "expected": ["alice", "18", "Chongqing"]},
                               {"input": ["a,b,c"], "expected": ["a", "b", "c"]},
                               {"input": [" one , two "], "expected": ["one", "two"]},
                           ], ["python", "文件读写", "CSV", "stage1"],
                           stage="stage1", cluster="files-and-io", subskills=["split", "strip", "CSV 预处理"], question_role="bridge"),
        make_code_question("py-code5", "medium", "按城市计数", "count_rows_by_city", ["rows"],
                           "请实现函数 count_rows_by_city(rows)。rows 是字典列表，每项包含 city 字段；返回每个 city 的出现次数。",
                           "def count_rows_by_city(rows):\n    pass",
                           "def count_rows_by_city(rows):\n    result = {}\n    for row in rows:\n        city = row.get('city')\n        result[city] = result.get(city, 0) + 1\n    return result",
                           [
                               {"input": [[{"city": "重庆"}, {"city": "北京"}, {"city": "重庆"}]], "expected": {"重庆": 2, "北京": 1}},
                               {"input": [[{"city": "上海"}]], "expected": {"上海": 1}},
                               {"input": [[]], "expected": {}},
                           ], ["python", "pandas", "groupby", "聚合", "stage2"],
                           stage="stage2", cluster="pandas-groupby-merge-reshape", subskills=["分组统计", "字典累加", "聚合思维"], question_role="learn", prerequisites=["DataFrame 基础", "字典计数"]),
        make_code_question("py-code6", "medium", "合并用户分数", "merge_user_scores", ["users", "scores"],
                           "请实现函数 merge_user_scores(users, scores)。users 是用户名列表，scores 是用户名到分数的映射；返回 [{'user': 用户名, 'score': 分数或None}]。",
                           "def merge_user_scores(users, scores):\n    pass",
                           "def merge_user_scores(users, scores):\n    return [{'user': user, 'score': scores.get(user)} for user in users]",
                           [
                               {"input": [["alice", "bob"], {"alice": 95}], "expected": [{"user": "alice", "score": 95}, {"user": "bob", "score": None}]},
                               {"input": [["tom"], {"tom": 88}], "expected": [{"user": "tom", "score": 88}]},
                               {"input": [[], {}], "expected": []},
                           ], ["python", "pandas", "merge", "连接", "stage2"],
                           stage="stage2", cluster="pandas-groupby-merge-reshape", subskills=["连接思维", "映射查找", "结果整形"], question_role="bridge", prerequisites=["列表推导式", "字典 get"]),
        make_code_question("py-code7", "medium", "按月份透视销售额", "pivot_month_sales", ["records"],
                           "请实现函数 pivot_month_sales(records)。records 是字典列表，字段包含 month 和 amount；返回 month 到 amount 总和的映射。",
                           "def pivot_month_sales(records):\n    pass",
                           "def pivot_month_sales(records):\n    result = {}\n    for record in records:\n        month = record['month']\n        result[month] = result.get(month, 0) + record.get('amount', 0)\n    return result",
                           [
                               {"input": [[{"month": "2026-01", "amount": 10}, {"month": "2026-01", "amount": 5}, {"month": "2026-02", "amount": 8}]], "expected": {"2026-01": 15, "2026-02": 8}},
                               {"input": [[{"month": "2026-03", "amount": 0}]], "expected": {"2026-03": 0}},
                               {"input": [[]], "expected": {}},
                           ], ["python", "pandas", "pivot", "reshape", "stage2"],
                           stage="stage2", cluster="pandas-groupby-merge-reshape", subskills=["透视思维", "聚合", "键值累加"], question_role="bridge", prerequisites=["groupby 基础", "字典聚合"]),
        make_code_question("py-code8", "medium", "标准化日期字符串", "normalize_date_strings", ["values"],
                           "请实现函数 normalize_date_strings(values)，把形如 '2026/4/3' 的日期规范成 '2026-04-03'。",
                           "def normalize_date_strings(values):\n    pass",
                           "def normalize_date_strings(values):\n    result = []\n    for value in values:\n        year, month, day = value.replace('-', '/').split('/')\n        result.append(f'{int(year):04d}-{int(month):02d}-{int(day):02d}')\n    return result",
                           [
                               {"input": [["2026/4/3", "2026/12/25"]], "expected": ["2026-04-03", "2026-12-25"]},
                               {"input": [["2025-1-9"]], "expected": ["2025-01-09"]},
                               {"input": [[]], "expected": []},
                           ], ["python", "时间处理", "日期", "stage2"],
                           stage="stage2", cluster="time-series-and-dates", subskills=["日期清洗", "字符串解析", "格式规范化"], question_role="learn", prerequisites=["字符串处理", "列表遍历"]),
        make_code_question("py-code9", "project", "清洗并汇总分类金额", "clean_and_report", ["records"],
                           "请实现函数 clean_and_report(records)。records 为字典列表，包含 category 和 amount；忽略 amount 为 None 的记录，返回每个 category 的金额总和。",
                           "def clean_and_report(records):\n    pass",
                           "def clean_and_report(records):\n    result = {}\n    for record in records:\n        amount = record.get('amount')\n        if amount is None:\n            continue\n        category = record.get('category')\n        result[category] = result.get(category, 0) + amount\n    return result",
                           [
                               {"input": [[{"category": "A", "amount": 10}, {"category": "A", "amount": None}, {"category": "B", "amount": 5}]], "expected": {"A": 10, "B": 5}},
                               {"input": [[{"category": "X", "amount": 3}, {"category": "X", "amount": 7}]], "expected": {"X": 10}},
                               {"input": [[]], "expected": {}},
                           ], ["python", "数据清洗", "聚合", "项目", "stage2", "stage4"],
                           stage="stage2", cluster="data-cleaning-and-vectorization", subskills=["缺失值处理", "清洗", "聚合汇总"], question_role="test", prerequisites=["过滤", "聚合", "字典操作"]),
    ]
    return concept, code


def collect_focus_terms(plan_source: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["current_stage", "today_topic", "difficulty_target", "day"]:
        value = plan_source.get(key)
        if value:
            values.append(str(value))
    for key in ["review", "new_learning", "exercise_focus", "covered", "weakness_focus", "recommended_materials"]:
        raw = plan_source.get(key) or []
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
        elif raw:
            values.append(str(raw))

    full_text = " ".join(values)
    normalized = re.sub(r"[：:，,；;、/()（）\[\]\-]+", " ", full_text.lower())
    terms = [term.strip() for term in normalized.split() if len(term.strip()) >= 2]

    extra_terms: list[str] = []
    mapping = {
        "函数": ["函数", "参数", "返回值", "functions-foundations"],
        "推导式": ["列表推导式", "推导式", "pythonic-expressions"],
        "文件": ["文件", "文件读写", "csv", "files-and-io"],
        "异常": ["异常", "try", "except", "traceback", "exceptions-and-debugging"],
        "调试": ["调试", "traceback", "exceptions-and-debugging"],
        "脚本": ["脚本组织", "函数化"],
        "pandas": ["pandas", "dataframe", "筛选", "pandas-filtering"],
        "numpy": ["numpy", "向量化", "data-cleaning-and-vectorization"],
        "groupby": ["groupby", "聚合", "pandas-groupby-merge-reshape"],
        "merge": ["merge", "连接", "pandas-groupby-merge-reshape"],
        "pivot": ["pivot", "reshape", "重塑", "pandas-groupby-merge-reshape"],
        "时间": ["时间处理", "日期", "时间列", "time-series-and-dates"],
        "日期": ["日期", "时间处理", "time-series-and-dates"],
        "pythonic": ["pythonic", "列表推导式", "生成器", "上下文管理器", "pythonic-expressions", "generators-and-context-managers"],
        "生成器": ["生成器", "generators-and-context-managers"],
        "上下文管理器": ["上下文管理器", "with", "generators-and-context-managers"],
        "阶段 1": ["stage1"],
        "阶段 2": ["stage2"],
        "阶段 3": ["stage3"],
        "阶段 4": ["stage4"],
    }
    full_text_lower = full_text.lower()
    for needle, mapped in mapping.items():
        if needle.lower() in full_text_lower:
            extra_terms.extend(mapped)

    ordered: list[str] = []
    for item in terms + extra_terms:
        if item and item not in ordered:
            ordered.append(item)
    return ordered


def extract_difficulty_targets(plan_source: dict[str, Any], category: str) -> list[str]:
    text = str(plan_source.get("difficulty_target") or "").lower()
    if not text:
        return []
    segment = text
    if category == "concept" and "concept" in text:
        segment = text.split("concept", 1)[1]
        if "code" in segment:
            segment = segment.split("code", 1)[0]
    if category == "code" and "code" in text:
        segment = text.split("code", 1)[1]
    levels = [level for level in ["easy", "medium", "hard", "project"] if level in segment]
    ordered: list[str] = []
    for level in levels:
        if level not in ordered:
            ordered.append(level)
    return ordered


def resolve_target_stages(plan_source: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(plan_source.get(key) or "")
        for key in ["current_stage", "day", "today_topic"]
    )
    stages = [stage for stage in ["stage1", "stage2", "stage3", "stage4"] if stage in text.lower()]
    if stages:
        return stages
    mapping = {
        "阶段 1": "stage1",
        "阶段 2": "stage2",
        "阶段 3": "stage3",
        "阶段 4": "stage4",
    }
    for needle, stage in mapping.items():
        if needle in text:
            return [stage]
    return []


def resolve_target_clusters(plan_source: dict[str, Any]) -> list[str]:
    focus_terms = collect_focus_terms(plan_source)
    cluster_mapping = {
        "functions-foundations": ["函数", "参数", "返回值", "列表处理"],
        "files-and-io": ["文件", "文件读写", "csv"],
        "exceptions-and-debugging": ["异常", "调试", "traceback", "try", "except"],
        "pandas-filtering": ["pandas", "筛选", "dataframe", "loc"],
        "pandas-groupby-merge-reshape": ["groupby", "merge", "pivot", "reshape", "聚合", "连接", "重塑"],
        "time-series-and-dates": ["时间", "日期", "时间处理"],
        "data-cleaning-and-vectorization": ["清洗", "向量化", "numpy", "缺失值"],
        "pythonic-expressions": ["pythonic", "推导式", "列表推导式"],
        "generators-and-context-managers": ["生成器", "上下文管理器", "with"],
    }
    matched: list[str] = []
    for cluster, needles in cluster_mapping.items():
        if any(term == cluster or any(needle in term for needle in needles) for term in focus_terms):
            matched.append(cluster)
    return matched


def score_question(item: dict[str, Any], focus_terms: list[str]) -> int:
    blob = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("question") or item.get("prompt") or ""),
            str(item.get("cluster") or ""),
            str(item.get("question_role") or ""),
            " ".join(str(tag) for tag in item.get("tags") or []),
            " ".join(str(skill) for skill in item.get("subskills") or []),
        ]
    ).lower()
    score = 0
    for term in focus_terms:
        if term and term in blob:
            score += 2 if len(term) >= 4 else 1
    role = str(item.get("question_role") or "")
    if role == "review":
        score += 1
    if role == "bridge":
        score += 1
    return score


def filter_python_questions_by_constraints(
    items: list[dict[str, Any]],
    *,
    target_stages: list[str],
    target_clusters: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stage_pool = items
    if target_stages:
        stage_filtered = [item for item in items if str(item.get("stage") or "") in target_stages]
        if stage_filtered:
            stage_pool = stage_filtered
    cluster_pool = stage_pool
    if target_clusters:
        cluster_filtered = [item for item in stage_pool if str(item.get("cluster") or "") in target_clusters]
        if cluster_filtered:
            cluster_pool = cluster_filtered
    return cluster_pool, stage_pool


def allocate_python_question_mix(
    items: list[dict[str, Any]],
    *,
    focus_terms: list[str],
    preferred_difficulties: list[str],
    limit: int,
    role_quota: list[tuple[str, int]],
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, int, int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        difficulty = str(item.get("difficulty") or "")
        score = score_question(item, focus_terms)
        preferred = 1 if (difficulty in preferred_difficulties if preferred_difficulties else True) else 0
        ranked.append((preferred, score, -index, item))
    ranked.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for role, quota in role_quota:
        if len(selected) >= limit:
            break
        for _, _, _, item in ranked:
            if len(selected) >= limit:
                break
            if item["id"] in selected_ids:
                continue
            if str(item.get("question_role") or "") != role:
                continue
            selected.append(item)
            selected_ids.add(item["id"])
            if len([candidate for candidate in selected if str(candidate.get("question_role") or "") == role]) >= quota:
                break

    if len(selected) < limit:
        for _, _, _, item in ranked:
            if item["id"] in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item["id"])
            if len(selected) >= limit:
                break
    return selected


def resolve_preference_quota(plan_source: dict[str, Any], *, category: str) -> list[tuple[str, int]]:
    preference_state = plan_source.get("preference_state") if isinstance(plan_source.get("preference_state"), dict) else {}
    user_model = plan_source.get("user_model") if isinstance(plan_source.get("user_model"), dict) else {}
    learning_style = normalize_string_list(preference_state.get("learning_style") or user_model.get("learning_style"))
    practice_style = normalize_string_list(preference_state.get("practice_style") or user_model.get("practice_style"))
    delivery_preference = normalize_string_list(preference_state.get("delivery_preference") or user_model.get("delivery_preference"))

    if category == "concept":
        quota = {"review": 2, "learn": 3, "bridge": 2, "test": 1}
    else:
        quota = {"review": 1, "learn": 3, "bridge": 2, "test": 1}

    if any(style in {"偏讲解", "讲解优先"} for style in learning_style):
        quota["learn"] += 1
        quota["bridge"] += 1
        quota["review"] = max(1, quota["review"] - 1)
    if any(style in {"偏练习", "练习优先"} for style in learning_style):
        quota["review"] += 1
        if category == "code":
            quota["test"] += 1
        quota["learn"] = max(1, quota["learn"] - 1)
    if any(style in {"偏项目", "项目优先"} for style in learning_style):
        quota["bridge"] += 1
        if category == "code":
            quota["test"] += 1
        quota["review"] = max(1, quota["review"] - 1)
    if any(style in {"边讲边练", "先讲后练"} for style in delivery_preference):
        quota["bridge"] += 1
    if any(style in {"先测后讲", "测试优先"} for style in delivery_preference):
        quota["review"] += 1
        quota["test"] += 1
        quota["learn"] = max(1, quota["learn"] - 1)
    if any(style in {"小代码题", "代码题优先"} for style in practice_style) and category == "code":
        quota["test"] += 1
    if any(style in {"选择/判断", "概念题优先"} for style in practice_style) and category == "concept":
        quota["review"] += 1
    if any(style in {"阅读复盘", "复盘优先"} for style in practice_style):
        quota["bridge"] += 1

    ordered_roles = ["review", "learn", "bridge", "test"]
    return [(role, quota[role]) for role in ordered_roles]



def select_python_questions(
    concept: list[dict[str, Any]],
    code: list[dict[str, Any]],
    plan_source: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    focus_terms = collect_focus_terms(plan_source)
    concept_difficulties = extract_difficulty_targets(plan_source, "concept")
    code_difficulties = extract_difficulty_targets(plan_source, "code")
    target_stages = resolve_target_stages(plan_source)
    target_clusters = resolve_target_clusters(plan_source)

    concept_cluster_pool, concept_stage_pool = filter_python_questions_by_constraints(concept, target_stages=target_stages, target_clusters=target_clusters)
    code_cluster_pool, code_stage_pool = filter_python_questions_by_constraints(code, target_stages=target_stages, target_clusters=target_clusters)

    concept_pool = concept_cluster_pool if len(concept_cluster_pool) >= 7 else concept_stage_pool
    code_pool = code_cluster_pool if len(code_cluster_pool) >= 7 else code_stage_pool

    concept_quota = resolve_preference_quota(plan_source, category="concept")
    code_quota = resolve_preference_quota(plan_source, category="code")

    selected_concept = allocate_python_question_mix(
        concept_pool,
        focus_terms=focus_terms,
        preferred_difficulties=concept_difficulties,
        limit=7,
        role_quota=concept_quota,
    )
    selected_code = allocate_python_question_mix(
        code_pool,
        focus_terms=focus_terms,
        preferred_difficulties=code_difficulties,
        limit=7,
        role_quota=code_quota,
    )
    selection_context = {
        "target_stages": target_stages,
        "target_clusters": target_clusters,
        "concept_difficulties": concept_difficulties,
        "code_difficulties": code_difficulties,
        "concept_quota": concept_quota,
        "code_quota": code_quota,
        "selection_policy": "python-constraint-filtering+preference-routing",
    }
    return selected_concept, selected_code, selection_context


def build_question_bank(domain: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    domain = resolve_question_bank_domain(domain)
    if domain == "english":
        return build_english_bank()
    if domain == "math":
        return build_math_bank()
    if domain == "algorithm":
        return build_algorithm_bank()
    if domain == "linux":
        return build_linux_bank()
    if domain == "llm-app":
        return build_llm_app_bank()
    if domain == "python":
        return build_python_bank()
    return build_general_cs_bank()


def domain_supports_code_questions(domain: str) -> bool:
    return domain not in {"linux", "english"}


def ensure_question_shape(data: dict[str, Any]) -> None:
    required_top_level = ["date", "topic", "mode", "session_type", "test_mode", "plan_source", "materials", "questions"]
    for key in required_top_level:
        if key not in data:
            raise ValueError(f"questions.json 缺少字段: {key}")
    if not isinstance(data["questions"], list) or not data["questions"]:
        raise ValueError("questions 必须是非空列表")
    ids: set[str] = set()
    for item in data["questions"]:
        qid = item.get("id")
        if not qid:
            raise ValueError("存在题目缺少 id")
        if qid in ids:
            raise ValueError(f"存在重复题目 id: {qid}")
        ids.add(qid)


def describe_execution_mode(execution_mode: str, topic: str) -> dict[str, Any]:
    mapping = {
        "clarification": {
            "study_mode": "澄清补全",
            "why_today": "当前还缺少足够清晰的目标、约束或边界，因此今天先完成顾问式澄清，不直接推进正式主线。",
            "coach_explanation": "本次 session 的任务是把学习目的、成功标准、已有基础和非目标范围说清楚，为后续规划建立可靠起点。",
            "practice_bridge": [
                "优先回答澄清问题，而不是着急进入题目训练。",
                "把不确定的目标、约束和非目标先写清楚。",
                "若今天仍有开放问题，下次 /learn-plan 需要继续澄清，而不是直接推进。",
            ],
        },
        "research": {
            "study_mode": "研究确认",
            "why_today": "当前目标需要外部能力标准或资料取舍依据，因此今天先完成研究计划确认，不直接推进正式主线。",
            "coach_explanation": "本次 session 的任务是确认：要查什么、为什么查、查完后如何影响学习路线和资料选择。",
            "practice_bridge": [
                "优先确认 research questions、资料来源类型和筛选标准。",
                "把主线候选资料和备选资料区分清楚。",
                "确认后再进入 deepsearch 或正式规划，而不是直接做常规学习题。",
            ],
        },
        "diagnostic": {
            "study_mode": "水平诊断",
            "why_today": "当前真实水平还不够确定，因此今天先做最小诊断验证，再决定从哪里开始学。",
            "coach_explanation": "本次 session 的任务不是推进新知识，而是确认你现在到底会什么、不会什么，以及主线应从哪一层开始。",
            "practice_bridge": [
                "优先完成解释题、小测试或小代码题，作为起点判断证据。",
                "不要把今天当成正式推进日，而应把它当作分层校准日。",
                "诊断完成后，下一轮才进入正式主线编排。",
            ],
        },
        "test-diagnostic": {
            "study_mode": "测试诊断",
            "why_today": "当前计划仍未达到正式推进条件，因此今天用测试型 session 先做诊断，而不是做阶段通过性测试。",
            "coach_explanation": "本次 session 以测试形态收集证据，用来判断真实薄弱点和起步阶段，而不是判断你是否已经可以推进。",
            "practice_bridge": [
                "把今天的题目当作定位工具，而不是通关测试。",
                "优先记录你卡住的概念、题型和表达问题。",
                "诊断证据足够后，才重新决定下一轮 today/test 的走向。",
            ],
        },
        "prestudy": {
            "study_mode": "预读/补资料",
            "why_today": "当前计划还未完成最终确认，因此今天先做主线候选资料预读和确认前准备，不直接进入正式主线推进。",
            "coach_explanation": "本次 session 的任务是先把主线候选材料、阅读定位和确认项补齐，避免后续沿错误路线推进。",
            "practice_bridge": [
                "先读候选主线材料和说明，而不是直接进入正常训练量。",
                "重点确认：主线材料是否合适、范围是否准确、是否还缺关键资料。",
                "完成预读和确认后，再进入正式学习 session。",
            ],
        },
    }
    return mapping.get(
        execution_mode,
        {
            "study_mode": "复习+推进",
            "why_today": "先根据当前阶段、最近复习重点和新学习点安排当天内容，再结合掌握度检验决定是否推进。",
            "coach_explanation": f"今天优先服务主线目标：{topic}；在主线之外，只补 1 个支撑能力点，并仅在时间预算允许时触发增强模块。",
            "practice_bridge": [
                "读完讲义后，立即到现有练习页面做对应题目，不要只停留在阅读层。",
                "做题时优先验证：你是否真的理解了今天这几个概念，而不是只记住名字。",
                "若练习卡住，先回到上面的讲解摘要和阅读指导，再继续做。",
            ],
        },
    )



def build_daily_lesson_plan(topic: str, plan_source: dict[str, Any], selected_segments: list[dict[str, Any]], mastery_targets: dict[str, list[str]]) -> dict[str, Any]:
    current_stage = plan_source.get("current_stage") or "未识别阶段"
    current_day = plan_source.get("day") or "未命名学习日"
    review = normalize_string_list(plan_source.get("review") or [])
    new_learning = normalize_string_list(plan_source.get("new_learning") or [])
    exercise_focus = normalize_string_list(plan_source.get("exercise_focus") or [])
    execution_mode = str(plan_source.get("plan_execution_mode") or "normal")
    plan_blockers = normalize_string_list(plan_source.get("plan_blockers") or [])

    lesson_lines = []
    teaching_points = []
    covered_topics: set[str] = set()
    preference_state = plan_source.get("preference_state") if isinstance(plan_source.get("preference_state"), dict) else {}
    learning_style = normalize_string_list(preference_state.get("learning_style") or (plan_source.get("user_model") or {}).get("learning_style"))
    practice_style = normalize_string_list(preference_state.get("practice_style") or (plan_source.get("user_model") or {}).get("practice_style"))
    delivery_preference = normalize_string_list(preference_state.get("delivery_preference") or (plan_source.get("user_model") or {}).get("delivery_preference"))
    for segment in selected_segments:
        locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
        sections = locator.get("sections") or []
        checkpoints = segment.get("checkpoints") or []
        lesson_lines.append(
            {
                "segment_id": segment.get("segment_id"),
                "label": segment.get("label"),
                "chapter": locator.get("chapter"),
                "pages": locator.get("pages"),
                "sections": sections,
                "purpose": segment.get("purpose"),
                "checkpoints": checkpoints,
                "material_title": segment.get("material_title"),
                "material_summary": segment.get("material_summary"),
                "material_source_name": segment.get("material_source_name"),
                "material_kind": segment.get("material_kind"),
                "material_teaching_style": segment.get("material_teaching_style"),
            }
        )
        for item in (sections or checkpoints)[:3]:
            topic_name = str(item).strip()
            if not topic_name or topic_name in covered_topics:
                continue
            covered_topics.add(topic_name)
            material_kind = str(segment.get("material_kind") or "")
            teaching_style = str(segment.get("material_teaching_style") or "")
            background = f"今天使用的主线资料是 {segment.get('material_title') or segment.get('label') or topic}，其中 {topic_name} 是这段材料要解决的关键内容。"
            explanation = f"结合 {segment.get('material_source_name') or '当前资料'} 的这一段内容，先弄清 {topic_name} 的基本概念、典型输入输出形式，以及它在 {segment.get('label') or topic} 中承担什么作用。"
            study_prompt = f"阅读 {segment.get('material_title') or '这份资料'} 时，重点留意 {topic_name} 的定义、例子、适用场景，以及它与同段其它概念之间的区别。"
            if material_kind == "book" or teaching_style == "chapter-lecture":
                background = f"今天使用的是书籍型主线资料 {segment.get('material_title') or segment.get('label') or topic}，这一段更适合按‘概念—例子—应用’的顺序去理解。"
                explanation = f"把 {topic_name} 看成这一章节里的核心概念，先理解它在书中是怎样被引入的，再理解它如何和本章其它内容衔接。"
                study_prompt = f"阅读 {segment.get('material_title') or '这本书'} 时，优先留意 {topic_name} 出现前后的例子、定义和章节过渡。"
            elif material_kind == "tutorial" or teaching_style == "step-by-step":
                background = f"今天使用的是教程型资料 {segment.get('material_title') or segment.get('label') or topic}，这一段更像步骤讲解，需要边看边跟着思路走。"
                explanation = f"把 {topic_name} 理解成教程里的一个操作步骤，先弄清它输入什么、输出什么、通常放在哪一步。"
                study_prompt = f"阅读 {segment.get('material_title') or '这份教程'} 时，重点关注 {topic_name} 的步骤顺序、前置条件和执行结果。"
            elif material_kind == "reference" or teaching_style == "concept-reference":
                background = f"今天使用的是参考资料 {segment.get('material_title') or segment.get('label') or topic}，这一段更适合按‘定义—接口—场景—边界’的顺序去读。"
                explanation = f"把 {topic_name} 看成这份参考资料中的一个关键条目，先弄清它的定义，再看它通常和哪些接口、场景或约束一起出现。"
                study_prompt = f"阅读 {segment.get('material_title') or '这份参考资料'} 时，重点留意 {topic_name} 的定义、典型用法、适用场景和使用边界。"
            teaching_points.append(
                {
                    "topic": topic_name,
                    "background": background,
                    "core_question": f"你需要先回答：{topic_name} 在 {segment.get('material_title') or topic} 这部分内容里，到底解决什么问题，为什么今天先学它？",
                    "explanation": explanation,
                    "practical_value": f"这段资料强调的是：{segment.get('material_summary') or segment.get('purpose') or topic}。掌握 {topic_name} 后，才能把这一段资料真正转成可用能力。",
                    "pitfall": f"学习 {topic_name} 时，要避免只记 API 或术语名字，而不理解它在这份资料里为什么重要、和相邻内容怎么配合。",
                    "study_prompt": study_prompt,
                }
            )

    if not teaching_points:
        for item in new_learning[:3]:
            teaching_points.append({
                "topic": item,
                "background": f"今天会把 {item} 作为新的推进点，它决定了后续能不能顺利进入下一层训练。",
                "core_question": f"阅读时要先想清楚：{item} 为什么会在今天出现，它补的是哪个能力缺口？",
                "explanation": f"今天需要重点理解 {item} 是什么、它解决什么问题、以及它和当前阶段任务的关系。",
                "practical_value": f"掌握 {item} 后，才能把 {topic} 的当前任务从‘会看’推进到‘会用’。",
                "pitfall": f"学习 {item} 时，要避免只记结论，不理解使用边界和实际场景。",
                "study_prompt": f"阅读相关资料时，重点关注 {item} 的定义、典型使用方式，以及它与旧知识的衔接。",
            })

    if not teaching_points:
        for item in review[:3]:
            teaching_points.append({
                "topic": item,
                "background": f"{item} 是你当前还不够稳的部分，所以今天要先把它补成可解释、可复用的知识。",
                "core_question": f"复习 {item} 时，先问自己：我之前为什么会在这里出错？是概念没懂，还是使用条件没搞清楚？",
                "explanation": f"今天先回看 {item}，把概念、用法和容易出错的地方重新讲清楚。",
                "practical_value": f"只有把 {item} 补稳，后续 {topic} 的推进才不会建立在不牢固的基础上。",
                "pitfall": f"复习 {item} 时，不要只看结果，要重新解释自己为什么这样做。",
                "study_prompt": f"读资料时重点回看 {item} 的定义、典型例子和反例，确认自己不是只会背结论。",
            })

    completion_criteria = normalize_string_list(mastery_targets.get("reading_checklist") or [])
    completion_criteria += normalize_string_list(mastery_targets.get("session_exercises") or [])[:2]
    completion_criteria += normalize_string_list(mastery_targets.get("applied_project") or [])[:1]
    completion_criteria += normalize_string_list(mastery_targets.get("reflection") or [])[:1]

    mode_description = describe_execution_mode(execution_mode, plan_source.get("mainline_goal") or topic)
    study_mode = "复习+推进" if review and new_learning else ("复习" if review else "推进")
    why_today = "先根据当前阶段、最近复习重点和新学习点安排当天内容，再结合掌握度检验决定是否推进。"
    coach_explanation = f"今天优先服务主线目标：{plan_source.get('mainline_goal') or topic}；在主线之外，只补 1 个支撑能力点，并仅在时间预算允许时触发增强模块。"
    positioning = f"当前处于 {current_stage}，今天围绕 {plan_source.get('today_topic') or topic} 安排学习。"
    practice_bridge = [
        "读完讲义后，立即到现有练习页面做对应题目，不要只停留在阅读层。",
        "做题时优先验证：你是否真的理解了今天这几个概念，而不是只记住名字。",
        "若练习卡住，先回到上面的讲解摘要和阅读指导，再继续做。",
    ]
    if learning_style:
        why_today += f" 当前已确认的学习风格：{'；'.join(learning_style)}。"
    if practice_style:
        coach_explanation += f" 当前优先练习方式：{'；'.join(practice_style)}。"
    if delivery_preference:
        coach_explanation += f" 讲练组织偏好：{'；'.join(delivery_preference)}。"
    if execution_mode != "normal":
        study_mode = mode_description["study_mode"]
        why_today = mode_description["why_today"]
        coach_explanation = mode_description["coach_explanation"]
        positioning = f"当前处于 {current_stage}，但计划执行模式为 {study_mode}。"
        practice_bridge = mode_description["practice_bridge"]
        if plan_blockers:
            blocker_title = {
                "clarification": "待补齐的澄清项",
                "research": "待确认的研究项",
                "diagnostic": "待完成的诊断项",
                "test-diagnostic": "待验证的诊断项",
                "prestudy": "待完成的确认项",
            }.get(execution_mode, "当前阻塞项")
            teaching_points.insert(0, {
                "topic": blocker_title,
                "background": "在进入正式学习前，系统检测到仍有关键 gate 未通过。",
                "core_question": "你需要先确认：这些前置条件是否已经补齐？",
                "explanation": "只有先补齐这些前置条件，后续路线和题目编排才不会建立在错误假设上。",
                "practical_value": "这一步是在为后续正式学习清路，而不是浪费时间。",
                "pitfall": "若跳过这些前置条件，后续 session 很容易继续沿着错误路径推进。",
                "study_prompt": "先逐条处理当前阻塞项，再决定是否进入正式主线学习。",
            })
            completion_criteria = normalize_string_list(plan_blockers)
            completion_criteria += normalize_string_list(exercise_focus)[:2]
            completion_criteria += normalize_string_list(mastery_targets.get("reflection") or [])[:1]

    return {
        "title": current_day,
        "current_stage": current_stage,
        "study_mode": study_mode,
        "positioning": positioning,
        "why_today": why_today,
        "coach_explanation": coach_explanation,
        "goal_focus": {
            "mainline": plan_source.get("mainline_goal") or topic,
            "supporting": normalize_string_list(plan_source.get("supporting_capabilities"))[:2],
            "enhancement": normalize_string_list(plan_source.get("enhancement_modules"))[:1],
        },
        "preference_focus": {
            "learning_style": learning_style,
            "practice_style": practice_style,
            "delivery_preference": delivery_preference,
        },
        "time_budget_today": plan_source.get("time_budget_today"),
        "lesson_intro": f"今天这一讲的核心，不是把所有内容都看完，而是先把 {', '.join([item.get('topic') for item in teaching_points[:3]]) or topic} 这几个关键点听懂、讲清、能在练习里用出来。",
        "plan_execution_mode": execution_mode,
        "plan_blockers": plan_blockers,
        "specific_tasks": lesson_lines,
        "teaching_points": teaching_points,
        "reading_guidance": [
            "先按资料顺序看今天指定 segment，优先弄懂概念和实际用途。",
            "每读完一个小节，都用自己的话复述：它解决什么问题、什么时候用、容易错在哪里。",
            "遇到不熟的 API / 术语时，先理解作用和输入输出，再补细节。",
            "今天不追求面面俱到，先把 selected segments 对应的核心内容吃透。",
        ],
        "lesson_summary": [
            f"今天学完后，你至少要能用自己的话解释：{', '.join(completion_criteria[:4]) or topic}。",
            "如果你只能记住术语，但说不出它解决什么问题，就说明还没有真正掌握。",
            "如果你能把今天的概念讲清楚，并能在练习里用出来，这一讲才算完成。",
        ],
        "exercise_plan": exercise_focus,
        "practice_bridge": practice_bridge,
        "completion_criteria": completion_criteria,
        "feedback_request": [
            "学完后请反馈：哪些内容已经能讲清楚，哪些地方还卡。",
            "如完成练习或小项目，请贴代码、结论或运行结果。",
            "最后运行 /learn-today-update，回写当天学习结果。",
        ],
    }



def render_daily_lesson_plan_markdown(plan: dict[str, Any]) -> str:
    task_lines: list[str] = []
    for item in plan.get("specific_tasks") or []:
        sections = "；".join(item.get("sections") or []) or "待补充小节"
        locator_bits = [bit for bit in [item.get("chapter"), item.get("pages")] if bit]
        locator_text = " / ".join(locator_bits) if locator_bits else "待补充定位"
        task_lines.extend(
            [
                f"- {item.get('label')}",
                f"  - 资料来源：{item.get('material_title') or '未命名资料'} / {item.get('material_source_name') or '未知来源'}",
                f"  - 阅读定位：{locator_text}",
                f"  - 重点小节：{sections}",
                f"  - 学习目的：{item.get('purpose')}",
                f"  - 资料摘要：{item.get('material_summary') or '待补充摘要'}",
            ]
        )

    teaching_lines: list[str] = []
    for item in plan.get("teaching_points") or []:
        teaching_lines.extend(
            [
                f"### {item.get('topic')}",
                f"- 背景：{item.get('background')}",
                f"- 先带着这个问题去学：{item.get('core_question')}",
                f"- 讲解：{item.get('explanation')}",
                f"- 实际意义：{item.get('practical_value')}",
                f"- 常见误区：{item.get('pitfall')}",
                f"- 阅读时重点关注：{item.get('study_prompt')}",
                "",
            ]
        )

    blocks = [
        f"# {plan.get('title')}",
        "",
        "## 今日定位",
        "",
        f"- 当前阶段：{plan.get('current_stage')}",
        f"- 今日类型：{plan.get('study_mode')}",
        f"- 今日定位：{plan.get('positioning')}",
        f"- 为什么今天学这些：{plan.get('why_today')}",
        f"- 教练解释：{plan.get('coach_explanation')}",
        f"- 主线目标：{(plan.get('goal_focus') or {}).get('mainline')}",
        *( [f"- 支撑能力：{'；'.join((plan.get('goal_focus') or {}).get('supporting') or [])}"] if (plan.get('goal_focus') or {}).get('supporting') else [] ),
        *( [f"- 增强模块：{'；'.join((plan.get('goal_focus') or {}).get('enhancement') or [])}"] if (plan.get('goal_focus') or {}).get('enhancement') else [] ),
        *( [f"- 学习风格：{'；'.join((plan.get('preference_focus') or {}).get('learning_style') or [])}"] if (plan.get('preference_focus') or {}).get('learning_style') else [] ),
        *( [f"- 练习方式：{'；'.join((plan.get('preference_focus') or {}).get('practice_style') or [])}"] if (plan.get('preference_focus') or {}).get('practice_style') else [] ),
        *( [f"- 讲练偏好：{'；'.join((plan.get('preference_focus') or {}).get('delivery_preference') or [])}"] if (plan.get('preference_focus') or {}).get('delivery_preference') else [] ),
        *( [f"- 时间预算：{plan.get('time_budget_today')}"] if plan.get('time_budget_today') else [] ),
        "",
        "## 导入",
        "",
        f"- {plan.get('lesson_intro')}",
        "",
        "## 今日具体学习任务",
        "",
        *(task_lines or ["- 暂无明确资料段落，需先补充主线资料或确认今日内容"]),
        "",
        "## 今日讲解摘要",
        "",
        *(teaching_lines or ["- 暂无可讲解内容，请先补充资料定位。"]),
        "## 阅读指导",
        "",
        *[f"- {item}" for item in plan.get("reading_guidance") or []],
        "",
        "## 小结",
        "",
        *[f"- {item}" for item in plan.get("lesson_summary") or []],
        "",
        "## 今日练习安排",
        "",
        *[f"- {item}" for item in plan.get("exercise_plan") or []],
        "",
        "## 练习如何衔接现有页面",
        "",
        *[f"- {item}" for item in plan.get("practice_bridge") or []],
        "",
        "## 今日完成标准",
        "",
        *[f"- {item}" for item in plan.get("completion_criteria") or []],
        "",
        "## 学完后反馈",
        "",
        *[f"- {item}" for item in plan.get("feedback_request") or []],
        "",
    ]
    return "\n".join(blocks).rstrip() + "\n"



def build_questions_payload(args: argparse.Namespace, topic: str, plan_text: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
    session_dir = Path(args.session_dir).expanduser().resolve()
    plan_path = Path(args.plan_path).expanduser().resolve()
    topic_profile = load_topic_profile(plan_path, topic)
    domain = resolve_topic_domain(topic, plan_text, topic_profile)
    concept, code = build_question_bank(domain)
    if not domain_supports_code_questions(resolve_question_bank_domain(domain)):
        code = []
    plan_source = make_plan_source(topic, args.session_type, args.test_mode, plan_text, plan_path, args, topic_profile=topic_profile)
    selected_segments, mastery_targets = select_material_segments(materials, plan_source)
    execution_mode = str(plan_source.get("plan_execution_mode") or "normal")
    if execution_mode in {"clarification", "research", "diagnostic", "test-diagnostic", "prestudy"}:
        selected_segments = []
        mastery_targets = {
            "reading_checklist": normalize_string_list(plan_source.get("plan_blockers") or []),
            "session_exercises": normalize_string_list(plan_source.get("exercise_focus") or []),
            "applied_project": [],
            "reflection": ["用自己的话解释当前为什么还不能直接进入正式主线学习"],
        }
    daily_lesson_plan = build_daily_lesson_plan(topic, plan_source, selected_segments, mastery_targets)
    plan_source["selected_segments"] = selected_segments
    plan_source["mastery_targets"] = mastery_targets
    plan_source["daily_lesson_plan"] = daily_lesson_plan
    plan_source["session_objectives"] = [
        "先确认真实进度，再决定今日复习与新学习内容",
        "围绕 selected segments 阅读、练习与复盘",
        "结合掌握度检验结果决定是否推进",
    ]
    if execution_mode in {"clarification", "research", "diagnostic", "test-diagnostic", "prestudy"}:
        plan_source["session_objectives"] = [
            "先解除当前 gate 阻塞，再决定是否进入正式主线学习",
            "围绕顾问式澄清、研究确认、诊断或预读任务完成本次 session",
            "完成阻塞项后再进入下一轮正式编排",
        ]
    plan_source["gating_decision"] = (
        "若 selected segments 未完成或阅读掌握清单未达标，则优先补读与复习；"
        "若 session 与复盘连续稳定，才允许推进到下一阶段。"
    )
    if execution_mode in {"clarification", "research", "diagnostic", "test-diagnostic", "prestudy"}:
        plan_source["gating_decision"] = "当前计划尚未通过执行 gate，本次 session 先处理阻塞项，不直接进入正式主线推进。"
    assessment_kind = None
    session_intent = "learning" if args.session_type == "today" else "assessment"
    if execution_mode in {"diagnostic", "test-diagnostic"}:
        assessment_kind = "plan-diagnostic"
        session_intent = "plan-diagnostic"
    elif args.session_type == "test":
        assessment_kind = "stage-test"

    mode = "today-generated" if args.session_type == "today" else f"test-{args.test_mode or 'general'}"

    python_selection_context: dict[str, Any] = {}
    if domain == "python":
        concept, code, python_selection_context = select_python_questions(concept, code, plan_source)

    questions = concept + code
    plan_source["lesson_path"] = str(session_dir / "lesson.md")
    payload = {
        "date": args.date,
        "topic": topic,
        "domain": domain,
        "mode": mode,
        "session_type": args.session_type,
        "session_intent": session_intent,
        "assessment_kind": assessment_kind,
        "test_mode": args.test_mode if args.session_type == "test" else None,
        "plan_source": plan_source,
        "selection_context": {
            "domain": domain,
            "source_kind": plan_source.get("source_kind") or plan_source.get("basis") or "plan-markdown-fallback",
            "current_stage": plan_source.get("current_stage"),
            "current_day": plan_source.get("day"),
            "topic_cluster": plan_source.get("today_topic"),
            "difficulty_target": plan_source.get("difficulty_target"),
            "selection_policy": python_selection_context.get("selection_policy") if domain == "python" else "domain-bank-fallback",
            "target_stages": python_selection_context.get("target_stages") if domain == "python" else [],
            "target_clusters": python_selection_context.get("target_clusters") if domain == "python" else [],
            "selected_segments": selected_segments,
            "mastery_targets": mastery_targets,
            "daily_lesson_plan": daily_lesson_plan,
            "question_mix": {
                "concept": {"count": len(concept), "roles": [str(item.get("question_role") or "") for item in concept]},
                "code": {"count": len(code), "roles": [str(item.get("question_role") or "") for item in code]},
            } if domain == "python" else None,
        },
        "materials": materials,
        "questions": questions,
    }
    ensure_question_shape(payload)
    return payload


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def progress_shape_is_valid(progress: dict[str, Any]) -> bool:
    if not isinstance(progress, dict):
        return False
    if not isinstance(progress.get("session"), dict):
        return False
    if not isinstance(progress.get("summary"), dict):
        return False
    if not isinstance(progress.get("questions"), dict):
        return False
    for key in ("date", "topic", "result_summary"):
        if key not in progress:
            return False
    return True


def is_complete_session(session_dir: Path) -> bool:
    required = [session_dir / "题集.html", session_dir / "questions.json", session_dir / "progress.json", session_dir / "server.py"]
    if not all(path.exists() for path in required):
        return False
    try:
        ensure_question_shape(json.loads((session_dir / "questions.json").read_text(encoding="utf-8")))
        progress = json.loads((session_dir / "progress.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    return progress_shape_is_valid(progress)


def run_bootstrap(args: argparse.Namespace, session_dir: Path, questions_path: Path | None) -> int:
    command = [sys.executable, str(BOOTSTRAP), "--session-dir", str(session_dir), "--plan-path", args.plan_path]
    if questions_path is not None:
        command.extend(["--questions", str(questions_path)])
    if args.session_type == "test":
        command.extend(["--session-type", "test"])
        if args.test_mode:
            command.extend(["--test-mode", args.test_mode])
    if args.force_bootstrap:
        command.append("--force")
    if args.no_start:
        command.append("--no-start")
    if args.no_open:
        command.append("--no-open")
    return subprocess.run(command, check=False).returncode


def write_daily_lesson_plan(plan_path: Path, payload: dict[str, Any], session_dir: Path) -> Path:
    plan_source = payload.get("plan_source") if isinstance(payload.get("plan_source"), dict) else {}
    daily_plan = plan_source.get("daily_lesson_plan") if isinstance(plan_source.get("daily_lesson_plan"), dict) else {}
    daily_path = session_dir / "lesson.md"
    content = render_daily_lesson_plan_markdown(daily_plan) if daily_plan else "# 当日学习计划\n\n- 暂无可生成的教学计划内容。\n"
    daily_path.write_text(content, encoding="utf-8")
    return daily_path



def print_orchestrator_summary(session_dir: Path, plan_path: Path, materials: list[dict[str, Any]], *, daily_plan_path: Path | None = None) -> None:
    print(f"检测 learn-plan.md：{'yes' if plan_path.exists() else 'no'}")
    print(f"材料条目数：{len(materials)}")
    if daily_plan_path is not None:
        print(f"当日教学计划：{daily_plan_path}")


def main() -> int:
    args = parse_args()
    if args.session_type == "test" and not args.test_mode:
        args.test_mode = "general"
    if args.session_type == "today":
        args.test_mode = None
    if args.test_mode and args.test_mode not in VALID_TEST_MODES:
        raise ValueError(f"无效 test_mode: {args.test_mode}")

    session_dir = Path(args.session_dir).expanduser().resolve()
    plan_path = Path(args.plan_path).expanduser().resolve()
    plan_text = read_text_if_exists(plan_path)
    topic = (args.topic or extract_topic_from_plan(plan_text) or "算法基础").strip()

    if is_complete_session(session_dir) and not args.force_generate:
        existing_payload = read_json_if_exists(session_dir / "questions.json")
        daily_plan_path = write_daily_lesson_plan(plan_path, existing_payload, session_dir) if existing_payload else None
        print_orchestrator_summary(session_dir, plan_path, load_materials(plan_path, topic), daily_plan_path=daily_plan_path)
        return run_bootstrap(args, session_dir, None)

    questions_path = session_dir / "questions.json"
    materials = load_materials(plan_path, topic)
    payload = build_questions_payload(args, topic, plan_text, materials)
    write_json(questions_path, payload)
    daily_plan_path = write_daily_lesson_plan(plan_path, payload, session_dir)
    print_orchestrator_summary(session_dir, plan_path, materials, daily_plan_path=daily_plan_path)
    return run_bootstrap(args, session_dir, questions_path)


if __name__ == "__main__":
    sys.exit(main())
