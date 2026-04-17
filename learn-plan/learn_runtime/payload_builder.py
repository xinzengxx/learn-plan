from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_string_list
from learn_core.topic_family import infer_domain as core_infer_domain
from learn_runtime.lesson_builder import build_grounded_daily_lesson_plan, build_lesson_grounding_context
from learn_runtime.material_selection import select_material_segments
from learn_runtime.plan_source import DEFAULT_TOPIC_FAMILIES, make_plan_source
from learn_runtime.question_banks import build_question_bank, domain_supports_code_questions, select_python_questions
from learn_runtime.question_generation import (
    build_content_driven_questions,
    count_content_questions,
    count_llm_lesson_questions,
    generate_questions_from_lesson_with_llm,
    merge_question_pools,
)
from learn_runtime.question_validation import ensure_questions_payload_quality


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


def build_questions_payload(args: argparse.Namespace, topic: str, plan_text: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
    session_dir = Path(args.session_dir).expanduser().resolve()
    plan_path = Path(args.plan_path).expanduser().resolve()
    domain = core_infer_domain(topic, DEFAULT_TOPIC_FAMILIES, fallback_text=plan_text)
    bank_concept, bank_code = build_question_bank(domain)
    if not domain_supports_code_questions(domain):
        bank_code = []
    plan_source = make_plan_source(topic, args.session_type, args.test_mode, plan_text, plan_path, args)
    plan_source["topic"] = topic
    plan_source["domain"] = domain
    selected_segments, mastery_targets = select_material_segments(materials, plan_source)
    execution_mode = str(plan_source.get("plan_execution_mode") or "normal")
    if execution_mode in {"clarification", "research", "diagnostic", "test-diagnostic"}:
        selected_segments = []
        mastery_targets = {
            "reading_checklist": normalize_string_list(plan_source.get("plan_blockers") or []),
            "session_exercises": normalize_string_list(plan_source.get("exercise_focus") or []),
            "applied_project": [],
            "reflection": ["用自己的话解释当前为什么还不能直接进入正式主线学习"],
        }
    elif execution_mode == "prestudy":
        if selected_segments:
            mastery_targets["reading_checklist"] = normalize_string_list(plan_source.get("plan_blockers") or []) + normalize_string_list(mastery_targets.get("reading_checklist") or [])
            mastery_targets["reflection"] = normalize_string_list(mastery_targets.get("reflection") or []) + ["用自己的话解释当前确认项与所选资料段落的关系"]
        else:
            mastery_targets = {
                "reading_checklist": normalize_string_list(plan_source.get("plan_blockers") or []),
                "session_exercises": normalize_string_list(plan_source.get("exercise_focus") or []),
                "applied_project": [],
                "reflection": ["用自己的话解释当前为什么还不能直接进入正式主线学习"],
            }
    lesson_grounding_context = build_lesson_grounding_context(topic, plan_source, selected_segments, mastery_targets)
    if domain:
        lesson_grounding_context["domain"] = domain
    daily_lesson_plan = build_grounded_daily_lesson_plan(topic, plan_source, selected_segments, mastery_targets, lesson_grounding_context)
    lesson_grounding_context["lesson_generation_mode"] = daily_lesson_plan.get("lesson_generation_mode")
    plan_source["lesson_grounding_context"] = lesson_grounding_context
    plan_source["selected_segments"] = selected_segments
    plan_source["mastery_targets"] = mastery_targets
    plan_source["daily_lesson_plan"] = daily_lesson_plan
    plan_source["lesson_generation_mode"] = daily_lesson_plan.get("lesson_generation_mode")
    plan_source["daily_plan_artifact_path"] = str(plan_path.parent / f"learn-today-{args.date}.md")
    plan_source["session_objectives"] = [
        "先确认真实进度，再决定今日复习与新学习内容",
        "围绕 selected segments 阅读、练习与复盘",
        "结合掌握度检验结果决定是否推进",
    ]
    if execution_mode in {"clarification", "research", "diagnostic", "test-diagnostic"}:
        plan_source["session_objectives"] = [
            "先解除当前 gate 阻塞，再决定是否进入正式主线学习",
            "围绕顾问式澄清、研究确认或诊断任务完成本次 session",
            "完成阻塞项后再进入下一轮正式编排",
        ]
    elif execution_mode == "prestudy":
        plan_source["session_objectives"] = [
            "保留已选资料段落，先完成确认项与资料预读",
            "围绕 selected segments 做轻量讲解和练习，避免退回泛化题库",
            "确认 gate 解除后再进入正式主线推进",
        ]
    plan_source["gating_decision"] = (
        "若 selected segments 未完成或阅读掌握清单未达标，则优先补读与复习；"
        "若 session 与复盘连续稳定，才允许推进到下一阶段。"
    )
    if execution_mode in {"clarification", "research", "diagnostic", "test-diagnostic"}:
        plan_source["gating_decision"] = "当前计划尚未通过执行 gate，本次 session 先处理阻塞项，不直接进入正式主线推进。"
    elif execution_mode == "prestudy":
        plan_source["gating_decision"] = "当前处于预读/确认模式，但会保留有效 selected segments，避免题目退回无关泛化题库。"

    planning_state = dict(plan_source.get("planning_state") or {})
    diagnostic_profile = dict(plan_source.get("diagnostic_profile") or {})
    assessment_depth = plan_source.get("assessment_depth") or planning_state.get("assessment_depth") or diagnostic_profile.get("assessment_depth")
    round_index = plan_source.get("round_index") or planning_state.get("diagnostic_round_index") or diagnostic_profile.get("round_index")
    max_rounds = plan_source.get("max_rounds") or planning_state.get("diagnostic_max_rounds") or diagnostic_profile.get("max_rounds")
    follow_up_needed = plan_source.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = planning_state.get("diagnostic_follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = diagnostic_profile.get("follow_up_needed")
    stop_reason = plan_source.get("stop_reason") or diagnostic_profile.get("stop_reason")
    if assessment_depth is not None:
        plan_source["assessment_depth"] = assessment_depth
    if round_index is not None:
        plan_source["round_index"] = round_index
    if max_rounds is not None:
        plan_source["max_rounds"] = max_rounds
    if follow_up_needed is not None:
        plan_source["follow_up_needed"] = follow_up_needed
    if stop_reason:
        plan_source["stop_reason"] = stop_reason

    session_type = args.session_type
    assessment_kind = None
    session_intent = "learning" if session_type == "today" else "assessment"
    explicit_diagnostic_stage = str(plan_source.get("current_stage") or "").strip().lower() in {"diagnostic", "test-diagnostic"}
    explicit_diagnostic_stop_reason = str(plan_source.get("stop_reason") or "").strip().lower().startswith("diagnostic")
    if execution_mode in {"diagnostic", "test-diagnostic"} or explicit_diagnostic_stage or explicit_diagnostic_stop_reason:
        session_type = "test"
        assessment_kind = "initial-test"
        session_intent = "assessment"
    elif session_type == "test":
        assessment_kind = "stage-test"
    test_mode = args.test_mode if session_type == "test" else None
    if test_mode is None and session_type == "test":
        test_mode = "general"

    mode = "today-generated" if session_type == "today" else f"test-{test_mode or 'general'}"
    if domain == "git" and session_type == "today":
        mode = "today-git-grounded"

    python_selection_context: dict[str, Any] = {}
    selected_bank_concept = bank_concept
    selected_bank_code = bank_code
    if domain == "python":
        selected_bank_concept, selected_bank_code, python_selection_context = select_python_questions(bank_concept, bank_code, plan_source)

    diagnostic_first = assessment_kind == "initial-test" or execution_mode in {"diagnostic", "test-diagnostic"}
    if diagnostic_first:
        content_concept, content_code, content_written = [], [], []
        content_generation_context = {
            "selection_policy": "disabled-for-initial-diagnostic",
            "lesson_generation_mode": daily_lesson_plan.get("lesson_generation_mode"),
            "attempted_segments": 0,
            "source_segment_ids": [],
            "generated_concept_count": 0,
            "generated_code_count": 0,
            "generated_written_count": 0,
        }
        llm_concept = []
        llm_question_generation_context = {
            "mode": "disabled-for-initial-diagnostic",
            "generated_count": 0,
        }
    else:
        content_concept, content_code, content_written, content_generation_context = build_content_driven_questions(domain, plan_source, selected_segments, daily_lesson_plan)
        llm_concept, llm_question_generation_context = generate_questions_from_lesson_with_llm(domain, lesson_grounding_context, daily_lesson_plan, limit=5)
    if diagnostic_first:
        concept_limit = len(selected_bank_concept) if selected_bank_concept else (7 if domain in {"python", "git"} else len(bank_concept))
        code_limit = len(selected_bank_code) if selected_bank_code else (4 if domain == "python" else (len(bank_code) if domain_supports_code_questions(domain) else 0))
        concept_pools = [selected_bank_concept] if selected_bank_concept else [bank_concept]
        code_pools = [selected_bank_code] if selected_bank_code else [bank_code]
    else:
        concept_limit = 7 if domain in {"python", "git"} else len(selected_bank_concept)
        code_limit = 7 if domain == "python" else (len(selected_bank_code) if domain_supports_code_questions(domain) else 0)
        concept_pools = [llm_concept, content_concept, selected_bank_concept, bank_concept]
        code_pools = [content_code, selected_bank_code, bank_code]
    written_limit = 0 if diagnostic_first else (2 if selected_segments else 0)
    concept = merge_question_pools(concept_pools, limit=concept_limit)
    code = merge_question_pools(code_pools, limit=code_limit)
    written = merge_question_pools([content_written], limit=written_limit)
    questions = concept + code + written
    if diagnostic_first:
        plan_source["question_generation_mode"] = "diagnostic-first-domain-bank"
    else:
        plan_source["question_generation_mode"] = "llm-lesson-derived" if llm_concept else ("content-derived" if content_concept or content_code or content_written else "domain-bank-fallback")
    plan_source["lesson_path"] = str(session_dir / "lesson.md")
    quality_context = {
        "source_grounding_required": bool(selected_segments),
        "question_traceability_required": True,
    }
    payload = {
        "date": args.date,
        "topic": topic,
        "domain": domain,
        "mode": mode,
        "session_type": session_type,
        "session_intent": session_intent,
        "assessment_kind": assessment_kind,
        "test_mode": test_mode,
        "plan_source": plan_source,
        "selection_context": {
            "domain": domain,
            "source_kind": plan_source.get("source_kind") or plan_source.get("basis") or "plan-markdown-fallback",
            "current_stage": plan_source.get("current_stage"),
            "current_day": plan_source.get("day"),
            "topic_cluster": plan_source.get("today_topic"),
            "difficulty_target": plan_source.get("difficulty_target"),
            "assessment_depth": assessment_depth,
            "round_index": round_index,
            "max_rounds": max_rounds,
            "follow_up_needed": follow_up_needed,
            "stop_reason": stop_reason,
            "selection_policy": python_selection_context.get("selection_policy") if domain == "python" else "domain-bank-fallback",
            "target_stages": python_selection_context.get("target_stages") if domain == "python" else [],
            "target_clusters": python_selection_context.get("target_clusters") if domain == "python" else [],
            "resolved_target_clusters": python_selection_context.get("resolved_target_clusters") if domain == "python" else [],
            "segment_target_clusters": python_selection_context.get("segment_target_clusters") if domain == "python" else [],
            "cluster_selection_basis": python_selection_context.get("cluster_selection_basis") if domain == "python" else None,
            "concept_pool_policy": python_selection_context.get("concept_pool_policy") if domain == "python" else None,
            "code_pool_policy": python_selection_context.get("code_pool_policy") if domain == "python" else None,
            "adjacent_fill_allowed": python_selection_context.get("adjacent_fill_allowed") if domain == "python" else None,
            "selected_segments": selected_segments,
            "mastery_targets": mastery_targets,
            "daily_lesson_plan": daily_lesson_plan,
            "material_alignment": plan_source.get("material_alignment") or {},
            "content_question_generation": {
                **content_generation_context,
                "llm_question_generation": llm_question_generation_context,
                "llm_generated_concept_count": len(llm_concept),
                "llm_generated_concept_kept": count_llm_lesson_questions(concept),
                "generated_concept_kept": count_content_questions(concept),
                "generated_code_kept": count_content_questions(code),
                "generated_written_kept": count_content_questions(written),
                "bank_fallback_used": len(concept) > (len(llm_concept) + len(content_concept)) or len(code) > len(content_code),
            },
            "question_mix": {
                "concept": {"count": len(concept), "roles": [str(item.get("question_role") or "") for item in concept]},
                "code": {"count": len(code), "roles": [str(item.get("question_role") or "") for item in code]},
                "written": {"count": len(written), "roles": [str(item.get("question_role") or "") for item in written]},
            },
            "quality_context": quality_context,
        },
        "materials": materials,
        "questions": questions,
    }
    question_quality = ensure_questions_payload_quality(payload)
    plan_source["question_quality"] = question_quality
    payload["selection_context"]["question_quality"] = question_quality
    payload_traceability = list(question_quality.get("traceability") or [])
    for segment in selected_segments[:8]:
        if not isinstance(segment, dict):
            continue
        ref = str(segment.get("segment_id") or segment.get("material_id") or segment.get("material_title") or "").strip()
        if not ref:
            continue
        payload_traceability.append(
            build_traceability_entry(
                kind="material-segment",
                ref=ref,
                title=segment.get("material_title") or segment.get("label") or ref,
                detail=segment.get("match_reason") or segment.get("purpose"),
                stage="questions",
                status=segment.get("source_status") or "selected",
                locator=(segment.get("locator") or {}).get("chapter") if isinstance(segment.get("locator"), dict) else None,
            )
        )
    payload = apply_quality_envelope(
        payload,
        stage="questions",
        generator="runtime-payload-builder",
        evidence=question_quality.get("evidence") or [
            f"question_generation_mode={plan_source.get('question_generation_mode') or 'unknown'}",
            f"question_count={len(questions)}",
        ],
        confidence=question_quality.get("confidence"),
        quality_review={
            "reviewer": "runtime-payload-builder",
            "valid": bool((question_quality.get("quality_review") or {}).get("valid", question_quality.get("valid"))),
            "issues": (question_quality.get("quality_review") or {}).get("issues") or question_quality.get("issues") or [],
            "warnings": (question_quality.get("quality_review") or {}).get("warnings") or question_quality.get("warnings") or [],
            "confidence": (question_quality.get("quality_review") or {}).get("confidence") or question_quality.get("confidence"),
            "evidence_adequacy": (question_quality.get("quality_review") or {}).get("evidence_adequacy") or "sufficient",
            "verdict": (question_quality.get("quality_review") or {}).get("verdict") or ("ready" if question_quality.get("valid") else "needs-revision"),
        },
        generation_trace={
            "stage": "questions",
            "generator": "runtime-payload-builder",
            "status": "ready",
            "question_generation_mode": plan_source.get("question_generation_mode"),
            "question_count": len(questions),
        },
        traceability=payload_traceability,
    )
    ensure_question_shape(payload)
    return payload


__all__ = [
    "build_questions_payload",
    "ensure_question_shape",
]
