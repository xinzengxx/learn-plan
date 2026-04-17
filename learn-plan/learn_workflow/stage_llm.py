from __future__ import annotations

from typing import Any

from learn_core.llm_json import parse_json_from_llm_output
from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_string_list
from learn_runtime.lesson_builder import json_for_prompt, run_claude_json_generation


STAGE_PROMPT_VERSION = "learn-plan.stage-llm.v1"
SUPPORTED_STAGES = {"clarification", "research", "diagnostic", "approval", "planning"}


_STAGE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "clarification": ["questionnaire", "clarification_state", "preference_state"],
    "research": ["deepsearch_status", "research_plan", "research_report"],
    "diagnostic": ["diagnostic_plan", "diagnostic_items", "diagnostic_result", "diagnostic_profile"],
    "approval": ["approval_state"],
    "planning": ["plan_candidate"],
}


_STAGE_INSTRUCTIONS: dict[str, str] = {
    "clarification": "补全用户画像、目标、约束、偏好、非目标与未决问题。必须显式确认起始测评深度，让用户在 assessment_depth_preference=simple|deep 二选一；未确认时不得默认 simple，必须把该问题保留在 open_questions / pending_items 中。",
    "research": "先给 research plan，再给 capability report。所有结论要能追溯到 source_evidence / evidence_summary。",
    "diagnostic": "为 capability 设计最小诊断题组、rubric 与 expected signals；显式区分 assessment_depth=simple|deep，并给出 round_index / max_rounds / follow_up_needed / stop_reason；诊断交付应面向网页 session 四件套（questions.json/progress.json/题集.html/server.py），用户先在网站作答，再分析结果；评估结果必须包含 recommended_entry_level 与 confidence，未完成网页作答时不得伪造已评阅结论。",
    "approval": "审查计划草案中的 material strategy、daily execution style、mastery checks 与 tradeoff 是否已明确。",
    "planning": "生成结构化计划候选，而不是直接写正式 markdown；内容必须体现个性化阶段目标、材料角色与掌握标准。",
}


def stage_required_fields(stage: str) -> list[str]:
    return list(_STAGE_REQUIRED_FIELDS.get(stage, []))


def build_stage_candidate_prompt(
    stage: str,
    *,
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    context: dict[str, Any],
    existing_state: dict[str, Any] | None = None,
) -> str:
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage not in SUPPORTED_STAGES:
        raise ValueError(f"不支持的 stage: {stage}")
    required_fields = stage_required_fields(normalized_stage)
    instruction = _STAGE_INSTRUCTIONS.get(normalized_stage, "生成结构化 workflow candidate。")
    return f"""你是 learn-plan 工作流中的 {normalized_stage} 阶段候选生成器。

目标：{instruction}

硬性要求：
1. 只输出一个 JSON object，不要 Markdown，不要解释 JSON 外文字。
2. 顶层必须包含 contract_version, stage, candidate_version, generation_trace, evidence, confidence, traceability。
3. 顶层 contract_version 固定为 learn-plan.workflow.v2。
4. stage 固定为 {normalized_stage}。
5. candidate_version 固定为 {STAGE_PROMPT_VERSION}。
6. generation_trace 至少包含 prompt_version、generator、status。
7. evidence 必须是字符串数组，写明你基于哪些用户输入/已有状态得到当前候选。
8. confidence 用 0~1 浮点数表示。
9. traceability 必须是对象数组，每项至少包含 kind 和 ref，可选 title/detail/stage/status/locator。
10. 顶层必须包含这些 stage 字段：{', '.join(required_fields)}。
11. 不要假装用户已经确认未确认的信息；无法确认时放入 open_questions / pending_decisions / open_risks。
12. clarification stage 必须在 questionnaire.mastery_preferences.assessment_depth_preference 写入 simple、deep 或 undecided；未明确选择 simple/deep 时保持 undecided，并把“请选择简单测评或深度测评”列入 open_questions / preference_state.pending_items。
13. diagnostic stage 必须沿用已确认的 assessment_depth；诊断题用于生成 initial-test 网页 session（兼容读取 legacy plan-diagnostic），用户未通过网页提交答案前，diagnostic_result.status 不得伪装为 evaluated。
14. planning stage 只生成 plan_candidate，不要输出正式 learn-plan.md markdown。

输入背景：
- topic: {topic}
- goal: {goal}
- level: {level}
- schedule: {schedule}
- preference: {preference}

STAGE_CONTEXT:
{json_for_prompt(context, limit=12000)}

EXISTING_STATE:
{json_for_prompt(existing_state or {}, limit=7000)}
"""


def build_stage_context(
    stage: str,
    *,
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    workflow_state: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "topic": topic,
        "goal": goal,
        "level": level,
        "schedule": schedule,
        "preference": preference,
        "current_stage": stage,
        "workflow_state": workflow_state or {},
        "artifacts": artifacts or {},
        "clarification": clarification or {},
        "research": research or {},
        "diagnostic": diagnostic or {},
        "approval": approval or {},
    }


def normalize_stage_candidate(stage: str, candidate: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    normalized_stage = str(stage or "").strip().lower()
    payload = dict(candidate)
    payload["contract_version"] = str(payload.get("contract_version") or "learn-plan.workflow.v2")
    payload["stage"] = normalized_stage
    payload["candidate_version"] = str(payload.get("candidate_version") or STAGE_PROMPT_VERSION)
    generation_trace = dict(payload.get("generation_trace") or {})
    generation_trace.setdefault("prompt_version", STAGE_PROMPT_VERSION)
    generation_trace.setdefault("generator", f"stage-candidate:{normalized_stage}")
    if metadata:
        for key, value in metadata.items():
            generation_trace.setdefault(key, value)
    payload["generation_trace"] = generation_trace
    evidence = normalize_string_list(payload.get("evidence"))
    traceability = payload.get("traceability")
    if not evidence:
        evidence = normalize_string_list(
            [
                f"stage={normalized_stage}",
                f"candidate_version={payload.get('candidate_version')}",
                f"generation_status={generation_trace.get('status') or 'unknown'}",
            ]
        )
    if not traceability:
        traceability = [
            build_traceability_entry(
                kind="stage-candidate",
                ref=normalized_stage,
                title=f"{normalized_stage} candidate",
                stage=normalized_stage,
                status=str(generation_trace.get("status") or "generated"),
            )
        ]
    resolved_confidence = payload.get("confidence")
    if resolved_confidence in (None, "") and metadata:
        resolved_confidence = metadata.get("confidence")
    return apply_quality_envelope(
        payload,
        stage=normalized_stage,
        generator=f"stage-candidate:{normalized_stage}",
        evidence=evidence,
        confidence=resolved_confidence,
        generation_trace=generation_trace,
        traceability=traceability,
    )


def generate_stage_candidate(
    stage: str,
    *,
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    context: dict[str, Any],
    existing_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    prompt = build_stage_candidate_prompt(
        stage,
        topic=topic,
        goal=goal,
        level=level,
        schedule=schedule,
        preference=preference,
        context=context,
        existing_state=existing_state,
    )
    raw_payload, metadata = run_claude_json_generation(prompt)
    if raw_payload is None and metadata.get("stdout_excerpt"):
        raw_payload = parse_json_from_llm_output(str(metadata.get("stdout_excerpt") or ""))
    normalized = normalize_stage_candidate(stage, raw_payload, metadata)
    if normalized is None:
        return None, {**metadata, "stage": stage, "mode": "stage-candidate"}
    return normalized, {**metadata, "stage": stage, "mode": "stage-candidate"}


__all__ = [
    "STAGE_PROMPT_VERSION",
    "SUPPORTED_STAGES",
    "build_stage_candidate_prompt",
    "build_stage_context",
    "generate_stage_candidate",
    "normalize_stage_candidate",
    "stage_required_fields",
]
