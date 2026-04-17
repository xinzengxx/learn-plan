#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from learn_core.io import read_json, read_text_if_exists, write_json, write_text
from learn_core.markdown_sections import upsert_markdown_section
from learn_core.text_utils import normalize_int, normalize_string_list
from learn_feedback import (
    build_session_facts,
    render_feedback_output_lines,
    update_learner_model_file,
    update_patch_queue_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a learn-plan today session and update learn-plan.md")
    parser.add_argument("--session-dir", required=True, help="session 目录，需包含 progress.json")
    parser.add_argument("--plan-path", default="learn-plan.md", help="学习计划文件路径")
    parser.add_argument("--project-path", help="可选 PROJECT.md 路径；仅在需要兼容旧项目记录时使用")
    parser.add_argument("--stdout-json", action="store_true", help="额外输出 JSON 摘要")
    return parser.parse_args()


def summarize_mastery(progress: dict[str, Any]) -> dict[str, Any]:
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    mastery_targets = context.get("mastery_targets") if isinstance(context.get("mastery_targets"), dict) else {}
    if not mastery_targets:
        plan_source_snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
        mastery_targets = plan_source_snapshot.get("mastery_targets") if isinstance(plan_source_snapshot.get("mastery_targets"), dict) else {}
    mastery_checks = progress.get("mastery_checks") if isinstance(progress.get("mastery_checks"), dict) else {}
    reading_progress = progress.get("reading_progress") if isinstance(progress.get("reading_progress"), dict) else {}
    artifacts = progress.get("artifacts") if isinstance(progress.get("artifacts"), list) else []
    reflection = str(progress.get("reflection") or "").strip()
    question_progress = progress.get("questions") if isinstance(progress.get("questions"), dict) else {}
    attempted_evidence = [
        qid for qid, item in question_progress.items()
        if normalize_int(((item or {}).get("stats") or {}).get("attempts")) > 0
    ]
    summary = progress.get("summary") if isinstance(progress.get("summary"), dict) else {}
    attempted_count = normalize_int(summary.get("attempted"))

    target_reading = normalize_string_list(mastery_targets.get("reading_checklist"))
    recorded_reading = normalize_string_list(mastery_checks.get("reading_checklist"))
    if reading_progress and not recorded_reading:
        recorded_reading = normalize_string_list(reading_progress.keys())
    reading_done = bool(target_reading) and len(recorded_reading) >= max(1, min(len(target_reading), 2))

    target_session = normalize_string_list(mastery_targets.get("session_exercises"))
    recorded_session = normalize_string_list(mastery_checks.get("session_exercises"))
    session_done = bool(recorded_session or attempted_evidence or attempted_count > 0)

    target_project = normalize_string_list(mastery_targets.get("applied_project"))
    recorded_project = normalize_string_list(mastery_checks.get("applied_project"))
    project_done = bool(recorded_project or artifacts)

    target_reflection = normalize_string_list(mastery_targets.get("reflection"))
    recorded_reflection = normalize_string_list(mastery_checks.get("reflection"))
    reflection_done = bool(recorded_reflection or reflection)

    return {
        "target_reading": target_reading,
        "recorded_reading": recorded_reading,
        "reading_done": reading_done,
        "target_session": target_session,
        "recorded_session": recorded_session,
        "session_done": session_done,
        "target_project": target_project,
        "recorded_project": recorded_project,
        "project_done": project_done,
        "target_reflection": target_reflection,
        "recorded_reflection": recorded_reflection,
        "reflection_done": reflection_done,
        "reflection_text": reflection,
        "artifacts": artifacts,
    }



def extract_question_clusters(question: dict[str, Any]) -> list[str]:
    clusters: list[str] = []
    for value in [question.get("cluster"), *(question.get("tags") or []), *(question.get("subskills") or [])]:
        text = str(value or "").strip()
        if text and text not in clusters:
            clusters.append(text)
    return clusters



def summarize_material_alignment(progress: dict[str, Any], questions_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    selected_segments = context.get("selected_segments") if isinstance(context.get("selected_segments"), list) else []
    existing_alignment = progress.get("material_alignment") if isinstance(progress.get("material_alignment"), dict) else {}
    lesson_generation_mode = context.get("lesson_generation_mode") or existing_alignment.get("lesson_generation_mode")
    question_generation_mode = context.get("question_generation_mode") or existing_alignment.get("question_generation_mode")
    if not selected_segments and not existing_alignment:
        return {
            "status": "legacy-no-segment-alignment",
            "selected_segments": [],
            "covered_segments": [],
            "missing_segments": [],
            "generic_completion": normalize_int((progress.get("summary") or {}).get("attempted")) > 0,
            "exact_mastery": False,
            "lesson_generation_mode": lesson_generation_mode,
            "question_generation_mode": question_generation_mode,
            "selection_mode": None,
            "source_statuses": [],
            "evidence": ["旧 session 未记录 selected_segments / material_alignment，按兼容逻辑处理"],
        }

    attempted_question_ids: list[str] = []
    covered_question_clusters: set[str] = set()
    for qid, item in (progress.get("questions") or {}).items():
        stats = item.get("stats") or {}
        if normalize_int(stats.get("attempts")) <= 0:
            continue
        attempted_question_ids.append(str(qid))
        for cluster in extract_question_clusters(questions_map.get(qid) or {}):
            covered_question_clusters.add(cluster)

    selected_ids: list[str] = []
    covered_segments: list[str] = []
    missing_segments: list[str] = []
    evidence: list[str] = []
    reading_progress = progress.get("reading_progress") if isinstance(progress.get("reading_progress"), dict) else {}
    mastery_checks = progress.get("mastery_checks") if isinstance(progress.get("mastery_checks"), dict) else {}
    recorded_reading_blob = " ".join(normalize_string_list(mastery_checks.get("reading_checklist")) + normalize_string_list(reading_progress.keys()))
    source_statuses: list[str] = []

    for segment in selected_segments:
        if not isinstance(segment, dict):
            continue
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id:
            continue
        selected_ids.append(segment_id)
        source_status = str(segment.get("source_status") or "fallback-metadata")
        if source_status not in source_statuses:
            source_statuses.append(source_status)
        target_clusters = normalize_string_list(segment.get("target_clusters"))
        cluster_hit = any(cluster in covered_question_clusters for cluster in target_clusters)
        reading_hit = segment_id in recorded_reading_blob
        if cluster_hit or reading_hit:
            covered_segments.append(segment_id)
            if cluster_hit:
                evidence.append(f"{segment_id}: 已完成匹配 cluster 的题目")
            if reading_hit:
                evidence.append(f"{segment_id}: 已记录阅读/掌握清单证据")
        else:
            missing_segments.append(segment_id)

    generic_completion = bool(attempted_question_ids)
    exact_mastery = bool(selected_ids) and not missing_segments and generic_completion
    if not selected_ids:
        status = "generic-practice-only" if generic_completion else "no-segment-target"
    elif exact_mastery:
        status = "exact-source-aligned" if lesson_generation_mode == "content-aware" else "exact-segment-covered"
    elif covered_segments:
        status = "same-segment-metadata-only" if lesson_generation_mode != "content-aware" else "partial-source-alignment"
    elif generic_completion:
        status = "generic-adjacent-practice"
    else:
        status = "no-evidence"

    if generic_completion and not covered_segments:
        evidence.append("已有答题记录，但未覆盖 selected_segments 对应 cluster / 阅读证据")
    if not generic_completion:
        evidence.append("未发现已尝试题目的记录")

    return {
        "status": status,
        "selected_segments": selected_ids,
        "covered_segments": covered_segments,
        "missing_segments": missing_segments,
        "generic_completion": generic_completion,
        "exact_mastery": exact_mastery,
        "lesson_generation_mode": lesson_generation_mode,
        "question_generation_mode": question_generation_mode,
        "selection_mode": existing_alignment.get("selection_mode"),
        "source_statuses": source_statuses or normalize_string_list(existing_alignment.get("source_statuses") or []),
        "evidence": normalize_string_list(evidence),
    }



def update_diagnostic_state(progress: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(progress))
    context = updated.get("context") if isinstance(updated.get("context"), dict) else {}
    user_model = context.get("user_model") if isinstance(context.get("user_model"), dict) else {}
    planning_state = context.get("planning_state") if isinstance(context.get("planning_state"), dict) else {}
    diagnostic_profile = summary.get("diagnostic_profile") or {}
    user_model["strengths"] = normalize_string_list(diagnostic_profile.get("observed_strengths"))
    user_model["weaknesses"] = normalize_string_list(diagnostic_profile.get("observed_weaknesses"))
    planning_state["diagnostic_status"] = diagnostic_profile.get("status") or "validated"
    planning_state["assessment_depth"] = diagnostic_profile.get("assessment_depth")
    planning_state["diagnostic_round_index"] = diagnostic_profile.get("round_index")
    planning_state["diagnostic_max_rounds"] = diagnostic_profile.get("max_rounds")
    planning_state["diagnostic_follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    context["user_model"] = user_model
    context["planning_state"] = planning_state
    context["diagnostic_profile"] = diagnostic_profile
    context["assessment_depth"] = diagnostic_profile.get("assessment_depth")
    context["round_index"] = diagnostic_profile.get("round_index")
    context["max_rounds"] = diagnostic_profile.get("max_rounds")
    context["follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    context["stop_reason"] = diagnostic_profile.get("stop_reason")
    snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
    snapshot["diagnostic_profile"] = diagnostic_profile
    snapshot["assessment_depth"] = diagnostic_profile.get("assessment_depth")
    snapshot["round_index"] = diagnostic_profile.get("round_index")
    snapshot["max_rounds"] = diagnostic_profile.get("max_rounds")
    snapshot["follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    snapshot["stop_reason"] = diagnostic_profile.get("stop_reason")
    context["plan_source_snapshot"] = snapshot
    updated["context"] = context
    session = updated.get("session") if isinstance(updated.get("session"), dict) else {}
    session["status"] = "finished"
    session["finished_at"] = summary.get("date")
    session["assessment_depth"] = diagnostic_profile.get("assessment_depth")
    session["round_index"] = diagnostic_profile.get("round_index")
    session["max_rounds"] = diagnostic_profile.get("max_rounds")
    session["follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    session["stop_reason"] = diagnostic_profile.get("stop_reason")
    updated["session"] = session
    updated["assessment_depth"] = diagnostic_profile.get("assessment_depth")
    updated["round_index"] = diagnostic_profile.get("round_index")
    updated["max_rounds"] = diagnostic_profile.get("max_rounds")
    updated["follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    updated["stop_reason"] = diagnostic_profile.get("stop_reason")
    updated["result_summary"] = {
        "attempted": summary.get("attempted", 0),
        "overall": summary.get("overall"),
        "recommended_entry_level": summary.get("recommended_entry_level"),
        "diagnostic_profile": diagnostic_profile,
    }
    history = updated.get("update_history") if isinstance(updated.get("update_history"), list) else []
    history.append({
        "update_type": "diagnostic",
        "updated_at": summary.get("date"),
        "summary": {
            "overall": summary.get("overall"),
            "recommended_entry_level": summary.get("recommended_entry_level"),
            "diagnostic_profile": diagnostic_profile,
        },
    })
    updated["update_history"] = history[-20:]
    return updated



def update_progress_state(progress: dict[str, Any], summary: dict[str, Any], *, session_dir: Path) -> dict[str, Any]:
    updated = json.loads(json.dumps(progress))
    context = updated.get("context") if isinstance(updated.get("context"), dict) else {}
    learning_state = updated.get("learning_state") if isinstance(updated.get("learning_state"), dict) else {}
    progression = updated.get("progression") if isinstance(updated.get("progression"), dict) else {}
    update_history = updated.get("update_history") if isinstance(updated.get("update_history"), list) else []
    session = updated.get("session") if isinstance(updated.get("session"), dict) else {}
    mastery = summary.get("mastery") or {}
    material_alignment = summary.get("material_alignment") if isinstance(summary.get("material_alignment"), dict) else {}

    review_focus = normalize_string_list(summary.get("review_focus"))
    next_learning = normalize_string_list(summary.get("next_learning"))
    weaknesses = normalize_string_list(summary.get("high_freq_errors"))
    strengths = normalize_string_list(item.get("title") for item in summary.get("solved_items") or [])
    attempted = normalize_int(summary.get("attempted"))
    finished_at = summary.get("finished_at") or summary.get("date")
    active_cluster = str(context.get("topic_cluster") or context.get("current_day") or context.get("current_stage") or summary.get("topic") or "").strip()

    needs_more_review = bool(weaknesses or not mastery.get("reading_done") or not mastery.get("reflection_done"))
    can_advance = bool(attempted > 0 and not weaknesses and mastery.get("reading_done") and mastery.get("reflection_done"))

    learning_state.update(
        {
            "overall": summary.get("overall") or "未开始",
            "review_focus": review_focus,
            "next_learning": next_learning,
            "weaknesses": weaknesses,
            "strengths": strengths,
            "should_review": needs_more_review,
            "can_advance": can_advance,
            "advancement_target": next_learning[0] if next_learning and can_advance else None,
            "next_actions": next_learning or review_focus,
        }
    )

    progression.update(
        {
            "stage_status": "planned" if attempted <= 0 else ("blocked_by_review" if needs_more_review else "ready_to_advance"),
            "day_status": "planned" if attempted <= 0 else ("completed_with_gaps" if needs_more_review else "completed"),
            "review_debt": review_focus,
            "mastered_clusters": normalize_string_list(list(progression.get("mastered_clusters") or []) + strengths),
            "active_clusters": normalize_string_list(([active_cluster] if active_cluster else []) + list(progression.get("active_clusters") or [])),
            "deferred_clusters": normalize_string_list(list(progression.get("deferred_clusters") or []) + weaknesses),
            "updated_at": summary.get("finished_at") or summary.get("date"),
        }
    )

    updated["mastery_checks"] = {
        "reading_checklist": mastery.get("recorded_reading") or [],
        "session_exercises": mastery.get("recorded_session") or [],
        "applied_project": mastery.get("recorded_project") or [],
        "reflection": mastery.get("recorded_reflection") or ([mastery.get("reflection_text")] if mastery.get("reflection_text") else []),
    }
    updated["artifacts"] = mastery.get("artifacts") or []
    updated["reflection"] = mastery.get("reflection_text") or updated.get("reflection")
    updated["material_alignment"] = material_alignment or updated.get("material_alignment") or {}
    context["material_alignment"] = updated["material_alignment"]
    updated["context"] = context

    update_history.append(
        {
            "update_type": "today",
            "updated_at": summary.get("finished_at") or summary.get("date"),
            "summary": {
                "overall": summary.get("overall"),
                "review_focus": review_focus,
                "next_learning": next_learning,
                "high_freq_errors": weaknesses,
                "mainline_progress": summary.get("mainline_progress"),
                "supporting_gap": summary.get("supporting_gap") or [],
                "defer_enhancement": summary.get("defer_enhancement") or [],
                "mastery": {
                    "reading_done": mastery.get("reading_done"),
                    "session_done": mastery.get("session_done"),
                    "project_done": mastery.get("project_done"),
                    "reflection_done": mastery.get("reflection_done"),
                },
                "material_alignment": material_alignment,
                "pending_review_count": summary.get("pending_review_count", 0),
                "pending_review_items": summary.get("pending_review_items") or [],
            },
        }
    )

    session["status"] = "finished"
    session["finished_at"] = finished_at
    updated["session"] = session
    updated["learning_state"] = learning_state
    updated["progression"] = progression
    updated["update_history"] = update_history[-20:]
    return updated


def load_questions_map(session_dir: Path) -> dict[str, dict[str, Any]]:
    questions_path = session_dir / "questions.json"
    if not questions_path.exists():
        raise FileNotFoundError(f"未找到 questions.json: {questions_path}")
    data = read_json(questions_path)
    items = data.get("questions") or []
    return {item.get("id"): item for item in items if item.get("id")}


def summarize_diagnostic_progress(progress: dict[str, Any], questions_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    topic = progress.get("topic") or "未命名主题"
    question_progress = progress.get("questions") or {}
    session = progress.get("session") or {}
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
    existing_profile = context.get("diagnostic_profile") if isinstance(context.get("diagnostic_profile"), dict) else {}
    existing_planning_state = context.get("planning_state") if isinstance(context.get("planning_state"), dict) else {}

    assessment_depth = (
        session.get("assessment_depth")
        or progress.get("assessment_depth")
        or context.get("assessment_depth")
        or snapshot.get("assessment_depth")
        or existing_planning_state.get("assessment_depth")
        or existing_profile.get("assessment_depth")
    )
    round_index = (
        session.get("round_index")
        or progress.get("round_index")
        or context.get("round_index")
        or snapshot.get("round_index")
        or existing_planning_state.get("diagnostic_round_index")
        or existing_profile.get("round_index")
        or 1
    )
    max_rounds = (
        session.get("max_rounds")
        or progress.get("max_rounds")
        or context.get("max_rounds")
        or snapshot.get("max_rounds")
        or existing_planning_state.get("diagnostic_max_rounds")
        or existing_profile.get("max_rounds")
        or round_index
    )
    follow_up_needed = progress.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = context.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = snapshot.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = existing_planning_state.get("diagnostic_follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = existing_profile.get("follow_up_needed")
    stop_reason = (
        progress.get("stop_reason")
        or context.get("stop_reason")
        or snapshot.get("stop_reason")
        or existing_profile.get("stop_reason")
    )

    strengths: list[str] = []
    weaknesses: list[str] = []
    evidence: list[str] = []
    pending_review_items: list[str] = []
    attempted = 0
    scorable_attempted = 0

    for qid, item in question_progress.items():
        stats = item.get("stats") or {}
        question = questions_map.get(qid) or {}
        title = question.get("title") or question.get("question") or qid
        attempts = normalize_int(stats.get("attempts"))
        if attempts <= 0:
            continue
        attempted += 1
        if question.get("category") == "open":
            pending_review_items.append(title)
            evidence.append(f"开放题《{title}》已提交，待评阅后补充诊断结论")
            continue
        scorable_attempted += 1
        success_count = normalize_int(stats.get("pass_count")) if question.get("category") == "code" else normalize_int(stats.get("correct_count"))
        if success_count > 0:
            strengths.append(title)
            evidence.append(f"题目《{title}》完成良好")
        else:
            weaknesses.append(title)
            evidence.append(f"题目《{title}》暴露当前薄弱点")

    current_stage = context.get("current_stage") or snapshot.get("current_stage")
    if not attempted:
        overall = "未完成诊断"
        recommended_entry_level = existing_profile.get("recommended_entry_level") or current_stage or "待诊断后判断"
    elif weaknesses:
        overall = "已形成起点判断，存在需优先补齐的基础薄弱点"
        recommended_entry_level = existing_profile.get("recommended_entry_level") or "阶段 1"
    elif scorable_attempted > 0 and pending_review_items:
        overall = "已形成初步起点判断，但仍有开放题待评阅"
        recommended_entry_level = existing_profile.get("recommended_entry_level") or current_stage or "当前阶段"
    elif scorable_attempted > 0:
        overall = "诊断结果显示可从当前阶段继续推进"
        recommended_entry_level = existing_profile.get("recommended_entry_level") or current_stage or "当前阶段"
    else:
        overall = "已收集开放题回答，待评阅后确认起点"
        recommended_entry_level = existing_profile.get("recommended_entry_level") or "待评阅后判断"

    if follow_up_needed is None:
        if pending_review_items and scorable_attempted <= 0:
            follow_up_needed = True
        elif assessment_depth == "deep" and attempted > 0:
            follow_up_needed = bool(weaknesses and normalize_int(round_index) < normalize_int(max_rounds))
    if not stop_reason:
        if pending_review_items and scorable_attempted <= 0:
            stop_reason = "pending-review"
        elif assessment_depth == "deep":
            if follow_up_needed:
                stop_reason = "undetermined"
            elif attempted > 0:
                stop_reason = "enough-evidence"

    status = "validated" if attempted > 0 and not follow_up_needed and (scorable_attempted > 0 or not pending_review_items) else "in-progress"

    return {
        "topic": topic,
        "date": progress.get("date") or "",
        "session_type": session.get("type") or "today",
        "status": session.get("status") or "active",
        "attempted": attempted,
        "overall": overall,
        "recommended_entry_level": recommended_entry_level,
        "diagnostic_profile": {
            "status": status,
            "assessment_depth": assessment_depth,
            "round_index": round_index,
            "max_rounds": max_rounds,
            "follow_up_needed": follow_up_needed,
            "stop_reason": stop_reason,
            "baseline_level": current_stage or topic,
            "dimensions": [q.get("question") or q.get("title") or qid for qid, q in questions_map.items()],
            "observed_strengths": normalize_string_list(strengths),
            "observed_weaknesses": normalize_string_list(weaknesses),
            "pending_review_count": len(pending_review_items),
            "pending_review_items": normalize_string_list(pending_review_items),
            "evidence": normalize_string_list(evidence),
            "recommended_entry_level": recommended_entry_level,
            "confidence": 0.8 if attempted > 0 and scorable_attempted > 0 else 0.3,
        },
    }



def summarize_progress(progress: dict[str, Any], questions_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    topic = progress.get("topic") or "未命名主题"
    session = progress.get("session") or {}
    summary = progress.get("summary") or {}
    result_summary = progress.get("result_summary") or {}
    question_progress = progress.get("questions") or {}
    mastery = summarize_mastery(progress)
    material_alignment = summarize_material_alignment(progress, questions_map)
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    goal_focus = context.get("goal_focus") if isinstance(context.get("goal_focus"), dict) else {}
    progression = progress.get("progression") if isinstance(progress.get("progression"), dict) else {}

    total = normalize_int(result_summary.get("total") if result_summary else None) or normalize_int(summary.get("total"))
    attempted = normalize_int(result_summary.get("attempted") if result_summary else None) or normalize_int(summary.get("attempted"))
    correct = normalize_int(result_summary.get("correct") if result_summary else None) or normalize_int(summary.get("correct"))

    wrong_items: list[dict[str, Any]] = []
    solved_items: list[dict[str, Any]] = []

    for qid, item in question_progress.items():
        stats = item.get("stats") or {}
        question = questions_map.get(qid) or {}
        title = question.get("title") or question.get("question") or qid
        attempts = normalize_int(stats.get("attempts"))
        last_status = stats.get("last_status")
        correct_count = normalize_int(stats.get("correct_count"))
        pass_count = normalize_int(stats.get("pass_count"))
        success_count = pass_count if question.get("category") == "code" else correct_count

        if attempts <= 0:
            continue
        if success_count > 0:
            solved_items.append({
                "id": qid,
                "title": title,
                "attempts": attempts,
                "success_count": success_count,
                "last_status": last_status,
            })
        else:
            wrong_items.append({
                "id": qid,
                "title": title,
                "attempts": attempts,
                "last_status": last_status,
                "category": question.get("category") or "unknown",
                "tags": question.get("tags") or [],
            })

    wrong_items.sort(key=lambda item: (-item["attempts"], item["title"]))
    solved_items.sort(key=lambda item: (-item["success_count"], -item["attempts"], item["title"]))

    high_freq_errors = [item["title"] for item in wrong_items[:3]]
    pending_review_items = [
        (questions_map.get(qid) or {}).get("title") or (questions_map.get(qid) or {}).get("question") or qid
        for qid, item in question_progress.items()
        if normalize_int(((item or {}).get("stats") or {}).get("attempts")) > 0 and (questions_map.get(qid) or {}).get("category") == "open"
    ]
    review_focus = high_freq_errors[:] or [f"复习 {topic} 的基础概念", f"回看 {topic} 的易错题型"]
    if not mastery.get("reading_done"):
        review_focus.append("补齐阅读掌握清单对应内容")
    if not mastery.get("reflection_done"):
        review_focus.append("补做书面/口头复盘，确认是否真正理解")
    if pending_review_items:
        review_focus.append("补看开放题提交内容与评阅结论，避免把待评阅题误当作已掌握")

    next_learning: list[str] = []
    if attempted == 0:
        next_learning = [f"先完成 {topic} 的首轮练习", f"补做至少 3 道概念题和 2 道代码题"]
    elif wrong_items:
        next_learning = [f"先针对 {wrong_items[0]['title']} 做定点复习", f"在 {topic} 中加入 1 组同类新题巩固"]
    else:
        next_learning = [f"进入 {topic} 的下一批新题", f"把训练重心从基础正确率转向速度和稳定性"]
    if not mastery.get("project_done"):
        next_learning.append("补 1 个小项目/实作，验证知识能否迁移应用")

    overall = "未开始"
    if attempted > 0:
        accuracy = correct / attempted if attempted else 0
        if accuracy >= 0.85 and mastery.get("reading_done") and mastery.get("reflection_done"):
            overall = "表现较稳"
        elif accuracy >= 0.6:
            overall = "表现中等"
        else:
            overall = "基础仍需巩固"
        if accuracy >= 0.85 and not mastery.get("project_done"):
            overall = "练习表现较稳，但应用验证不足"
        if accuracy >= 0.85 and not mastery.get("reading_done"):
            overall = "练习表现尚可，但阅读理解未稳固"

    return {
        "topic": topic,
        "date": progress.get("date") or "",
        "session_type": session.get("type") or "today",
        "test_mode": session.get("test_mode"),
        "status": session.get("status") or "active",
        "started_at": session.get("started_at"),
        "finished_at": session.get("finished_at"),
        "total": total,
        "attempted": attempted,
        "correct": correct,
        "pending_review_count": len(pending_review_items),
        "pending_review_items": normalize_string_list(pending_review_items),
        "overall": overall,
        "high_freq_errors": high_freq_errors,
        "review_focus": normalize_string_list(review_focus),
        "next_learning": normalize_string_list(next_learning),
        "wrong_items": wrong_items,
        "solved_items": solved_items[:3],
        "mastery": mastery,
        "material_alignment": material_alignment,
        "mainline_progress": goal_focus.get("mainline") or context.get("topic_cluster") or topic,
        "supporting_gap": normalize_string_list(goal_focus.get("supporting"))[:2] if high_freq_errors else [],
        "defer_enhancement": normalize_string_list(goal_focus.get("enhancement"))[:1] if (high_freq_errors or progression.get("review_debt")) else [],
    }


def render_log_entry(summary: dict[str, Any], session_dir: Path) -> str:
    weak_text = "；".join(summary["high_freq_errors"]) if summary["high_freq_errors"] else "暂无明显高频错误"
    review_text = "；".join(summary["review_focus"])
    next_text = "；".join(summary["next_learning"])
    mastery = summary.get("mastery") or {}
    material_alignment = summary.get("material_alignment") if isinstance(summary.get("material_alignment"), dict) else {}
    material_text = material_alignment.get("status") or "未记录"
    if material_alignment.get("selected_segments"):
        material_text += f"（覆盖 {len(material_alignment.get('covered_segments') or [])}/{len(material_alignment.get('selected_segments') or [])} 个 segment）"
    return "\n".join(
        [
            f"### {summary['date']} / {summary['topic']} / 今日学习更新",
            f"- session 目录：`{session_dir}`",
            f"- 总题数：{summary['total']}",
            f"- 已练习题数：{summary['attempted']}",
            f"- 正确/通过题数：{summary['correct']}",
            f"- 总体表现：{summary['overall']}",
            f"- 高频错误点：{weak_text}",
            f"- 材料 segment 覆盖：{material_text}",
            f"- 阅读掌握清单：{'已达标' if mastery.get('reading_done') else '未达标'}",
            f"- session 练习/测试：{'已完成' if mastery.get('session_done') else '未完成'}",
            f"- 小项目/实作：{'已完成' if mastery.get('project_done') else '未完成'}",
            f"- 口头/书面复盘：{'已完成' if mastery.get('reflection_done') else '未完成'}",
            f"- 下次复习重点：{review_text}",
            f"- 下次新学习建议：{next_text}",
        ]
    )


def upsert_section(text: str, heading: str, block: str) -> str:
    return upsert_markdown_section(text, heading, block)


def update_learn_plan_with_diagnostic(plan_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(plan_path)
    diagnostic = summary.get("diagnostic_profile") or {}
    block = "\n".join([
        f"### {summary['date']} / {summary['topic']} / 前置诊断更新",
        f"- session 目录：`{session_dir}`",
        f"- 总体判断：{summary.get('overall')}",
        f"- 推荐起步层级：{summary.get('recommended_entry_level')}",
        *( [f"- 测评深度：{diagnostic.get('assessment_depth')}"] if diagnostic.get("assessment_depth") else [] ),
        *( [f"- 诊断轮次：{diagnostic.get('round_index')} / {diagnostic.get('max_rounds')}"] if diagnostic.get("round_index") else [] ),
        *( [f"- 是否需要追问轮次：{diagnostic.get('follow_up_needed')}"] if diagnostic.get("follow_up_needed") is not None else [] ),
        *( [f"- 结束原因：{diagnostic.get('stop_reason')}"] if diagnostic.get("stop_reason") else [] ),
        *( [f"- 已观察到的优势：{'；'.join(diagnostic.get('observed_strengths', []))}"] if diagnostic.get("observed_strengths") else [] ),
        *( [f"- 已观察到的薄弱点：{'；'.join(diagnostic.get('observed_weaknesses', []))}"] if diagnostic.get("observed_weaknesses") else [] ),
    ])
    updated = upsert_section(original, "学习记录", block)
    write_text(plan_path, updated)



def update_learn_plan(plan_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(plan_path)
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "学习记录", block)
    write_text(plan_path, updated)


def update_project_log(project_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(project_path)
    if not original and not project_path.exists():
        return
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "Learning Progress Log", block)
    write_text(project_path, updated)


def write_feedback_artifacts(plan_path: Path, summary: dict[str, Any], progress: dict[str, Any], session_dir: Path, *, update_type: str) -> dict[str, Any]:
    session_facts = build_session_facts(progress, summary, session_dir=session_dir, update_type=update_type)
    learner_model = update_learner_model_file(plan_path, summary, session_facts, update_type=update_type)
    patch_queue = update_patch_queue_file(plan_path, summary, session_facts, update_type=update_type)
    return {
        "session_facts": session_facts,
        "learner_model": learner_model,
        "patch_queue": patch_queue,
    }



def print_diagnostic_summary(summary: dict[str, Any], plan_path: Path, *, stdout_json: bool, feedback_result: dict[str, Any] | None = None) -> None:
    diagnostic = summary.get("diagnostic_profile") or {}
    print(f"主题：{summary['topic']}")
    print(f"诊断结论：{summary.get('overall')}")
    print(f"推荐起步层级：{summary.get('recommended_entry_level')}")
    if diagnostic.get("assessment_depth"):
        print(f"测评深度：{diagnostic.get('assessment_depth')}")
    if diagnostic.get("round_index"):
        print(f"诊断轮次：{diagnostic.get('round_index')} / {diagnostic.get('max_rounds')}")
    if diagnostic.get("follow_up_needed") is not None:
        print(f"是否需要追问轮次：{diagnostic.get('follow_up_needed')}")
    if diagnostic.get("stop_reason"):
        print(f"结束原因：{diagnostic.get('stop_reason')}")
    print(f"已观察到的优势：{'；'.join(diagnostic.get('observed_strengths', [])) if diagnostic.get('observed_strengths') else '暂无'}")
    print(f"已观察到的薄弱点：{'；'.join(diagnostic.get('observed_weaknesses', [])) if diagnostic.get('observed_weaknesses') else '暂无明显薄弱点'}")
    print(f"学习计划：{plan_path}")
    if feedback_result:
        for line in render_feedback_output_lines(learner_model_result=feedback_result["learner_model"], patch_result=feedback_result["patch_queue"]):
            print(line)
    if stdout_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))



def print_summary(summary: dict[str, Any], plan_path: Path, project_path: Path | None, *, stdout_json: bool, feedback_result: dict[str, Any] | None = None) -> None:
    print(f"主题：{summary['topic']}")
    print(f"总题数：{summary['total']}")
    print(f"已练习：{summary['attempted']}")
    print(f"正确/通过：{summary['correct']}")
    print(f"高频错误点：{'；'.join(summary['high_freq_errors']) if summary['high_freq_errors'] else '暂无明显高频错误'}")
    material_alignment = summary.get("material_alignment") if isinstance(summary.get("material_alignment"), dict) else {}
    if material_alignment:
        print(f"材料 segment 覆盖：{material_alignment.get('status') or '未记录'}")
    print(f"下次复习重点：{'；'.join(summary['review_focus'])}")
    print(f"下次新学习建议：{'；'.join(summary['next_learning'])}")
    print(f"学习计划：{plan_path}")
    if project_path is not None:
        print(f"PROJECT：{project_path}")
    if feedback_result:
        for line in render_feedback_output_lines(learner_model_result=feedback_result["learner_model"], patch_result=feedback_result["patch_queue"]):
            print(line)
    if stdout_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    session_dir = Path(args.session_dir).expanduser().resolve()
    progress_path = session_dir / "progress.json"
    if not progress_path.exists():
        raise FileNotFoundError(f"未找到 progress.json: {progress_path}")

    plan_path = Path(args.plan_path).expanduser().resolve()
    project_path = Path(args.project_path).expanduser().resolve() if args.project_path else None

    progress = read_json(progress_path)
    questions_map = load_questions_map(session_dir)
    session = progress.get("session") if isinstance(progress.get("session"), dict) else {}
    if (
        session.get("assessment_kind") == "initial-test"
        and session.get("intent") == "assessment"
        and session.get("plan_execution_mode") == "diagnostic"
    ):
        raise ValueError("当前 session 属于 initial-test 起始测试，请改用 learn_test_update.py 处理")
    if (
        session.get("intent") == "plan-diagnostic"
        or session.get("assessment_kind") == "plan-diagnostic"
        or (session.get("plan_execution_mode") == "diagnostic" and session.get("assessment_kind") != "initial-test")
    ):
        summary = summarize_diagnostic_progress(progress, questions_map)
        updated_progress = update_diagnostic_state(progress, summary)
        write_json(progress_path, updated_progress)
        update_learn_plan_with_diagnostic(plan_path, summary, session_dir)
        feedback_result = write_feedback_artifacts(plan_path, summary, updated_progress, session_dir, update_type="diagnostic")
        print_diagnostic_summary(summary, plan_path, stdout_json=args.stdout_json, feedback_result=feedback_result)
        return 0
    summary = summarize_progress(progress, questions_map)
    updated_progress = update_progress_state(progress, summary, session_dir=session_dir)
    write_json(progress_path, updated_progress)
    update_learn_plan(plan_path, summary, session_dir)
    feedback_result = write_feedback_artifacts(plan_path, summary, updated_progress, session_dir, update_type="today")
    if project_path is not None:
        update_project_log(project_path, summary, session_dir)
    print_summary(summary, plan_path, project_path, stdout_json=args.stdout_json, feedback_result=feedback_result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
