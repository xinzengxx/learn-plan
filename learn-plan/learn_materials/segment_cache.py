from __future__ import annotations

from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists, write_json


def segment_cache_path(materials_dir: Path) -> Path:
    return materials_dir / "segment_cache.json"


def load_segment_cache(path: Path) -> dict[str, Any]:
    return read_json_if_exists(path)


def write_segment_cache(path: Path, cache_data: dict[str, Any]) -> None:
    write_json(path, cache_data)


def get_segment_excerpt(cache_data: dict[str, Any], material_id: str, segment_id: str) -> dict[str, Any] | None:
    materials = cache_data.get("materials") or {}
    if not isinstance(materials, dict):
        return None
    material_cache = materials.get(material_id) or {}
    if not isinstance(material_cache, dict):
        return None
    segments = material_cache.get("segments") or {}
    if not isinstance(segments, dict):
        return None
    excerpt = segments.get(segment_id)
    return excerpt if isinstance(excerpt, dict) else None
