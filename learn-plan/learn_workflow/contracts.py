from __future__ import annotations

from pathlib import Path
from typing import Final


CONTRACT_VERSION: Final = "learn-plan.workflow.v2"
WORKFLOW_DIRNAME: Final = ".learn-workflow"
QUALITY_ENVELOPE_FIELDS: Final[tuple[str, ...]] = (
    "generation_trace",
    "quality_review",
    "evidence",
    "confidence",
    "traceability",
)

DEFAULT_CONSULTATION_TOPICS: Final[tuple[dict[str, object], ...]] = (
    {
        "id": "learning_purpose",
        "label": "学习目的",
        "required": True,
        "exit_criteria": ["目标场景已明确", "目标不是只停留在泛泛表述"],
    },
    {
        "id": "exam_or_job_target",
        "label": "考试/求职/项目目标",
        "required": True,
        "exit_criteria": ["评价方式或目标场景已明确", "缺失资料已记录为 open question 或 risk"],
    },
    {
        "id": "success_criteria",
        "label": "成功标准",
        "required": True,
        "exit_criteria": ["用户认可的达标证据已明确"],
    },
    {
        "id": "current_level",
        "label": "当前水平",
        "required": True,
        "exit_criteria": ["当前水平有具体证据", "或已明确 deferred 到 diagnostic"],
    },
    {
        "id": "constraints",
        "label": "时间与节奏约束",
        "required": True,
        "exit_criteria": ["频率、单次时长、截止日期或作息约束至少明确一类"],
    },
    {
        "id": "teaching_preference",
        "label": "授课偏好",
        "required": False,
        "exit_criteria": ["偏好已确认或记录为后续可调整"],
    },
    {
        "id": "practice_preference",
        "label": "练习偏好",
        "required": False,
        "exit_criteria": ["练习类型、题量或反馈偏好已确认或记录为后续可调整"],
    },
    {
        "id": "materials",
        "label": "资料条件",
        "required": False,
        "exit_criteria": ["已有资料/真题/课程/项目条件已记录，或确认暂无"],
    },
    {
        "id": "assessment_scope",
        "label": "起始测评范围",
        "required": True,
        "exit_criteria": ["最多测评轮数已确认", "每轮题量已确认"],
    },
    {
        "id": "non_goals",
        "label": "非目标",
        "required": False,
        "exit_criteria": ["当前不学或后置内容已记录，或确认暂无"],
    },
)

STAGE_EXIT_CONTRACTS: Final[dict[str, dict[str, object]]] = {
    "clarification": {
        "required_artifacts": ["clarification.json"],
        "required_values": [
            "questionnaire.topic",
            "questionnaire.goal",
            "questionnaire.success_criteria",
            "questionnaire.current_level_self_report 或 current_level deferred_to_diagnostic",
            "questionnaire.time_constraints",
            "questionnaire.mastery_preferences.max_assessment_rounds_preference",
            "questionnaire.mastery_preferences.questions_per_round_preference",
            "consultation_state.required_topics resolved/deferred",
        ],
        "user_visible_next_step": "围绕当前 consultation topic 继续追问，直到该主题满足 exit criteria。",
    },
    "research": {
        "required_artifacts": ["research.json", "reports/purpose-analysis.html"],
        "required_values": [
            "research_plan.status approved/completed",
            "research_report.report_status completed",
            "research_report.goal_target_band",
            "research_report.required_level_definition",
            "research_report.must_master_core",
            "research_report.capability_metrics",
            "research_report.evidence_expectations",
            "research_report.evidence_summary/source_evidence",
            "research_report.diagnostic_scope",
            "research_report.user_facing_report",
        ],
        "user_visible_next_step": "展示能力要求与达标水平报告，并确认它是否符合用户目标。",
    },
    "diagnostic": {
        "required_artifacts": ["diagnostic.json", "diagnostic session progress.json"],
        "required_values": [
            "diagnostic_plan.delivery web-session",
            "diagnostic_plan.target_capability_ids",
            "diagnostic_plan.scoring_rubric",
            "diagnostic_result.status evaluated",
            "diagnostic_profile.recommended_entry_level",
        ],
        "user_visible_next_step": "启动网页起点测评，等待用户完成后再解释能力信号。",
    },
    "approval": {
        "required_artifacts": ["approval.json", "planning candidate/review"],
        "required_values": [
            "plan draft",
            "stage goals",
            "material roles",
            "practice design",
            "mastery standards",
            "tradeoffs/open risks",
            "user approval decision",
        ],
        "user_visible_next_step": "展示草案取舍并等待用户明确确认或修改。",
    },
    "planning": {
        "required_artifacts": ["planning candidate", "planning review"],
        "required_values": ["formal plan write blockers cleared"],
        "user_visible_next_step": "完成 finalize 前的 planning artifact 校验。",
    },
    "ready": {
        "required_artifacts": ["learn-plan.md", "materials/index.json"],
        "required_values": ["formal plan ready"],
        "user_visible_next_step": "进入 /learn-today。",
    },
}

DEFAULT_LANGUAGE_POLICY: Final[dict[str, object]] = {
    "user_facing_language": "zh-CN",
    "detected_from": "fallback",
    "localization_required": True,
    "source_language_policy": "sources-may-be-original-language",
    "quote_policy": "preserve-source-quotes-with-local-explanation",
    "code_identifier_policy": "preserve-code-identifiers",
}

WORKFLOW_STATE_QUALITY_PREFIXES: Final[dict[str, str]] = {
    "clarification": "clarification",
    "research": "research",
    "diagnostic": "diagnostic",
    "approval": "approval",
    "planning": "planning",
}

WORKFLOW_MODES: Final[tuple[str, ...]] = (
    "auto",
    "draft",
    "research-report",
    "diagnostic",
    "finalize",
)
INTERMEDIATE_MODES: Final[frozenset[str]] = frozenset({"draft", "research-report", "diagnostic"})
WORKFLOW_TYPES: Final[tuple[str, ...]] = (
    "light",
    "diagnostic-first",
    "research-first",
    "mixed",
)
BLOCKING_STAGES: Final[tuple[str, ...]] = (
    "clarification",
    "research",
    "diagnostic",
    "approval",
    "planning",
    "ready",
)
ACTIONABLE_STATE_FIELDS: Final[tuple[str, ...]] = (
    "all_missing_requirements",
    "missing_requirements_by_stage",
    "actionable_stage",
    "actionable_missing_requirements",
    "reference_missing_requirements",
    "actionable_quality_issues",
    "reference_quality_issues",
    "workflow_instruction",
    "manual_patch_warning",
)

NEXT_ACTION_DRAFT: Final = "switch_to:draft"
NEXT_ACTION_RESEARCH_REPORT: Final = "switch_to:research-report"
NEXT_ACTION_DIAGNOSTIC: Final = "switch_to:diagnostic"
NEXT_ACTION_FINALIZE: Final = "switch_to:finalize"
NEXT_ACTION_ENTER_TODAY: Final = "enter:/learn-today"

WORKFLOW_FILENAMES: Final[dict[str, str]] = {
    "clarification_json": "clarification.json",
    "research_json": "research.json",
    "research_report_html": "research-report.html",
    "diagnostic_json": "diagnostic.json",
    "approval_json": "approval.json",
    "workflow_state_json": "workflow_state.json",
    "learner_model_json": "learner_model.json",
    "curriculum_patch_queue_json": "curriculum_patch_queue.json",
    "session_facts_json": "session_facts.json",
}


def default_workflow_paths(learn_root: Path, plan_path: Path, materials_index: Path) -> dict[str, Path]:
    workflow_dir = learn_root / WORKFLOW_DIRNAME
    paths = {key: workflow_dir / filename for key, filename in WORKFLOW_FILENAMES.items()}
    paths["research_report_html"] = learn_root / "reports" / "purpose-analysis.html"
    paths["plan_path"] = plan_path
    paths["materials_index"] = materials_index
    return paths


def next_action_for_mode(mode: str) -> str:
    mapping = {
        "draft": NEXT_ACTION_DRAFT,
        "research-report": NEXT_ACTION_RESEARCH_REPORT,
        "diagnostic": NEXT_ACTION_DIAGNOSTIC,
        "finalize": NEXT_ACTION_FINALIZE,
    }
    return mapping.get(mode, NEXT_ACTION_DRAFT)
