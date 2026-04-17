from __future__ import annotations

from typing import Any


def detect_topic_family(topic: str, family_keywords: dict[str, list[str]], *, fallback_text: str = "") -> str:
    topic_text = (topic or "").strip()
    for family, keywords in family_keywords.items():
        for keyword in keywords:
            if keyword and keyword in topic_text:
                return family

    if topic_text:
        return "general-cs"

    text = (fallback_text or "").strip()
    for family, keywords in family_keywords.items():
        for keyword in keywords:
            if keyword and keyword in text:
                return family
    return "general-cs"


def detect_topic_family_from_configs(topic: str, family_configs: dict[str, dict[str, Any]]) -> str:
    text = (topic or "").strip()
    for family, config in family_configs.items():
        for keyword in config.get("keywords", []):
            if keyword and keyword in text:
                return family
    return "general-cs"


def infer_domain(topic: str, family_keywords: dict[str, list[str]], *, fallback_text: str = "") -> str:
    return detect_topic_family(topic, family_keywords, fallback_text=fallback_text)


def infer_domain_from_configs(topic: str, family_configs: dict[str, dict[str, Any]]) -> str:
    return detect_topic_family_from_configs(topic, family_configs)
