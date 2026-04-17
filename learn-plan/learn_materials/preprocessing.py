from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def default_preprocessing_state(material: dict[str, Any], *, status: str = "not-started", note: str | None = None) -> dict[str, Any]:
    local_path = material.get("local_path")
    file_type = Path(str(local_path)).suffix.lstrip(".") if local_path else None
    return {
        "status": status,
        "file_type": file_type or None,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "note": note or "预处理入口已保留；当前版本不强制解析本地材料全文。",
    }


def update_preprocessing_status(material: dict[str, Any], *, status: str, note: str | None = None) -> dict[str, Any]:
    updated = dict(material)
    updated["preprocessing_status"] = status
    updated["source_excerpt_status"] = updated.get("source_excerpt_status") or "not-built"
    updated["preprocessing"] = default_preprocessing_state(updated, status=status, note=note)
    return updated


def preprocess_material(material: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    current_status = str(material.get("preprocessing_status") or "not-started")
    if current_status == "ready" and not force:
        return dict(material)
    return update_preprocessing_status(
        material,
        status="not-started",
        note="预处理尚未启用；runtime 应基于 local_path / reading_segments / metadata fallback。",
    )
