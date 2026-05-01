from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists as core_read_json_if_exists
from learn_core.quality_review import apply_quality_envelope, build_traceability_entry, normalize_confidence
from learn_core.text_utils import normalize_string_list
from learn_core.topic_family import infer_domain as core_infer_domain
from learn_runtime.lesson_builder import (
    build_daily_lesson_plan,
    build_lesson_grounding_context,
    build_lesson_quality_artifact,
    normalize_llm_daily_lesson_payload,
)
from learn_runtime.question_generation import (
    build_content_driven_questions,
    build_question_review,
    infer_question_role_from_primary_category,
    merge_question_review_results,
    normalize_generated_runtime_questions,
    normalize_question_repair_plan,
    normalize_strict_question_review,
)
from learn_runtime.material_selection import select_material_segments
from learn_runtime.plan_source import DEFAULT_TOPIC_FAMILIES, make_plan_source, normalize_language_policy
from learn_runtime.question_banks import build_question_bank, build_python_question_generation_seed, domain_supports_code_questions
from learn_runtime.question_validation import ensure_questions_payload_quality
from learn_runtime.schemas import (
    ensure_dataset_artifact_basic,
    ensure_parameter_artifact_basic,
    ensure_parameter_spec_basic,
    ensure_question_plan_basic,
    ensure_question_scope_basic,
    ensure_questions_basic,
)


def ensure_question_shape(data: dict[str, Any]) -> None:
    ensure_questions_basic(data)


def resolve_session_semantics(args: argparse.Namespace, plan_source: dict[str, Any], execution_mode: str) -> dict[str, Any]:
    session_type = args.session_type
    assessment_kind = None
    session_intent = "learning" if session_type == "today" else "assessment"
    locked_execution_mode = str(plan_source.get("locked_plan_execution_mode") or "").strip()
    explicit_stage_arg = str(getattr(args, "current_stage", "") or "").strip().lower()
    explicit_stop_reason_arg = str(getattr(args, "stop_reason", "") or "").strip().lower()
    explicit_diagnostic_stage = explicit_stage_arg in {"diagnostic", "test-diagnostic"}
    explicit_diagnostic_stop_reason = explicit_stop_reason_arg.startswith("diagnostic")
    forced_initial_diagnostic = locked_execution_mode in {"diagnostic", "test-diagnostic"}
    resolved_execution_mode = execution_mode
    if forced_initial_diagnostic:
        resolved_execution_mode = locked_execution_mode
        plan_source["plan_execution_mode"] = locked_execution_mode
    semantic_profile = "today"
    if forced_initial_diagnostic or explicit_diagnostic_stage or explicit_diagnostic_stop_reason:
        session_type = "test"
        assessment_kind = "initial-test"
        session_intent = "assessment"
        semantic_profile = "initial-test"
        plan_source["current_stage"] = "diagnostic"
    elif session_type == "test":
        assessment_kind = "stage-test"
        semantic_profile = "stage-test"
    plan_source["session_type"] = session_type
    plan_source["assessment_kind"] = assessment_kind
    plan_source["session_intent"] = session_intent
    plan_source["semantic_profile"] = semantic_profile
    return {
        "session_type": session_type,
        "assessment_kind": assessment_kind,
        "session_intent": session_intent,
        "semantic_profile": semantic_profile,
        "execution_mode": resolved_execution_mode,
    }


def load_optional_payload(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    payload = core_read_json_if_exists(path)
    return payload if isinstance(payload, dict) and payload else None


def build_runtime_lesson_artifact(
    topic: str,
    plan_source: dict[str, Any],
    selected_segments: list[dict[str, Any]],
    mastery_targets: dict[str, list[str]],
    grounding_context: dict[str, Any],
    lesson_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    fallback_plan = build_daily_lesson_plan(topic, plan_source, selected_segments, mastery_targets)
    if not isinstance(lesson_artifact, dict) or not lesson_artifact:
        raise ValueError("缺少 Agent 生成的 lesson artifact：请先派 subagent 生成 lesson-artifact-json，再调用 session_orchestrator.py")
    candidate = lesson_artifact.get("lesson") if isinstance(lesson_artifact.get("lesson"), dict) else lesson_artifact
    normalized = normalize_llm_daily_lesson_payload(candidate, fallback_plan)
    if normalized is None:
        raise ValueError("lesson artifact 结构无效：请让 subagent 依据 runtime input bundle 重新生成 lesson-artifact-json")
    normalized["lesson_generation_mode"] = "harness-injected"
    metadata = dict(lesson_artifact.get("generation_trace") or {})
    metadata.setdefault("status", "ok")
    metadata.setdefault("artifact_source", "agent-subagent")
    metadata.setdefault("reason", "lesson-artifact-json")
    return build_lesson_quality_artifact(normalized, metadata)


def normalize_injected_question_review(review_artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(review_artifact, dict) or not review_artifact:
        raise ValueError("缺少 Agent 生成的 strict question review artifact：请先派 subagent 审查 question-artifact-json")
    metadata = dict(review_artifact.get("metadata") or {})
    metadata.setdefault("status", str(review_artifact.get("status") or "completed").strip() or "completed")
    metadata.setdefault("artifact_source", str(review_artifact.get("artifact_source") or "agent-subagent").strip() or "agent-subagent")
    return normalize_strict_question_review(review_artifact, metadata)


def _require_question_scope_and_plan(question_scope: dict[str, Any] | None, question_plan: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(question_scope, dict) or not question_scope:
        raise ValueError("缺少 Agent 生成的 question scope artifact：请先生成 question-scope-json")
    if not isinstance(question_plan, dict) or not question_plan:
        raise ValueError("缺少 Agent 生成的 question plan artifact：请先生成 question-plan-json")
    ensure_question_scope_basic(question_scope)
    ensure_question_plan_basic(question_plan)
    if str(question_plan.get("scope_id") or "").strip() != str(question_scope.get("scope_id") or "").strip():
        raise ValueError("question plan 与 question scope 的 scope_id 不一致")
    return question_scope, question_plan


def _load_runtime_context(args: argparse.Namespace) -> dict[str, Any]:
    parameter_spec = load_optional_payload(getattr(args, "parameter_spec_json", None))
    parameter_artifact = load_optional_payload(getattr(args, "parameter_artifact_json", None))
    dataset_artifact = load_optional_payload(getattr(args, "dataset_artifact_json", None))
    materialized_datasets = load_optional_payload(getattr(args, "materialized_dataset_json", None))
    mysql_config = load_optional_payload(getattr(args, "mysql_config_json", None))
    if parameter_spec is not None:
        ensure_parameter_spec_basic(parameter_spec)
    if parameter_artifact is not None:
        ensure_parameter_artifact_basic(parameter_artifact)
    if dataset_artifact is not None:
        ensure_dataset_artifact_basic(dataset_artifact)
    return {
        "parameter_spec": parameter_spec,
        "parameter_artifact": parameter_artifact,
        "dataset_artifact": dataset_artifact,
        "materialized_datasets": materialized_datasets,
        "mysql_runtime": {
            "config": mysql_config,
            "skip_materialize": bool(getattr(args, "skip_materialize", False)),
            "configured": bool(mysql_config or materialized_datasets),
        },
    }


def build_assessment_context_artifact_from_scope(
    topic: str,
    plan_source: dict[str, Any],
    question_scope: dict[str, Any],
    question_plan: dict[str, Any],
    language_policy: dict[str, Any],
) -> dict[str, Any]:
    minimum_pass_shape = dict(question_plan.get("minimum_pass_shape") or question_scope.get("minimum_pass_shape") or {})
    target_capability_ids = normalize_string_list(question_scope.get("target_capability_ids") or [])
    context = {
        "topic": topic,
        "language_policy": language_policy,
        "lesson_generation_mode": "assessment-scope",
        "assessment_kind": question_scope.get("assessment_kind"),
        "session_intent": question_scope.get("session_intent") or "assessment",
        "semantic_profile": "initial-test" if question_scope.get("source_profile") == "initial-diagnostic" else "stage-test",
        "question_source": "agent-injected",
        "diagnostic_generation_mode": "agent-injected" if question_scope.get("source_profile") == "initial-diagnostic" else plan_source.get("diagnostic_generation_mode"),
        "target_capability_ids": target_capability_ids,
        "minimum_pass_shape": minimum_pass_shape,
        "difficulty_target": question_scope.get("difficulty_target") or {},
        "lesson_focus_points": normalize_string_list(question_scope.get("lesson_focus_points") or question_scope.get("target_concepts") or []),
        "project_tasks": normalize_string_list(question_scope.get("project_tasks") or []),
        "project_blockers": normalize_string_list(question_scope.get("project_blockers") or []),
        "review_targets": normalize_string_list(question_scope.get("review_targets") or []),
        "today_teaching_brief": {
            "lesson_focus_points": normalize_string_list(question_scope.get("target_concepts") or question_scope.get("lesson_focus_points") or []),
            "review_targets": normalize_string_list(question_scope.get("review_targets") or []),
        },
        "lesson_review": {"valid": True, "issues": [], "warnings": [], "verdict": "assessment-scope"},
        "question_scope": question_scope,
        "question_plan": question_plan,
        "generation_trace": {"status": "ok", "artifact_source": "question-scope-json", "reason": "assessment-scope"},
        "quality_review": {"valid": True, "issues": [], "warnings": [], "verdict": "assessment-scope"},
    }
    return context


def build_questions_payload(args: argparse.Namespace, topic: str, plan_text: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
    session_dir = Path(args.session_dir).expanduser().resolve()
    plan_path = Path(args.plan_path).expanduser().resolve()
    lesson_artifact = load_optional_payload(getattr(args, "lesson_artifact_json", None))
    question_scope, question_plan = _require_question_scope_and_plan(
        load_optional_payload(getattr(args, "question_scope_json", None)),
        load_optional_payload(getattr(args, "question_plan_json", None)),
    )
    question_artifact = load_optional_payload(getattr(args, "question_artifact_json", None))
    review_artifact = load_optional_payload(getattr(args, "question_review_json", None))
    runtime_context = _load_runtime_context(args)
    domain = core_infer_domain(topic, DEFAULT_TOPIC_FAMILIES, fallback_text=plan_text)
    bank_concept, bank_code = build_question_bank(domain)
    if not domain_supports_code_questions(domain):
        bank_code = []
    plan_source = make_plan_source(topic, args.session_type, args.test_mode, plan_text, plan_path, args)
    language_policy = normalize_language_policy(plan_source.get("language_policy"))
    plan_source["language_policy"] = language_policy
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
    lesson_grounding_context["language_policy"] = language_policy
    lesson_grounding_context["question_scope"] = question_scope
    lesson_grounding_context["question_plan"] = question_plan
    if domain:
        lesson_grounding_context["domain"] = domain
    if args.session_type == "today":
        daily_lesson_plan = build_runtime_lesson_artifact(
            topic,
            plan_source,
            selected_segments,
            mastery_targets,
            lesson_grounding_context,
            lesson_artifact,
        )
    else:
        daily_lesson_plan = build_assessment_context_artifact_from_scope(topic, plan_source, question_scope, question_plan, language_policy)
    lesson_review = dict(daily_lesson_plan.get("lesson_review") or daily_lesson_plan.get("quality_review") or {})
    today_teaching_brief = dict(daily_lesson_plan.get("today_teaching_brief") or {})
    if execution_mode in {"diagnostic", "test-diagnostic"}:
        lesson_focus_points = normalize_string_list(plan_source.get("lesson_focus_points") or [])
        project_tasks = normalize_string_list(plan_source.get("project_tasks") or [])
        project_blockers = normalize_string_list(plan_source.get("project_blockers") or [])
        review_targets = normalize_string_list(plan_source.get("review_targets") or [])
    else:
        lesson_focus_points = normalize_string_list(
            daily_lesson_plan.get("lesson_focus_points") or today_teaching_brief.get("lesson_focus_points") or []
        )
        project_tasks = normalize_string_list(
            daily_lesson_plan.get("project_tasks") or today_teaching_brief.get("project_tasks") or []
        )
        project_blockers = normalize_string_list(
            daily_lesson_plan.get("project_blockers") or today_teaching_brief.get("project_blockers") or []
        )
        review_targets = normalize_string_list(
            daily_lesson_plan.get("review_targets") or today_teaching_brief.get("review_targets") or []
        )
    daily_lesson_plan["language_policy"] = language_policy
    lesson_grounding_context["language_policy"] = language_policy
    lesson_grounding_context["lesson_generation_mode"] = daily_lesson_plan.get("lesson_generation_mode")
    lesson_grounding_context["today_teaching_brief"] = today_teaching_brief
    lesson_grounding_context["lesson_review"] = lesson_review
    lesson_grounding_context["lesson_focus_points"] = lesson_focus_points
    lesson_grounding_context["project_tasks"] = project_tasks
    lesson_grounding_context["project_blockers"] = project_blockers
    lesson_grounding_context["review_targets"] = review_targets
    plan_source["question_scope"] = question_scope
    plan_source["question_plan"] = question_plan
    daily_lesson_plan["question_scope"] = question_scope
    daily_lesson_plan["question_plan"] = question_plan
    plan_source["lesson_grounding_context"] = lesson_grounding_context
    plan_source["selected_segments"] = selected_segments
    plan_source["mastery_targets"] = mastery_targets
    plan_source["daily_lesson_plan"] = daily_lesson_plan
    plan_source["today_teaching_brief"] = today_teaching_brief
    plan_source["lesson_review"] = lesson_review
    plan_source["lesson_focus_points"] = lesson_focus_points
    plan_source["project_tasks"] = project_tasks
    plan_source["project_blockers"] = project_blockers
    plan_source["review_targets"] = review_targets
    plan_source["lesson_generation_mode"] = daily_lesson_plan.get("lesson_generation_mode")
    plan_source["daily_plan_artifact_path"] = str(plan_path.parent / f"learn-today-{args.date}.ipynb")
    plan_source["lesson_notebook_path"] = str(plan_path.parent / f"learn-today-{args.date}.ipynb")
    plan_source["lesson_markdown_path"] = str(plan_path.parent / f"learn-today-{args.date}.md")
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
    round_index = plan_source.get("round_index") or planning_state.get("diagnostic_round_index") or diagnostic_profile.get("round_index")
    max_rounds = plan_source.get("max_rounds") or planning_state.get("diagnostic_max_rounds") or diagnostic_profile.get("max_rounds")
    questions_per_round = plan_source.get("questions_per_round") or planning_state.get("questions_per_round") or diagnostic_profile.get("questions_per_round")
    follow_up_needed = plan_source.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = planning_state.get("diagnostic_follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = diagnostic_profile.get("follow_up_needed")
    stop_reason = plan_source.get("stop_reason") or diagnostic_profile.get("stop_reason")
    if round_index is not None:
        plan_source["round_index"] = round_index
    if max_rounds is not None:
        plan_source["max_rounds"] = max_rounds
    if questions_per_round is not None:
        plan_source["questions_per_round"] = questions_per_round
    if follow_up_needed is not None:
        plan_source["follow_up_needed"] = follow_up_needed
    if stop_reason:
        plan_source["stop_reason"] = stop_reason

    session_semantics = resolve_session_semantics(args, plan_source, execution_mode)
    session_type = str(session_semantics.get("session_type") or args.session_type)
    assessment_kind = session_semantics.get("assessment_kind")
    session_intent = str(session_semantics.get("session_intent") or ("learning" if session_type == "today" else "assessment"))
    semantic_profile = str(session_semantics.get("semantic_profile") or ("today" if session_type == "today" else "stage-test"))
    execution_mode = str(session_semantics.get("execution_mode") or execution_mode)
    history_state = plan_source.get("history_state") if isinstance(plan_source.get("history_state"), dict) else {}
    if session_type == "test" and assessment_kind == "stage-test" and bool(history_state.get("user_action_required")):
        guidance = str(history_state.get("guidance") or "当前缺少可用于阶段测试的学习记录，请先确认学习路径或先开始学习。")
        reason = str(history_state.get("reason") or history_state.get("lookup_status") or "history-missing")
        sessions_dir = str(history_state.get("sessions_dir") or "")
        detail = f"；sessions目录：{sessions_dir}" if sessions_dir else ""
        raise ValueError(f"stage-test 缺少历史记录：{reason}。{guidance}{detail}")
    if session_type == "test" and assessment_kind == "stage-test" and execution_mode in {"clarification", "research", "diagnostic", "test-diagnostic"}:
        raise ValueError(
            f"当前 learn-plan 仍处于 {execution_mode} gate，不能启动普通 stage-test。"
            "请先继续 /learn-plan，或通过 switch_to:diagnostic / --locked-plan-execution-mode 启动 initial-test。"
        )
    test_mode = args.test_mode if session_type == "test" else None
    if test_mode is None and session_type == "test":
        test_mode = "general"

    mode = "today-generated" if session_type == "today" else f"test-{test_mode or 'general'}"
    if domain == "git" and session_type == "today":
        mode = "today-git-grounded"

    diagnostic_first = assessment_kind == "initial-test" or execution_mode in {"diagnostic", "test-diagnostic"}
    python_selection_context: dict[str, Any] = {}
    selected_bank_concept = bank_concept
    selected_bank_code = bank_code
    diagnostic_review_attempts: list[dict[str, Any]] = []
    diagnostic_repair_plan: dict[str, Any] = {}
    bank_fallback_used = False
    grounded_generation_shortfalls: list[str] = []
    diagnostic_blueprint = plan_source.get("diagnostic_blueprint") if isinstance(plan_source.get("diagnostic_blueprint"), dict) else {}
    diagnostic_blueprint_basis = plan_source.get("diagnostic_blueprint_basis") if isinstance(plan_source.get("diagnostic_blueprint_basis"), dict) else {}
    diagnostic_blueprint_tags = normalize_string_list(
        diagnostic_blueprint.get("target_capability_ids") or diagnostic_blueprint_basis.get("target_capability_ids") or []
    )
    scope_target_capability_ids = normalize_string_list(question_scope.get("target_capability_ids") or [])
    resolved_target_capability_ids = scope_target_capability_ids or diagnostic_blueprint_tags or normalize_string_list(plan_source.get("target_capability_ids") or [])
    if resolved_target_capability_ids:
        plan_source["target_capability_ids"] = resolved_target_capability_ids
    if isinstance(question_scope.get("difficulty_target"), dict) and question_scope.get("difficulty_target"):
        plan_source["difficulty_target"] = question_scope.get("difficulty_target")
    lesson_grounding_context["assessment_kind"] = assessment_kind
    lesson_grounding_context["session_intent"] = session_intent
    lesson_grounding_context["semantic_profile"] = semantic_profile
    lesson_grounding_context["question_source"] = plan_source.get("question_source")
    lesson_grounding_context["diagnostic_generation_mode"] = plan_source.get("diagnostic_generation_mode")
    lesson_grounding_context["target_capability_ids"] = resolved_target_capability_ids
    lesson_grounding_context["round_index"] = round_index
    lesson_grounding_context["max_rounds"] = max_rounds
    lesson_grounding_context["questions_per_round"] = questions_per_round
    lesson_grounding_context["follow_up_needed"] = follow_up_needed
    lesson_grounding_context["stop_reason"] = stop_reason
    lesson_grounding_context["diagnostic_blueprint_version"] = plan_source.get("diagnostic_blueprint_version")
    daily_lesson_plan["assessment_kind"] = assessment_kind
    daily_lesson_plan["session_intent"] = session_intent
    daily_lesson_plan["semantic_profile"] = semantic_profile
    daily_lesson_plan["question_source"] = plan_source.get("question_source")
    daily_lesson_plan["diagnostic_generation_mode"] = plan_source.get("diagnostic_generation_mode")
    daily_lesson_plan["target_capability_ids"] = resolved_target_capability_ids
    daily_lesson_plan["round_index"] = round_index
    daily_lesson_plan["max_rounds"] = max_rounds
    daily_lesson_plan["questions_per_round"] = questions_per_round
    daily_lesson_plan["follow_up_needed"] = follow_up_needed
    daily_lesson_plan["stop_reason"] = stop_reason
    daily_lesson_plan["diagnostic_blueprint_version"] = plan_source.get("diagnostic_blueprint_version")

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
        # 新设计：不再要求 diagnostic_blueprint。题目由外部 Agent 注入。
        plan_source["question_generation_mode"] = "agent-injected"
        plan_source["question_source"] = "agent-injected"
        plan_source["diagnostic_generation_mode"] = "agent-injected"
        lesson_grounding_context["question_source"] = "agent-injected"
        lesson_grounding_context["diagnostic_generation_mode"] = "agent-injected"
        lesson_grounding_context["target_capability_ids"] = diagnostic_blueprint_tags or normalize_string_list(plan_source.get("target_capability_ids") or [])
        lesson_grounding_context["semantic_profile"] = "initial-test"
        daily_lesson_plan["question_source"] = "agent-injected"
        daily_lesson_plan["diagnostic_generation_mode"] = "agent-injected"
        daily_lesson_plan["target_capability_ids"] = diagnostic_blueprint_tags or normalize_string_list(plan_source.get("target_capability_ids") or [])
        daily_lesson_plan["semantic_profile"] = "initial-test"
        questions_per_round_limit = 0
        try:
            questions_per_round_limit = int(questions_per_round)
        except (TypeError, ValueError):
            questions_per_round_limit = 0
        questions_per_round_limit = max(1, questions_per_round_limit) if questions_per_round_limit else 0
        # 简单：题量和 mix 由注入的 question_artifact 决定，不定死 domain bank 逻辑
        python_selection_context: dict[str, Any] = {"selection_policy": "agent-injected"}
        runtime_question_mix = {"concept": questions_per_round_limit or 8, "code": 0, "open": 0}
        questions = normalize_generated_runtime_questions(
            question_artifact,
            domain,
            limit=questions_per_round_limit or 8,
            default_question_source="agent-injected",
            default_source_status="agent-injected",
            default_diagnostic_generation_mode="agent-injected",
            default_question_role="project_task",
        )
        question_generation_context = {
            "mode": "agent-injected" if questions else "harness-required",
            "artifact_source": "harness-injected" if isinstance(question_artifact, dict) and question_artifact else "harness-required",
            "status": "ok" if questions else "missing-external-artifact",
            "review_loop_status": "completed" if questions else "missing-external-artifact",
            "generated_count": len(questions),
            "seed_fallback_used": False,
        }
        if not questions:
            raise ValueError("initial diagnostic 缺少 Agent 生成的 question artifact：请先派 subagent 生成 question-artifact-json，严禁 fallback 到内置题库")
        deterministic_question_review = build_question_review(questions, domain, lesson_grounding_context, daily_lesson_plan)
        strict_question_review = normalize_injected_question_review(review_artifact)
        if not strict_question_review.get("valid"):
            raise ValueError("initial diagnostic strict review 未通过：请让 subagent 根据 repair_plan 重新生成并审查题目")
        question_generation_context["deterministic_question_review"] = deterministic_question_review
        question_generation_context["strict_question_review"] = strict_question_review
        question_generation_context["question_review"] = merge_question_review_results(
            deterministic_question_review,
            strict_question_review,
        )
        plan_source["lesson_path"] = plan_source.get("daily_plan_artifact_path")
        # target capability tags：可选，来自 Phase 1 报告而非强制 blueprint
        for item in questions:
            if not isinstance(item, dict):
                continue
            item["source_status"] = item.get("source_status") or "agent-injected"
            source_trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
            source_trace = dict(source_trace)
            source_trace.setdefault("question_source", "agent-injected")
            source_trace.setdefault("diagnostic_generation_mode", "agent-injected")
            item["question_role"] = infer_question_role_from_primary_category(str(source_trace.get("primary_category") or ""), default=str(item.get("question_role") or "project_task"))
            item["diagnostic_generation_mode"] = "agent-injected"
            item["source_trace"] = source_trace
        deterministic_question_review = question_generation_context.get("deterministic_question_review") if isinstance(question_generation_context.get("deterministic_question_review"), dict) else {}
        strict_question_review = question_generation_context.get("strict_question_review") if isinstance(question_generation_context.get("strict_question_review"), dict) else {}
        question_review = question_generation_context.get("question_review") if isinstance(question_generation_context.get("question_review"), dict) else {}
        diagnostic_review_attempts = [item for item in (question_generation_context.get("review_attempts") or []) if isinstance(item, dict)]
        diagnostic_repair_plan = normalize_question_repair_plan(question_review.get("repair_plan")) if isinstance(question_review, dict) else {}
    else:
        selected_bank_concept = bank_concept
        selected_bank_code = bank_code
        runtime_seed_questions: list[dict[str, Any]] = []
        runtime_seed_constraints: dict[str, Any] = {}
        if domain == "python":
            seed_payload = build_python_question_generation_seed(bank_concept, bank_code, plan_source)
            python_selection_context = seed_payload.get("selection_context") if isinstance(seed_payload.get("selection_context"), dict) else {}
            runtime_seed_questions.extend([item for item in (seed_payload.get("seed_questions") or []) if isinstance(item, dict)])
            runtime_seed_constraints.update(seed_payload.get("seed_constraints") or {})
        else:
            python_selection_context = {}
        content_concept, content_code, content_written, content_generation_context = build_content_driven_questions(domain, plan_source, selected_segments, daily_lesson_plan)
        runtime_seed_questions.extend(content_concept + content_code + content_written)
        concept_limit = 6 if domain in {"python", "git"} else max(len(content_concept), 5)
        code_limit = 2 if domain == "python" else (len(content_code) if domain_supports_code_questions(domain) else 0)
        written_limit = 1 if (session_type == "test" and domain == "python") else len(content_written)
        runtime_question_mix = {
            "concept": concept_limit,
            "code": code_limit,
            "open": written_limit,
        }
        questions = normalize_generated_runtime_questions(
            question_artifact,
            domain,
            limit=max(1, concept_limit + code_limit + written_limit),
            default_question_source="runtime-generated",
            default_source_status="runtime-generated",
            default_diagnostic_generation_mode=str(plan_source.get("diagnostic_generation_mode") or daily_lesson_plan.get("diagnostic_generation_mode") or ""),
            default_question_role=("project_task" if semantic_profile == "initial-test" else "learn"),
        )
        question_generation_context = {
            "mode": "harness-injected" if questions else "harness-required",
            "artifact_source": "harness-injected" if isinstance(question_artifact, dict) and question_artifact else "harness-required",
            "status": "ok" if questions else "missing-external-artifact",
            "review_loop_status": "completed" if questions else "missing-external-artifact",
            "generated_count": len(questions),
            "seed_fallback_used": False,
        }
        if questions:
            deterministic_question_review = build_question_review(questions, domain, lesson_grounding_context, daily_lesson_plan)
            strict_question_review = normalize_injected_question_review(review_artifact)
            if not strict_question_review.get("valid"):
                raise ValueError("strict question review 未通过：请让 subagent 根据 repair_plan 重新生成并审查题目")
            question_generation_context["deterministic_question_review"] = deterministic_question_review
            question_generation_context["strict_question_review"] = strict_question_review
            question_generation_context["question_review"] = merge_question_review_results(
                deterministic_question_review,
                strict_question_review,
            )
        actual_category_counts: dict[str, int] = {}
        for item in questions:
            category = str(item.get("category") or "unknown").strip().lower() or "unknown"
            actual_category_counts[category] = actual_category_counts.get(category, 0) + 1
        if concept_limit > 0 and actual_category_counts.get("concept", 0) < concept_limit:
            grounded_generation_shortfalls.append(f"concept:{actual_category_counts.get('concept', 0)}/{concept_limit}")
        if code_limit > 0 and actual_category_counts.get("code", 0) < code_limit:
            grounded_generation_shortfalls.append(f"code:{actual_category_counts.get('code', 0)}/{code_limit}")
        if written_limit > 0 and actual_category_counts.get("open", 0) < written_limit:
            grounded_generation_shortfalls.append(f"written:{actual_category_counts.get('open', 0)}/{written_limit}")
        if grounded_generation_shortfalls:
            plan_source["question_generation_mode"] = "grounded-generation-missing"
            plan_source["question_generation_blockers"] = [
                f"grounded 题目数量不足：{'，'.join(grounded_generation_shortfalls)}",
                "当前配置不允许 domain bank fallback，请重生成 grounded/外部 artifact 题目。",
            ]
        elif questions:
            plan_source["question_generation_mode"] = "harness-injected"
        else:
            raise ValueError("缺少 Agent 生成的 question artifact：禁止 fallback 到 runtime seed/domain bank 题库，请先派 subagent 生成 question-artifact-json")
        plan_source["lesson_path"] = plan_source.get("daily_plan_artifact_path")
        deterministic_question_review = question_generation_context.get("deterministic_question_review") if isinstance(question_generation_context.get("deterministic_question_review"), dict) else {}
        strict_question_review = question_generation_context.get("strict_question_review") if isinstance(question_generation_context.get("strict_question_review"), dict) else {}
        question_review = question_generation_context.get("question_review") if isinstance(question_generation_context.get("question_review"), dict) else {}
    artifact_review = question_generation_context.get("question_review") if isinstance(question_generation_context, dict) else None
    if isinstance(question_generation_context, dict):
        question_generation_context["payload_strict_question_review"] = strict_question_review
        question_generation_context["payload_deterministic_question_review"] = deterministic_question_review
    if diagnostic_first:
        plan_source["question_source"] = "diagnostic-session-derived"
    elif questions:
        plan_source["question_source"] = "runtime-generated"
    plan_source["deterministic_question_review"] = deterministic_question_review
    plan_source["strict_question_review"] = strict_question_review
    if isinstance(artifact_review, dict):
        plan_source["artifact_question_review"] = artifact_review
    plan_source["question_review"] = question_review
    if isinstance(question_generation_context, dict):
        if question_generation_context.get("review_loop_status") is not None:
            plan_source["review_loop_status"] = question_generation_context.get("review_loop_status")
        if question_generation_context.get("review_attempt_count") is not None:
            plan_source["review_attempt_count"] = question_generation_context.get("review_attempt_count")
        if isinstance(question_generation_context.get("review_attempts"), list):
            plan_source["review_attempts"] = question_generation_context.get("review_attempts")
    quality_context = {
        "source_grounding_required": bool(selected_segments),
        "question_traceability_required": True,
    }
    concept_questions = [item for item in questions if str(item.get("category") or "").strip().lower() == "concept"]
    code_questions = [item for item in questions if str(item.get("category") or "").strip().lower() == "code"]
    written_questions = [item for item in questions if str(item.get("category") or "").strip().lower() == "open"]
    payload = {
        "date": args.date,
        "topic": topic,
        "domain": domain,
        "mode": mode,
        "session_type": session_type,
        "session_intent": session_intent,
        "assessment_kind": assessment_kind,
        "test_mode": test_mode,
        "language_policy": language_policy,
        "plan_source": plan_source,
        "selection_context": {
            "domain": domain,
            "language_policy": language_policy,
            "source_kind": plan_source.get("source_kind") or plan_source.get("basis") or "plan-markdown-fallback",
            "current_stage": plan_source.get("current_stage"),
            "current_day": plan_source.get("day"),
            "topic_cluster": plan_source.get("today_topic"),
            "difficulty_target": plan_source.get("difficulty_target"),
            "round_index": round_index,
            "max_rounds": max_rounds,
            "questions_per_round": questions_per_round,
            "follow_up_needed": follow_up_needed,
            "stop_reason": stop_reason,
            "selection_policy": python_selection_context.get("selection_policy") if domain == "python" else ("runtime-generated-from-blueprint" if diagnostic_first else "runtime-seed-grounded"),
            "semantic_profile": semantic_profile,
            "question_source": plan_source.get("question_source"),
            "diagnostic_blueprint_version": plan_source.get("diagnostic_blueprint_version"),
            "diagnostic_generation_mode": plan_source.get("diagnostic_generation_mode"),
            "diagnostic_blueprint_basis_source": diagnostic_blueprint_basis.get("source"),
            "scope_target_capability_ids": scope_target_capability_ids or diagnostic_blueprint_tags,
            "question_scope": question_scope,
            "question_plan": question_plan,
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
            "today_teaching_brief": today_teaching_brief,
            "lesson_review": lesson_review,
            "question_review": question_review,
            "deterministic_question_review": deterministic_question_review,
            "strict_question_review": strict_question_review,
            "lesson_focus_points": lesson_focus_points,
            "project_tasks": project_tasks,
            "project_blockers": project_blockers,
            "review_targets": review_targets,
            "material_alignment": plan_source.get("material_alignment") or {},
            "content_question_generation": {
                **content_generation_context,
                "artifact_question_generation": question_generation_context,
                "artifact_generated_question_count": len(questions),
                "artifact_generated_concept_count": len(concept_questions),
                "artifact_generated_code_count": len(code_questions),
                "artifact_generated_written_count": len(written_questions),
                "generated_concept_kept": len([item for item in concept_questions if str(item.get("id") or "").startswith("content-")]),
                "generated_code_kept": len([item for item in code_questions if str(item.get("id") or "").startswith("content-")]),
                "generated_written_kept": len([item for item in written_questions if str(item.get("id") or "").startswith("content-")]),
                "bank_fallback_used": bank_fallback_used,
                "grounded_generation_shortfalls": grounded_generation_shortfalls,
            },
            "question_mix": {
                "concept": {"count": len(concept_questions), "roles": [str(item.get("question_role") or "") for item in concept_questions]},
                "code": {"count": len(code_questions), "roles": [str(item.get("question_role") or "") for item in code_questions]},
                "written": {"count": len(written_questions), "roles": [str(item.get("question_role") or "") for item in written_questions]},
            },
            "quality_context": quality_context,
        },
        "materials": materials,
        "questions": questions,
        "runtime_context": runtime_context,
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
            f"strict_review={strict_question_review.get('verdict') or 'unknown'}",
            f"deterministic_review={deterministic_question_review.get('verdict') or 'unknown'}",
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
