from __future__ import annotations

import json
from pathlib import Path
from typing import Any


LEGACY_RUNTIME_FIELDS = {
    "cache_note",
    "downloaded_at",
    "exists_locally",
    "local_artifact",
}


def merge_reading_segments(default_segments: list[dict[str, Any]], existing_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged_by_id: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []

    for segment in default_segments:
        if not isinstance(segment, dict):
            continue
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id:
            continue
        ordered_ids.append(segment_id)
        merged_by_id[segment_id] = json.loads(json.dumps(segment))

    for segment in existing_segments:
        if not isinstance(segment, dict):
            continue
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id:
            continue
        if segment_id not in ordered_ids:
            ordered_ids.append(segment_id)
        default_segment = merged_by_id.get(segment_id, {})
        merged_by_id[segment_id] = {**default_segment, **json.loads(json.dumps(segment))}

    return [merged_by_id[segment_id] for segment_id in ordered_ids if segment_id in merged_by_id]


def merge_material_entries(existing_entries: list[dict[str, Any]], default_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    schema_critical_fields = {
        "role_in_plan",
        "goal_alignment",
        "capability_alignment",
        "mastery_checks",
        "coverage",
        "usage_modes",
        "discovery_notes",
        "selection_status",
        "availability",
    }
    runtime_preferred_fields = {
        "cache_status",
        "cached_at",
        "last_attempt",
        "local_path",
        "download_validation",
    }
    for item in existing_entries:
        if isinstance(item, dict) and item.get("id"):
            merged[item["id"]] = dict(item)
    for item in default_entries:
        current = merged.get(item["id"], {})
        merged_item = {**item, **current}
        for field in schema_critical_fields:
            if field in item:
                merged_item[field] = json.loads(json.dumps(item[field]))
        merged_item["reading_segments"] = merge_reading_segments(
            item.get("reading_segments") or [],
            current.get("reading_segments") or [],
        )
        for field in runtime_preferred_fields:
            if field in current:
                merged_item[field] = json.loads(json.dumps(current[field]))
        merged_item["topic"] = item.get("topic")
        merged_item["domain"] = item.get("domain")
        if not merged_item.get("local_path"):
            merged_item["local_path"] = item.get("local_path")
        for legacy_field in LEGACY_RUNTIME_FIELDS:
            merged_item.pop(legacy_field, None)
        merged[item["id"]] = merged_item
        local_path = merged[item["id"]].get("local_path")
        if local_path:
            exists_locally = Path(local_path).exists()
            if exists_locally:
                merged[item["id"]]["cache_status"] = "cached"
            else:
                merged[item["id"]].setdefault("cache_status", "metadata-only")
    return list(merged.values())
