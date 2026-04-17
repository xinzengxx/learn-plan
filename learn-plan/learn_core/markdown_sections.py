from __future__ import annotations

import re


HEADING_PATTERN = re.compile(r"^##\s+(?:\d+\.\s*)?(?P<title>.+?)\s*$")


def extract_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    target = heading.strip()
    start = None
    for idx, line in enumerate(lines):
        match = HEADING_PATTERN.match(line.strip())
        if match and match.group("title").strip() == target:
            start = idx + 1
            break
    if start is None:
        return ""
    while start < len(lines) and not lines[start].strip():
        start += 1
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def upsert_markdown_section(text: str, heading: str, block: str) -> str:
    if not text.strip():
        return f"# Learn Plan\n\n## {heading}\n\n{block}\n"

    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        match = HEADING_PATTERN.match(line.strip())
        if match and match.group("title").strip() == heading:
            start = idx
            break

    if start is None:
        suffix = "" if text.endswith("\n") else "\n"
        return f"{text}{suffix}\n## {heading}\n\n{block}\n"

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break

    section_lines = lines[start:end]
    existing = "\n".join(section_lines).rstrip()
    updated = f"{existing}\n\n{block}".strip()
    new_lines = lines[:start] + updated.splitlines() + lines[end:]
    return "\n".join(new_lines).rstrip() + "\n"
