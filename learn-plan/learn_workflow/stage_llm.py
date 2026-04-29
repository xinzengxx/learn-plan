from __future__ import annotations

from typing import Any

from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_string_list
from learn_runtime.lesson_builder import json_for_prompt, shared_style_prompt_block
from .contracts import STAGE_EXIT_CONTRACTS


STAGE_PROMPT_VERSION = "learn-plan.stage-llm.v1"
SUPPORTED_STAGES = {"clarification", "research", "diagnostic", "approval", "planning"}


_STAGE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "clarification": ["questionnaire", "clarification_state", "preference_state", "consultation_state", "language_policy"],
    "research": ["deepsearch_status", "research_plan", "research_report"],
    "diagnostic": ["diagnostic_plan", "diagnostic_items", "diagnostic_result", "diagnostic_profile"],
    "approval": ["approval_state", "material_curation"],
    "planning": ["plan_candidate"],
}


_STAGE_INSTRUCTIONS: dict[str, str] = {
    "clarification": "执行主题式顾问访谈候选生成。开始时必须生成 theme_inventory 告诉用户本轮会确认哪些主题；本轮只能聚焦 consultation_state.current_topic_id 所指的一个主题，围绕该主题追问 1–3 个问题；若当前主题未满足 exit criteria，不得跳到规划或跨主题批量问卷。必须维护 consultation_state.topics/thread，并把已确认信息投影回 questionnaire/clarification_state/preference_state。进入规划前必须生成 learner_profile 用户画像候选，包含 background、goal_context、constraints、learning_preferences 与 confirmation_status=pending_user_confirmation，等待用户确认或补充。必须显式确认起始测评预算：最多接受几轮测试、每轮最多接受多少题；默认按每轮总题数理解。未确认时不得默认预算，必须把该问题保留在当前 topic 的 open_questions 与兼容 open_questions / pending_items 中。",
    "research": "先给 research plan，再给面向用户审阅的目的解析报告。若真实进入 research/search 阶段，先给极简核心分析：goal_target_band、must_master_core、evidence_expectations、research_brief；所有结论要能追溯到 source_evidence / evidence_summary。目的解析报告只回答外部目标要求什么，不提前展开学习路线、资料安排、阶段计划。若用户已选择要做测试，则 research_report 必须额外产出 machine-consumable 的 diagnostic_scope，明确接下来要测什么、为什么这么安排，并作为后续 diagnostic 的真实上游约束。",
    "diagnostic": "为 capability 设计最小诊断 blueprint、rubric 与 expected signals；必须消费已确认的 max_rounds 与 questions_per_round，并给出 round_index / max_rounds / questions_per_round / follow_up_needed / stop_reason。若上游 research_report 中存在 diagnostic_scope，则 diagnostic_plan.target_capability_ids、scoring_rubric 与 diagnostic_items 必须优先承接该 scope，不得回退为默认题库导向。diagnostic_items 表示能力覆盖蓝图与评估规格，不等于最终 questions.json 真题；起始诊断题由 runtime 生成，但必须受 blueprint 约束。诊断交付应面向网页 session 四件套（questions.json/progress.json/题集.html/server.py），用户先在网站作答，再分析结果；评估结果必须包含 recommended_entry_level 与 confidence，未完成网页作答时不得伪造已评阅结论。",
    "approval": "审查计划草案中的 material strategy、daily execution style、mastery checks 与 tradeoff 是否已明确；必须生成 material_curation：基于 research 的目标能力与资料池、diagnostic 的起点和薄弱项，把资料分为 mainline / required-support / optional-candidate / rejected，并说明每份资料适合或不适合当前用户的原因、对应能力缺口、片段范围、下载风险与 open risks。未经用户明确确认时，confirmed_material_strategy 不得为 true，material_curation.status 不得为 confirmed。不得把未验证下载、空文件、登录页、错误页标为 cached。若 curriculum_patch_queue 中存在待决 patch，应把 patch 的批准/拒绝决定写入 approval_state.approved_patch_ids / rejected_patch_ids。",
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
    search_context: dict[str, Any] | None = None,
) -> str:
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage not in SUPPORTED_STAGES:
        raise ValueError(f"不支持的 stage: {stage}")
    required_fields = stage_required_fields(normalized_stage)
    instruction = _STAGE_INSTRUCTIONS.get(normalized_stage, "生成结构化 workflow candidate。")
    stage_exit_contract = STAGE_EXIT_CONTRACTS.get(normalized_stage) or {}
    context_limit = 6000 if normalized_stage == "planning" else 12000
    existing_state_limit = 3500 if normalized_stage == "planning" else 7000
    return f"""你是 learn-plan 工作流中的 {normalized_stage} 阶段候选生成器。

目标：{instruction}

{shared_style_prompt_block(audience=f'{normalized_stage} 阶段候选')}

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
12. clarification stage 的用户追问由主会话用自然语言完成；你只把已经发生的对话整理成结构化 candidate patch，不要生成给用户的选择题 UI，不要输出 AskUserQuestion/UserQuestions schema。
13. clarification stage 必须输出 theme_inventory（主题清单）与 learner_profile（用户画像候选）；learner_profile 必须等待用户确认，使用 confirmation_status=pending_user_confirmation / confirmed / needs_revision 这类状态表达，不得把未确认画像当作正式事实。
14. clarification stage 必须在 questionnaire.mastery_preferences 写入 max_assessment_rounds_preference 与 questions_per_round_preference；若用户把预算写在 consultation_state.topics[].confirmed_values、preference_state 或 user_model，也要同步投影到 questionnaire.mastery_preferences。未明确预算时不要默认，必须把“最多接受几轮测试”“每轮最多接受多少题”列入 open_questions / preference_state.pending_items。默认按每轮总题数理解，只有用户明确在意题型占比时才补 question_mix_preference。
15. research stage 若被触发，research_report 中必须包含 goal_target_band、must_master_core、evidence_expectations、research_brief、evaluator_roles、source_categories、web_source_evidence；evaluator_roles 至少覆盖 HR/老师/技术负责人/招聘经理/一线实践者中与目标相关的多方视角，source_categories 覆盖岗位或考试要求、经验文档、课程、书籍、练习题、开源仓库等资源类别。research_brief 只保留面向用户的核心结论，不要写成长篇 artifact 摘要。若用户已选择要做测试，则 research_report 还必须包含 diagnostic_scope，至少给出 target_goal_band、target_capability_ids、target_capabilities、scope_rationale、evidence_expectations、scoring_dimensions、gap_judgement_basis，并保证这些字段可直接支撑后续 diagnostic 蓝图生成。
16. diagnostic stage 必须沿用已确认的 max_rounds 与 questions_per_round，并输出 start_difficulty、difficulty_ladder、difficulty_adjustment_policy；过难时应建议降低难度或补基础，过易时应建议提升难度并再次测试。若上游 research_report.diagnostic_scope 存在，则 diagnostic_plan.target_capability_ids、scoring_rubric 与 diagnostic_items 必须优先承接该 scope，不得忽略或回退为默认题库导向。诊断题用于生成 initial-test 网页 session（兼容读取 legacy plan-diagnostic），用户未通过网页提交答案前，diagnostic_result.status 不得伪装为 evaluated。
17. planning stage 只生成 plan_candidate，不要输出正式 learn-plan.md markdown；plan_candidate 必须包含 problem_definition，每个阶段必须包含 target_gap、capability_metric、evidence_requirement、approx_time_range。
16. 当前阶段 exit contract 是本轮唯一目标；不要补未来阶段 artifact，也不要为了通过 gate 伪造用户确认。

CURRENT_STAGE_EXIT_CONTRACT:
{json_for_prompt(stage_exit_contract, limit=2500)}

输入背景：
- topic: {topic}
- goal: {goal}
- level: {level}
- schedule: {schedule}
- preference: {preference}

STAGE_CONTEXT:
{json_for_prompt(context, limit=context_limit)}

EXISTING_STATE:
{json_for_prompt(existing_state or {}, limit=existing_state_limit)}
{f'''SEARCH_RESULTS:
{json_for_prompt(search_context, limit=4000)}''' if search_context else ''}
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
    learner_model: dict[str, Any] | None = None,
    curriculum_patch_queue: dict[str, Any] | None = None,
    workflow_state: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    search_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
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
        "learner_model": learner_model or {},
        "curriculum_patch_queue": curriculum_patch_queue or {},
    }
    if search_context:
        result["search_context"] = search_context
    return result


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


__all__ = [
    "STAGE_PROMPT_VERSION",
    "SUPPORTED_STAGES",
    "build_stage_candidate_prompt",
    "build_stage_context",
    "normalize_stage_candidate",
    "stage_required_fields",
]
