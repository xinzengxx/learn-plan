from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists, read_text_if_exists
from learn_core.text_utils import normalize_string_list
from learn_runtime.plan_source import day_matches, normalize_day_key
from learn_runtime.source_grounding import (
    build_segment_source_brief,
    segment_specificity,
    source_brief_has_substance,
)

GIT_POSITIVE_SIGNALS = [
    "git", "pro git", "版本控制", "仓库", "repository", "暂存", "staging",
    "提交", "commit", "branch", "分支", "merge", "remote", "head",
]
GIT_NEGATIVE_ONLY_SIGNALS = [
    "http", "json", "日志", "logging", "testing", "测试", "deploy", "部署", "database", "数据库",
    "前端", "后端", "api", "reference", "tooling", "tutorial",
]


def text_has_any(text: str, signals: list[str]) -> bool:
    lower_text = str(text or "").lower()
    return any(signal.lower() in lower_text for signal in signals if signal)


def material_text_blob(material: dict[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in [
            material.get("id"),
            material.get("title"),
            material.get("source_name"),
            material.get("use"),
            material.get("summary"),
            " ".join(str(item) for item in material.get("tags") or []),
            " ".join(str(item) for item in material.get("focus_topics") or []),
            " ".join(str(item) for item in material.get("capability_alignment") or []),
        ]
    )


def prefer_precise_segments(selected_segments: list[dict[str, Any]], target_segment_ids: set[str]) -> list[dict[str, Any]]:
    if not selected_segments:
        return []
    precise_ids = {
        str(item).strip()
        for item in target_segment_ids
        if str(item).strip() and str(item).strip() != "python-crash-course-3e-segment-3"
    }
    if not precise_ids:
        return selected_segments

    precise_segments = [segment for segment in selected_segments if str(segment.get("segment_id") or "") in precise_ids]
    if precise_segments:
        return sorted(
            precise_segments,
            key=lambda item: (
                source_brief_has_substance(item),
                int(item.get("match_score") or 0),
                segment_specificity(item),
            ),
            reverse=True,
        )

    return sorted(
        selected_segments,
        key=lambda item: (
            str(item.get("match_reason") or "") == "explicit-target-segment",
            source_brief_has_substance(item),
            int(item.get("match_score") or 0),
            segment_specificity(item),
        ),
        reverse=True,
    )


def choose_material_local_path(item: dict[str, Any]) -> Any:
    local_path = item.get("local_path")
    artifact_path = (item.get("local_artifact") or {}).get("path") if isinstance(item.get("local_artifact"), dict) else None
    if artifact_path:
        expanded_artifact = Path(str(artifact_path)).expanduser()
        expanded_local = Path(str(local_path)).expanduser() if local_path else None
        if expanded_artifact.exists() and (expanded_local is None or not expanded_local.exists()):
            return artifact_path
    return local_path or artifact_path


def normalize_material_item(item: dict[str, Any], topic: str) -> dict[str, Any]:
    local_path = choose_material_local_path(item)
    local_exists = bool(Path(str(local_path)).expanduser().exists()) if local_path else False
    return {
        "id": item.get("id") or item.get("title") or "material",
        "title": item.get("title") or item.get("id") or "未命名材料",
        "topic": item.get("topic") or topic,
        "domain": item.get("domain"),
        "kind": item.get("kind") or "reference",
        "use": item.get("use") or "配合当前 session 学习",
        "summary": item.get("summary"),
        "source_name": item.get("source_name"),
        "source_type": item.get("source_type"),
        "url": item.get("url"),
        "local_path": local_path,
        "cache_status": item.get("cache_status") or ("cached" if local_exists or item.get("exists_locally") else "metadata-only"),
        "cache_note": item.get("cache_note"),
        "tags": item.get("tags") or [],
        "focus_topics": item.get("focus_topics") or [],
        "exists_locally": local_exists or bool(item.get("exists_locally")),
        "selection_status": item.get("selection_status"),
        "availability": item.get("availability"),
        "role_in_plan": item.get("role_in_plan") or "optional",
        "goal_alignment": item.get("goal_alignment") or topic,
        "capability_alignment": item.get("capability_alignment") or [],
        "reading_segments": item.get("reading_segments") or [],
        "mastery_checks": item.get("mastery_checks") or {},
        "local_artifact": item.get("local_artifact") or {},
    }


def load_materials(plan_path: Path, topic: str) -> list[dict[str, Any]]:
    candidate_indexes: list[Path] = []
    plan_text = read_text_if_exists(plan_path)
    material_dir_match = re.search(r"^- 本地目录：`(?P<path>[^`]+)`", plan_text, re.MULTILINE)
    if material_dir_match:
        candidate_indexes.append(Path(material_dir_match.group("path")).expanduser() / "index.json")
    if plan_path.stem.startswith("learn-plan-"):
        suffix = plan_path.stem[len("learn-plan-"):]
        candidate_indexes.append(plan_path.parent / f"materials-{suffix}" / "index.json")
    candidate_indexes.append(plan_path.parent / "materials" / "index.json")

    seen_paths: set[str] = set()
    data: dict[str, Any] = {}
    for materials_index in candidate_indexes:
        key = str(materials_index)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        loaded = read_json_if_exists(materials_index)
        if loaded:
            data = loaded
            break

    entries = data.get("entries") or data.get("materials") or []
    if not isinstance(entries, list):
        return []

    result = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        item_topic = str(item.get("topic") or "").strip()
        if item_topic and item_topic != topic:
            continue
        result.append(normalize_material_item(item, topic))
    return result


def segment_matches_day(segment: dict[str, Any], day: Any) -> bool:
    if not day:
        return False
    recommended_for = segment.get("recommended_for") if isinstance(segment.get("recommended_for"), dict) else {}
    days = normalize_string_list(recommended_for.get("days") or [])
    if any(day_matches(day, candidate) for candidate in days):
        return True
    return day_matches(day, segment.get("label"))


def material_matches_recommendation(material: dict[str, Any], recommended_materials: list[str]) -> bool:
    if not recommended_materials:
        return False
    material_names = normalize_string_list([
        material.get("id"),
        material.get("title"),
        material.get("source_name"),
    ])
    material_blob = " ".join(material_names).lower()
    for recommendation in recommended_materials:
        rec = str(recommendation or "").strip().lower()
        if rec and (rec in material_blob or any(name and name.lower() in rec for name in material_names)):
            return True
    return False


def select_material_segments(materials: list[dict[str, Any]], plan_source: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    review_terms = normalize_string_list(plan_source.get("review") or plan_source.get("weakness_focus"))
    new_terms = normalize_string_list(plan_source.get("new_learning"))
    exercise_terms = normalize_string_list(plan_source.get("exercise_focus"))
    supporting_terms = normalize_string_list(plan_source.get("supporting_capabilities"))
    enhancement_terms = normalize_string_list(plan_source.get("enhancement_modules"))
    recommended_materials = normalize_string_list(plan_source.get("recommended_materials"))
    preferred_stage = str(plan_source.get("current_stage") or "")
    preferred_day = plan_source.get("day")
    target_segment_ids = set(normalize_string_list(plan_source.get("target_segment_ids") or []))
    selected_segments: list[dict[str, Any]] = []
    mastery_targets = {
        "reading_checklist": [],
        "session_exercises": normalize_string_list(plan_source.get("exercise_focus") or []),
        "applied_project": [],
        "reflection": [],
    }

    def segment_blob(segment: dict[str, Any], material: dict[str, Any]) -> str:
        locator = segment.get("locator") if isinstance(segment, dict) else {}
        return " ".join(
            [
                str(segment.get("segment_id") or ""),
                str(segment.get("label") or material.get("title") or ""),
                str(locator.get("chapter") or "") if isinstance(locator, dict) else "",
                " ".join(str(item) for item in (locator.get("sections") or [])) if isinstance(locator, dict) else "",
                " ".join(str(item) for item in segment.get("checkpoints") or []),
                " ".join(str(item) for item in segment.get("target_clusters") or []),
                " ".join(str(item) for item in material.get("capability_alignment") or []),
            ]
        )

    def enrich_segment(segment: dict[str, Any], material: dict[str, Any], role: str, *, match_reason: str, match_score: int) -> dict[str, Any]:
        return {
            **segment,
            "material_id": material.get("id"),
            "material_title": material.get("title"),
            "material_summary": material.get("summary") or material.get("use"),
            "material_source_name": material.get("source_name"),
            "material_source_type": material.get("source_type"),
            "material_local_path": material.get("local_path"),
            "material_kind": material.get("kind"),
            "material_teaching_style": material.get("teaching_style"),
            "role_in_plan": role,
            "goal_alignment": material.get("goal_alignment"),
            "capability_alignment": material.get("capability_alignment") or [],
            "recommended_for": segment.get("recommended_for") or {},
            "target_clusters": segment.get("target_clusters") or [],
            "match_reason": match_reason,
            "match_score": match_score,
        }

    candidates: list[tuple[int, int, dict[str, Any]]] = []
    fallback_candidates: list[tuple[int, int, dict[str, Any]]] = []
    role_rank = {"mainline": 3, "supporting": 2, "optional": 1}
    focus_terms = review_terms + new_terms + exercise_terms
    domain = str(plan_source.get("domain") or "").strip().lower()
    topic_blob = " ".join(
        str(value or "")
        for value in [
            plan_source.get("topic"),
            plan_source.get("today_topic"),
            plan_source.get("mainline_goal"),
            plan_source.get("day"),
            *review_terms,
            *new_terms,
            *exercise_terms,
        ]
    )
    git_session = domain == "git" or text_has_any(topic_blob, GIT_POSITIVE_SIGNALS)
    for material in materials:
        material_blob_text = material_text_blob(material)
        material_has_local_content = bool(material.get("local_path") and Path(str(material.get("local_path"))).expanduser().exists())
        if material.get("selection_status") not in {None, "confirmed"}:
            if not (material.get("cache_status") == "cached" and material_has_local_content):
                continue
            if git_session and not text_has_any(material_blob_text, GIT_POSITIVE_SIGNALS):
                continue
        role = str(material.get("role_in_plan") or "optional")
        material_match = material_matches_recommendation(material, recommended_materials)
        material_git_match = git_session and text_has_any(material_blob_text, GIT_POSITIVE_SIGNALS)
        for segment in material.get("reading_segments") or []:
            if not isinstance(segment, dict):
                continue
            blob = segment_blob(segment, material)
            blob_lower = blob.lower()
            segment_id = str(segment.get("segment_id") or "").strip()
            explicit_match = bool(segment_id and segment_id in target_segment_ids)
            day_match = segment_matches_day(segment, preferred_day)
            focus_match = any(term and term.lower() in blob_lower for term in focus_terms)
            support_match = role == "supporting" and any(term and term.lower() in blob_lower for term in supporting_terms)
            enhancement_match = role == "optional" and any(term and term.lower() in blob_lower for term in enhancement_terms)
            stage_match = bool(preferred_stage and preferred_stage in blob)
            combined_blob = f"{blob} {material_blob_text}"
            segment_git_match = git_session and text_has_any(combined_blob, GIT_POSITIVE_SIGNALS)

            score = 0
            reason = ""
            if explicit_match:
                score = 100
                reason = "explicit-target-segment"
            elif git_session and segment_git_match and day_match:
                score = 110 if material_match or material_git_match else 95
                reason = "git-material+day"
            elif git_session and segment_git_match and (material_match or focus_match):
                score = 85
                reason = "git-material+focus"
            elif git_session and segment_git_match:
                score = 70
                reason = "git-material"
            elif day_match:
                score = 90 if material_match else 80
                reason = "recommended-day" if not material_match else "recommended-material+day"
            elif material_match and focus_match:
                score = 65
                reason = "recommended-material+checkpoint-overlap"
            elif focus_match:
                score = 55
                reason = "checkpoint-overlap"
            elif support_match:
                score = 45
                reason = "supporting-capability-overlap"
            elif enhancement_match:
                score = 35
                reason = "enhancement-overlap"
            elif stage_match:
                score = 10
                reason = "broad-stage-fallback"

            if git_session and not segment_git_match:
                score = min(score, 20)
                if score:
                    reason = f"non-git-{reason or 'fallback'}"

            if score >= 35:
                candidates.append((score, role_rank.get(role, 0), enrich_segment(segment, material, role, match_reason=reason, match_score=score)))
            elif stage_match:
                fallback_candidates.append((score, role_rank.get(role, 0), enrich_segment(segment, material, role, match_reason=reason or "broad-stage-fallback", match_score=score)))

    usable_candidates = candidates if candidates else fallback_candidates
    usable_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)

    seen_segment_ids: set[str] = set()
    for _, _, segment in usable_candidates:
        segment_id = str(segment.get("segment_id") or "")
        if not segment_id or segment_id in seen_segment_ids:
            continue
        seen_segment_ids.add(segment_id)
        selected_segments.append(segment)
        for checkpoint in segment.get("checkpoints") or []:
            if checkpoint not in mastery_targets["reading_checklist"]:
                mastery_targets["reading_checklist"].append(checkpoint)
        mastery_targets["reflection"].append(f"解释 {segment.get('label') or segment_id} 的关键概念与实际用途")
        mastery_targets["applied_project"].append(f"基于 {segment.get('label') or segment_id} 做 1 个小练习或小项目")
        if len(selected_segments) >= 4:
            break

    if not selected_segments:
        fallback_materials = materials
        if git_session:
            fallback_materials = [material for material in materials if text_has_any(material_text_blob(material), GIT_POSITIVE_SIGNALS)] or materials
        for material in fallback_materials[:3]:
            role = str(material.get("role_in_plan") or "optional")
            for segment in (material.get("reading_segments") or [])[:1]:
                segment_id = str(segment.get("segment_id") or "")
                if not segment_id or segment_id in seen_segment_ids:
                    continue
                seen_segment_ids.add(segment_id)
                selected_segment = enrich_segment(segment, material, role, match_reason="first-material-fallback", match_score=0)
                selected_segments.append(selected_segment)
                for checkpoint in selected_segment.get("checkpoints") or []:
                    if checkpoint not in mastery_targets["reading_checklist"]:
                        mastery_targets["reading_checklist"].append(checkpoint)
                mastery_targets["reflection"].append(f"解释 {selected_segment.get('label') or segment_id} 的关键概念与实际用途")
                mastery_targets["applied_project"].append(f"基于 {selected_segment.get('label') or segment_id} 做 1 个小练习或小项目")
                break
            if len(selected_segments) >= 3:
                break

    selected_segments = selected_segments[:4]
    selected_segments = [build_segment_source_brief(item) for item in selected_segments]
    if git_session:
        git_segments = [segment for segment in selected_segments if text_has_any(f"{segment.get('segment_id')} {segment.get('label')} {segment.get('material_title')} {segment.get('source_summary')} {' '.join(str(item) for item in segment.get('source_key_points') or [])}", GIT_POSITIVE_SIGNALS)]
        if git_segments:
            selected_segments = git_segments
    selected_segments = prefer_precise_segments(selected_segments, target_segment_ids)
    match_reasons = [str(item.get("match_reason") or "") for item in selected_segments if item.get("match_reason")]
    aligned_reason_prefixes = ("explicit", "recommended", "checkpoint", "git-material")
    material_alignment = {
        "status": "aligned" if selected_segments and any(reason.startswith(aligned_reason_prefixes) for reason in match_reasons) else ("fallback" if selected_segments else "missing"),
        "target_day_key": normalize_day_key(preferred_day),
        "selected_segment_ids": [str(item.get("segment_id")) for item in selected_segments if item.get("segment_id")],
        "material_ids": [str(item.get("material_id")) for item in selected_segments if item.get("material_id")],
        "match_reasons": match_reasons,
        "selection_mode": (
            "exact-segment" if any(reason == "explicit-target-segment" for reason in match_reasons)
            else "git-grounded" if any(reason.startswith("git-material") for reason in match_reasons)
            else "same-day-broad" if any(reason.startswith(("recommended", "checkpoint")) for reason in match_reasons)
            else "metadata-fallback"
        ),
        "source_statuses": [str(item.get("source_status") or "fallback-metadata") for item in selected_segments],
        "fallback_reasons": [str(item.get("match_reason") or "") for item in selected_segments if str(item.get("source_status") or "") != "extracted"],
    }
    plan_source["material_alignment"] = material_alignment
    return selected_segments, mastery_targets
