#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from learn_core.io import read_json, read_json_if_exists as core_read_json_if_exists, read_text_if_exists, write_json, write_text
from learn_core.markdown_sections import upsert_markdown_section
from learn_core.text_utils import normalize_int, normalize_string_list
from learn_workflow import refresh_workflow_state
from learn_workflow.contracts import default_workflow_paths
from learn_workflow.stage_review import review_stage_candidate
from learn_workflow.workflow_store import resolve_learning_root
from learn_knowledge import (
    build_interaction_knowledge_evidence_items,
    build_session_knowledge_evidence_items,
    count_applicable_session_evidence,
    load_knowledge_state,
    save_knowledge_state,
    update_state_from_session_evidence,
)
from learn_feedback import (
    aggregate_diagnostic_targets,
    append_micro_adjustments,
    build_diagnostic_trigger_facts,
    build_patch_proposal,
    build_result_summary,
    build_session_facts,
    render_feedback_output_lines,
    update_learner_model_file,
    update_patch_queue_file,
)
from learn_feedback.curriculum_patch import pending_patch_items
from learn_feedback.diagnostic_update import (
    print_diagnostic_summary,
    semantic_diagnostic_is_valid,
    summarize_diagnostic_progress,
    update_diagnostic_state,
    update_learn_plan_with_diagnostic,
    write_feedback_artifacts as write_diagnostic_feedback_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a learn-plan test session and update learn-plan.md")
    parser.add_argument("--session-dir", required=True, help="session 目录，需包含 progress.json")
    parser.add_argument("--plan-path", default="learn-plan.md", help="学习计划文件路径")
    parser.add_argument("--project-path", default=None, help="可选 PROJECT.md 路径；仅在显式兼容旧项目记录时使用")
    parser.add_argument("--semantic-review-json", help="由外部 subagent 生成的 test semantic review JSON 文件路径")
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
    blocking_statuses = {"partial", "fragile", "blocked", "solid_after_intervention"}
    return {
        "completion_received": completion_received,
        "reflection_completed": reflection_completed,
        "status": status,
        "prompting_level": prompting_level,
        "mastery_level": judgement.get("mastery_level"),
        "blocking_gaps": normalize_string_list(judgement.get("blocking_gaps")),
        "next_session_reinforcement": normalize_string_list(judgement.get("next_session_reinforcement")),
        "can_mark_mastered": bool(completion_received and reflection_completed and status == "mastered" and prompting_level in {"none", "unprompted", "unknown"}),
        "blocks_advance": bool((not completion_received) or (not reflection_completed) or status in blocking_statuses),
    }


def summarize_mastery(progress: dict[str, Any], questions_data: dict[str, Any]) -> dict[str, Any]:
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    plan_source = questions_data.get("plan_source") if isinstance(questions_data.get("plan_source"), dict) else {}
    mastery_targets = context.get("mastery_targets") if isinstance(context.get("mastery_targets"), dict) else {}
    if not mastery_targets:
        mastery_targets = plan_source.get("mastery_targets") if isinstance(plan_source.get("mastery_targets"), dict) else {}
    mastery_checks = progress.get("mastery_checks") if isinstance(progress.get("mastery_checks"), dict) else {}
    reading_progress = progress.get("reading_progress") if isinstance(progress.get("reading_progress"), dict) else {}
    artifacts = progress.get("artifacts") if isinstance(progress.get("artifacts"), list) else []
    reflection = str(progress.get("reflection") or "").strip()

    target_reading = normalize_string_list(mastery_targets.get("reading_checklist"))
    recorded_reading = normalize_string_list(mastery_checks.get("reading_checklist"))
    if reading_progress and not recorded_reading:
        recorded_reading = normalize_string_list(reading_progress.keys())
    reading_done = bool(target_reading) and len(recorded_reading) >= max(1, min(len(target_reading), 2))

    target_session = normalize_string_list(mastery_targets.get("session_exercises"))
    recorded_session = normalize_string_list(mastery_checks.get("session_exercises"))
    session_done = bool(target_session or recorded_session)

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



def update_progress_state(progress: dict[str, Any], summary: dict[str, Any], *, questions_data: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(progress))
    context = updated.get("context") if isinstance(updated.get("context"), dict) else {}
    learning_state = updated.get("learning_state") if isinstance(updated.get("learning_state"), dict) else {}
    progression = updated.get("progression") if isinstance(updated.get("progression"), dict) else {}
    update_history = updated.get("update_history") if isinstance(updated.get("update_history"), list) else []
    session = updated.get("session") if isinstance(updated.get("session"), dict) else {}
    plan_source = questions_data.get("plan_source") if isinstance(questions_data.get("plan_source"), dict) else {}
    mastery = summary.get("mastery") or {}

    weaknesses = normalize_string_list(summary.get("weaknesses"))
    evidence_gate_reasons = normalize_string_list(summary.get("evidence_gate_reasons"))
    next_actions = normalize_string_list(summary.get("next_actions"))
    covered_scope = normalize_string_list(summary.get("covered_scope"))
    attempted = normalize_int(summary.get("attempted"))
    finished_at = summary.get("finished_at") or summary.get("date")
    active_cluster = str(context.get("topic_cluster") or plan_source.get("today_topic") or context.get("current_day") or context.get("current_stage") or summary.get("topic") or "").strip()
    test_started = attempted > 0

    gate = mastery_gate(updated)
    gated_review_debt = normalize_string_list(
        gate.get("blocking_gaps")
        + gate.get("next_session_reinforcement")
        + evidence_gate_reasons
        + (["缺少用户完成信号"] if not gate.get("completion_received") else [])
        + (["缺少 update 前测试复盘证据"] if not gate.get("reflection_completed") else [])
    )
    should_review = bool(test_started and (summary.get("should_review") or not mastery.get("reading_done") or not mastery.get("reflection_done") or gated_review_debt or gate.get("blocks_advance")))
    can_advance = bool(test_started and summary.get("can_advance") and mastery.get("reading_done") and mastery.get("reflection_done") and not gate.get("blocks_advance"))
    mastered_additions = covered_scope if gate.get("can_mark_mastered") and can_advance else []

    learning_state.update(
        {
            "overall": summary.get("overall") or "未开始",
            "review_focus": weaknesses,
            "next_learning": next_actions if can_advance else [],
            "weaknesses": weaknesses,
            "strengths": normalize_string_list(item.get("title") for item in summary.get("solved_items") or []),
            "should_review": should_review,
            "can_advance": can_advance,
            "advancement_target": next_actions[0] if can_advance and next_actions else None,
            "next_actions": next_actions,
        }
    )

    progression.update(
        {
            "stage_status": "planned" if not test_started else ("blocked_by_review" if should_review else ("ready_to_advance" if can_advance else "in_progress")),
            "day_status": "planned" if not test_started else ("completed_with_gaps" if should_review else "completed"),
            "review_debt": normalize_string_list(weaknesses + gated_review_debt) if test_started else [],
            "mastered_clusters": normalize_string_list(list(progression.get("mastered_clusters") or []) + mastered_additions),
            "active_clusters": normalize_string_list(([active_cluster] if active_cluster else []) + list(progression.get("active_clusters") or [])),
            "deferred_clusters": normalize_string_list(list(progression.get("deferred_clusters") or []) + (weaknesses if should_review else [])),
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
    result_summary = dict(summary.get("result_summary") if isinstance(summary.get("result_summary"), dict) else {})
    result_summary.update(
        {
            "overall": summary.get("overall"),
            "covered_scope": covered_scope,
            "weaknesses": weaknesses,
            "can_advance": can_advance,
            "should_review": should_review,
        }
    )
    updated["result_summary"] = result_summary

    update_history.append(
        {
            "update_type": "test",
            "updated_at": summary.get("finished_at") or summary.get("date"),
            "summary": {
                "overall": summary.get("overall"),
                "covered_scope": covered_scope,
                "weaknesses": weaknesses,
                "should_review": should_review,
                "can_advance": can_advance,
                "next_actions": next_actions,
                "blocking_weaknesses": summary.get("blocking_weaknesses") or [],
                "deferred_enhancement": summary.get("deferred_enhancement") or [],
                "mastery": {
                    "reading_done": mastery.get("reading_done"),
                    "session_done": mastery.get("session_done"),
                    "project_done": mastery.get("project_done"),
                    "reflection_done": mastery.get("reflection_done"),
                },
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


def load_questions_data(session_dir: Path) -> dict[str, Any]:
    questions_path = session_dir / "questions.json"
    if not questions_path.exists():
        raise FileNotFoundError(f"未找到 questions.json: {questions_path}")
    return read_json(questions_path)


def load_questions_map(questions_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = questions_data.get("questions") or []
    return {item.get("id"): item for item in items if item.get("id")}


def update_knowledge_state_from_progress(
    plan_path: Path,
    session_dir: Path,
    progress: dict[str, Any],
    questions_map: dict[str, dict[str, Any]],
    summary: dict[str, Any],
    *,
    session_type: str = "test",
) -> dict[str, Any]:
    state = load_knowledge_state(plan_path)
    if not state:
        return {"status": "skipped", "reason": "missing_knowledge_state", "evidence_count": 0}
    if state.get("status") not in {"confirmed", "active"}:
        return {"status": "skipped", "reason": "knowledge_state_not_confirmed", "evidence_count": 0}
    semantic_required = "semantic_diagnostic" if session_type == "diagnostic" else "semantic_review"
    semantic_valid = semantic_diagnostic_is_valid(summary) if session_type == "diagnostic" else semantic_review_is_valid(summary)
    if summary.get("semantic_status") != "ok" and not semantic_valid:
        return {"status": "skipped", "reason": f"{semantic_required}_missing", "evidence_count": 0}
    evidence_items = build_session_knowledge_evidence_items(
        progress,
        questions_map,
        session_type=session_type,
        gate=mastery_gate(progress),
    )
    session_facts = build_session_facts(progress, summary, session_dir=session_dir, update_type="test")
    evidence_items.extend(build_interaction_knowledge_evidence_items(session_facts, session_type=session_type))
    if not evidence_items:
        return {"status": "skipped", "reason": "no_bound_question_evidence", "evidence_count": 0}
    applicable_count = count_applicable_session_evidence(state, evidence_items)
    if applicable_count <= 0:
        return {"status": "skipped", "reason": "invalid_knowledge_point_binding", "evidence_count": 0}
    updated_state = update_state_from_session_evidence(
        state,
        session_dir=session_dir,
        session_type=session_type,
        evidence_items=evidence_items,
        summary=summary,
    )
    save_knowledge_state(plan_path, updated_state)
    return {"status": "updated", "reason": None, "evidence_count": applicable_count}


def is_legacy_plan_diagnostic_session(session: dict[str, Any]) -> bool:
    if session.get("intent") == "plan-diagnostic" or session.get("assessment_kind") == "plan-diagnostic":
        return True
    return session.get("plan_execution_mode") == "diagnostic" and session.get("assessment_kind") != "initial-test"


def is_initial_test_diagnostic_session(session: dict[str, Any], progress: dict[str, Any] | None = None) -> bool:
    if not (
        session.get("assessment_kind") == "initial-test"
        and session.get("intent") == "assessment"
    ):
        return False
    if session.get("plan_execution_mode") == "diagnostic":
        return True
    if not isinstance(progress, dict):
        return False
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    current_stage = str(context.get("current_stage") or "").strip().lower()
    stop_reason = str(session.get("stop_reason") or context.get("stop_reason") or "").strip().lower()
    round_index = session.get("round_index") or context.get("round_index")
    max_rounds = session.get("max_rounds") or context.get("max_rounds")
    return current_stage == "diagnostic" or stop_reason.startswith("diagnostic") or any(
        value is not None and str(value).strip() not in {"", "null", "None"}
        for value in [round_index, max_rounds]
    )


def semantic_review_is_valid(payload: dict[str, Any] | None) -> bool:
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


def summarize_test_progress(progress: dict[str, Any], questions_data: dict[str, Any], semantic_review: dict[str, Any] | None = None) -> dict[str, Any]:
    topic = progress.get("topic") or "未命名主题"
    session = progress.get("session") or {}
    summary = progress.get("summary") or {}
    result_summary = progress.get("result_summary") or {}
    question_progress = progress.get("questions") or {}
    questions_map = load_questions_map(questions_data)
    plan_source = questions_data.get("plan_source") or {}
    mastery = summarize_mastery(progress, questions_data)

    total = normalize_int(result_summary.get("total") if result_summary else None) or normalize_int(summary.get("total"))
    attempted = normalize_int(result_summary.get("attempted") if result_summary else None) or normalize_int(summary.get("attempted"))
    correct = normalize_int(result_summary.get("correct") if result_summary else None) or normalize_int(summary.get("correct"))

    wrong_items: list[dict[str, Any]] = []
    solved_items: list[dict[str, Any]] = []
    pending_review_items: list[dict[str, Any]] = []

    for qid, item in question_progress.items():
        stats = item.get("stats") or {}
        question = questions_map.get(qid) or {}
        title = question.get("question") or question.get("title") or qid
        attempts = normalize_int(stats.get("attempts"))
        if attempts <= 0:
            continue

        tags = question.get("tags") or []
        capability_tags = normalize_string_list(question.get("capability_tags") or tags)
        submit_result = stats.get("last_submit_result") if isinstance(stats.get("last_submit_result"), dict) else None
        if question.get("category") == "open":
            pending_review_items.append(
                {
                    "id": qid,
                    "title": title,
                    "attempts": attempts,
                    "category": question.get("category") or "unknown",
                    "tags": tags,
                    "review_status": stats.get("review_status") or stats.get("last_status"),
                }
            )
            continue

        correct_count = normalize_int(stats.get("correct_count"))
        pass_count = normalize_int(stats.get("pass_count"))
        success_count = pass_count if question.get("category") == "code" else correct_count

        record = {
            "id": qid,
            "title": title,
            "attempts": attempts,
            "success_count": success_count,
            "category": question.get("category") or "unknown",
            "tags": tags,
            "capability_tags": capability_tags,
        }
        if submit_result:
            record["submit_result"] = submit_result
        if success_count > 0:
            solved_items.append(record)
        else:
            wrong_items.append(record)

    wrong_items.sort(key=lambda item: (-item["attempts"], item["title"]))
    solved_items.sort(key=lambda item: (-item["success_count"], -item["attempts"], item["title"]))

    weakness_titles = [item["title"] for item in wrong_items[:3]]
    pending_review_titles = [item["title"] for item in pending_review_items]
    weakness_tags: list[str] = []
    for item in wrong_items:
        for tag in item.get("tags") or []:
            if tag not in weakness_tags:
                weakness_tags.append(tag)
            if len(weakness_tags) >= 3:
                break
        if len(weakness_tags) >= 3:
            break

    covered_scope = []
    for key in ("covered", "weakness_focus", "review", "new_learning"):
        values = plan_source.get(key) or []
        for value in values:
            if value and value not in covered_scope:
                covered_scope.append(value)
    if not covered_scope:
        covered_scope = [f"{topic} 已学核心内容", f"{topic} 最近练习重点"]

    semantic_valid = semantic_review_is_valid(semantic_review)
    semantic_review = semantic_review if isinstance(semantic_review, dict) else {}
    semantic_status = "ok" if semantic_valid else "missing_artifact"
    overall = str(semantic_review.get("overall") or "").strip() if semantic_valid else ""
    weaknesses = normalize_string_list(semantic_review.get("weaknesses") if semantic_valid else [])
    next_actions = normalize_string_list(semantic_review.get("next_actions") if semantic_valid else [])
    gate = mastery_gate(progress)
    gate_review_reasons: list[str] = []
    if not gate.get("completion_received"):
        gate_review_reasons.append("缺少用户完成信号")
    if not gate.get("reflection_completed"):
        gate_review_reasons.append("缺少 update 前测试复盘证据")
    mastery_status = str(gate.get("status") or "unknown")
    if mastery_status in {"partial", "fragile", "blocked", "solid_after_intervention"}:
        gate_review_reasons.append(f"测试掌握判断为 {mastery_status}")
    for gap in gate.get("blocking_gaps") or []:
        gate_review_reasons.append(str(gap))
    for reinforcement in gate.get("next_session_reinforcement") or []:
        gate_review_reasons.append(str(reinforcement))

    should_review = bool(semantic_review.get("should_review")) if semantic_valid else False
    if gate_review_reasons:
        should_review = True
    can_advance = bool(semantic_review.get("can_advance")) if semantic_valid else False
    can_advance = bool(can_advance and not gate.get("blocks_advance"))
    review_decision = str(semantic_review.get("review_decision") or "").strip() if semantic_valid else "缺少 semantic review artifact"
    advance_decision = str(semantic_review.get("advance_decision") or "").strip() if semantic_valid else "缺少 semantic review artifact"
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
        review_targets=weaknesses,
        should_review=should_review,
        can_advance=can_advance,
    )

    return {
        "topic": topic,
        "date": progress.get("date") or "",
        "session_type": session.get("type") or "test",
        "test_mode": session.get("test_mode"),
        "status": session.get("status") or "active",
        "started_at": session.get("started_at"),
        "finished_at": session.get("finished_at"),
        "total": session_result_summary["total"],
        "attempted": session_result_summary["attempted"],
        "correct": session_result_summary["correct"],
        "result_summary": session_result_summary,
        "pending_review_count": len(pending_review_items),
        "pending_review_items": normalize_string_list(pending_review_titles),
        "overall": overall or None,
        "semantic_status": semantic_status,
        "semantic_missing_requirements": ([] if semantic_valid else ["semantic_review"]),
        "semantic_review": semantic_review if semantic_valid else {},
        "covered_scope": covered_scope[:4],
        "weaknesses": weaknesses,
        "evidence_gate_reasons": normalize_string_list(gate_review_reasons),
        "should_review": should_review,
        "can_advance": can_advance,
        "review_decision": review_decision,
        "advance_decision": advance_decision,
        "next_actions": normalize_string_list(next_actions),
        "wrong_items": wrong_items,
        "solved_items": solved_items[:3],
        "diagnostic_triggers": diagnostic_triggers,
        "diagnostic_targets": diagnostic_targets,
        "review_debt_candidates": review_debt_candidates,
        "mastery": mastery,
        "blocking_weaknesses": weaknesses[:2] if semantic_valid else [],
        "deferred_enhancement": normalize_string_list(semantic_review.get("deferred_enhancement") if semantic_valid else []),
        "user_feedback": progress.get("user_feedback") if isinstance(progress.get("user_feedback"), dict) else {},
    }


def render_log_entry(summary: dict[str, Any], session_dir: Path) -> str:
    covered_text = "；".join(summary["covered_scope"])
    semantic_ready = summary.get("semantic_status") == "ok"
    weakness_text = ("；".join(summary["weaknesses"]) or "暂无明显薄弱项") if semantic_ready else "缺少 semantic review artifact"
    next_text = "；".join(summary["next_actions"]) if semantic_ready else "缺少 semantic review artifact"
    overall_text = summary.get("overall") if semantic_ready else "缺少 semantic review artifact"
    test_mode = summary.get("test_mode") or "general"
    mastery = summary.get("mastery") or {}
    return "\n".join(
        [
            f"### {summary['date']} / {summary['topic']} / 测试更新",
            f"- session 目录：`{session_dir}`",
            f"- 测试模式：{test_mode}",
            f"- 本次测试覆盖范围：{covered_text}",
            f"- 总题数：{summary['total']}",
            f"- 已练习题数：{summary['attempted']}",
            f"- 正确/通过题数：{summary['correct']}",
            f"- 总体表现：{overall_text}",
            f"- semantic review 状态：{summary.get('semantic_status') or 'unknown'}",
            f"- 阅读掌握清单：{'已达标' if mastery.get('reading_done') else '未达标'}",
            f"- session 练习/测试：{'已完成' if mastery.get('session_done') else '未完成'}",
            f"- 小项目/实作：{'已完成' if mastery.get('project_done') else '未完成'}",
            f"- 口头/书面复盘：{'已完成' if mastery.get('reflection_done') else '未完成'}",
            f"- 薄弱项：{weakness_text}",
            f"- 是否应回退复习：{summary['review_decision']}",
            f"- 是否可以进入下一阶段：{summary['advance_decision']}",
            f"- 后续建议：{next_text}",
        ]
    )


def upsert_section(text: str, heading: str, block: str) -> str:
    return upsert_markdown_section(text, heading, block)


def update_learn_plan(plan_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(plan_path)
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "测试记录", block)
    write_text(plan_path, updated)
    append_micro_adjustments(plan_path, summary)


def update_project_log(project_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(project_path)
    if not original and not project_path.exists():
        return
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "Learning Progress Log", block)
    write_text(project_path, updated)


def write_feedback_artifacts(plan_path: Path, summary: dict[str, Any], progress: dict[str, Any], session_dir: Path) -> dict[str, Any]:
    session_facts = build_session_facts(progress, summary, session_dir=session_dir, update_type="test")
    paths = default_workflow_paths(resolve_learning_root(plan_path), plan_path, plan_path.parent / "materials" / "index.json")
    write_json(paths["session_facts_json"], session_facts)
    learner_model = update_learner_model_file(plan_path, summary, session_facts, update_type="test")
    patch_candidate = build_patch_proposal(summary, session_facts, update_type="test")
    patch_queue = update_patch_queue_file(plan_path, summary, session_facts, update_type="test", patch_candidate=patch_candidate)
    return {
        "session_facts": session_facts,
        "learner_model": learner_model,
        "patch_queue": patch_queue,
    }



def write_diagnostic_workflow_artifact(plan_path: Path, summary: dict[str, Any], questions_data: dict[str, Any], session_dir: Path, progress: dict[str, Any] | None = None) -> Path:
    paths = default_workflow_paths(resolve_learning_root(plan_path), plan_path, plan_path.parent / "materials" / "index.json")
    workflow_dir = paths["workflow_state_json"].parent
    diagnostic_path = paths["diagnostic_json"]
    diagnostic_profile = summary.get("diagnostic_profile") if isinstance(summary.get("diagnostic_profile"), dict) else {}
    plan_source = questions_data.get("plan_source") if isinstance(questions_data.get("plan_source"), dict) else {}
    blueprint = plan_source.get("diagnostic_blueprint") if isinstance(plan_source.get("diagnostic_blueprint"), dict) else {}
    blueprint_items = blueprint.get("diagnostic_items") if isinstance(blueprint.get("diagnostic_items"), list) else []
    runtime_question_snapshot = []
    runtime_blueprint_items = []
    for index, item in enumerate(questions_data.get("questions") or [], start=1):
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("id") or f"runtime-question-{index}")
        category = str(item.get("category") or "unknown")
        tags = normalize_string_list(item.get("tags") or [])
        runtime_question_snapshot.append(
            {
                "id": question_id,
                "category": category,
                "question_role": str(item.get("question_role") or ""),
                "tags": tags,
                "source_trace": item.get("source_trace") or {},
            }
        )
        runtime_blueprint_items.append(
            {
                "id": question_id,
                "capability_id": question_id,
                "capability_label": str(item.get("title") or item.get("question") or item.get("prompt") or question_id).strip(),
                "type": category,
                "prompt": str(item.get("prompt") or item.get("question") or item.get("title") or question_id).strip(),
                "expected_signals": tags,
                "rubric": item.get("rubric") or "runtime-fallback",
            }
        )

    session = progress.get("session") if isinstance(progress, dict) and isinstance(progress.get("session"), dict) else {}
    if not blueprint_items:
        blueprint_items = runtime_blueprint_items
    blueprint_item_map: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(blueprint_items, start=1):
        if not isinstance(item, dict):
            continue
        capability_id = str(item.get("capability_id") or item.get("capability") or item.get("id") or f"cap-{index}").strip()
        if not capability_id:
            continue
        normalized_item = dict(item)
        normalized_item["capability_id"] = capability_id
        if "capability" in normalized_item and not normalized_item.get("capability_label"):
            normalized_item["capability_label"] = normalized_item.get("capability")
        blueprint_item_map[capability_id] = normalized_item
    blueprint_items = list(blueprint_item_map.values())

    observed_strengths = set(normalize_string_list(diagnostic_profile.get("observed_strengths") or []))
    observed_weaknesses = set(normalize_string_list(diagnostic_profile.get("observed_weaknesses") or []))
    capability_assessment = []
    seen_capability_ids: set[str] = set()
    for item in blueprint_items:
        capability_id = str(item.get("capability_id") or "").strip()
        if not capability_id or capability_id in seen_capability_ids:
            continue
        seen_capability_ids.add(capability_id)
        capability_label = str(item.get("capability_label") or item.get("prompt") or capability_id).strip()
        if capability_label in observed_strengths or capability_id in observed_strengths:
            current_level = "strength"
            gap = ""
        elif capability_label in observed_weaknesses or capability_id in observed_weaknesses:
            current_level = "weakness"
            gap = "needs-review"
        else:
            current_level = "observed"
            gap = ""
        capability_assessment.append(
            {
                "capability_id": capability_id,
                "capability_label": capability_label,
                "current_level": current_level,
                "target_level": str(summary.get("recommended_entry_level") or diagnostic_profile.get("baseline_level") or "diagnostic").strip(),
                "gap": gap,
                "confidence": diagnostic_profile.get("confidence"),
            }
        )

    candidate = {
        "contract_version": "learn-plan.workflow.v2",
        "stage": "diagnostic",
        "candidate_version": blueprint.get("candidate_version") or "manual.diagnostic-update.v1",
        "diagnostic_plan": {
            "delivery": "web-session",
            "assessment_kind": "initial-test",
            "session_intent": "assessment",
            "plan_execution_mode": "diagnostic",
            "round_index": diagnostic_profile.get("round_index"),
            "max_rounds": diagnostic_profile.get("max_rounds"),
            "questions_per_round": diagnostic_profile.get("questions_per_round"),
            "follow_up_needed": diagnostic_profile.get("follow_up_needed"),
            "question_source": plan_source.get("question_source") or "runtime-generated",
            "diagnostic_generation_mode": plan_source.get("diagnostic_generation_mode") or "runtime-generated-domain-bank",
            "target_capability_ids": normalize_string_list(blueprint.get("target_capability_ids") or []),
            "scoring_rubric": blueprint.get("scoring_rubric") or [],
        },
        "diagnostic_items": blueprint_items,
        "diagnostic_result": {
            "status": "evaluated",
            "overall": summary.get("overall"),
            "recommended_entry_level": summary.get("recommended_entry_level"),
            "follow_up_needed": diagnostic_profile.get("follow_up_needed"),
            "stop_reason": diagnostic_profile.get("stop_reason"),
            "capability_assessment": capability_assessment,
            "confidence": diagnostic_profile.get("confidence"),
        },
        "diagnostic_profile": diagnostic_profile,
        "resume_context": {
            "topic": session.get("resume_topic") or summary.get("topic") or plan_source.get("topic"),
            "goal": session.get("resume_goal") or (plan_source.get("goal_model") or {}).get("mainline_goal") or summary.get("topic"),
            "level": session.get("resume_level") or summary.get("recommended_entry_level") or diagnostic_profile.get("baseline_level") or "diagnostic",
            "schedule": session.get("resume_schedule") or "未指定",
            "preference": session.get("resume_preference") or "混合",
        },
        "runtime_question_snapshot": runtime_question_snapshot,
        "evidence": normalize_string_list(
            list(diagnostic_profile.get("evidence") or [])
            + [f"session_dir={session_dir}", f"recommended_entry_level={summary.get('recommended_entry_level')}", f"question_source={plan_source.get('question_source') or 'runtime-generated'}"]
        ),
        "confidence": diagnostic_profile.get("confidence") or 0.8,
        "generation_trace": {
            "stage": "diagnostic",
            "generator": "learn-test-update",
            "status": "completed",
            "update_type": "diagnostic",
        },
        "traceability": [
            {
                "kind": "session",
                "ref": str(session_dir),
                "title": str(summary.get("topic") or "diagnostic session"),
                "detail": "diagnostic",
                "stage": "diagnostic",
                "status": "recorded",
            }
        ],
    }
    reviewed = review_stage_candidate("diagnostic", candidate)
    reviewed["contract_version"] = "learn-plan.workflow.v2"
    reviewed["stage"] = "diagnostic"
    reviewed["candidate_version"] = reviewed.get("candidate_version") or "manual.diagnostic-update.v1"
    write_json(diagnostic_path, reviewed)
    return diagnostic_path



def print_summary(summary: dict[str, Any], plan_path: Path, project_path: Path | None, *, stdout_json: bool, feedback_result: dict[str, Any] | None = None) -> None:
    semantic_ready = summary.get("semantic_status") == "ok"
    weakness_text = ('；'.join(summary['weaknesses']) or '暂无明显薄弱项') if semantic_ready else '缺少 semantic review artifact'
    overall_text = summary.get("overall") if semantic_ready else "缺少 semantic review artifact"
    print(f"主题：{summary['topic']}")
    print(f"测试模式：{summary.get('test_mode') or 'general'}")
    print(f"覆盖范围：{'；'.join(summary['covered_scope'])}")
    print(f"semantic review 状态：{summary.get('semantic_status') or 'unknown'}")
    print(f"总体表现：{overall_text}")
    print(f"薄弱项：{weakness_text}")
    print(f"是否应回退复习：{summary['review_decision']}")
    next_text = '；'.join(summary['next_actions']) if semantic_ready else '缺少 semantic review artifact'
    print(f"是否进入下一阶段：{summary['advance_decision']}")
    print(f"后续建议：{next_text}")
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
    session = progress.get("session") if isinstance(progress.get("session"), dict) else {}
    questions_data = load_questions_data(session_dir)
    semantic_review = read_json(Path(args.semantic_review_json).expanduser().resolve()) if args.semantic_review_json else None
    semantic_diagnostic = read_json(Path(args.semantic_diagnostic_json).expanduser().resolve()) if args.semantic_diagnostic_json else None
    if is_initial_test_diagnostic_session(session, progress) or is_legacy_plan_diagnostic_session(session):
        questions_map = load_questions_map(questions_data)
        summary = summarize_diagnostic_progress(progress, questions_map, semantic_diagnostic=semantic_diagnostic)
        updated_progress = update_diagnostic_state(progress, summary)
        knowledge_update = update_knowledge_state_from_progress(plan_path, session_dir, updated_progress, questions_map, summary, session_type="diagnostic")
        summary["knowledge_state_update"] = knowledge_update
        write_json(progress_path, updated_progress)
        update_learn_plan_with_diagnostic(plan_path, summary, session_dir)
        write_diagnostic_workflow_artifact(plan_path, summary, questions_data, session_dir, progress=updated_progress)
        paths = default_workflow_paths(resolve_learning_root(plan_path), plan_path, plan_path.parent / "materials" / "index.json")
        diagnostic_data = core_read_json_if_exists(paths["diagnostic_json"])
        diagnostic_plan = diagnostic_data.get("diagnostic_plan") if isinstance(diagnostic_data.get("diagnostic_plan"), dict) else {}
        diagnostic_profile = summary.get("diagnostic_profile") if isinstance(summary.get("diagnostic_profile"), dict) else {}
        follow_up = diagnostic_profile.get("follow_up_needed") or diagnostic_plan.get("follow_up_needed")
        round_index = diagnostic_plan.get("round_index", 0)
        max_rounds = diagnostic_plan.get("max_rounds", 1)
        if follow_up and isinstance(round_index, int) and isinstance(max_rounds, int) and round_index < max_rounds:
            next_round = round_index + 1
            if args.stdout_json:
                print(json.dumps({"pending_patch_count": 0, "next_action": "switch_to:diagnostic", "next_round_index": next_round, "follow_up_needed": True}))
            print(f"\n建议启动第 {next_round} 轮诊断（共 {max_rounds} 轮），运行 /learn-plan 进入续轮")
        feedback_result = write_diagnostic_feedback_artifacts(plan_path, summary, updated_progress, session_dir, update_type="diagnostic")
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
    questions_map = load_questions_map(questions_data)
    summary = summarize_test_progress(progress, questions_data, semantic_review=semantic_review)
    updated_progress = update_progress_state(progress, summary, questions_data=questions_data)
    knowledge_update = update_knowledge_state_from_progress(plan_path, session_dir, updated_progress, questions_map, summary, session_type="test")
    summary["knowledge_state_update"] = knowledge_update
    write_json(progress_path, updated_progress)
    update_learn_plan(plan_path, summary, session_dir)
    feedback_result = write_feedback_artifacts(plan_path, summary, updated_progress, session_dir)
    refresh_workflow_state(plan_path)
    if project_path is not None:
        update_project_log(project_path, summary, session_dir)
    print_summary(summary, plan_path, project_path, stdout_json=args.stdout_json, feedback_result=feedback_result)
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
