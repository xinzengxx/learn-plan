from __future__ import annotations

from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists


def load_latest_structured_state(plan_path: Path, topic: str) -> dict[str, Any] | None:
    sessions_dir = plan_path.parent / "sessions"
    if not sessions_dir.exists() or not sessions_dir.is_dir():
        return None

    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for progress_path in sessions_dir.glob("*/progress.json"):
        progress = read_json_if_exists(progress_path)
        if not progress:
            continue
        if str(progress.get("topic") or "").strip() != topic:
            continue
        session = progress.get("session") or {}
        context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
        learning_state = progress.get("learning_state") if isinstance(progress.get("learning_state"), dict) else {}
        progression = progress.get("progression") if isinstance(progress.get("progression"), dict) else {}
        if not context and not learning_state and not progression:
            continue
        status = str(session.get("status") or "")
        if status not in {"finished", "active"}:
            continue
        if status == "active" and not (learning_state or progression):
            continue
        current_stage = str(context.get("current_stage") or "").strip()
        current_day = str(context.get("current_day") or "").strip()
        topic_cluster = str(context.get("topic_cluster") or "").strip()
        anchor_score = 1 if (current_stage and (current_day or topic_cluster)) else 0
        status_score = 2 if status == "active" else 1
        try:
            sort_ts = progress_path.stat().st_mtime
        except OSError:
            continue
        candidates.append(
            (
                sort_ts,
                anchor_score * 10 + status_score,
                {
                    "progress_path": str(progress_path),
                    "session": session,
                    "context": context,
                    "learning_state": learning_state,
                    "progression": progression,
                    "material_alignment": progress.get("material_alignment") if isinstance(progress.get("material_alignment"), dict) else {},
                },
            )
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[1], item[0]), reverse=True)
    return candidates[0][2]
