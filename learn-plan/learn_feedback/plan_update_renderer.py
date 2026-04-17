from __future__ import annotations

from pathlib import Path
from typing import Any

from learn_core.io import read_text_if_exists, write_text
from learn_core.markdown_sections import upsert_markdown_section


def append_plan_record(plan_path: Path, heading: str, block: str) -> None:
    original = read_text_if_exists(plan_path)
    updated = upsert_markdown_section(original, heading, block)
    write_text(plan_path, updated)


def render_feedback_output_lines(*, learner_model_result: dict[str, Any], patch_result: dict[str, Any]) -> list[str]:
    lines = [f"learner model：{learner_model_result.get('path')}"]
    patch = patch_result.get("patch")
    if patch:
        lines.append(f"curriculum patch：{patch_result.get('path')}（{patch.get('status')} / {patch.get('patch_type')}）")
    else:
        lines.append(f"curriculum patch：{patch_result.get('path')}（本次无需新增 patch）")
    return lines


__all__ = [
    "append_plan_record",
    "render_feedback_output_lines",
]
