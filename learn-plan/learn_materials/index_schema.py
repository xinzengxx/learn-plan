from __future__ import annotations

from typing import Any

INDEX_SCHEMA_VERSION = "learn-plan.materials.v1"

CACHE_FIELDS = frozenset(
    {
        "cache_status",
        "cache_note",
        "cached_at",
        "downloaded_at",
        "exists_locally",
        "last_attempt",
        "local_artifact",
        "local_path",
    }
)

PLANNING_FIELDS = frozenset(
    {
        "availability",
        "capability_alignment",
        "coverage",
        "discovery_notes",
        "goal_alignment",
        "mastery_checks",
        "reading_segments",
        "role_in_plan",
        "selection_status",
        "usage_modes",
    }
)


def get_index_entries(index_data: dict[str, Any]) -> list[dict[str, Any]]:
    entries = index_data.get("entries") or index_data.get("materials") or []
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict)]


def normalize_materials_index(index_data: dict[str, Any] | None, *, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    normalized = dict(index_data or {})
    normalized_entries = entries if entries is not None else get_index_entries(normalized)
    normalized["material_schema_version"] = normalized.get("material_schema_version") or INDEX_SCHEMA_VERSION
    normalized["entries"] = normalized_entries
    normalized["materials"] = normalized_entries
    return normalized
