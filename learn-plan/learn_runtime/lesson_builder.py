from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from learn_core.llm_json import parse_json_from_llm_output as core_parse_json_from_llm_output
from learn_core.plan_parser import split_semicolon_values
from learn_core.quality_review import apply_quality_envelope, build_traceability_entry, normalize_confidence
from learn_core.text_utils import normalize_string_list
from learn_runtime.plan_source import normalize_day_key
from learn_runtime.source_grounding import (
    build_content_aware_explanation,
    build_content_aware_pitfall,
    clean_source_teaching_terms,
    compact_source_text,
)

SKILL_DIR = Path(__file__).resolve().parents[1]
LLM_DISABLE_VALUES = {"1", "true", "yes", "on"}


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


def llm_generation_disabled() -> bool:
    return str(os.environ.get("LEARN_PLAN_DISABLE_LLM") or "").strip().lower() in LLM_DISABLE_VALUES


def llm_generation_timeout() -> int:
    raw_value = str(os.environ.get("LEARN_PLAN_LLM_TIMEOUT_SECONDS") or "90").strip()
    try:
        value = int(raw_value)
    except ValueError:
        return 90
    return max(20, min(value, 240))


def json_for_prompt(value: Any, *, limit: int = 16000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...<truncated>"


def parse_json_from_llm_output(raw_text: str) -> Any | None:
    return core_parse_json_from_llm_output(raw_text)


def run_claude_json_generation(prompt: str) -> tuple[Any | None, dict[str, Any]]:
    if llm_generation_disabled():
        return None, {"status": "disabled", "reason": "LEARN_PLAN_DISABLE_LLM"}
    claude_path = shutil.which("claude")
    if not claude_path:
        return None, {"status": "unavailable", "reason": "claude-cli-not-found"}
    model = str(os.environ.get("LEARN_PLAN_LLM_MODEL") or "claude-sonnet-4-6").strip()
    command = [claude_path, "-p", prompt, "--model", model]
    started = time.time()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=llm_generation_timeout(),
            cwd=str(SKILL_DIR),
        )
    except subprocess.TimeoutExpired:
        return None, {"status": "timeout", "reason": "claude-cli-timeout", "model": model}
    except OSError as exc:
        return None, {"status": "error", "reason": f"claude-cli-os-error: {exc}", "model": model}
    elapsed_ms = int((time.time() - started) * 1000)
    if result.returncode != 0:
        return None, {
            "status": "error",
            "reason": "claude-cli-nonzero-exit",
            "returncode": result.returncode,
            "stderr_excerpt": compact_source_text(result.stderr or "", 500),
            "model": model,
            "elapsed_ms": elapsed_ms,
        }
    parsed = parse_json_from_llm_output(result.stdout or "")
    if parsed is None:
        return None, {
            "status": "invalid-json",
            "reason": "claude-cli-returned-non-json",
            "stdout_excerpt": compact_source_text(result.stdout or "", 500),
            "model": model,
            "elapsed_ms": elapsed_ms,
        }
    return parsed, {"status": "ok", "model": model, "elapsed_ms": elapsed_ms}


def normalize_llm_text_list(values: Any, fallback: Any, *, limit: int = 8) -> list[str]:
    result: list[str] = []
    if isinstance(values, list):
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
            if len(result) >= limit:
                break
    return result or normalize_string_list(fallback)[:limit]


def normalize_llm_mapping(value: Any, fallback: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(fallback, dict):
        return fallback
    return {}


def normalize_llm_teaching_points(values: Any, fallback: Any) -> list[dict[str, Any]]:
    fallback_points = [item for item in (fallback or []) if isinstance(item, dict)]
    if not isinstance(values, list):
        return fallback_points
    normalized: list[dict[str, Any]] = []
    required_keys = ["topic", "background", "core_question", "explanation", "practical_value", "pitfall", "study_prompt", "source_status"]
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback_points[index] if index < len(fallback_points) else {}
        topic = str(item.get("topic") or fallback_item.get("topic") or "").strip()
        if not topic:
            continue
        point: dict[str, Any] = {}
        for key in required_keys:
            default = "llm-grounded" if key == "source_status" else ""
            point[key] = str(item.get(key) or fallback_item.get(key) or default).strip()
        point["topic"] = topic
        normalized.append(point)
        if len(normalized) >= 8:
            break
    return normalized or fallback_points


def normalize_llm_daily_lesson_payload(candidate: Any, fallback_plan: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    string_fields = [
        "title", "current_stage", "study_mode", "positioning", "why_today", "coach_explanation", "lesson_intro",
    ]
    list_fields = [
        "content_summary", "reading_guidance", "lesson_summary", "exercise_plan", "practice_bridge", "completion_criteria", "feedback_request",
    ]
    normalized = json.loads(json.dumps(fallback_plan))
    for field in string_fields:
        value = str(candidate.get(field) or "").strip()
        if value:
            normalized[field] = value
    for field in list_fields:
        normalized[field] = normalize_llm_text_list(candidate.get(field), fallback_plan.get(field), limit=8)
    normalized["goal_focus"] = normalize_llm_mapping(candidate.get("goal_focus"), fallback_plan.get("goal_focus"))
    normalized["preference_focus"] = normalize_llm_mapping(candidate.get("preference_focus"), fallback_plan.get("preference_focus"))
    normalized["material_alignment"] = normalize_llm_mapping(candidate.get("material_alignment"), fallback_plan.get("material_alignment"))
    normalized["specific_tasks"] = candidate.get("specific_tasks") if isinstance(candidate.get("specific_tasks"), list) and candidate.get("specific_tasks") else fallback_plan.get("specific_tasks") or []
    normalized["teaching_points"] = normalize_llm_teaching_points(candidate.get("teaching_points"), fallback_plan.get("teaching_points"))
    normalized["time_budget_today"] = candidate.get("time_budget_today") or fallback_plan.get("time_budget_today")
    normalized["plan_execution_mode"] = fallback_plan.get("plan_execution_mode")
    normalized["plan_blockers"] = fallback_plan.get("plan_blockers") or []
    normalized["lesson_generation_mode"] = "llm-grounded"
    normalized["source_trace"] = candidate.get("source_trace") or {"basis": "grounding_context+fallback_plan"}
    return normalized


def build_daily_lesson_prompt(grounding_context: dict[str, Any], fallback_plan: dict[str, Any]) -> str:
    return f"""你是一个中文学习教练。请基于给定的 grounding_context 和 fallback_plan 生成当天教学计划。

硬性要求：
1. 只输出一个 JSON object，不要 Markdown，不要解释 JSON 外的文字。
2. 教学计划必须严格围绕 grounding_context 的 topic、review、new_learning、selected_segments、source_excerpt；不要加入无关主题。
3. 如果 topic/domain 是 Git，只能围绕 Git 的快照、commit、暂存区、git add、git status、branch/remote 等上下文中出现的内容；不得混入 HTTP、JSON、日志、测试、部署等无关题材。
4. 面向零基础学习者，先讲清心智模型，再衔接练习。
5. 保持 10 分钟左右的短 session 风格。

必须返回这些字段：
title, current_stage, study_mode, positioning, why_today, coach_explanation, goal_focus, preference_focus, time_budget_today, lesson_intro, content_summary, specific_tasks, teaching_points, reading_guidance, lesson_summary, exercise_plan, practice_bridge, completion_criteria, feedback_request, material_alignment, source_trace。

teaching_points 是对象数组，每个对象必须包含：topic, background, core_question, explanation, practical_value, pitfall, study_prompt, source_status。

GROUNDING_CONTEXT:
{json_for_prompt(grounding_context, limit=14000)}

FALLBACK_PLAN:
{json_for_prompt(fallback_plan, limit=7000)}
"""


def generate_daily_lesson_with_llm(grounding_context: dict[str, Any], fallback_plan: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    prompt = build_daily_lesson_prompt(grounding_context, fallback_plan)
    raw_payload, metadata = run_claude_json_generation(prompt)
    normalized = normalize_llm_daily_lesson_payload(raw_payload, fallback_plan)
    if normalized is None:
        return None, metadata
    metadata = {**metadata, "mode": "llm-grounded", "generator": "runtime-lesson-llm"}
    normalized["generation_trace"] = metadata
    return normalized, metadata



def build_lesson_quality_artifact(plan: dict[str, Any], generation_trace: dict[str, Any] | None = None) -> dict[str, Any]:
    lesson_plan = dict(plan) if isinstance(plan, dict) else {}
    teaching_points = [item for item in lesson_plan.get("teaching_points") or [] if isinstance(item, dict)]
    evidence = normalize_string_list(
        [
            *(lesson_plan.get("content_summary") or []),
            *(lesson_plan.get("completion_criteria") or []),
            *(lesson_plan.get("feedback_request") or []),
            *[
                item.get("topic")
                for item in teaching_points
                if str(item.get("topic") or "").strip()
            ],
        ]
    )[:20]
    quality_issues: list[str] = []
    if not teaching_points:
        quality_issues.append("lesson.teaching_points_missing")
    if not evidence:
        quality_issues.append("lesson.evidence_missing")
    if not normalize_string_list(lesson_plan.get("practice_bridge") or []):
        quality_issues.append("lesson.practice_bridge_missing")
    if not normalize_string_list(lesson_plan.get("reading_guidance") or []):
        quality_issues.append("lesson.reading_guidance_missing")
    if not normalize_string_list(lesson_plan.get("completion_criteria") or []):
        quality_issues.append("lesson.completion_criteria_missing")

    traceability_entries: list[dict[str, Any]] = []
    for segment in lesson_plan.get("specific_tasks") or []:
        if not isinstance(segment, dict):
            continue
        ref = str(segment.get("segment_id") or segment.get("material_title") or segment.get("label") or "").strip()
        if not ref:
            continue
        locator_bits = [
            str(value).strip()
            for value in [
                (segment.get("chapter") if isinstance(segment, dict) else None),
                (segment.get("pages") if isinstance(segment, dict) else None),
            ]
            if str(value or "").strip()
        ]
        traceability_entries.append(
            build_traceability_entry(
                kind="material-segment",
                ref=ref,
                title=segment.get("material_title") or segment.get("label") or ref,
                detail=segment.get("purpose") or segment.get("match_reason"),
                stage="lesson",
                status=segment.get("source_status") or lesson_plan.get("lesson_generation_mode") or "ready",
                locator=" / ".join(locator_bits) if locator_bits else None,
            )
        )
    if not traceability_entries:
        traceability_entries.append(
            build_traceability_entry(
                kind="lesson-plan",
                ref=str(lesson_plan.get("title") or lesson_plan.get("current_stage") or "lesson").strip() or "lesson",
                title=lesson_plan.get("title") or lesson_plan.get("current_stage") or "lesson",
                detail=lesson_plan.get("why_today") or lesson_plan.get("positioning"),
                stage="lesson",
                status=lesson_plan.get("lesson_generation_mode") or "fallback",
            )
        )

    generation = generation_trace if isinstance(generation_trace, dict) else lesson_plan.get("generation_trace")
    resolved_confidence = normalize_confidence((generation or {}).get("confidence"), default=0.0)
    if resolved_confidence <= 0:
        resolved_confidence = 0.75 if not quality_issues else 0.45

    return apply_quality_envelope(
        lesson_plan,
        stage="lesson",
        generator="runtime-lesson-builder",
        evidence=evidence,
        confidence=resolved_confidence,
        quality_review={
            "reviewer": "runtime-lesson-quality-gate",
            "valid": not quality_issues,
            "issues": quality_issues,
            "warnings": [],
            "confidence": resolved_confidence,
            "evidence_adequacy": "sufficient" if not quality_issues else "partial",
            "verdict": "ready" if not quality_issues else "needs-revision",
        },
        generation_trace=generation,
        traceability=traceability_entries,
    )


def build_grounded_daily_lesson_plan(topic: str, plan_source: dict[str, Any], selected_segments: list[dict[str, Any]], mastery_targets: dict[str, list[str]], grounding_context: dict[str, Any]) -> dict[str, Any]:
    fallback_plan = build_daily_lesson_plan(topic, plan_source, selected_segments, mastery_targets)
    llm_plan, metadata = generate_daily_lesson_with_llm(grounding_context, fallback_plan)
    if llm_plan:
        return build_lesson_quality_artifact(llm_plan, metadata)
    fallback_plan["generation_trace"] = metadata
    return build_lesson_quality_artifact(fallback_plan, metadata)


def build_lesson_grounding_context(topic: str, plan_source: dict[str, Any], selected_segments: list[dict[str, Any]], mastery_targets: dict[str, list[str]]) -> dict[str, Any]:
    checkin = plan_source.get("today_progress_checkin") if isinstance(plan_source.get("today_progress_checkin"), dict) else {}
    return {
        "topic": topic,
        "current_stage": plan_source.get("current_stage"),
        "current_day": plan_source.get("day"),
        "today_topic": plan_source.get("today_topic"),
        "review": normalize_string_list(plan_source.get("review") or []),
        "new_learning": normalize_string_list(plan_source.get("new_learning") or []),
        "exercise_focus": normalize_string_list(plan_source.get("exercise_focus") or []),
        "weak_points": normalize_string_list(plan_source.get("progress_review_debt") or plan_source.get("weakness_focus") or []),
        "time_budget_today": plan_source.get("time_budget_today") or checkin.get("time_budget_today"),
        "plan_execution_mode": plan_source.get("plan_execution_mode") or "normal",
        "plan_blockers": normalize_string_list(plan_source.get("plan_blockers") or []),
        "material_alignment": plan_source.get("material_alignment") or {},
        "selected_segments": [
            {
                "segment_id": segment.get("segment_id"),
                "label": segment.get("label"),
                "material_title": segment.get("material_title"),
                "source_status": segment.get("source_status"),
                "source_summary": segment.get("source_summary"),
                "source_key_points": segment.get("source_key_points") or [],
                "source_examples": segment.get("source_examples") or [],
                "source_pitfalls": segment.get("source_pitfalls") or [],
                "source_excerpt": compact_source_text(segment.get("source_excerpt") or "", 700),
                "locator": segment.get("locator") if isinstance(segment.get("locator"), dict) else {},
            }
            for segment in selected_segments
            if isinstance(segment, dict)
        ],
        "mastery_targets": mastery_targets,
        "generation_mode": "grounded-local-context",
        "llm_available": bool(shutil.which("claude")) and not llm_generation_disabled(),
    }


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
    content_summaries: list[str] = []
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
                "material_source_type": segment.get("material_source_type"),
                "material_local_path": segment.get("material_local_path"),
                "material_kind": segment.get("material_kind"),
                "material_teaching_style": segment.get("material_teaching_style"),
                "target_clusters": segment.get("target_clusters") or [],
                "match_reason": segment.get("match_reason"),
                "source_status": segment.get("source_status") or "fallback-metadata",
                "source_summary": segment.get("source_summary") or "",
                "source_excerpt": segment.get("source_excerpt") or "",
                "source_examples": segment.get("source_examples") or [],
                "source_pitfalls": segment.get("source_pitfalls") or [],
                "source_key_points": segment.get("source_key_points") or [],
                "source_path": segment.get("source_path"),
                "source_kind": segment.get("source_kind"),
            }
        )
        segment_key_points = clean_source_teaching_terms(normalize_string_list(segment.get("source_key_points") or []))
        if segment.get("source_summary"):
            summary_terms = clean_source_teaching_terms(split_semicolon_values(segment.get("source_summary")))
            content_summaries.append("；".join(summary_terms) or str(segment.get("source_summary")))
        for item in (segment_key_points or clean_source_teaching_terms(normalize_string_list(sections)) or clean_source_teaching_terms(normalize_string_list(checkpoints)))[:6]:
            topic_name = str(item).strip()
            if not topic_name or topic_name in covered_topics:
                continue
            covered_topics.add(topic_name)
            source_status = str(segment.get("source_status") or "fallback-metadata")
            source_excerpt = str(segment.get("source_excerpt") or "").strip()
            if source_status == "extracted":
                background = f"今天先不要求你通读原资料；我先根据 {segment.get('material_title') or segment.get('label') or topic} 里和 {topic_name} 直接相关的例子，讲清楚它解决什么问题。"
                explanation = build_content_aware_explanation(topic_name, segment, source_excerpt)
                practical_value = f"资料原文这部分真正想让你掌握的是：{'；'.join(segment_key_points) or segment.get('source_summary') or segment.get('purpose') or topic}。学完后，你应该能把 {topic_name} 的方向、输入输出和边界讲清楚，并在题里用出来。"
                pitfall = build_content_aware_pitfall(topic_name, segment)
                study_prompt = f"如果你对我上面的讲解还有疑惑，再回原资料看 {segment.get('material_title') or '该资料'} 的 {locator.get('chapter') or '对应章节'}，重点盯 {topic_name} 附近的例子和说明。"
            else:
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
                practical_value = f"这段资料强调的是：{segment.get('material_summary') or segment.get('purpose') or topic}。掌握 {topic_name} 后，才能把这一段资料真正转成可用能力。"
                pitfall = f"学习 {topic_name} 时，要避免只记 API 或术语名字，而不理解它在这份资料里为什么重要、和相邻内容怎么配合。"
            teaching_points.append(
                {
                    "topic": topic_name,
                    "background": background,
                    "core_question": f"你需要先回答：{topic_name} 在 {segment.get('material_title') or topic} 这部分内容里，到底解决什么问题，为什么今天先学它？",
                    "explanation": explanation,
                    "practical_value": practical_value,
                    "pitfall": pitfall,
                    "study_prompt": study_prompt,
                    "source_status": source_status,
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
                "study_prompt": f"读资料时重点关注 {item} 的定义、典型使用方式，以及它与旧知识的衔接。",
                "source_status": "fallback-metadata",
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
                "source_status": "fallback-metadata",
            })

    completion_criteria = normalize_string_list(mastery_targets.get("reading_checklist") or [])
    completion_criteria += normalize_string_list(mastery_targets.get("session_exercises") or [])[:2]
    completion_criteria += normalize_string_list(mastery_targets.get("applied_project") or [])[:1]
    completion_criteria += normalize_string_list(mastery_targets.get("reflection") or [])[:1]

    material_alignment = plan_source.get("material_alignment") if isinstance(plan_source.get("material_alignment"), dict) else {}
    if not material_alignment and selected_segments:
        material_alignment = {
            "status": "aligned",
            "target_day_key": normalize_day_key(current_day),
            "selected_segment_ids": [str(item.get("segment_id")) for item in selected_segments if item.get("segment_id")],
            "material_ids": [str(item.get("material_id")) for item in selected_segments if item.get("material_id")],
            "match_reasons": [str(item.get("match_reason")) for item in selected_segments if item.get("match_reason")],
            "selection_mode": "metadata-fallback",
            "source_statuses": [str(item.get("source_status") or "fallback-metadata") for item in selected_segments],
            "fallback_reasons": [],
        }

    mode_description = describe_execution_mode(execution_mode, plan_source.get("mainline_goal") or topic)
    study_mode = "复习+推进" if review and new_learning else ("复习" if review else "推进")
    why_today = "先根据当前阶段、最近复习重点和新学习点安排当天内容，再结合掌握度检验决定是否推进。"
    coach_explanation = f"今天优先服务主线目标：{plan_source.get('mainline_goal') or topic}；在主线之外，只补 1 个支撑能力点，并仅在时间预算允许时触发增强模块。"
    positioning = f"当前处于 {current_stage}，今天围绕 {plan_source.get('today_topic') or topic} 安排学习。"
    practice_bridge = [
        "先消化上面的摘要和讲解，再进入练习页面做对应题目。",
        "做题时优先验证：你是否真的理解了今天这几个概念，而不是只记住名字。",
        "若练习卡住，再回到上面的讲解摘要或原资料定位处复看。",
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
                "source_status": "fallback-metadata",
            })
            completion_criteria = normalize_string_list(plan_blockers)
            completion_criteria += normalize_string_list(exercise_focus)[:2]
            completion_criteria += normalize_string_list(mastery_targets.get("reflection") or [])[:1]

    content_summary = content_summaries[:3] or [str(item.get("practical_value") or "") for item in teaching_points[:2] if item.get("practical_value")]
    lesson_generation_mode = "content-aware" if any(str(item.get("source_status") or "") == "extracted" for item in selected_segments) else "metadata-fallback"
    material_alignment["lesson_generation_mode"] = lesson_generation_mode

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
        "lesson_intro": f"今天这一讲先不要求你把原资料整段读完；我会先把 {', '.join([item.get('topic') for item in teaching_points[:3]]) or topic} 这些关键点讲清楚，再带你回原资料定位。",
        "content_summary": content_summary,
        "lesson_generation_mode": lesson_generation_mode,
        "plan_execution_mode": execution_mode,
        "plan_blockers": plan_blockers,
        "material_alignment": material_alignment,
        "specific_tasks": lesson_lines,
        "teaching_points": teaching_points,
        "reading_guidance": [
            "先看上面的今日摘要和重点讲解，确认自己已经知道今天在学什么、为什么学。",
            "若你对某个点仍模糊，再回原资料看对应 segment 的章节、例子和说明。",
            "阅读原资料时优先核对：我的讲解是否与你看到的定义、例子和边界一致。",
            "最后再进入练习，验证自己是否真的把这些点用出来了。",
        ],
        "lesson_summary": [
            f"今天学完后，你至少要能用自己的话解释：{', '.join(completion_criteria[:4]) or topic}。",
            "如果你只能复述术语，却说不清它为什么重要、怎么用、边界在哪，就还不算真正掌握。",
            "如果你能先讲清楚，再在练习里做出来，这一讲才算完成。",
        ],
        "exercise_plan": exercise_focus,
        "practice_bridge": practice_bridge,
        "completion_criteria": completion_criteria,
        "feedback_request": [
            "学完后请反馈：哪些内容已经能讲清楚，哪些地方还卡。",
            "如完成练习或小项目，请贴代码、结论或运行结果。",
            f"最后运行 {'/learn-test-update' if execution_mode in {'diagnostic', 'test-diagnostic'} else '/learn-today-update'}，回写本次结果。",
        ],
    }


def render_daily_lesson_plan_markdown(plan: dict[str, Any]) -> str:
    material_alignment = plan.get("material_alignment") if isinstance(plan.get("material_alignment"), dict) else {}
    alignment_lines: list[str] = []
    if material_alignment:
        alignment_lines.extend(
            [
                f"- 对齐状态：{material_alignment.get('status') or 'unknown'}",
                f"- 目标 Day：{material_alignment.get('target_day_key') or '未识别'}",
            ]
        )
        if material_alignment.get("selected_segment_ids"):
            alignment_lines.append(f"- 选中 segment：{'；'.join(material_alignment.get('selected_segment_ids') or [])}")
        if material_alignment.get("material_ids"):
            alignment_lines.append(f"- 选中材料：{'；'.join(material_alignment.get('material_ids') or [])}")
        if material_alignment.get("match_reasons"):
            alignment_lines.append(f"- 匹配依据：{'；'.join(material_alignment.get('match_reasons') or [])}")

    task_lines: list[str] = []
    for item in plan.get("specific_tasks") or []:
        sections = "；".join(item.get("sections") or []) or "待补充小节"
        locator_bits = [bit for bit in [item.get("chapter"), item.get("pages")] if bit]
        locator_text = " / ".join(locator_bits) if locator_bits else "待补充定位"
        task_lines.extend(
            [
                f"- {item.get('label')}",
                f"  - 资料来源：{item.get('material_title') or '未命名资料'} / {item.get('material_source_name') or '未知来源'}",
                *( [f"  - 本地路径：{item.get('material_local_path')}"] if item.get('material_local_path') else [] ),
                f"  - segment：{item.get('segment_id') or '未标注'}",
                f"  - 阅读定位：{locator_text}",
                f"  - 重点小节：{sections}",
                *( [f"  - 对齐 cluster：{'；'.join(item.get('target_clusters') or [])}"] if item.get('target_clusters') else [] ),
                *( [f"  - 匹配依据：{item.get('match_reason')}"] if item.get('match_reason') else [] ),
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
        "## 今日摘要",
        "",
        *[f"- {item}" for item in plan.get("content_summary") or []],
        "",
        "## 导入",
        "",
        f"- {plan.get('lesson_intro')}",
        "",
        "## 资料对齐",
        "",
        *(alignment_lines or ["- 未记录明确 material alignment；需优先确认今日资料段落。"]),
        "",
        "## 重点讲解",
        "",
        *(teaching_lines or ["- 暂无可讲解内容，请先补充资料定位。"]),
        "## 回原资料看哪里",
        "",
        *(task_lines or ["- 暂无明确资料段落，需先补充主线资料或确认今日内容"]),
        "",
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


__all__ = [
    "LLM_DISABLE_VALUES",
    "build_daily_lesson_plan",
    "build_daily_lesson_prompt",
    "build_grounded_daily_lesson_plan",
    "build_lesson_grounding_context",
    "build_lesson_quality_artifact",
    "describe_execution_mode",
    "generate_daily_lesson_with_llm",
    "json_for_prompt",
    "llm_generation_disabled",
    "llm_generation_timeout",
    "normalize_llm_daily_lesson_payload",
    "normalize_llm_mapping",
    "normalize_llm_teaching_points",
    "normalize_llm_text_list",
    "parse_json_from_llm_output",
    "render_daily_lesson_plan_markdown",
    "run_claude_json_generation",
]
