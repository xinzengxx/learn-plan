from __future__ import annotations

from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists, write_json

from .contracts import CONTRACT_VERSION, default_workflow_paths


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
        "clarification": read_json_if_exists(paths["clarification_json"]),
        "research": read_json_if_exists(paths["research_json"]),
        "diagnostic": read_json_if_exists(paths["diagnostic_json"]),
        "approval": read_json_if_exists(paths["approval_json"]),
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
