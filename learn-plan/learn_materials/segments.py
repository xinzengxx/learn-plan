from __future__ import annotations

import re
from typing import Any


def group_topics_for_segments(focus_topics: list[str], *, chunk_size: int = 3) -> list[list[str]]:
    cleaned = [str(item).strip() for item in focus_topics if str(item).strip()]
    if not cleaned:
        return []
    return [cleaned[index:index + chunk_size] for index in range(0, len(cleaned), chunk_size)]


def build_special_reading_segments(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[dict[str, Any]]:
    if curriculum.get("family") != "python" or entry.get("id") != "python-crash-course-3e":
        return []
    return [
        {
            "segment_id": "python-crash-course-3e-day-2-ch10-files-exceptions-json",
            "label": "阶段 1 / Day 2 / 第 10 章 / pathlib 文本读写、异常与 JSON",
            "locator": {
                "chapter": "《Python编程：从入门到实践（第3版）》第 10 章",
                "pages": None,
                "sections": [
                    "pathlib.Path",
                    "Path.read_text()",
                    "Path.write_text()",
                    "try-except",
                    "json.dumps()",
                    "json.loads()",
                ],
            },
            "purpose": "服务于 Day 2 文件读写基础：围绕本书第 10 章掌握 Path 文本读写、文件/JSON 异常边界与 JSON 序列化。",
            "recommended_for": {
                "stage": "阶段 1",
                "days": ["Day 2", "Day 2：文件读写基础", "Day 2：pathlib 文本读写、异常与 JSON"],
            },
            "estimated_minutes": 40,
            "checkpoints": [
                "能说明 Path 对象与路径字符串的关系",
                "能用 Path.read_text() 读取文本并处理缺失文件异常",
                "能用 Path.write_text() 写出文本",
                "能区分 json.dumps() 与 json.loads() 的方向",
                "能在文件/JSON 边界使用 try-except 处理常见错误",
            ],
            "target_clusters": ["files-pathlib-json-exceptions"],
        }
    ]


def build_reading_segments(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[dict[str, Any]]:
    recommended_stages = list(entry.get("recommended_stage") or [])
    focus_topics = list(entry.get("focus_topics") or [])
    topic_groups = group_topics_for_segments(focus_topics, chunk_size=3)
    segments: list[dict[str, Any]] = build_special_reading_segments(entry, curriculum)

    if recommended_stages:
        for stage_index, stage_name in enumerate(recommended_stages[:3], start=1):
            groups = topic_groups or [[curriculum["topic"]]]
            for group_index, group in enumerate(groups[:2], start=1):
                section_label = " / ".join(group)
                label = f"{stage_name} / {entry.get('title', '材料')} / {section_label}"
                locator = {"chapter": stage_name, "pages": None, "sections": group}
                if entry.get("source_type") == "local":
                    locator["pages"] = f"待补充页码（优先定位到 {stage_name} 中与 {section_label} 对应的内容）"
                segments.append(
                    {
                        "segment_id": f"{entry.get('id', 'material')}-segment-{stage_index}-{group_index}",
                        "label": label,
                        "locator": locator,
                        "purpose": entry.get("use") or f"服务于 {curriculum['topic']} 学习",
                        "recommended_for": {"stage": stage_name, "days": entry.get("recommended_day") or []},
                        "estimated_minutes": 35 if len(group) <= 2 else 45,
                        "checkpoints": group,
                    }
                )
    if not segments:
        fallback_group = (topic_groups[0] if topic_groups else [curriculum["topic"]])[:3]
        segments.append(
            {
                "segment_id": f"{entry.get('id', 'material')}-segment-1",
                "label": f"{entry.get('title') or '未命名材料'} / {' / '.join(fallback_group)}",
                "locator": {"chapter": "待补充章节", "pages": None, "sections": fallback_group},
                "purpose": entry.get("use") or f"服务于 {curriculum['topic']} 学习",
                "recommended_for": {"stage": None, "days": entry.get("recommended_day") or []},
                "estimated_minutes": 45,
                "checkpoints": fallback_group,
            }
        )
    return segments


def infer_material_recommended_day(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[str]:
    title_blob = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("use") or ""),
            " ".join(str(tag) for tag in entry.get("tags") or []),
        ]
    ).lower()
    matched: list[str] = []
    for day in curriculum["daily_templates"]:
        today_topic = str(day.get("今日主题") or "")
        if any(token and token in title_blob for token in re.split(r"[\s/、，；:：]+", today_topic.lower()) if len(token) >= 2):
            matched.append(str(day["day"]))
    return matched[:3]
