from __future__ import annotations

from learn_core.markdown_sections import extract_markdown_section


def choose_existing_section(original: str, heading: str, default: str) -> str:
    existing = extract_markdown_section(original, heading)
    if not existing:
        return default
    return existing
