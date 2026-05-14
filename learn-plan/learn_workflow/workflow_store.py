from __future__ import annotations

from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists, write_json

from .contracts import CONTRACT_VERSION, default_workflow_paths


def _manual_companion_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.manual{path.suffix}")


def _value_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _fill_missing(primary: Any, fallback: Any) -> Any:
    if isinstance(primary, dict) and isinstance(fallback, dict):
        merged = dict(fallback)
        for key, value in primary.items():
            merged[key] = _fill_missing(value, fallback.get(key)) if key in fallback else value
        return merged
    if isinstance(primary, list):
        return primary if primary else fallback
    return fallback if _value_missing(primary) else primary


def _read_json_with_manual_fallback(path: Path) -> Any:
    primary = read_json_if_exists(path)
    manual = read_json_if_exists(_manual_companion_path(path))
    if isinstance(primary, dict) and isinstance(manual, dict):
        return _fill_missing(primary, manual)
    if isinstance(primary, dict) and primary:
        return primary
    if isinstance(manual, dict) and manual:
        return manual
    return primary if primary is not None else manual


def resolve_learning_root(plan_path: Path) -> Path:
    return plan_path.expanduser().resolve().parent


def build_workflow_paths(
    plan_path: Path,
    materials_index: Path,
    *,
    clarification_path: str | None = None,
    research_path: str | None = None,
    diagnostic_path: str | None = None,
    approval_path: str | None = None,
) -> dict[str, Path]:
    normalized_plan_path = plan_path.expanduser().resolve()
    normalized_materials_index = materials_index.expanduser().resolve()
    defaults = default_workflow_paths(resolve_learning_root(normalized_plan_path), normalized_plan_path, normalized_materials_index)
    overrides = {
        "clarification_json": clarification_path,
        "research_json": research_path,
        "diagnostic_json": diagnostic_path,
        "approval_json": approval_path,
    }
    paths = dict(defaults)
    for key, raw_path in overrides.items():
        if raw_path:
            paths[key] = Path(raw_path).expanduser().resolve()
    return paths


def build_artifact_manifest(paths: dict[str, Path]) -> dict[str, str]:
    return {key: str(path) for key, path in paths.items()}


def load_workflow_inputs(
    plan_path: Path,
    materials_index: Path,
    *,
    clarification_path: str | None = None,
    research_path: str | None = None,
    diagnostic_path: str | None = None,
    approval_path: str | None = None,
) -> dict[str, Any]:
    paths = build_workflow_paths(
        plan_path,
        materials_index,
        clarification_path=clarification_path,
        research_path=research_path,
        diagnostic_path=diagnostic_path,
        approval_path=approval_path,
    )
    return {
        "clarification": _read_json_with_manual_fallback(paths["clarification_json"]),
        "research": _read_json_with_manual_fallback(paths["research_json"]),
        "diagnostic": _read_json_with_manual_fallback(paths["diagnostic_json"]),
        "approval": _read_json_with_manual_fallback(paths["approval_json"]),
        "workflow_state": read_json_if_exists(paths["workflow_state_json"]),
        "learner_model": read_json_if_exists(paths["learner_model_json"]),
        "curriculum_patch_queue": read_json_if_exists(paths["curriculum_patch_queue_json"]),
        "paths": paths,
        "artifacts": build_artifact_manifest(paths),
    }


def write_workflow_state(path: Path, state: dict[str, Any]) -> None:
    payload = dict(state)
    payload.setdefault("contract_version", CONTRACT_VERSION)
    write_json(path, payload)


def refresh_workflow_state(
    plan_path: Path,
    *,
    materials_index: Path | None = None,
    topic: str | None = None,
    goal: str | None = None,
    requested_mode: str = "auto",
    current_mode: str = "finalize",
    quality_issues: list[str] | None = None,
) -> dict[str, Any]:
    normalized_plan_path = plan_path.expanduser().resolve()
    normalized_materials_index = materials_index.expanduser().resolve() if isinstance(materials_index, Path) else (normalized_plan_path.parent / "materials" / "index.json")
    workflow_inputs = load_workflow_inputs(normalized_plan_path, normalized_materials_index)
    clarification = dict(workflow_inputs.get("clarification") or {})
    research = dict(workflow_inputs.get("research") or {})
    diagnostic = dict(workflow_inputs.get("diagnostic") or {})
    approval = dict(workflow_inputs.get("approval") or {})
    learner_model = dict(workflow_inputs.get("learner_model") or {})
    curriculum_patch_queue = dict(workflow_inputs.get("curriculum_patch_queue") or {})
    existing_workflow_state = dict(workflow_inputs.get("workflow_state") or {})
    existing_workflow_type = str(existing_workflow_state.get("workflow_type") or "").strip()
    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    goal_model = clarification.get("goal_model") if isinstance(clarification.get("goal_model"), dict) else {}
    resolved_topic = str(topic or questionnaire.get("topic") or existing_workflow_state.get("topic") or "").strip()
    resolved_goal = str(goal or questionnaire.get("goal") or goal_model.get("mainline_goal") or existing_workflow_state.get("goal") or "").strip()
    inherited_quality_issues = list(quality_issues) if quality_issues is not None else list(existing_workflow_state.get("quality_issues") or [])
    from .gates import annotate_formal_plan_gate
    from .state_machine import build_workflow_state

    refreshed = build_workflow_state(
        topic=resolved_topic,
        goal=resolved_goal,
        requested_mode=requested_mode,
        current_mode=current_mode,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning={},
        learner_model=learner_model,
        curriculum_patch_queue=curriculum_patch_queue,
        quality_issues=inherited_quality_issues,
        artifacts=workflow_inputs.get("artifacts") or {},
        workflow_type=existing_workflow_type,
    )
    refreshed = annotate_formal_plan_gate(refreshed, current_mode)
    if not refreshed.get("topic") and resolved_topic:
        refreshed["topic"] = resolved_topic
    if not refreshed.get("goal") and resolved_goal:
        refreshed["goal"] = resolved_goal
    if "planning_artifact" in existing_workflow_state:
        refreshed["legacy_planning_artifact_ignored"] = True
    workflow_state_path = workflow_inputs.get("paths", {}).get("workflow_state_json")
    if isinstance(workflow_state_path, Path):
        write_workflow_state(workflow_state_path, refreshed)
    return refreshed
