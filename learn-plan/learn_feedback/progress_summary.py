from __future__ import annotations

from pathlib import Path
from typing import Any

from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_int, normalize_string_list


def build_session_facts(
    progress: dict[str, Any],
    summary: dict[str, Any],
    *,
    session_dir: Path,
    update_type: str,
) -> dict[str, Any]:
    session = progress.get("session") if isinstance(progress.get("session"), dict) else {}
    mastery = summary.get("mastery") if isinstance(summary.get("mastery"), dict) else {}
    evidence = build_session_evidence(summary)
    facts = {
        "schema": "learn-plan.session-facts.v1",
        "update_type": update_type,
        "topic": summary.get("topic") or progress.get("topic") or "未命名主题",
        "date": summary.get("finished_at") or summary.get("date") or progress.get("date") or "",
        "session_dir": str(session_dir),
        "session": {
            "type": summary.get("session_type") or session.get("type") or update_type,
            "status": session.get("status") or summary.get("status") or "active",
            "intent": session.get("intent"),
            "assessment_kind": session.get("assessment_kind"),
            "test_mode": summary.get("test_mode") or session.get("test_mode"),
        },
        "scores": {
            "total": normalize_int(summary.get("total")),
            "attempted": normalize_int(summary.get("attempted")),
            "correct": normalize_int(summary.get("correct")),
        },
        "outcome": {
            "overall": summary.get("overall"),
            "can_advance": bool(summary.get("can_advance")),
            "should_review": bool(summary.get("should_review")),
            "recommended_entry_level": summary.get("recommended_entry_level"),
        },
        "mastery": {
            "reading_done": bool(mastery.get("reading_done")),
            "session_done": bool(mastery.get("session_done")),
            "project_done": bool(mastery.get("project_done")),
            "reflection_done": bool(mastery.get("reflection_done")),
        },
        "evidence": evidence,
    }
    material_alignment = summary.get("material_alignment")
    if isinstance(material_alignment, dict):
        facts["material_alignment"] = {
            "status": material_alignment.get("status"),
            "selected_segments": normalize_string_list(material_alignment.get("selected_segments")),
            "covered_segments": normalize_string_list(material_alignment.get("covered_segments")),
            "missing_segments": normalize_string_list(material_alignment.get("missing_segments")),
            "evidence": normalize_string_list(material_alignment.get("evidence")),
        }

    traceability: list[dict[str, Any]] = [
        build_traceability_entry(
            kind="session",
            ref=str(session_dir),
            title=facts["topic"],
            detail=facts["session"].get("type") or update_type,
            stage="feedback",
            status=facts["session"].get("status") or "active",
        )
    ]
    for segment_id in normalize_string_list(((facts.get("material_alignment") or {}).get("selected_segments") or []))[:8]:
        traceability.append(
            build_traceability_entry(
                kind="material-segment",
                ref=segment_id,
                title=segment_id,
                detail="selected segment",
                stage="feedback",
                status=(facts.get("material_alignment") or {}).get("status") or "recorded",
            )
        )

    generation_trace = {
        "stage": "feedback",
        "generator": "progress-summary",
        "status": "summarized",
        "update_type": update_type,
    }
    confidence = 0.75 if evidence else 0.35
    if not facts["scores"]["attempted"]:
        confidence = min(confidence, 0.45)
    facts["outcome"]["confidence"] = confidence

    return apply_quality_envelope(
        facts,
        stage="feedback",
        generator="progress-summary",
        evidence=evidence,
        confidence=confidence,
        quality_review={
            "reviewer": "feedback-session-facts-gate",
            "valid": True,
            "issues": [],
            "warnings": [],
            "confidence": confidence,
            "evidence_adequacy": "sufficient" if evidence else "partial",
            "verdict": "ready",
        },
        generation_trace=generation_trace,
        traceability=traceability,
    )


def build_session_evidence(summary: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    attempted = normalize_int(summary.get("attempted"))
    correct = normalize_int(summary.get("correct"))
    if attempted:
        evidence.append(f"已尝试 {attempted} 题，正确/通过 {correct} 题")
    for item in summary.get("solved_items") or []:
        if isinstance(item, dict) and item.get("title"):
            evidence.append(f"已解决：{item['title']}")
    for item in summary.get("wrong_items") or []:
        if isinstance(item, dict) and item.get("title"):
            evidence.append(f"暴露薄弱点：{item['title']}")
    for value in normalize_string_list(summary.get("high_freq_errors") or summary.get("weaknesses")):
        evidence.append(f"需复习：{value}")
    mastery = summary.get("mastery") if isinstance(summary.get("mastery"), dict) else {}
    if mastery.get("reflection_text"):
        evidence.append("已有复盘文本")
    return normalize_string_list(evidence)[:20]


__all__ = [
    "build_session_evidence",
    "build_session_facts",
]
