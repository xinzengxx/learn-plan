from __future__ import annotations

from typing import Any

from .text_utils import normalize_string_list


QUALITY_ENVELOPE_FIELDS = (
    "generation_trace",
    "quality_review",
    "evidence",
    "confidence",
    "traceability",
)
DEFAULT_QUALITY_REVIEWER = "deterministic-quality-gate"


def normalize_confidence(value: Any, *, default: float = 0.0) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    if confidence < 0:
        return 0.0
    if confidence > 1:
        return 1.0
    return confidence


def build_traceability_entry(
    *,
    kind: str,
    ref: str,
    title: Any = None,
    detail: Any = None,
    stage: Any = None,
    status: Any = None,
    locator: Any = None,
) -> dict[str, Any]:
    entry = {
        "kind": str(kind or "reference").strip() or "reference",
        "ref": str(ref or "").strip(),
    }
    if title:
        entry["title"] = str(title).strip()
    if detail:
        entry["detail"] = str(detail).strip()
    if stage:
        entry["stage"] = str(stage).strip()
    if status:
        entry["status"] = str(status).strip()
    if locator:
        entry["locator"] = str(locator).strip()
    return entry


def normalize_traceability(values: Any, *, limit: int = 20) -> list[dict[str, Any]]:
    candidates = values
    if isinstance(candidates, dict):
        candidates = [candidates]
    elif isinstance(candidates, str):
        candidates = [candidates]
    elif not isinstance(candidates, list):
        candidates = []

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        if isinstance(item, dict):
            entry = build_traceability_entry(
                kind=str(item.get("kind") or "reference"),
                ref=str(item.get("ref") or item.get("id") or item.get("path") or item.get("source") or "").strip(),
                title=item.get("title") or item.get("label"),
                detail=item.get("detail") or item.get("reason"),
                stage=item.get("stage"),
                status=item.get("status"),
                locator=item.get("locator"),
            )
        else:
            text = str(item or "").strip()
            if not text:
                continue
            entry = build_traceability_entry(kind="reference", ref=text, title=text)
        if not entry.get("ref"):
            continue
        key = (
            str(entry.get("kind") or "reference"),
            str(entry.get("ref") or ""),
            str(entry.get("stage") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(entry)
        if len(normalized) >= limit:
            break
    return normalized


def normalize_generation_trace(
    value: Any,
    *,
    stage: str = "",
    generator: str = "",
    status: str = "",
) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    normalized = {key: source[key] for key in source.keys()}
    if stage:
        normalized.setdefault("stage", stage)
    if generator:
        normalized.setdefault("generator", generator)
    if status:
        normalized.setdefault("status", status)
    return normalized


def normalize_quality_review(
    value: Any,
    *,
    reviewer: str = DEFAULT_QUALITY_REVIEWER,
    valid: bool | None = None,
    issues: Any = None,
    warnings: Any = None,
    confidence: Any = None,
    evidence_adequacy: str | None = None,
    verdict: str | None = None,
) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    normalized = {key: source[key] for key in source.keys()}
    normalized["reviewer"] = str(source.get("reviewer") or reviewer or DEFAULT_QUALITY_REVIEWER).strip()
    issue_values = normalize_string_list(source.get("issues") if issues is None else issues)
    warning_values = normalize_string_list(source.get("warnings") if warnings is None else warnings)
    normalized["issues"] = issue_values
    normalized["warnings"] = warning_values
    normalized["valid"] = bool((source.get("valid") if valid is None else valid) if (valid is not None or "valid" in source) else (not issue_values))
    review_confidence = source.get("confidence") if confidence is None else confidence
    normalized["confidence"] = normalize_confidence(review_confidence, default=0.0)
    normalized["evidence_adequacy"] = str(source.get("evidence_adequacy") or evidence_adequacy or ("sufficient" if normalized["valid"] else "partial")).strip()
    normalized["verdict"] = str(source.get("verdict") or verdict or ("ready" if normalized["valid"] else "needs-revision")).strip()
    return normalized


def apply_quality_envelope(
    payload: dict[str, Any] | None,
    *,
    stage: str = "",
    generator: str = "",
    evidence: Any = None,
    confidence: Any = None,
    quality_review: Any = None,
    generation_trace: Any = None,
    traceability: Any = None,
) -> dict[str, Any]:
    updated = dict(payload) if isinstance(payload, dict) else {}
    normalized_evidence = normalize_string_list(updated.get("evidence") if evidence is None else evidence)
    normalized_confidence = normalize_confidence(updated.get("confidence") if confidence is None else confidence, default=0.0)
    normalized_generation_trace = normalize_generation_trace(
        updated.get("generation_trace") if generation_trace is None else generation_trace,
        stage=stage,
        generator=generator,
    )
    normalized_traceability = normalize_traceability(updated.get("traceability") if traceability is None else traceability)
    updated["evidence"] = normalized_evidence
    updated["confidence"] = normalized_confidence
    updated["generation_trace"] = normalized_generation_trace
    updated["traceability"] = normalized_traceability
    updated["quality_review"] = normalize_quality_review(
        updated.get("quality_review") if quality_review is None else quality_review,
        confidence=normalized_confidence,
    )
    return updated


def collect_quality_issues(
    payload: dict[str, Any] | None,
    *,
    prefix: str,
    require_evidence: bool = True,
    require_traceability: bool = True,
    require_generation_trace: bool = True,
    require_review: bool = True,
    require_valid_review: bool = False,
    min_confidence: float | None = None,
) -> list[str]:
    if not isinstance(payload, dict) or not payload:
        return [f"{prefix}.missing"]

    issues: list[str] = []
    evidence = normalize_string_list(payload.get("evidence"))
    traceability = normalize_traceability(payload.get("traceability"))
    generation_trace = payload.get("generation_trace") if isinstance(payload.get("generation_trace"), dict) else {}
    review = payload.get("quality_review") if isinstance(payload.get("quality_review"), dict) else {}
    confidence = normalize_confidence(payload.get("confidence"), default=-1.0)

    if require_evidence and not evidence:
        issues.append(f"{prefix}.evidence_missing")
    if require_traceability and not traceability:
        issues.append(f"{prefix}.traceability_missing")
    if require_generation_trace and not generation_trace:
        issues.append(f"{prefix}.generation_trace_missing")
    if require_review and not review:
        issues.append(f"{prefix}.quality_review_missing")
    elif require_review:
        if not str(review.get("reviewer") or "").strip():
            issues.append(f"{prefix}.quality_review_reviewer_missing")
        if require_valid_review and not bool(review.get("valid")):
            issues.append(f"{prefix}.quality_review_invalid")
        for item in normalize_string_list(review.get("issues")):
            issues.append(f"{prefix}.review:{item}")
    if min_confidence is not None:
        if confidence < 0:
            issues.append(f"{prefix}.confidence_missing")
        elif confidence < float(min_confidence):
            issues.append(f"{prefix}.confidence_below_threshold")
    return issues


__all__ = [
    "DEFAULT_QUALITY_REVIEWER",
    "QUALITY_ENVELOPE_FIELDS",
    "apply_quality_envelope",
    "build_traceability_entry",
    "collect_quality_issues",
    "normalize_confidence",
    "normalize_generation_trace",
    "normalize_quality_review",
    "normalize_traceability",
]
