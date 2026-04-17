from __future__ import annotations

import re
from typing import Any

from .markdown_sections import extract_markdown_section


def extract_section(plan_text: str, heading: str) -> str:
    return extract_markdown_section(plan_text, heading)


def extract_recent_bullet_values(section_text: str, prefixes: list[str], *, limit: int = 3) -> list[str]:
    values: list[str] = []
    for raw_line in reversed(section_text.splitlines()):
        stripped = raw_line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:].strip()
        for prefix in prefixes:
            if content.startswith(prefix):
                value = content[len(prefix):].strip()
                parts = [item.strip() for item in value.replace("；", ";").split(";") if item.strip()]
                for item in parts:
                    if item not in values:
                        values.append(item)
                        if len(values) >= limit:
                            return values
    return values


def extract_plain_bullets(section_text: str, *, limit: int = 4) -> list[str]:
    values: list[str] = []
    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if value and value not in values:
            values.append(value)
            if len(values) >= limit:
                break
    return values


def extract_numbered_subsection(section_text: str, heading: str) -> str:
    lines = section_text.splitlines()
    start = None
    target = heading.strip()
    pattern = re.compile(r"^\d+\.\s+(?P<title>.+?)\s*$")
    for idx, raw_line in enumerate(lines):
        match = pattern.match(raw_line.strip())
        if match and match.group("title").strip() == target:
            start = idx + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start, len(lines)):
        if pattern.match(lines[idx].strip()):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def summarize_plan_bullets(plan_text: str, *, limit: int = 6) -> list[str]:
    summary = []
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            value = stripped[2:].strip()
            if value and value not in summary:
                summary.append(value)
        if len(summary) >= limit:
            break
    return summary


def split_semicolon_values(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").replace("；", ";").split(";") if item.strip()]
