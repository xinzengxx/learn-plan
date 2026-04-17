from __future__ import annotations

import re
from typing import Any


def normalize_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def normalize_string_list(values: Any) -> list[str]:
    if values is None:
        iterable: Any = []
    elif isinstance(values, str):
        iterable = [values]
    else:
        try:
            iterable = iter(values)
        except TypeError:
            iterable = [values]
    result: list[str] = []
    for value in iterable:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
    cleaned = cleaned.strip('. ')
    return cleaned[:200]
