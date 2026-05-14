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
    aggregate_diagnostic_targets,
    append_micro_adjustments,
    build_diagnostic_trigger_facts,
    build_result_summary,
    build_session_facts,
    render_feedback_output_lines,
    update_learner_model_file,
    update_patch_queue_file,
)
from learn_feedback.curriculum_patch import pending_patch_items
from learn_knowledge import (
    build_interaction_knowledge_evidence_items,
    build_session_knowledge_evidence_items,
    count_applicable_session_evidence,
    load_knowledge_state,
    save_knowledge_state,
    update_state_from_session_evidence,
)
from learn_feedback.diagnostic_update import (
    extract_question_clusters,
    load_questions_map,
    print_diagnostic_summary,
    summarize_diagnostic_progress,
    update_diagnostic_state,
    update_learn_plan_with_diagnostic,
    write_feedback_artifacts,
)
from learn_workflow import refresh_workflow_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a learn-plan today session and update learn-plan.md")
    parser.add_argument("--session-dir", required=True, help="session 目录，需包含 progress.json")
    parser.add_argument("--plan-path", default="learn-plan.md", help="学习计划文件路径")
    parser.add_argument("--semantic-summary-json", help="由外部 subagent 生成的 today semantic summary JSON 文件路径")
    parser.add_argument("--semantic-diagnostic-json", help="由外部 subagent 生成的 diagnostic semantic JSON 文件路径")
    parser.add_argument("--stdout-json", action="store_true", help="额外输出 JSON 摘要")
    return parser.parse_args()


def completion_signal_received(progress: dict[str, Any]) -> bool:
    signal = progress.get("completion_signal") if isinstance(progress.get("completion_signal"), dict) else {}
    return signal.get("status") in {"received", "completed", "skipped_by_user"}


def reflection_gate_completed(progress: dict[str, Any]) -> bool:
    signal = progress.get("completion_signal") if isinstance(progress.get("completion_signal"), dict) else {}
    if signal.get("status") == "skipped_by_user":
        return False
    if not completion_signal_received(progress):
        return False
    judgement = progress.get("mastery_judgement") if isinstance(progress.get("mastery_judgement"), dict) else {}
    if str(judgement.get("status") or "").strip() not in {"", "unknown", "not_observed"}:
        return True
    mastery_checks = progress.get("mastery_checks") if isinstance(progress.get("mastery_checks"), dict) else {}
    return bool(progress.get("reflection") or normalize_string_list(mastery_checks.get("reflection")))


def mastery_gate(progress: dict[str, Any]) -> dict[str, Any]:
    judgement = progress.get("mastery_judgement") if isinstance(progress.get("mastery_judgement"), dict) else {}
    status = str(judgement.get("status") or "unknown").strip() or "unknown"
    prompting_level = str(judgement.get("prompting_level") or "unknown").strip() or "unknown"
    completion_received = completion_signal_received(progress)
    reflection_completed = reflection_gate_completed(progress)
    blocking_statuses = {"partial", "fragile", "blocked"}
    strong_statuses = {"mastered", "solid_after_intervention"}
    return {
        "completion_received": completion_received,
        "reflection_completed": reflection_completed,
        "status": status,
        "prompting_level": prompting_level,
        "mastery_level": judgement.get("mastery_level"),
        "blocking_gaps": normalize_string_list(judgement.get("blocking_gaps")),
        "next_session_reinforcement": normalize_string_list(judgement.get("next_session_reinforcement")),
        "can_mark_mastered": bool(completion_received and reflection_completed and status == "mastered" and prompting_level in {"none", "unprompted", "unknown"}),
        "can_advance_with_review": bool(completion_received and reflection_completed and status == "solid_after_intervention"),
        "blocks_advance": bool((not completion_received) or (not reflection_completed) or status in blocking_statuses),
        "has_positive_mastery_evidence": bool(completion_received and reflection_completed and status in strong_statuses),
    }


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
    reflection_done = bool(recorded_reflection or reflection) and reflection_gate_completed(progress)
    gate = mastery_gate(progress)

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
        "completion_received": gate.get("completion_received"),
        "reflection_gate_completed": gate.get("reflection_completed"),
        "mastery_judgement_status": gate.get("status"),
        "prompting_level": gate.get("prompting_level"),
        "mastery_level": gate.get("mastery_level"),
        "artifacts": artifacts,
    }


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


def extract_today_contract(progress: dict[str, Any]) -> dict[str, Any]:
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}

    def merged_dict(key: str) -> dict[str, Any]:
        primary = context.get(key) if isinstance(context.get(key), dict) else {}
        fallback = snapshot.get(key) if isinstance(snapshot.get(key), dict) else {}
        return {**fallback, **primary}

    def merged_list(key: str) -> list[str]:
        return normalize_string_list(context.get(key) or snapshot.get(key) or [])

    return {
        "today_teaching_brief": merged_dict("today_teaching_brief"),
        "lesson_review": merged_dict("lesson_review"),
        "question_review": merged_dict("question_review"),
        "lesson_focus_points": merged_list("lesson_focus_points"),
        "project_tasks": merged_list("project_tasks"),
        "project_blockers": merged_list("project_blockers"),
        "review_targets": merged_list("review_targets"),
        "lesson_path": context.get("lesson_path") or snapshot.get("lesson_path") or context.get("daily_plan_artifact_path") or snapshot.get("daily_plan_artifact_path"),
        "session_theme": str((merged_dict("today_teaching_brief").get("session_theme") or context.get("topic_cluster") or progress.get("topic") or "")).strip(),
    }


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
    evidence_gate_reasons = normalize_string_list(summary.get("evidence_gate_reasons"))
    next_learning = normalize_string_list(summary.get("next_learning"))
    weaknesses = normalize_string_list(summary.get("high_freq_errors"))
    strengths = normalize_string_list(item.get("title") for item in summary.get("solved_items") or [])
    review_gap = normalize_string_list(summary.get("review_gap"))
    project_tasks = normalize_string_list(summary.get("project_tasks"))
    project_blockers = normalize_string_list(summary.get("project_blockers"))
    review_targets = normalize_string_list(summary.get("review_targets"))
    lesson_focus_points = normalize_string_list(summary.get("lesson_focus_points"))
    pending_review_items = normalize_string_list(summary.get("pending_review_items"))
    attempted = normalize_int(summary.get("attempted"))
    finished_at = summary.get("finished_at") or summary.get("date")
    active_cluster = str(context.get("topic_cluster") or context.get("current_day") or context.get("current_stage") or summary.get("topic") or "").strip()
    session_theme = str(summary.get("session_theme") or active_cluster or summary.get("topic") or "").strip()
    reviewer_verdict = summary.get("reviewer_verdict") if isinstance(summary.get("reviewer_verdict"), dict) else {}

    gate = mastery_gate(updated)
    gated_review_debt = normalize_string_list(
        gate.get("blocking_gaps")
        + gate.get("next_session_reinforcement")
        + (["缺少用户完成信号"] if not gate.get("completion_received") else [])
        + (["缺少 update 前复盘证据"] if not gate.get("reflection_completed") else [])
    )
    needs_more_review = bool(summary.get("should_review") or review_gap or gated_review_debt or gate.get("blocks_advance"))
    can_advance = bool(summary.get("can_advance") and not needs_more_review)
    review_debt = normalize_string_list(review_gap + review_focus + evidence_gate_reasons + gated_review_debt)
    mastered_additions = normalize_string_list(strengths + normalize_string_list(summary.get("covered_scope"))) if gate.get("can_mark_mastered") else []

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
            "next_actions": (review_focus if needs_more_review else next_learning) or review_focus,
        }
    )

    progression.update(
        {
            "stage_status": "planned" if attempted <= 0 else ("blocked_by_review" if needs_more_review else "ready_to_advance"),
            "day_status": "planned" if attempted <= 0 else ("completed_with_gaps" if needs_more_review else "completed"),
            "review_debt": review_debt,
            "mastered_clusters": normalize_string_list(list(progression.get("mastered_clusters") or []) + mastered_additions),
            "active_clusters": normalize_string_list(([session_theme] if session_theme else [active_cluster] if active_cluster else []) + list(progression.get("active_clusters") or [])),
            "deferred_clusters": normalize_string_list(list(progression.get("deferred_clusters") or []) + weaknesses + project_blockers + review_gap),
            "updated_at": finished_at,
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
    context["review_focus"] = review_focus
    context["new_learning_focus"] = next_learning
    context["today_teaching_brief"] = summary.get("today_teaching_brief") or context.get("today_teaching_brief") or {}
    context["lesson_review"] = summary.get("lesson_review") or context.get("lesson_review") or {}
    context["question_review"] = summary.get("question_review") or context.get("question_review") or {}
    context["lesson_focus_points"] = lesson_focus_points
    context["project_tasks"] = project_tasks
    context["project_blockers"] = project_blockers
    context["review_targets"] = review_targets
    context["lesson_path"] = summary.get("lesson_path") or context.get("lesson_path")
    snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
    snapshot["today_teaching_brief"] = context["today_teaching_brief"]
    snapshot["lesson_review"] = context["lesson_review"]
    snapshot["question_review"] = context["question_review"]
    snapshot["lesson_focus_points"] = lesson_focus_points
    snapshot["project_tasks"] = project_tasks
    snapshot["project_blockers"] = project_blockers
    snapshot["review_targets"] = review_targets
    if context.get("lesson_path"):
        snapshot["lesson_path"] = context.get("lesson_path")
    context["plan_source_snapshot"] = snapshot
    updated["context"] = context
    result_summary = dict(summary.get("result_summary") if isinstance(summary.get("result_summary"), dict) else {})
    result_summary.update(
        {
            "overall": summary.get("overall"),
            "session_theme": session_theme,
            "reviewer_verdict": reviewer_verdict,
            "review_gap": review_gap,
            "project_tasks": project_tasks[:4],
            "review_targets": review_targets[:4],
            "can_advance": can_advance,
            "should_review": needs_more_review,
        }
    )
    updated["result_summary"] = result_summary

    update_history.append(
        {
            "update_type": "today",
            "updated_at": finished_at,
            "session_dir": str(session_dir),
            "summary": {
                "overall": summary.get("overall"),
                "session_theme": session_theme,
                "reviewer_verdict": reviewer_verdict,
                "review_focus": review_focus,
                "next_learning": next_learning,
                "high_freq_errors": weaknesses,
                "mainline_progress": summary.get("mainline_progress"),
                "supporting_gap": summary.get("supporting_gap") or [],
                "defer_enhancement": summary.get("defer_enhancement") or [],
                "project_tasks": project_tasks[:4],
                "project_blockers": project_blockers[:4],
                "review_targets": review_targets[:4],
                "review_gap": review_gap[:6],
                "mastery": {
                    "reading_done": mastery.get("reading_done"),
                    "session_done": mastery.get("session_done"),
                    "project_done": mastery.get("project_done"),
                    "reflection_done": mastery.get("reflection_done"),
                },
                "material_alignment": material_alignment,
                "pending_review_count": summary.get("pending_review_count", 0),
                "pending_review_items": pending_review_items,
                "can_advance": can_advance,
                "should_review": needs_more_review,
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


def semantic_summary_is_valid(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    quality_review = payload.get("quality_review") if isinstance(payload.get("quality_review"), dict) else {}
    generation_trace = payload.get("generation_trace") if isinstance(payload.get("generation_trace"), dict) else {}
    return bool(
        quality_review.get("valid")
        and normalize_string_list(payload.get("evidence") or [])
        and generation_trace
        and normalize_string_list(payload.get("traceability") or [])
    )


def summarize_progress(progress: dict[str, Any], questions_map: dict[str, dict[str, Any]], semantic_summary: dict[str, Any] | None = None) -> dict[str, Any]:
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
    today_contract = extract_today_contract(progress)
    lesson_review = today_contract.get("lesson_review") if isinstance(today_contract.get("lesson_review"), dict) else {}
    question_review = today_contract.get("question_review") if isinstance(today_contract.get("question_review"), dict) else {}
    teaching_brief = today_contract.get("today_teaching_brief") if isinstance(today_contract.get("today_teaching_brief"), dict) else {}
    lesson_focus_points = normalize_string_list(today_contract.get("lesson_focus_points") or [])
    project_tasks = normalize_string_list(today_contract.get("project_tasks") or [])
    project_blockers = normalize_string_list(today_contract.get("project_blockers") or [])
    review_targets = normalize_string_list(today_contract.get("review_targets") or [])

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

    question_review_warnings = normalize_string_list(question_review.get("warnings") or [])
    question_review_issues = normalize_string_list(question_review.get("issues") or [])
    lesson_review_warnings = normalize_string_list(lesson_review.get("warnings") or [])
    lesson_review_issues = normalize_string_list(lesson_review.get("issues") or [])
    review_gap = normalize_string_list(question_review_issues + question_review_warnings + lesson_review_issues + lesson_review_warnings)
    semantic_valid = semantic_summary_is_valid(semantic_summary)
    semantic_summary = semantic_summary if isinstance(semantic_summary, dict) else {}
    review_focus = normalize_string_list(semantic_summary.get("review_focus") if semantic_valid else [])
    next_learning = normalize_string_list(semantic_summary.get("next_learning") if semantic_valid else [])

    gate = mastery_gate(progress)
    gate_review_reasons: list[str] = []
    if not gate.get("completion_received"):
        gate_review_reasons.append("缺少用户完成信号")
    if not gate.get("reflection_completed"):
        gate_review_reasons.append("缺少 update 前复盘证据")
    mastery_status = str(gate.get("status") or "unknown")
    if mastery_status in {"partial", "fragile", "blocked"}:
        gate_review_reasons.append(f"掌握判断为 {mastery_status}")
    for gap in gate.get("blocking_gaps") or []:
        gate_review_reasons.append(str(gap))
    for reinforcement in gate.get("next_session_reinforcement") or []:
        gate_review_reasons.append(str(reinforcement))

    facts_indicate_review = bool(
        review_gap
        or high_freq_errors
        or not mastery.get("reading_done")
        or not mastery.get("reflection_done")
        or pending_review_items
        or gate_review_reasons
    )
    needs_more_review = bool(semantic_summary.get("should_review")) if semantic_valid else facts_indicate_review
    if gate_review_reasons:
        needs_more_review = True
    can_advance = bool(semantic_summary.get("can_advance")) if semantic_valid else False
    can_advance = bool(can_advance and not gate.get("blocks_advance"))
    reviewer_verdict = {
        "lesson": lesson_review.get("verdict"),
        "question": question_review.get("verdict"),
    }
    covered_scope = normalize_string_list(
        lesson_focus_points[:3]
        + project_tasks[:2]
        + [item["title"] for item in solved_items[:2]]
    )

    overall = str(semantic_summary.get("overall") or "").strip() if semantic_valid else ""
    semantic_status = "ok" if semantic_valid else "missing_artifact"
    diagnostic_triggers = build_diagnostic_trigger_facts(progress)
    all_diagnostic_targets = aggregate_diagnostic_targets(diagnostic_triggers, max_targets=999)
    diagnostic_targets = all_diagnostic_targets[:3]
    review_debt_candidates = all_diagnostic_targets[3:]
    session_result_summary = build_result_summary(
        total=total,
        attempted=attempted,
        correct=correct,
        diagnostic_triggers=diagnostic_triggers,
        diagnostic_targets=diagnostic_targets,
        review_targets=review_focus or high_freq_errors,
        should_review=needs_more_review,
        can_advance=can_advance,
    )

    return {
        "topic": topic,
        "date": progress.get("date") or "",
        "session_type": session.get("type") or "today",
        "test_mode": session.get("test_mode"),
        "status": session.get("status") or "active",
        "started_at": session.get("started_at"),
        "finished_at": session.get("finished_at"),
        "total": session_result_summary["total"],
        "attempted": session_result_summary["attempted"],
        "correct": session_result_summary["correct"],
        "result_summary": session_result_summary,
        "pending_review_count": len(pending_review_items),
        "pending_review_items": normalize_string_list(pending_review_items),
        "overall": overall or None,
        "semantic_status": semantic_status,
        "semantic_missing_requirements": ([] if semantic_valid else ["semantic_summary"]),
        "semantic_summary": semantic_summary if semantic_valid else {},
        "high_freq_errors": high_freq_errors,
        "review_focus": normalize_string_list(review_focus),
        "next_learning": normalize_string_list(next_learning),
        "evidence_gate_reasons": normalize_string_list(gate_review_reasons),
        "wrong_items": wrong_items,
        "solved_items": solved_items[:3],
        "diagnostic_triggers": diagnostic_triggers,
        "diagnostic_targets": diagnostic_targets,
        "review_debt_candidates": review_debt_candidates,
        "mastery": mastery,
        "material_alignment": material_alignment,
        "mainline_progress": goal_focus.get("mainline") or context.get("topic_cluster") or topic,
        "supporting_gap": normalize_string_list(goal_focus.get("supporting"))[:2] if high_freq_errors else [],
        "defer_enhancement": normalize_string_list(goal_focus.get("enhancement"))[:1] if (high_freq_errors or progression.get("review_debt")) else [],
        "covered_scope": covered_scope,
        "session_theme": today_contract.get("session_theme") or topic,
        "lesson_path": today_contract.get("lesson_path"),
        "today_teaching_brief": teaching_brief,
        "lesson_review": lesson_review,
        "question_review": question_review,
        "lesson_focus_points": lesson_focus_points,
        "project_tasks": project_tasks,
        "project_blockers": project_blockers,
        "review_targets": review_targets,
        "review_gap": review_gap,
        "reviewer_verdict": reviewer_verdict,
        "user_feedback": progress.get("user_feedback") if isinstance(progress.get("user_feedback"), dict) else {},
        "should_review": needs_more_review,
        "can_advance": can_advance,
    }


def render_log_entry(summary: dict[str, Any], session_dir: Path) -> str:
    weak_text = "；".join(summary["high_freq_errors"]) if summary["high_freq_errors"] else "暂无明显高频错误"
    semantic_ready = summary.get("semantic_status") == "ok"
    review_text = "；".join(summary["review_focus"]) if semantic_ready else "缺少 semantic summary artifact"
    next_text = "；".join(summary["next_learning"]) if semantic_ready else "缺少 semantic summary artifact"
    overall_text = summary.get("overall") if semantic_ready else "缺少 semantic summary artifact"
    mastery = summary.get("mastery") or {}
    material_alignment = summary.get("material_alignment") if isinstance(summary.get("material_alignment"), dict) else {}
    material_text = material_alignment.get("status") or "未记录"
    if material_alignment.get("selected_segments"):
        material_text += f"（覆盖 {len(material_alignment.get('covered_segments') or [])}/{len(material_alignment.get('selected_segments') or [])} 个 segment）"
    project_text = "；".join(normalize_string_list(summary.get("project_tasks"))[:4]) or "无"
    review_target_text = "；".join(normalize_string_list(summary.get("review_targets"))[:4]) or "无"
    review_gap_text = "；".join(normalize_string_list(summary.get("review_gap"))[:6]) or "无明显 reviewer 缺口"
    reviewer_verdict = summary.get("reviewer_verdict") if isinstance(summary.get("reviewer_verdict"), dict) else {}
    verdict_text = " / ".join(
        part for part in [
            f"lesson={reviewer_verdict.get('lesson')}" if reviewer_verdict.get("lesson") else "",
            f"question={reviewer_verdict.get('question')}" if reviewer_verdict.get("question") else "",
        ]
        if part
    ) or "未记录"
    return "\n".join(
        [
            f"### {summary['date']} / {summary['topic']} / 今日学习更新",
            f"- session 目录：`{session_dir}`",
            f"- 今日主题：{summary.get('session_theme') or summary['topic']}",
            f"- lesson 文件：`{summary.get('lesson_path') or '未记录'}`",
            f"- 总题数：{summary['total']}",
            f"- 已练习题数：{summary['attempted']}",
            f"- 正确/通过题数：{summary['correct']}",
            f"- 总体表现：{overall_text}",
            f"- semantic summary 状态：{summary.get('semantic_status') or 'unknown'}",
            f"- reviewer 结论：{verdict_text}",
            f"- 高频错误点：{weak_text}",
            f"- 今日项目任务：{project_text}",
            f"- 今日复习目标：{review_target_text}",
            f"- reviewer coverage 缺口：{review_gap_text}",
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


def update_knowledge_state_from_progress(
    plan_path: Path,
    session_dir: Path,
    progress: dict[str, Any],
    questions_map: dict[str, dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    state = load_knowledge_state(plan_path)
    if not state:
        return {"status": "skipped", "reason": "missing_knowledge_state", "evidence_count": 0}
    if state.get("status") not in {"confirmed", "active"}:
        return {"status": "skipped", "reason": "knowledge_state_not_confirmed", "evidence_count": 0}
    if summary.get("semantic_status") != "ok" and not semantic_summary_is_valid(summary):
        return {"status": "skipped", "reason": "semantic_summary_missing", "evidence_count": 0}
    evidence_items = build_session_knowledge_evidence_items(
        progress,
        questions_map,
        session_type="today",
        gate=mastery_gate(progress),
    )
    session_facts = build_session_facts(progress, summary, session_dir=session_dir, update_type="today")
    evidence_items.extend(build_interaction_knowledge_evidence_items(session_facts, session_type="today"))
    if not evidence_items:
        return {"status": "skipped", "reason": "no_bound_question_evidence", "evidence_count": 0}
    applicable_count = count_applicable_session_evidence(state, evidence_items)
    if applicable_count <= 0:
        return {"status": "skipped", "reason": "invalid_knowledge_point_binding", "evidence_count": 0}
    updated_state = update_state_from_session_evidence(
        state,
        session_dir=session_dir,
        session_type="today",
        evidence_items=evidence_items,
        summary=summary,
    )
    save_knowledge_state(plan_path, updated_state)
    return {"status": "updated", "reason": None, "evidence_count": applicable_count}


def update_learn_plan(plan_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(plan_path)
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "学习记录", block)
    write_text(plan_path, updated)
    append_micro_adjustments(plan_path, summary)


def print_summary(summary: dict[str, Any], plan_path: Path, *, stdout_json: bool, feedback_result: dict[str, Any] | None = None) -> None:
    semantic_ready = summary.get("semantic_status") == "ok"
    print(f"主题：{summary['topic']}")
    print(f"总题数：{summary['total']}")
    print(f"已练习：{summary['attempted']}")
    print(f"正确/通过：{summary['correct']}")
    print(f"semantic summary 状态：{summary.get('semantic_status') or 'unknown'}")
    print(f"高频错误点：{'；'.join(summary['high_freq_errors']) if summary['high_freq_errors'] else '暂无明显高频错误'}")
    material_alignment = summary.get("material_alignment") if isinstance(summary.get("material_alignment"), dict) else {}
    if material_alignment:
        print(f"材料 segment 覆盖：{material_alignment.get('status') or '未记录'}")
    review_text = "；".join(summary["review_focus"]) if semantic_ready else "缺少 semantic summary artifact"
    next_text = "；".join(summary["next_learning"]) if semantic_ready else "缺少 semantic summary artifact"
    print(f"下次复习重点：{review_text}")
    print(f"下次新学习建议：{next_text}")
    print(f"学习计划：{plan_path}")
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

    progress = read_json(progress_path)
    questions_map = load_questions_map(session_dir)
    semantic_summary = read_json(Path(args.semantic_summary_json).expanduser().resolve()) if args.semantic_summary_json else None
    semantic_diagnostic = read_json(Path(args.semantic_diagnostic_json).expanduser().resolve()) if args.semantic_diagnostic_json else None
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
        summary = summarize_diagnostic_progress(progress, questions_map, semantic_diagnostic=semantic_diagnostic)
        updated_progress = update_diagnostic_state(progress, summary)
        write_json(progress_path, updated_progress)
        update_learn_plan_with_diagnostic(plan_path, summary, session_dir)
        feedback_result = write_feedback_artifacts(plan_path, summary, updated_progress, session_dir, update_type="diagnostic")
        refresh_workflow_state(plan_path)
        print_diagnostic_summary(summary, plan_path, stdout_json=args.stdout_json, feedback_result=feedback_result)
        patch_queue = (feedback_result.get("patch_queue") or {}).get("queue")
        if isinstance(patch_queue, dict):
            pending_count = len(pending_patch_items(patch_queue))
            if pending_count > 0:
                print(f"提示：有 {pending_count} 条待审批的课程调整建议，可运行 /learn-plan 审批")
                if args.stdout_json:
                    print(json.dumps({"pending_patch_count": pending_count, "suggested_action": "run /learn-plan to review and approve curriculum adjustments"}, ensure_ascii=False))
        return 0
    summary = summarize_progress(progress, questions_map, semantic_summary=semantic_summary)
    updated_progress = update_progress_state(progress, summary, session_dir=session_dir)
    knowledge_update = update_knowledge_state_from_progress(plan_path, session_dir, updated_progress, questions_map, summary)
    summary["knowledge_state_update"] = knowledge_update
    write_json(progress_path, updated_progress)
    update_learn_plan(plan_path, summary, session_dir)
    feedback_result = write_feedback_artifacts(plan_path, summary, updated_progress, session_dir, update_type="today")
    refresh_workflow_state(plan_path)
    print_summary(summary, plan_path, stdout_json=args.stdout_json, feedback_result=feedback_result)
    patch_queue = (feedback_result.get("patch_queue") or {}).get("queue")
    if isinstance(patch_queue, dict):
        pending_count = len(pending_patch_items(patch_queue))
        if pending_count > 0:
            print(f"提示：有 {pending_count} 条待审批的课程调整建议，可运行 /learn-plan 审批")
            if args.stdout_json:
                print(json.dumps({"pending_patch_count": pending_count, "suggested_action": "run /learn-plan to review and approve curriculum adjustments"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
