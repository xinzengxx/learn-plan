from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists, write_json
from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_string_list
from learn_workflow.contracts import CONTRACT_VERSION, default_workflow_paths
from learn_workflow.workflow_store import resolve_learning_root


PATCH_QUEUE_SCHEMA = "learn-plan.curriculum-patch-queue.v1"


def _sorted_patch_items(queue: dict[str, Any]) -> list[dict[str, Any]]:
    patches = [item for item in (queue.get("patches") or []) if isinstance(item, dict)]
    return sorted(
        patches,
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("source_update_type") or ""),
            str(item.get("id") or ""),
        ),
    )


def _build_patch_queue_root_evidence(queue: dict[str, Any]) -> list[str]:
    patches = _sorted_patch_items(queue)
    latest_patch = patches[-1] if patches else {}
    evidence: list[str] = []
    latest_parts = [
        str(latest_patch.get("created_at") or "").strip(),
        str(latest_patch.get("topic") or "").strip(),
        str(latest_patch.get("patch_type") or "").strip(),
    ]
    latest_text = " / ".join(part for part in latest_parts if part)
    if latest_text:
        evidence.append(f"最近 patch：{latest_text}")
    status_counts: dict[str, int] = {}
    for item in patches:
        status = str(item.get("status") or "unknown").strip() or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    if status_counts:
        summary = "；".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
        evidence.append(f"patch 状态分布：{summary}")
    return normalize_string_list(evidence)[:6]


def _build_patch_queue_root_traceability(queue: dict[str, Any]) -> list[dict[str, Any]]:
    patches = _sorted_patch_items(queue)
    traceability: list[dict[str, Any]] = []
    for item in reversed(patches):
        item_traceability = item.get("traceability") if isinstance(item.get("traceability"), list) else []
        traceability.extend(item_traceability)
        if len(traceability) >= 12:
            break
    if not traceability and patches:
        latest_patch = patches[-1]
        traceability.append(
            build_traceability_entry(
                kind="patch",
                ref=str(latest_patch.get("id") or "").strip(),
                title=latest_patch.get("topic") or "curriculum-patch-queue",
                detail=latest_patch.get("patch_type") or "feedback",
                stage="feedback",
                status=latest_patch.get("status") or "recorded",
            )
        )
    return traceability[:12]


def _apply_patch_queue_envelope(queue: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(queue) if isinstance(queue, dict) else {}
    updated.setdefault("schema", PATCH_QUEUE_SCHEMA)
    updated.setdefault("contract_version", CONTRACT_VERSION)
    patches = updated.get("patches") if isinstance(updated.get("patches"), list) else []
    updated["patches"] = patches
    evidence = _build_patch_queue_root_evidence(updated)
    latest_patch = patches[-1] if patches else {}
    queue_confidence = 0.0
    if patches:
        queue_confidence = max(float(item.get("confidence") or 0.0) for item in patches if isinstance(item, dict))
    generation_trace = {
        "stage": "feedback",
        "generator": "curriculum-patch-queue",
        "status": "updated" if patches else "initialized",
    }
    if latest_patch.get("source_update_type"):
        generation_trace["update_type"] = latest_patch.get("source_update_type")
    if latest_patch.get("created_at"):
        generation_trace["updated_at"] = latest_patch.get("created_at")
    return apply_quality_envelope(
        updated,
        stage="feedback",
        generator="curriculum-patch-queue",
        evidence=evidence,
        confidence=queue_confidence,
        quality_review={
            "reviewer": "patch-queue-root-gate",
            "valid": True,
            "issues": [],
            "warnings": [],
            "confidence": queue_confidence,
            "evidence_adequacy": "sufficient" if patches else "partial",
            "verdict": "ready",
        },
        generation_trace=generation_trace,
        traceability=_build_patch_queue_root_traceability(updated),
    )


def patch_queue_path_for_plan(plan_path: Path) -> Path:
    plan = plan_path.expanduser().resolve()
    paths = default_workflow_paths(resolve_learning_root(plan), plan, plan.parent / "materials" / "index.json")
    return paths["curriculum_patch_queue_json"]


def default_patch_queue() -> dict[str, Any]:
    return _apply_patch_queue_envelope(
        {
            "schema": PATCH_QUEUE_SCHEMA,
            "contract_version": CONTRACT_VERSION,
            "patches": [],
        }
    )


def load_patch_queue(path: Path) -> dict[str, Any]:
    existing = read_json_if_exists(path)
    queue = default_patch_queue()
    if isinstance(existing, dict):
        queue.update(existing)
    if not isinstance(queue.get("patches"), list):
        queue["patches"] = []
    queue.setdefault("schema", PATCH_QUEUE_SCHEMA)
    queue.setdefault("contract_version", CONTRACT_VERSION)
    return _apply_patch_queue_envelope(queue)


def should_propose_patch(summary: dict[str, Any], update_type: str) -> bool:
    if update_type == "diagnostic":
        return bool(summary.get("recommended_entry_level"))
    if summary.get("can_advance"):
        return True
    if summary.get("should_review"):
        return True
    if normalize_string_list(summary.get("high_freq_errors") or summary.get("weaknesses")):
        return True
    mastery = summary.get("mastery") if isinstance(summary.get("mastery"), dict) else {}
    return bool(mastery and (not mastery.get("reading_done") or not mastery.get("reflection_done")))


def validate_patch_proposal(patch: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not patch.get("evidence"):
        issues.append("patch.evidence_missing")
    if patch.get("application_policy") != "pending-user-approval":
        issues.append("patch.must_wait_for_user_approval")
    confidence = patch.get("confidence")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    if confidence_value <= 0:
        issues.append("patch.confidence_missing")
    return issues



def build_patch_proposal(summary: dict[str, Any], session_facts: dict[str, Any], *, update_type: str) -> dict[str, Any] | None:
    if not should_propose_patch(summary, update_type):
        return None
    date = session_facts.get("date") or summary.get("date") or "unknown-date"
    topic = session_facts.get("topic") or summary.get("topic") or "未命名主题"
    weaknesses = normalize_string_list(summary.get("high_freq_errors") or summary.get("weaknesses"))
    review_focus = normalize_string_list(summary.get("review_focus") or weaknesses)
    next_actions = normalize_string_list(summary.get("next_learning") or summary.get("next_actions"))
    evidence = normalize_string_list(session_facts.get("evidence"))
    status = "proposed" if evidence else "pending-evidence"
    patch_type = "review-adjustment"
    rationale = "根据本次 session 证据补充复习债。"
    if update_type == "diagnostic":
        patch_type = "entry-level-adjustment"
        rationale = "根据前置诊断建议调整起步层级。"
    elif summary.get("can_advance"):
        patch_type = "advance-proposal"
        rationale = "本次 session 达到推进条件，建议进入下一阶段或下一批内容。"
    elif summary.get("should_review") or weaknesses:
        patch_type = "review-adjustment"
        rationale = "本次 session 暴露薄弱点，建议先补强再推进。"

    patch = {
        "id": f"{date}:{update_type}:{topic}",
        "status": status,
        "patch_type": patch_type,
        "topic": topic,
        "created_at": date,
        "source_update_type": update_type,
        "rationale": rationale,
        "evidence": evidence,
        "confidence": session_facts.get("outcome", {}).get("confidence") or (0.65 if evidence else 0.35),
        "proposal": {
            "recommended_entry_level": summary.get("recommended_entry_level"),
            "review_focus": review_focus,
            "next_actions": next_actions,
            "blocking_weaknesses": normalize_string_list(summary.get("blocking_weaknesses") or weaknesses),
            "deferred_enhancement": normalize_string_list(summary.get("deferred_enhancement") or summary.get("defer_enhancement")),
            "can_advance": bool(summary.get("can_advance")),
            "should_review": bool(summary.get("should_review")),
        },
        "application_policy": "pending-user-approval",
    }
    quality_issues = validate_patch_proposal(patch)
    if quality_issues and patch["status"] == "proposed":
        patch["status"] = "pending-evidence"
    traceability = list(session_facts.get("traceability") or [])
    traceability.append(
        build_traceability_entry(
            kind="session",
            ref=str(session_facts.get("session_dir") or ""),
            title=topic,
            detail=patch_type,
            stage="feedback",
            status=patch["status"],
        )
    )
    return apply_quality_envelope(
        patch,
        stage="feedback",
        generator="curriculum-patch",
        evidence=evidence,
        confidence=patch.get("confidence"),
        quality_review={
            "reviewer": "deterministic-feedback-gate",
            "valid": not quality_issues,
            "issues": quality_issues,
            "warnings": [],
            "confidence": patch.get("confidence"),
            "evidence_adequacy": "sufficient" if evidence else "partial",
            "verdict": "ready" if not quality_issues else "needs-revision",
        },
        generation_trace={
            "stage": "feedback",
            "generator": "curriculum-patch",
            "status": patch["status"],
            "update_type": update_type,
        },
        traceability=traceability,
    )



def merge_patch(queue: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    updated = deepcopy(queue) if isinstance(queue, dict) else default_patch_queue()
    updated.setdefault("schema", PATCH_QUEUE_SCHEMA)
    updated.setdefault("contract_version", CONTRACT_VERSION)
    patches = updated.get("patches") if isinstance(updated.get("patches"), list) else []
    if not patch:
        updated["patches"] = patches
        return updated
    patch_id = patch.get("id")
    replaced = False
    next_patches: list[dict[str, Any]] = []
    for item in patches:
        if isinstance(item, dict) and item.get("id") == patch_id and item.get("status") in {"proposed", "pending", "pending-evidence"}:
            next_patches.append(patch)
            replaced = True
        else:
            next_patches.append(item)
    if not replaced:
        next_patches.append(patch)
    updated["patches"] = next_patches[-100:]
    return _apply_patch_queue_envelope(updated)


def write_patch_queue(path: Path, queue: dict[str, Any]) -> None:
    write_json(path, queue)


def update_patch_queue_file(plan_path: Path, summary: dict[str, Any], session_facts: dict[str, Any], *, update_type: str) -> dict[str, Any]:
    path = patch_queue_path_for_plan(plan_path)
    queue = load_patch_queue(path)
    patch = build_patch_proposal(summary, session_facts, update_type=update_type)
    updated = merge_patch(queue, patch)
    write_patch_queue(path, updated)
    return {"path": str(path), "patch": patch, "queue": updated}


__all__ = [
    "PATCH_QUEUE_SCHEMA",
    "build_patch_proposal",
    "default_patch_queue",
    "load_patch_queue",
    "merge_patch",
    "patch_queue_path_for_plan",
    "should_propose_patch",
    "update_patch_queue_file",
    "write_patch_queue",
]
