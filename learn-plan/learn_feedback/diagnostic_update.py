"""Shared diagnostic/feedback update functions extracted from learn_today_update.

This module breaks the reverse dependency: learn_test_update no longer needs
to import from learn_today_update. Both update scripts import from here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from learn_core.io import read_json, read_text_if_exists, write_json, write_text
from learn_core.markdown_sections import upsert_markdown_section
from learn_core.text_utils import normalize_int, normalize_string_list
from learn_workflow.contracts import default_workflow_paths
from learn_workflow.workflow_store import resolve_learning_root

from . import (
    build_patch_proposal,
    build_session_facts,
    render_feedback_output_lines,
    update_learner_model_file,
    update_patch_queue_file,
)


def extract_question_clusters(question: dict[str, Any]) -> list[str]:
    clusters: list[str] = []
    for value in [question.get("cluster"), *(question.get("tags") or []), *(question.get("subskills") or [])]:
        text = str(value or "").strip()
        if text and text not in clusters:
            clusters.append(text)
    return clusters


def load_questions_map(session_dir: Path) -> dict[str, dict[str, Any]]:
    questions_path = session_dir / "questions.json"
    if not questions_path.exists():
        raise FileNotFoundError(f"未找到 questions.json: {questions_path}")
    data = read_json(questions_path)
    items = data.get("questions") or []
    return {item.get("id"): item for item in items if item.get("id")}


def semantic_diagnostic_is_valid(payload: dict[str, Any] | None) -> bool:
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


def summarize_diagnostic_progress(
    progress: dict[str, Any],
    questions_map: dict[str, dict[str, Any]],
    semantic_diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    topic = progress.get("topic") or "未命名主题"
    question_progress = progress.get("questions") or {}
    session = progress.get("session") or {}
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
    existing_profile = context.get("diagnostic_profile") if isinstance(context.get("diagnostic_profile"), dict) else {}
    existing_planning_state = context.get("planning_state") if isinstance(context.get("planning_state"), dict) else {}

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
    correct = 0
    questions_per_round = (
        session.get("questions_per_round")
        or progress.get("questions_per_round")
        or context.get("questions_per_round")
        or snapshot.get("questions_per_round")
        or existing_planning_state.get("questions_per_round")
        or existing_profile.get("questions_per_round")
    )
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
            correct += 1
            strengths.append(title)
            evidence.append(f"题目《{title}》完成良好")
        else:
            weaknesses.append(title)
            evidence.append(f"题目《{title}》暴露当前薄弱点")

    mastery_judgement = progress.get("mastery_judgement") if isinstance(progress.get("mastery_judgement"), dict) else {}
    for gap in normalize_string_list(mastery_judgement.get("blocking_gaps")):
        if gap not in weaknesses:
            weaknesses.append(gap)
        evidence.append(f"用户复盘暴露薄弱点：{gap}")
    for reinforcement in normalize_string_list(mastery_judgement.get("next_session_reinforcement")):
        evidence.append(f"用户复盘建议后续强化：{reinforcement}")

    current_stage = context.get("current_stage") or snapshot.get("current_stage")
    semantic_valid = semantic_diagnostic_is_valid(semantic_diagnostic)
    semantic_diagnostic = semantic_diagnostic if isinstance(semantic_diagnostic, dict) else {}
    semantic_profile = semantic_diagnostic.get("diagnostic_profile") if isinstance(semantic_diagnostic.get("diagnostic_profile"), dict) else {}
    overall = str(semantic_diagnostic.get("overall") or "").strip() if semantic_valid else ""
    recommended_entry_level = str(semantic_diagnostic.get("recommended_entry_level") or semantic_profile.get("recommended_entry_level") or "").strip() if semantic_valid else ""
    if semantic_valid:
        round_index = semantic_profile.get("round_index") or semantic_diagnostic.get("round_index") or round_index
        max_rounds = semantic_profile.get("max_rounds") or semantic_diagnostic.get("max_rounds") or max_rounds
        questions_per_round = semantic_profile.get("questions_per_round") or semantic_diagnostic.get("questions_per_round") or questions_per_round
        if "follow_up_needed" in semantic_diagnostic:
            follow_up_needed = bool(semantic_diagnostic.get("follow_up_needed"))
        elif "follow_up_needed" in semantic_profile:
            follow_up_needed = bool(semantic_profile.get("follow_up_needed"))
        if semantic_diagnostic.get("stop_reason"):
            stop_reason = semantic_diagnostic.get("stop_reason")
        elif semantic_profile.get("stop_reason"):
            stop_reason = semantic_profile.get("stop_reason")
    else:
        follow_up_needed = True
        stop_reason = "missing-semantic-diagnostic"

    status = str(semantic_profile.get("status") or "").strip() if semantic_valid else "blocked-missing-semantic-diagnostic"
    if semantic_valid and not status:
        status = "validated" if attempted > 0 and not follow_up_needed and (scorable_attempted > 0 or not pending_review_items) else "in-progress"

    return {
        "topic": topic,
        "date": progress.get("date") or "",
        "session_type": session.get("type") or "today",
        "status": session.get("status") or "active",
        "attempted": attempted,
        "correct": correct,
        "overall": overall or None,
        "recommended_entry_level": recommended_entry_level or None,
        "semantic_status": "ok" if semantic_valid else "missing_artifact",
        "semantic_missing_requirements": ([] if semantic_valid else ["semantic_diagnostic"]),
        "semantic_diagnostic": semantic_diagnostic if semantic_valid else {},
        "diagnostic_profile": {
            "status": status,
            "round_index": round_index,
            "max_rounds": max_rounds,
            "questions_per_round": questions_per_round,
            "follow_up_needed": follow_up_needed,
            "stop_reason": stop_reason,
            "baseline_level": current_stage or topic,
            "dimensions": [q.get("question") or q.get("title") or qid for qid, q in questions_map.items()],
            "observed_strengths": normalize_string_list(strengths),
            "observed_weaknesses": normalize_string_list(weaknesses),
            "pending_review_count": len(pending_review_items),
            "pending_review_items": normalize_string_list(pending_review_items),
            "evidence": normalize_string_list(evidence),
            "recommended_entry_level": recommended_entry_level or None,
            "confidence": semantic_diagnostic.get("confidence") if semantic_valid else 0.0,
        },
    }


def update_diagnostic_state(progress: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(progress))
    context = updated.get("context") if isinstance(updated.get("context"), dict) else {}
    user_model = context.get("user_model") if isinstance(context.get("user_model"), dict) else {}
    planning_state = context.get("planning_state") if isinstance(context.get("planning_state"), dict) else {}
    diagnostic_profile = summary.get("diagnostic_profile") or {}
    user_model["strengths"] = normalize_string_list(diagnostic_profile.get("observed_strengths"))
    user_model["weaknesses"] = normalize_string_list(diagnostic_profile.get("observed_weaknesses"))
    planning_state["diagnostic_status"] = diagnostic_profile.get("status") or "in-progress"
    planning_state["diagnostic_round_index"] = diagnostic_profile.get("round_index")
    planning_state["diagnostic_max_rounds"] = diagnostic_profile.get("max_rounds")
    planning_state["diagnostic_follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    context["user_model"] = user_model
    context["planning_state"] = planning_state
    context["diagnostic_profile"] = diagnostic_profile
    context["round_index"] = diagnostic_profile.get("round_index")
    context["max_rounds"] = diagnostic_profile.get("max_rounds")
    context["follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    context["stop_reason"] = diagnostic_profile.get("stop_reason")
    snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
    snapshot["diagnostic_profile"] = diagnostic_profile
    snapshot["round_index"] = diagnostic_profile.get("round_index")
    snapshot["max_rounds"] = diagnostic_profile.get("max_rounds")
    snapshot["follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    snapshot["stop_reason"] = diagnostic_profile.get("stop_reason")
    context["plan_source_snapshot"] = snapshot
    updated["context"] = context
    session = updated.get("session") if isinstance(updated.get("session"), dict) else {}
    semantic_ready = summary.get("semantic_status") == "ok"
    if semantic_ready:
        session["status"] = "finished"
        session["finished_at"] = summary.get("date")
    else:
        session["status"] = "blocked-missing-semantic-diagnostic"
        session.pop("finished_at", None)
    session["round_index"] = diagnostic_profile.get("round_index")
    session["max_rounds"] = diagnostic_profile.get("max_rounds")
    session["follow_up_needed"] = diagnostic_profile.get("follow_up_needed")
    session["stop_reason"] = diagnostic_profile.get("stop_reason")
    updated["session"] = session
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


def update_learn_plan_with_diagnostic(plan_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(plan_path)
    diagnostic = summary.get("diagnostic_profile") or {}
    semantic_ready = summary.get("semantic_status") == "ok"
    overall_text = summary.get("overall") if semantic_ready else "缺少 semantic diagnostic artifact"
    entry_text = summary.get("recommended_entry_level") if semantic_ready else "缺少 semantic diagnostic artifact"
    block = "\n".join([
        f"### {summary['date']} / {summary['topic']} / 前置诊断更新",
        f"- session 目录：`{session_dir}`",
        f"- semantic diagnostic 状态：{summary.get('semantic_status') or 'unknown'}",
        f"- 总体判断：{overall_text}",
        f"- 推荐起步层级：{entry_text}",
        *( [f"- 最多轮次：{diagnostic.get('max_rounds')}"] if diagnostic.get("max_rounds") else [] ),
        *( [f"- 每轮题量：{diagnostic.get('questions_per_round')}"] if diagnostic.get("questions_per_round") else [] ),
        *( [f"- 当前轮次：第 {diagnostic.get('round_index')} 轮 / 共 {diagnostic.get('max_rounds')} 轮"] if diagnostic.get("round_index") else [] ),
        *( [f"- 是否需要追问轮次：{diagnostic.get('follow_up_needed')}"] if diagnostic.get("follow_up_needed") is not None else [] ),
        *( [f"- 结束原因：{diagnostic.get('stop_reason')}"] if diagnostic.get("stop_reason") else [] ),
        *( [f"- 已观察到的优势：{'；'.join(diagnostic.get('observed_strengths', []))}"] if diagnostic.get("observed_strengths") else [] ),
        *( [f"- 已观察到的薄弱点：{'；'.join(diagnostic.get('observed_weaknesses', []))}"] if diagnostic.get("observed_weaknesses") else [] ),
    ])
    updated = upsert_markdown_section(original, "学习记录", block)
    write_text(plan_path, updated)


def write_feedback_artifacts(plan_path: Path, summary: dict[str, Any], progress: dict[str, Any], session_dir: Path, *, update_type: str) -> dict[str, Any]:
    session_facts = build_session_facts(progress, summary, session_dir=session_dir, update_type=update_type)
    paths = default_workflow_paths(resolve_learning_root(plan_path), plan_path, plan_path.parent / "materials" / "index.json")
    write_json(paths["session_facts_json"], session_facts)
    learner_model = update_learner_model_file(plan_path, summary, session_facts, update_type=update_type)
    patch_candidate = build_patch_proposal(summary, session_facts, update_type=update_type)
    patch_queue = update_patch_queue_file(plan_path, summary, session_facts, update_type=update_type, patch_candidate=patch_candidate)
    return {
        "session_facts": session_facts,
        "learner_model": learner_model,
        "patch_queue": patch_queue,
    }


def print_diagnostic_summary(summary: dict[str, Any], plan_path: Path, *, stdout_json: bool, feedback_result: dict[str, Any] | None = None) -> None:
    diagnostic = summary.get("diagnostic_profile") or {}
    semantic_ready = summary.get("semantic_status") == "ok"
    overall_text = summary.get("overall") if semantic_ready else "缺少 semantic diagnostic artifact"
    entry_text = summary.get("recommended_entry_level") if semantic_ready else "缺少 semantic diagnostic artifact"
    print(f"主题：{summary['topic']}")
    print(f"semantic diagnostic 状态：{summary.get('semantic_status') or 'unknown'}")
    print(f"诊断结论：{overall_text}")
    print(f"推荐起步层级：{entry_text}")
    if diagnostic.get("max_rounds"):
        print(f"最多轮次：{diagnostic.get('max_rounds')}")
    if diagnostic.get("questions_per_round"):
        print(f"每轮题量：{diagnostic.get('questions_per_round')}")
    if diagnostic.get("round_index"):
        print(f"当前轮次：第 {diagnostic.get('round_index')} 轮 / 共 {diagnostic.get('max_rounds')} 轮")
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


__all__ = [
    "extract_question_clusters",
    "load_questions_map",
    "print_diagnostic_summary",
    "summarize_diagnostic_progress",
    "update_diagnostic_state",
    "update_learn_plan_with_diagnostic",
    "write_feedback_artifacts",
]
