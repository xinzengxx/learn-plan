from __future__ import annotations

import json
from typing import Any


def parse_json_from_llm_output(raw_text: str) -> Any | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    object_start = text.find("{")
    object_end = text.rfind("}")
    if 0 <= object_start < object_end:
        try:
            return json.loads(text[object_start: object_end + 1])
        except json.JSONDecodeError:
            pass
    array_start = text.find("[")
    array_end = text.rfind("]")
    if 0 <= array_start < array_end:
        try:
            return json.loads(text[array_start: array_end + 1])
        except json.JSONDecodeError:
            return None
    return None
