from __future__ import annotations

from copy import deepcopy
from typing import Any


def append_update_history(progress: dict[str, Any], entry: dict[str, Any], *, limit: int = 20) -> dict[str, Any]:
    updated = deepcopy(progress) if isinstance(progress, dict) else {}
    history = updated.get("update_history") if isinstance(updated.get("update_history"), list) else []
    history.append(entry)
    updated["update_history"] = history[-limit:]
    return updated


__all__ = ["append_update_history"]
