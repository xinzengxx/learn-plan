from __future__ import annotations

from typing import Any

from learn_core.quality_review import apply_quality_envelope, build_traceability_entry, normalize_confidence
from learn_core.text_utils import normalize_string_list
from learn_runtime.question_generation import is_valid_runtime_question


REQUIRED_TOP_LEVEL = ["date", "topic", "mode", "session_type", "test_mode", "plan_source", "materials", "questions"]
FALLBACK_SOURCE_STATUSES = {"fallback-metadata", "metadata-fallback", "domain-bank-fallback", "bank-fallback"}


def question_source_marker(item: dict[str, Any]) -> str:
    for key in ("source_status", "source_trace", "source_segment_id", "source_material_title", "material_segment_id"):
        value = item.get(key)
        if value:
            return str(value)
    tags = normalize_string_list(item.get("tags"))
    if "content-derived" in tags:
        return str(item.get("source_status") or "content-derived")
    if "lesson-derived" in tags:
        return str(item.get("source_trace") or "daily_lesson_plan")
    return "bank-fallback"


def question_has_answer_and_explanation(item: dict[str, Any]) -> bool:
    category = str(item.get("category") or "")
    if category == "concept":
        return "answer" in item and bool(str(item.get("explanation") or "").strip())
    if category == "code":
        return bool(item.get("solution_code") or item.get("expected_code") or item.get("explanation"))
    if category == "open":
        reference_points = item.get("reference_points")
        has_reference_points = isinstance(reference_points, list) and any(str(point).strip() for point in reference_points)
        has_grading_hint = bool(str(item.get("grading_hint") or "").strip())
        has_explanation = bool(str(item.get("explanation") or "").strip())
        return has_reference_points or has_grading_hint or has_explanation
    return False


def question_traceability_status(item: dict[str, Any], marker: str) -> str:
    source_status = str(item.get("source_status") or "").strip()
    if source_status:
        return source_status
    tags = normalize_string_list(item.get("tags"))
    if "lesson-derived" in tags:
        return "lesson-derived"
    if "content-derived" in tags:
        return "content-derived"
    if marker in FALLBACK_SOURCE_STATUSES or "fallback" in marker:
        return "bank-fallback"
    return "derived"


def question_traceability_locator(item: dict[str, Any]) -> str | None:
    for key in ("source_segment_id", "material_segment_id"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    source_trace = item.get("source_trace")
    if isinstance(source_trace, dict):
        for key in ("segment_id", "source_segment_id", "material_segment_id"):
            value = str(source_trace.get(key) or "").strip()
            if value:
                return value
    return None


def validate_question_item(item: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["题目不是 object"]
    qid = str(item.get("id") or "<missing-id>")
    if not is_valid_runtime_question(item):
        issues.append(f"{qid}: schema 不合法")
    if not question_has_answer_and_explanation(item):
        issues.append(f"{qid}: 缺少答案或解析/参考解")
    marker = question_source_marker(item)
    if not marker:
        issues.append(f"{qid}: 缺少来源或 fallback 标记")
    if str(item.get("question_role") or "").strip() == "":
        tags = normalize_string_list(item.get("tags"))
        if "content-derived" in tags or "lesson-derived" in tags:
            issues.append(f"{qid}: 内容生成题缺少 question_role")
    return issues


def validate_questions_payload(data: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            issues.append(f"questions.json 缺少字段: {key}")
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        issues.append("questions 必须是非空列表")
        questions = []
    ids: set[str] = set()
    source_markers: list[str] = []
    fallback_count = 0
    category_counts: dict[str, int] = {}
    traceability: list[dict[str, Any]] = []
    for item in questions:
        if isinstance(item, dict):
            qid = str(item.get("id") or "")
            category = str(item.get("category") or "unknown")
            category_counts[category] = category_counts.get(category, 0) + 1
            if not qid:
                issues.append("存在题目缺少 id")
            elif qid in ids:
                issues.append(f"存在重复题目 id: {qid}")
            else:
                ids.add(qid)
            marker = question_source_marker(item)
            source_markers.append(marker)
            if marker in FALLBACK_SOURCE_STATUSES or "fallback" in marker:
                fallback_count += 1
            traceability.append(
                build_traceability_entry(
                    kind="question",
                    ref=qid or marker or "question",
                    title=item.get("title") or item.get("question") or item.get("prompt") or qid or "question",
                    detail=item.get("question_role") or category,
                    stage="questions",
                    status=question_traceability_status(item, marker),
                    locator=question_traceability_locator(item),
                )
            )
        issues.extend(validate_question_item(item))
    if questions and fallback_count == len(questions):
        warnings.append("所有题目均为 fallback 来源，未能形成可靠 source grounding")
    if questions and not category_counts.get("concept"):
        warnings.append("本次 payload 没有 concept 题")

    evidence = normalize_string_list(
        [
            *[f"题目总数 {len(questions)}"],
            *[f"fallback 题数 {fallback_count}"],
            *[f"类别 {key}:{value}" for key, value in sorted(category_counts.items())],
            *source_markers[:6],
        ]
    )[:20]
    confidence = 0.85 if not issues else 0.35
    if warnings:
        confidence = min(confidence, 0.65)
    if questions and fallback_count == len(questions):
        confidence = min(confidence, 0.45)

    result = {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "question_count": len(questions),
        "category_counts": category_counts,
        "fallback_count": fallback_count,
        "source_markers": source_markers[:20],
    }
    return apply_quality_envelope(
        result,
        stage="questions",
        generator="runtime-question-validation",
        evidence=evidence,
        confidence=confidence,
        quality_review={
            "reviewer": "runtime-question-quality-gate",
            "valid": not issues,
            "issues": issues,
            "warnings": warnings,
            "confidence": confidence,
            "evidence_adequacy": "sufficient" if not issues else "partial",
            "verdict": "ready" if not issues else "needs-revision",
        },
        generation_trace={
            "stage": "questions",
            "generator": "runtime-question-validation",
            "status": "validated",
            "question_count": len(questions),
            "fallback_count": fallback_count,
        },
        traceability=traceability[:20],
    )


def ensure_questions_payload_quality(data: dict[str, Any]) -> dict[str, Any]:
    result = validate_questions_payload(data)
    review = result.get("quality_review") if isinstance(result.get("quality_review"), dict) else {}
    issues = normalize_string_list(review.get("issues") or result.get("issues"))
    if not bool(review.get("valid", result.get("valid"))):
        raise ValueError("questions.json 质量校验失败: " + "；".join(issues[:8]))
    return result


__all__ = [
    "FALLBACK_SOURCE_STATUSES",
    "REQUIRED_TOP_LEVEL",
    "ensure_questions_payload_quality",
    "question_has_answer_and_explanation",
    "question_source_marker",
    "question_traceability_locator",
    "question_traceability_status",
    "validate_question_item",
    "validate_questions_payload",
]
