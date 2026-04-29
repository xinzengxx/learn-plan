from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from learn_core.text_utils import sanitize_filename

from .merge import merge_material_entries
from .segments import build_reading_segments, infer_material_recommended_day


def enrich_material_entry(entry: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(entry)
    kind = str(enriched.get("kind") or "")
    if not enriched.get("summary"):
        enriched["summary"] = enriched.get("use") or f"{enriched.get('title', '材料')}，用于 {curriculum['topic']} 学习。"
    if kind == "book":
        enriched["summary"] = enriched.get("summary") or enriched.get("use")
        enriched["teaching_style"] = "chapter-lecture"
    elif kind == "tutorial":
        enriched["summary"] = enriched.get("summary") or f"这是一份偏步骤型教程，适合按概念、步骤、结果的顺序学习 {curriculum['topic']}。"
        enriched["teaching_style"] = "step-by-step"
    elif kind == "reference":
        enriched["summary"] = enriched.get("summary") or f"这是一份偏查阅型参考资料，适合围绕定义、接口、使用边界学习 {curriculum['topic']}。"
        enriched["teaching_style"] = "concept-reference"
    else:
        enriched.setdefault("teaching_style", "general")
    if not enriched.get("focus_topics"):
        tags = [str(tag) for tag in enriched.get("tags") or [] if str(tag).strip()]
        enriched["focus_topics"] = tags[:5] or [curriculum["topic"]]
    if not enriched.get("recommended_stage"):
        stages = [stage["name"] for stage in curriculum["stages"]]
        if kind in {"reference", "tutorial"}:
            enriched["recommended_stage"] = stages[:2] or stages
        elif kind in {"practice", "roadmap"}:
            enriched["recommended_stage"] = stages[1:] or stages
        else:
            enriched["recommended_stage"] = stages
    if not enriched.get("recommended_day"):
        enriched["recommended_day"] = infer_material_recommended_day(enriched, curriculum)
    if not enriched.get("exercise_types"):
        enriched["exercise_types"] = [stage["practice"] for stage in curriculum["stages"][:2]]
    return enriched


def build_default_material_entries(
    topic: str,
    domain: str,
    materials_dir: Path,
    curriculum: dict[str, Any],
    *,
    family_configs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    family_config = family_configs.get(domain, family_configs["general-cs"])
    entries = []
    for item in family_config.get("materials", []):
        kind = item.get("kind") or "reference"
        safe_title = sanitize_filename(item.get("title") or item["id"])
        local_path = materials_dir / domain / kind / f"{item['id']}_{safe_title}"
        entry = enrich_material_entry(item, curriculum)
        entry["topic"] = topic
        entry["domain"] = domain
        entry["local_path"] = str(local_path)
        local_exists = local_path.exists()
        is_local_mainline = entry.get("source_type") == "local"
        entry["availability"] = "cached" if local_exists else ("local-downloadable" if entry.get("downloadable") or is_local_mainline else "metadata-only")
        entry["selection_status"] = "confirmed" if local_exists or entry.get("downloadable") or is_local_mainline else "candidate"
        entry["coverage"] = {
            "topic": topic,
            "stages": entry.get("recommended_stage") or [],
            "skills": entry.get("focus_topics") or [],
        }
        entry["goal_alignment"] = topic
        entry["capability_alignment"] = (entry.get("focus_topics") or [topic])[:3]
        entry["role_in_plan"] = "mainline" if entry["selection_status"] == "confirmed" else "optional"
        entry["usage_modes"] = ["reading", "reference"] if kind in {"book", "tutorial", "reference"} else ["reference"]
        entry["discovery_notes"] = (
            "主线资料：可本地获得或可直链下载，适合作为正式学习材料。"
            if entry["selection_status"] == "confirmed"
            else "候选资料：当前无法直接落地到本地，仅作补充参考，不应直接进入主线。"
        )
        entry["reading_segments"] = build_reading_segments(entry, curriculum)
        entry["mastery_checks"] = {
            "reading_checklist": entry.get("focus_topics") or [topic],
            "session_exercises": entry.get("exercise_types") or [],
            "applied_project": [f"围绕 {entry.get('title') or topic} 做 1 个小练习或小项目"],
            "reflection": [f"用自己的话解释 {entry.get('title') or topic} 的关键概念与实际用途"],
        }
        if local_exists:
            entry["cache_status"] = "cached"
            entry["cached_at"] = time.strftime("%Y-%m-%d")
        entries.append(entry)
    return entries


def build_materials_index(
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    materials_dir: Path,
    plan_path: Path,
    existing: dict[str, Any],
    *,
    domain: str,
    curriculum: dict[str, Any],
    family_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    data = dict(existing) if existing else {}
    existing_pool = data.get("entries") or data.get("items") or data.get("materials") or []
    index_domain = str(data.get("domain") or "").strip()
    existing_entries: list[dict[str, Any]] = []
    for item in existing_pool:
        if not isinstance(item, dict):
            continue
        item_domain = str(item.get("domain") or index_domain or "").strip()
        if item_domain and item_domain != domain:
            continue
        normalized_item = dict(item)
        normalized_item["domain"] = item_domain or domain
        existing_entries.append(normalized_item)
    entries = merge_material_entries(
        existing_entries,
        build_default_material_entries(topic, domain, materials_dir, curriculum, family_configs=family_configs),
    )
    confirmed_entries = [item for item in entries if item.get("selection_status") == "confirmed" and item.get("role_in_plan") == "mainline"]
    candidate_entries = [item for item in entries if item.get("selection_status") != "confirmed" or item.get("role_in_plan") != "mainline"]
    data["topic"] = topic
    data["goal"] = goal
    data["level"] = level
    data["schedule"] = schedule
    data["preference"] = preference
    data["domain"] = domain
    data["updated_at"] = time.strftime("%Y-%m-%d")
    data["plan_path"] = str(plan_path)
    data["materials_dir"] = str(materials_dir)
    data["material_policy"] = "正式主线资料必须优先使用本地已存在或可直链下载到本地的材料。"
    data["entries"] = entries
    data["items"] = entries
    data["materials"] = entries
    data["confirmed_materials"] = confirmed_entries
    data["candidate_materials"] = candidate_entries
    data["sources"] = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "url": item.get("url"),
            "source_name": item.get("source_name"),
            "source_type": item.get("source_type"),
            "selection_status": item.get("selection_status"),
            "availability": item.get("availability"),
        }
        for item in entries
    ]
    data["local_materials"] = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "local_path": item.get("local_path"),
            "reading_segments": item.get("reading_segments") or [],
        }
        for item in entries
        if item.get("cache_status") == "cached" and item.get("local_path")
    ]
    curation_candidate_fields = (
        "id", "title", "url", "direct_url", "role_in_plan", "selection_status",
        "availability", "cache_status", "downloadable", "local_path", "goal_alignment",
        "capability_alignment", "coverage", "reading_segments", "mastery_checks",
        "discovery_notes", "known_risks",
    )
    curation_candidates = [
        {field: item.get(field) for field in curation_candidate_fields if field in item}
        for item in entries
    ]
    data["curation_inputs"] = {
        "requires_user_confirmation": True,
        "mainline_candidates": [item for item in curation_candidates if item.get("selection_status") == "confirmed" and item.get("role_in_plan") == "mainline"],
        "support_candidates": [item for item in curation_candidates if item.get("selection_status") == "confirmed" and item.get("role_in_plan") != "mainline"],
        "optional_candidates": [item for item in curation_candidates if item.get("selection_status") != "confirmed"],
        "rejected_or_unusable": [],
    }
    data["notes"] = "当前版本要求主线资料优先本地可得，并为主线资料补充章节/页码/小节级阅读定位与掌握度检验信息。"
    return data
