from __future__ import annotations

from typing import Any

from learn_core.topic_family import detect_topic_family_from_configs


def build_curriculum(
    topic: str,
    level: str,
    preference: str,
    *,
    family_configs: dict[str, dict[str, Any]],
    stage_details: dict[str, list[dict[str, Any]]],
    daily_templates: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    family = detect_topic_family_from_configs(topic, family_configs)
    family_config = family_configs.get(family, family_configs["general-cs"])
    raw_stages = list(family_config.get("stages", []))
    family_stage_details = stage_details.get(family) or stage_details["general-cs"]
    stages: list[dict[str, Any]] = []
    for index, stage in enumerate(raw_stages):
        name, focus, goal, practice, test_gate = stage
        detail = family_stage_details[index] if index < len(family_stage_details) else {}
        stages.append(
            {
                "name": name,
                "focus": focus,
                "goal": goal,
                "practice": practice,
                "test_gate": test_gate,
                "reading": detail.get("reading", []),
                "exercise_types": detail.get("exercise_types", []),
                "future_use": detail.get("future_use", goal),
            }
        )
    return {
        "family": family,
        "topic": topic,
        "level": level,
        "preference": preference,
        "stages": stages,
        "daily_templates": daily_templates.get(family) or daily_templates["general-cs"],
    }
