from __future__ import annotations

from typing import Any


FORMAL_PLAN_WRITE_ALLOWED = "formal_plan_write_allowed"
FORMAL_PLAN_WRITE_BLOCKERS = "formal_plan_write_blockers"


def formal_plan_write_blockers(workflow_state: dict[str, Any], mode: str) -> list[str]:
    blockers: list[str] = []
    normalized_mode = str(mode or "").strip()
    blocking_stage = str(workflow_state.get("blocking_stage") or "")
    quality_issues = list(workflow_state.get("quality_issues") or [])
    missing_requirements = list(workflow_state.get("missing_requirements") or [])

    if normalized_mode != "finalize":
        blockers.append("formal_plan.mode_not_finalize")
    if blocking_stage != "ready":
        blockers.append(f"formal_plan.blocking_stage.{blocking_stage or 'unknown'}")
    if quality_issues:
        blockers.append("formal_plan.quality_issues")
    if missing_requirements:
        blockers.append("formal_plan.missing_requirements")
    return blockers


def can_write_formal_plan(workflow_state: dict[str, Any], mode: str) -> bool:
    return not formal_plan_write_blockers(workflow_state, mode)


def annotate_formal_plan_gate(workflow_state: dict[str, Any], mode: str) -> dict[str, Any]:
    annotated = dict(workflow_state)
    blockers = formal_plan_write_blockers(annotated, mode)
    annotated[FORMAL_PLAN_WRITE_ALLOWED] = not blockers
    annotated[FORMAL_PLAN_WRITE_BLOCKERS] = blockers
    return annotated
