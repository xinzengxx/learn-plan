from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists, write_json
from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_string_list
from learn_workflow.contracts import CONTRACT_VERSION, default_workflow_paths
from learn_workflow.workflow_store import resolve_learning_root


LEARNER_MODEL_SCHEMA = "learn-plan.learner-model.v1"
PLACEHOLDER_WEAKNESS = "暂无明显薄弱项"


def _sanitize_feedback_focus(values: Any) -> list[str]:
    return [item for item in normalize_string_list(values) if item != PLACEHOLDER_WEAKNESS]


def _build_learner_model_root_evidence(model: dict[str, Any]) -> list[str]:
    evidence_entries = [item for item in (model.get("evidence_log") or []) if isinstance(item, dict)]
    latest_entry = evidence_entries[-1] if evidence_entries else {}
    evidence: list[str] = []
    latest_parts = [
        str(latest_entry.get("date") or "").strip(),
        str(latest_entry.get("topic") or "").strip(),
        str(latest_entry.get("summary") or "").strip(),
    ]
    latest_text = " / ".join(part for part in latest_parts if part)
    if latest_text:
        evidence.append(f"最近 session：{latest_text}")
    strengths = normalize_string_list(model.get("strengths"))[:3]
    weaknesses = _sanitize_feedback_focus(model.get("weaknesses"))[:3]
    review_debt = _sanitize_feedback_focus(model.get("review_debt"))[:3]
    mastered_scope = sanitize_mastered_scope(model.get("mastered_scope"))[:3]
    if strengths:
        evidence.append(f"当前优势：{'；'.join(strengths)}")
    if weaknesses:
        evidence.append(f"当前薄弱项：{'；'.join(weaknesses)}")
    if review_debt:
        evidence.append(f"当前复习债：{'；'.join(review_debt)}")
    if mastered_scope:
        evidence.append(f"当前已覆盖：{'；'.join(mastered_scope)}")
    return normalize_string_list(evidence)[:8]


def _build_learner_model_root_traceability(model: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_entries = [item for item in (model.get("evidence_log") or []) if isinstance(item, dict)]
    traceability: list[dict[str, Any]] = []
    for item in reversed(evidence_entries):
        item_traceability = item.get("traceability") if isinstance(item.get("traceability"), list) else []
        traceability.extend(item_traceability)
        if len(traceability) >= 12:
            break
    if not traceability and evidence_entries:
        latest_entry = evidence_entries[-1]
        session_dir = str(latest_entry.get("session_dir") or "").strip()
        if session_dir:
            traceability.append(
                build_traceability_entry(
                    kind="session",
                    ref=session_dir,
                    title=latest_entry.get("topic") or "learner-model",
                    detail=latest_entry.get("update_type") or "feedback",
                    stage="feedback",
                    status="recorded",
                )
            )
    return traceability[:12]


def _apply_learner_model_envelope(model: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(model) if isinstance(model, dict) else {}
    updated.setdefault("schema", LEARNER_MODEL_SCHEMA)
    updated.setdefault("contract_version", CONTRACT_VERSION)
    evidence_log = updated.get("evidence_log") if isinstance(updated.get("evidence_log"), list) else []
    updated["evidence_log"] = evidence_log
    evidence = _build_learner_model_root_evidence(updated)
    latest_entry = evidence_log[-1] if evidence_log else {}
    generation_trace = {
        "stage": "feedback",
        "generator": "learner-model-state",
        "status": "updated" if updated.get("last_updated") else "initialized",
    }
    if latest_entry.get("update_type"):
        generation_trace["update_type"] = latest_entry.get("update_type")
    if updated.get("last_updated"):
        generation_trace["updated_at"] = updated.get("last_updated")
    return apply_quality_envelope(
        updated,
        stage="feedback",
        generator="learner-model-state",
        evidence=evidence,
        confidence=updated.get("confidence"),
        quality_review={
            "reviewer": "learner-model-root-gate",
            "valid": True,
            "issues": [],
            "warnings": [],
            "confidence": updated.get("confidence"),
            "evidence_adequacy": "sufficient" if evidence_log else "partial",
            "verdict": "ready",
        },
        generation_trace=generation_trace,
        traceability=_build_learner_model_root_traceability(updated),
    )


def default_learner_model() -> dict[str, Any]:
    return _apply_learner_model_envelope(
        {
            "schema": LEARNER_MODEL_SCHEMA,
            "contract_version": CONTRACT_VERSION,
            "evidence_log": [],
            "strengths": [],
            "weaknesses": [],
            "review_debt": [],
            "mastered_scope": [],
            "confidence": 0.0,
            "last_updated": None,
        }
    )


def learner_model_path_for_plan(plan_path: Path) -> Path:
    plan = plan_path.expanduser().resolve()
    paths = default_workflow_paths(resolve_learning_root(plan), plan, plan.parent / "materials" / "index.json")
    return paths["learner_model_json"]


def load_learner_model(path: Path) -> dict[str, Any]:
    existing = read_json_if_exists(path)
    model = default_learner_model()
    if isinstance(existing, dict):
        model.update(existing)
    model.setdefault("schema", LEARNER_MODEL_SCHEMA)
    model.setdefault("contract_version", CONTRACT_VERSION)
    for key in ("evidence_log", "strengths", "weaknesses", "review_debt", "mastered_scope"):
        if not isinstance(model.get(key), list):
            model[key] = []
    return _apply_learner_model_envelope(model)


def append_unique(existing: list[Any], values: Any, *, limit: int = 50) -> list[str]:
    merged = normalize_string_list(existing)
    for value in normalize_string_list(values):
        if value not in merged:
            merged.append(value)
    return merged[-limit:]


def sanitize_mastered_scope(values: Any) -> list[str]:
    items = normalize_string_list(values)
    single_chars = [item for item in items if len(item) == 1]
    multi_chars = [item for item in items if len(item) > 1]
    if len(single_chars) >= 5 and multi_chars:
        return multi_chars
    return items


def dedupe_evidence_log(entries: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    evidence_entries = [item for item in (entries or []) if isinstance(item, dict)]
    seen: set[tuple[str, str, str, str]] = set()
    deduped_reversed: list[dict[str, Any]] = []
    for item in reversed(evidence_entries):
        key = (
            str(item.get("update_type") or "").strip(),
            str(item.get("date") or "").strip(),
            str(item.get("topic") or "").strip(),
            str(item.get("session_dir") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped_reversed.append(item)
    return list(reversed(deduped_reversed))[-limit:]


def update_learner_model_from_summary(
    model: dict[str, Any],
    summary: dict[str, Any],
    *,
    session_facts: dict[str, Any],
    update_type: str,
) -> dict[str, Any]:
    updated = deepcopy(model) if isinstance(model, dict) else default_learner_model()
    updated.setdefault("schema", LEARNER_MODEL_SCHEMA)
    updated.setdefault("contract_version", CONTRACT_VERSION)
    evidence = normalize_string_list(session_facts.get("evidence"))
    strengths = normalize_string_list(item.get("title") for item in summary.get("solved_items") or [])
    weaknesses = _sanitize_feedback_focus(summary.get("high_freq_errors") or summary.get("weaknesses"))
    review_debt = _sanitize_feedback_focus(summary.get("review_focus") or weaknesses)
    mastered_scope = normalize_string_list(summary.get("covered_scope") or summary.get("mainline_progress"))

    updated["strengths"] = append_unique(updated.get("strengths") or [], strengths, limit=80)
    updated["weaknesses"] = append_unique(updated.get("weaknesses") or [], weaknesses, limit=80)
    updated["review_debt"] = append_unique(updated.get("review_debt") or [], review_debt, limit=80)
    updated_mastered_scope = append_unique(updated.get("mastered_scope") or [], mastered_scope, limit=80)
    updated["mastered_scope"] = sanitize_mastered_scope(updated_mastered_scope)
    updated["last_updated"] = session_facts.get("date") or summary.get("date")

    attempted = int((session_facts.get("scores") or {}).get("attempted") or 0)
    confidence = 0.2
    if attempted >= 5:
        confidence = 0.7
    elif attempted > 0:
        confidence = 0.5
    if weaknesses:
        confidence = min(confidence, 0.65)
    updated["confidence"] = confidence

    evidence_log = updated.get("evidence_log") if isinstance(updated.get("evidence_log"), list) else []
    evidence_log.append(
        apply_quality_envelope(
            {
                "update_type": update_type,
                "date": session_facts.get("date") or summary.get("date"),
                "topic": session_facts.get("topic") or summary.get("topic"),
                "summary": summary.get("overall"),
                "evidence": evidence,
                "session_dir": session_facts.get("session_dir"),
                "confidence": confidence,
            },
            stage="feedback",
            generator="learner-model-update",
            evidence=evidence,
            confidence=confidence,
            quality_review={
                "reviewer": "learner-model-gate",
                "valid": True,
                "issues": [],
                "warnings": [],
                "confidence": confidence,
                "evidence_adequacy": "sufficient" if evidence else "partial",
                "verdict": "ready",
            },
            generation_trace={
                "stage": "feedback",
                "generator": "learner-model-update",
                "status": "summarized",
                "update_type": update_type,
            },
            traceability=[
                build_traceability_entry(
                    kind="session",
                    ref=str(session_facts.get("session_dir") or ""),
                    title=session_facts.get("topic") or summary.get("topic") or "session",
                    detail=update_type,
                    stage="feedback",
                    status="recorded",
                )
            ],
        )
    )
    updated["evidence_log"] = dedupe_evidence_log(evidence_log, limit=50)
    return _apply_learner_model_envelope(updated)


def write_learner_model(path: Path, model: dict[str, Any]) -> None:
    write_json(path, model)


def update_learner_model_file(plan_path: Path, summary: dict[str, Any], session_facts: dict[str, Any], *, update_type: str) -> dict[str, Any]:
    path = learner_model_path_for_plan(plan_path)
    model = load_learner_model(path)
    updated = update_learner_model_from_summary(model, summary, session_facts=session_facts, update_type=update_type)
    write_learner_model(path, updated)
    return {"path": str(path), "model": updated}


__all__ = [
    "LEARNER_MODEL_SCHEMA",
    "append_unique",
    "default_learner_model",
    "learner_model_path_for_plan",
    "load_learner_model",
    "update_learner_model_file",
    "update_learner_model_from_summary",
    "write_learner_model",
]
