from __future__ import annotations

from typing import Any

from learn_core.text_utils import normalize_string_list
from learn_runtime.source_grounding import build_segment_source_brief

from .index_schema import get_index_entries

MATERIAL_CURATION_SCHEMA_VERSION = "learn-plan.material-curation.v1"


def _diagnostic_weaknesses(diagnostic: dict[str, Any]) -> list[str]:
    result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}
    profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    weaknesses = normalize_string_list(profile.get("weaknesses") or result.get("weaknesses") or [])
    for item in result.get("capability_assessment") or []:
        if not isinstance(item, dict):
            continue
        level = str(item.get("current_level") or item.get("status") or "").lower()
        if any(marker in level for marker in ("weak", "薄弱", "不足", "入门", "missing")):
            weaknesses.extend(normalize_string_list([item.get("capability_id"), item.get("capability")]))
    return list(dict.fromkeys([item for item in weaknesses if item]))


def _goal_requirements(research: dict[str, Any]) -> list[str]:
    report = research.get("research_report") if isinstance(research.get("research_report"), dict) else research
    values: list[str] = []
    for key in ("must_master_core", "must_master_capabilities", "mainline_capabilities", "capability_metrics", "evidence_expectations"):
        values.extend(normalize_string_list(report.get(key) if isinstance(report, dict) else []))
    return list(dict.fromkeys([item for item in values if item]))


def _entry_level(diagnostic: dict[str, Any], fallback: str = "") -> str:
    result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}
    profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    return str(result.get("recommended_entry_level") or profile.get("recommended_entry_level") or fallback or "unknown").strip()


def _compact_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}: {inner}" for key, inner in value.items() if str(inner).strip()]
    return normalize_string_list(value)


def _material_role(entry: dict[str, Any]) -> str:
    if str(entry.get("selection_status") or "") == "confirmed" and str(entry.get("role_in_plan") or "") == "mainline":
        return "mainline"
    if entry.get("downloadable") or str(entry.get("availability") or "") in {"cached", "local-downloadable"}:
        return "required-support"
    return "optional-candidate"


def _download_summary(entry: dict[str, Any]) -> dict[str, Any]:
    validation = entry.get("download_validation") if isinstance(entry.get("download_validation"), dict) else {}
    should_download = bool(entry.get("downloadable")) or str(entry.get("availability") or "") == "local-downloadable"
    return {
        "should_download": should_download,
        "reason": "已缓存" if entry.get("cache_status") == "cached" else ("可直链下载" if should_download else "仅作为在线候选或元数据资料"),
        "preflight_status": "pass" if validation.get("status") == "valid" else "unknown",
        "validation_status": validation.get("status") or ("valid" if entry.get("cache_status") == "cached" else "unknown"),
        "content_type": validation.get("content_type") or "",
        "content_length": validation.get("content_length"),
        "validated_size_bytes": validation.get("size_bytes"),
        "error": validation.get("reason") or validation.get("message") or "",
    }


def _excerpt_briefs(entry: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    briefs: list[dict[str, Any]] = []
    for segment in (entry.get("reading_segments") or [])[:limit]:
        if not isinstance(segment, dict):
            continue
        enriched_segment = {
            **segment,
            "material_id": entry.get("id"),
            "material_title": entry.get("title"),
            "material_local_path": entry.get("local_path"),
            "material_kind": entry.get("kind"),
        }
        try:
            brief = build_segment_source_brief(enriched_segment)
        except Exception:
            brief = enriched_segment
            brief.setdefault("source_status", "missing-local-content")
        briefs.append(
            {
                "segment_id": brief.get("segment_id") or segment.get("segment_id") or "",
                "locator": brief.get("locator") or segment.get("locator") or {},
                "source_status": brief.get("source_status") or "fallback-metadata",
                "source_excerpt": brief.get("source_excerpt") or "",
                "source_summary": brief.get("source_summary") or brief.get("purpose") or "",
                "source_key_points": normalize_string_list(brief.get("source_key_points") or []),
                "source_examples": normalize_string_list(brief.get("source_examples") or []),
                "source_pitfalls": normalize_string_list(brief.get("source_pitfalls") or []),
            }
        )
    return briefs


def build_material_curation(
    materials_index: dict[str, Any],
    *,
    topic: str,
    goal: str,
    level: str,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clarification = clarification or {}
    research = research or {}
    diagnostic = diagnostic or {}
    approval = approval or {}
    weaknesses = _diagnostic_weaknesses(diagnostic)
    requirements = _goal_requirements(research)
    materials: list[dict[str, Any]] = []
    for entry in get_index_entries(materials_index):
        role = _material_role(entry)
        selection_status = "confirmed" if role == "mainline" else "candidate"
        capability_alignment = normalize_string_list(entry.get("capability_alignment") or entry.get("focus_topics") or [])
        diagnostic_alignment = [item for item in weaknesses if item in capability_alignment or item in normalize_string_list(entry.get("coverage", {}).get("skills") if isinstance(entry.get("coverage"), dict) else [])]
        risks = normalize_string_list(entry.get("known_risks") or [])
        if entry.get("cache_status") in {"download-failed", "validation-failed"}:
            risks.append("材料下载或验证失败，不能作为本地主线 grounding。")
        if str(entry.get("availability") or "") == "metadata-only" and role == "optional-candidate":
            risks.append("当前仅有在线元数据，尚未验证本地可用内容。")
        materials.append(
            {
                "id": entry.get("id") or "",
                "title": entry.get("title") or entry.get("id") or "",
                "url": entry.get("url") or "",
                "local_path": entry.get("local_path") or "",
                "role": role,
                "selection_status": selection_status,
                "availability": entry.get("availability") or "metadata-only",
                "cache_status": entry.get("cache_status") or "metadata-only",
                "fit": {
                    "goal_alignment": entry.get("goal_alignment") or goal,
                    "level_fit": "unknown",
                    "capability_alignment": capability_alignment,
                    "diagnostic_gap_alignment": diagnostic_alignment,
                    "constraints_fit": "待用户确认材料负担是否匹配时间约束。",
                },
                "curation_reason": entry.get("discovery_notes") or entry.get("summary") or "候选资料，需要结合目标、起点和可下载性确认角色。",
                "risks": list(dict.fromkeys(risks)),
                "rejection_reason": "",
                "download": _download_summary(entry),
                "excerpt_briefs": _excerpt_briefs(entry),
            }
        )
    existing_curation = approval.get("material_curation") if isinstance(approval.get("material_curation"), dict) else {}
    user_confirmation = existing_curation.get("user_confirmation") if isinstance(existing_curation.get("user_confirmation"), dict) else {}
    confirmed = bool(user_confirmation.get("confirmed")) and str(existing_curation.get("status") or "") == "confirmed"
    return {
        "schema_version": MATERIAL_CURATION_SCHEMA_VERSION,
        "status": "confirmed" if confirmed else "needs-user-confirmation",
        "topic": topic,
        "goal": goal,
        "learner_fit_summary": {
            "entry_level": _entry_level(diagnostic, level),
            "observed_weaknesses": weaknesses,
            "goal_requirements": requirements,
            "constraints": _compact_values(clarification.get("questionnaire", {}).get("time_constraints") if isinstance(clarification.get("questionnaire"), dict) else []),
            "preferences": _compact_values(clarification.get("questionnaire", {}).get("learning_preferences") if isinstance(clarification.get("questionnaire"), dict) else []),
        },
        "strategy_summary": {
            "mainline_strategy": "只把目标适配、用户起点适配且有明确阅读片段的资料作为主线。",
            "supporting_strategy": "把可用但覆盖不完整的资料作为必要辅助或候选补充。",
            "download_strategy": "只缓存已确认主线或必要辅助资料；下载后必须通过内容验证。",
            "rejected_strategy": "需要登录、动态交互、空内容、错误页或难度明显不匹配的资料不进入主线。",
        },
        "materials": materials,
        "open_risks": [risk for item in materials for risk in item.get("risks", [])],
        "user_confirmation": {
            "required": True,
            "confirmed": confirmed,
            "confirmed_at": user_confirmation.get("confirmed_at"),
            "pending_questions": [] if confirmed else ["请确认主线/辅助/候选资料划分、片段范围与下载风险。"],
            "requested_changes": normalize_string_list(user_confirmation.get("requested_changes") or []),
            "confirmed_by_user_text": user_confirmation.get("confirmed_by_user_text") or "",
        },
    }


def material_curation_mainline_items(material_curation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in (material_curation.get("materials") or [])
        if isinstance(item, dict) and item.get("role") == "mainline" and item.get("selection_status") == "confirmed"
    ]
