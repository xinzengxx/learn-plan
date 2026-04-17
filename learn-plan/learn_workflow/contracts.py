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

NEXT_ACTION_DRAFT: Final = "switch_to:draft"
NEXT_ACTION_RESEARCH_REPORT: Final = "switch_to:research-report"
NEXT_ACTION_DIAGNOSTIC: Final = "switch_to:diagnostic"
NEXT_ACTION_FINALIZE: Final = "switch_to:finalize"
NEXT_ACTION_ENTER_TODAY: Final = "enter:/learn-today"

WORKFLOW_FILENAMES: Final[dict[str, str]] = {
    "clarification_json": "clarification.json",
    "research_json": "research.json",
    "diagnostic_json": "diagnostic.json",
    "approval_json": "approval.json",
    "workflow_state_json": "workflow_state.json",
    "learner_model_json": "learner_model.json",
    "curriculum_patch_queue_json": "curriculum_patch_queue.json",
}


def default_workflow_paths(learn_root: Path, plan_path: Path, materials_index: Path) -> dict[str, Path]:
    workflow_dir = learn_root / WORKFLOW_DIRNAME
    paths = {key: workflow_dir / filename for key, filename in WORKFLOW_FILENAMES.items()}
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
