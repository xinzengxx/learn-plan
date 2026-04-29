from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from learn_core.llm_json import parse_json_from_llm_output as core_parse_json_from_llm_output
from learn_core.plan_parser import split_semicolon_values
from learn_core.quality_review import apply_quality_envelope, build_traceability_entry, normalize_confidence
from learn_core.text_utils import normalize_string_list
from learn_runtime.plan_source import normalize_day_key
from learn_runtime.source_grounding import (
    build_content_aware_explanation,
    build_content_aware_pitfall,
    clean_source_teaching_terms,
    compact_source_text,
)

SKILL_DIR = Path(__file__).resolve().parents[1]


def describe_execution_mode(execution_mode: str, topic: str) -> dict[str, Any]:
    mapping = {
        "clarification": {
            "study_mode": "澄清补全",
            "why_today": "当前还缺少足够清晰的目标、约束或边界，因此今天先完成顾问式澄清，不直接推进正式主线。",
            "coach_explanation": "本次 session 的任务是把学习目的、成功标准、已有基础和非目标范围说清楚，为后续规划建立可靠起点。",
            "practice_bridge": [
                "优先回答澄清问题，而不是着急进入题目训练。",
                "把不确定的目标、约束和非目标先写清楚。",
                "若今天仍有开放问题，下次 /learn-plan 需要继续澄清，而不是直接推进。",
            ],
        },
        "research": {
            "study_mode": "研究确认",
            "why_today": "当前目标需要外部能力标准或资料取舍依据，因此今天先完成研究计划确认，不直接推进正式主线。",
            "coach_explanation": "本次 session 的任务是确认：要查什么、为什么查、查完后如何影响学习路线和资料选择。",
            "practice_bridge": [
                "优先确认 research questions、资料来源类型和筛选标准。",
                "把主线候选资料和备选资料区分清楚。",
                "确认后再进入 deepsearch 或正式规划，而不是直接做常规学习题。",
            ],
        },
        "diagnostic": {
            "study_mode": "水平诊断",
            "why_today": "当前真实水平还不够确定，因此今天先做最小诊断验证，再决定从哪里开始学。",
            "coach_explanation": "本次 session 的任务不是推进新知识，而是确认你现在到底会什么、不会什么，以及主线应从哪一层开始。",
            "practice_bridge": [
                "优先完成解释题、小测试或小代码题，作为起点判断证据。",
                "不要把今天当成正式推进日，而应把它当作分层校准日。",
                "诊断完成后，下一轮才进入正式主线编排。",
            ],
        },
        "test-diagnostic": {
            "study_mode": "测试诊断",
            "why_today": "当前计划仍未达到正式推进条件，因此今天用测试型 session 先做诊断，而不是做阶段通过性测试。",
            "coach_explanation": "本次 session 以测试形态收集证据，用来判断真实薄弱点和起步阶段，而不是判断你是否已经可以推进。",
            "practice_bridge": [
                "把今天的题目当作定位工具，而不是通关测试。",
                "优先记录你卡住的概念、题型和表达问题。",
                "诊断证据足够后，才重新决定下一轮 today/test 的走向。",
            ],
        },
        "prestudy": {
            "study_mode": "预读/补资料",
            "why_today": "当前计划还未完成最终确认，因此今天先做主线候选资料预读和确认前准备，不直接进入正式主线推进。",
            "coach_explanation": "本次 session 的任务是先把主线候选材料、阅读定位和确认项补齐，避免后续沿错误路线推进。",
            "practice_bridge": [
                "先读候选主线材料和说明，而不是直接进入正常训练量。",
                "重点确认：主线材料是否合适、范围是否准确、是否还缺关键资料。",
                "完成预读和确认后，再进入正式学习 session。",
            ],
        },
    }
    return mapping.get(
        execution_mode,
        {
            "study_mode": "复习+推进",
            "why_today": "先根据当前阶段、最近复习重点和新学习点安排当天内容，再结合掌握度检验决定是否推进。",
            "coach_explanation": f"今天优先服务主线目标：{topic}；在主线之外，只补 1 个支撑能力点，并仅在时间预算允许时触发增强模块。",
            "practice_bridge": [
                "读完讲义后，立即到现有练习页面做对应题目，不要只停留在阅读层。",
                "做题时优先验证：你是否真的理解了今天这几个概念，而不是只记住名字。",
                "若练习卡住，先回到上面的讲解摘要和阅读指导，再继续做。",
            ],
        },
    )


def json_for_prompt(value: Any, *, limit: int = 16000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...<truncated>"


def language_policy_prompt_block(language_policy: dict[str, Any] | None) -> str:
    policy = language_policy if isinstance(language_policy, dict) else {}
    user_facing_language = str(policy.get("user_facing_language") or "zh-CN").strip() or "zh-CN"
    return f"""语言策略：
- 用户可见内容必须使用 {user_facing_language}。
- 英文资料标题、代码标识符、API 名、命令、文件路径和原文引用可以保留原语言，但要用 {user_facing_language} 解释。
- 不要把代码、命令或专有名词强行翻译成不自然表达。"""


def shared_style_prompt_block(*, audience: str = "学习产物") -> str:
    narrative_extra = ""
    if "讲义" in audience or "课件" in audience or "解释" in audience:
        narrative_extra = (
            "- 课件采用三段教学框架：Part 1 往期复习、Part 2 本期知识点讲解、Part 3 本期内容回看。\n"
            "- 往期复习要承接上一期学习结果、错题/薄弱点、已掌握内容与本期入口。\n"
            "- 本期知识点讲解要围绕真实问题逐步分析，可自由使用段落、列表、表格、代码块、案例、反例和推理步骤。\n"
            "- 本期内容回看要列出材料来源，尽量精确到材料名、章节、页码、段落、section 或 locator；缺失精确定位时明确说明，不编造。\n"
            "- 不限制 section 数量或版式；优先让内容好读、好学、可验证，而不是套固定故事模板。\n"
        )
    return f"""共享风格约束（适用于{audience}）：
- 内容必须绑定当前 goal、当前阶段、已选材料/证据、当前 blocker 或薄弱点，不能写成放哪都行的通用话术。
- 要有真实背景：优先解释"为什么现在学它、它在当前任务/阶段里解决什么问题、哪里最容易卡住"。
- 少废话：不要写"你可以考虑""下面给出建议""建议如下"这类提示语或咨询式套话。
- 精简但有深度：保留真正帮助理解与执行的信息，省掉空泛铺垫和同义反复。
- 解释应服务行动：尽量把解释落到可判断的 mastery check、下一步动作或具体取舍上。
- 若输入证据不足，宁可明确保留 open questions / pending items，也不要脑补细节。
{narrative_extra}"""
def parse_json_from_llm_output(raw_text: str) -> Any | None:
    return core_parse_json_from_llm_output(raw_text)


def normalize_llm_text_list(values: Any, fallback: Any, *, limit: int = 8) -> list[str]:
    result: list[str] = []
    if isinstance(values, list):
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
            if len(result) >= limit:
                break
    return result or normalize_string_list(fallback)[:limit]


def normalize_llm_mapping(value: Any, fallback: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(fallback, dict):
        return fallback
    return {}


def normalize_llm_teaching_points(values: Any, fallback: Any) -> list[dict[str, Any]]:
    fallback_points = [item for item in (fallback or []) if isinstance(item, dict)]
    if not isinstance(values, list):
        return fallback_points
    normalized: list[dict[str, Any]] = []
    required_keys = ["topic", "background", "core_question", "explanation", "practical_value", "pitfall", "study_prompt", "source_status"]
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback_points[index] if index < len(fallback_points) else {}
        topic = str(item.get("topic") or fallback_item.get("topic") or "").strip()
        if not topic:
            continue
        point: dict[str, Any] = {}
        for key in required_keys:
            default = "llm-grounded" if key == "source_status" else ""
            point[key] = str(item.get(key) or fallback_item.get(key) or default).strip()
        point["topic"] = topic
        point["segment_id"] = str(item.get("segment_id") or fallback_item.get("segment_id") or "").strip() or None
        point["material_title"] = str(item.get("material_title") or fallback_item.get("material_title") or "").strip() or None
        normalized.append(point)
        if len(normalized) >= 8:
            break
    return normalized or fallback_points


def normalize_prompt_string_list(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, list):
        return normalize_string_list(value)[:limit]
    if isinstance(value, str):
        split_values = split_semicolon_values(value)
        if split_values:
            return split_values[:limit]
        text = value.strip()
        return [text] if text else []
    return []


def format_locator(*, locator: Any = None, chapter: Any = None, pages: Any = None, sections: Any = None) -> str:
    locator_text = str(locator or "").strip()
    if locator_text:
        return locator_text
    section_values = normalize_prompt_string_list(sections, limit=3)
    bits = [str(chapter or "").strip(), str(pages or "").strip(), "；".join(section_values)]
    return " / ".join(bit for bit in bits if bit)


TODAY_TAXONOMY_STOP_TERMS = {
    "general-cs",
    "general cs",
    "tooling",
    "tutorial",
    "reference",
}

TODAY_INTERNAL_REASON_MARKERS = {
    "explicit-target-segment",
    "fallback-metadata",
    "metadata-fallback",
    "llm-grounded",
    "content-aware",
}

TODAY_SECTION_DISPLAY = {
    "git": "Git",
}



def looks_like_today_noise(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return True
    if lowered in TODAY_TAXONOMY_STOP_TERMS or lowered in TODAY_INTERNAL_REASON_MARKERS:
        return True
    return bool(
        re.fullmatch(
            r"(?i)(?:stage\s*\d+|阶段\s*\d+|task\s*\d+|任务\s*\d+|任务|用途|重点边界)",
            text.strip(),
        )
    )



def sanitize_today_user_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(
        r"(?i)\b(?:general-cs|general cs|tooling|tutorial|reference|explicit-target-segment|fallback-metadata|metadata-fallback|llm-grounded|content-aware)\b",
        " ",
        text,
    )
    text = re.sub(r"(?i)\bstage\s*\d+\b", " ", text)
    text = re.sub(r"阶段\s*\d+", " ", text)
    text = re.sub(r"\s*([/；;，,、|-])\s*", r" \1 ", text)
    text = re.sub(r"(?:\s+[/:：；;，,、|-]\s+){2,}", " / ", text)
    text = re.sub(r"\s+", " ", text).strip(" /：:；;，,、|-")
    if looks_like_today_noise(text):
        return ""
    return text.strip()



def normalize_today_sections(values: Any, *, limit: int = 4) -> list[str]:
    sections = normalize_prompt_string_list(values, limit=limit * 2)
    normalized: list[str] = []
    for value in sections:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in TODAY_TAXONOMY_STOP_TERMS:
            continue
        display = TODAY_SECTION_DISPLAY.get(lowered, text)
        if display not in normalized:
            normalized.append(display)
        if len(normalized) >= limit:
            break
    return normalized



def build_today_locator(*, locator: Any = None, chapter: Any = None, pages: Any = None, sections: Any = None) -> str:
    return format_locator(
        locator=sanitize_today_user_text(locator),
        chapter=sanitize_today_user_text(chapter),
        pages=sanitize_today_user_text(pages),
        sections=normalize_today_sections(sections, limit=4),
    )



def display_material_reason(task: dict[str, Any]) -> str | None:
    for raw_value, allow_internal in [
        (task.get("source_summary"), True),
        (task.get("purpose"), True),
        (task.get("match_reason"), False),
    ]:
        text = sanitize_today_user_text(raw_value)
        if not text:
            continue
        if not allow_internal and text.lower() in TODAY_INTERNAL_REASON_MARKERS:
            continue
        if re.fullmatch(r"[a-z0-9._-]+", text.lower()) and not allow_internal:
            continue
        return text
    return None



def infer_material_locator_from_grounding(task: dict[str, Any]) -> str:
    for example in normalize_string_list(task.get("source_examples") or []):
        for pattern in [r'title:\s*"([^"]+)"', r"\]\]\s*==\s*([^\n]+)"]:
            matched = re.search(pattern, example, re.IGNORECASE)
            if not matched:
                continue
            text = sanitize_today_user_text(matched.group(1))
            if text:
                return shorten_today_text(text, limit=32)
    summary_terms = clean_source_teaching_terms(split_semicolon_values(task.get("source_summary") or ""))
    if summary_terms:
        return shorten_today_text("；".join(summary_terms[:2]), limit=32)
    return ""



def build_material_reference(task: dict[str, Any]) -> dict[str, Any]:
    sections = normalize_today_sections(task.get("sections") or [], limit=4)
    locator = build_today_locator(
        chapter=task.get("chapter"),
        pages=task.get("pages"),
        sections=sections,
    )
    locator = locator or infer_material_locator_from_grounding(task) or "待补充定位"
    return {
        "segment_id": str(task.get("segment_id") or "").strip() or None,
        "material_title": sanitize_today_user_text(task.get("material_title") or task.get("label") or "未命名资料") or "未命名资料",
        "locator": locator,
        "chapter": sanitize_today_user_text(task.get("chapter")) or None,
        "pages": sanitize_today_user_text(task.get("pages")) or None,
        "sections": sections,
        "match_reason": display_material_reason(task),
        "source_status": str(task.get("source_status") or "fallback-metadata").strip(),
        "material_source_name": sanitize_today_user_text(task.get("material_source_name")) or None,
    }


def shorten_today_text(value: Any, *, limit: int = 32) -> str:
    text = sanitize_today_user_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip(" /：:；;，,、|-") + "…"



def normalize_today_display_list(values: Any, *, limit: int = 8) -> list[str]:
    raw_values: list[str]
    if isinstance(values, str):
        raw_values = normalize_prompt_string_list(values, limit=limit * 3)
    elif isinstance(values, list):
        raw_values = normalize_string_list(values)
    else:
        raw_values = []
    normalized: list[str] = []
    for value in raw_values:
        text = sanitize_today_user_text(value)
        if not text:
            continue
        lowered = text.lower()
        if lowered in TODAY_TAXONOMY_STOP_TERMS or lowered in TODAY_INTERNAL_REASON_MARKERS:
            continue
        if re.fullmatch(r"(?:阶段\s*\d+|任务|用途|重点边界)", text, re.IGNORECASE):
            continue
        if text not in normalized:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized



def looks_like_generic_project_task(value: Any) -> bool:
    text = sanitize_today_user_text(value).lower()
    if not text:
        return True
    generic_markers = [
        "补命令行",
        "自动化",
        "工程工具基础",
        "系统学习",
        "工作流与协作基础",
        "当前资料",
        "主线资料",
    ]
    if any(marker in text for marker in generic_markers):
        return True
    if text.startswith("围绕 ") and text.endswith(" 完成一个最小任务"):
        return True
    return False



def grounded_task_profile(line: dict[str, Any], knowledge_points: list[str]) -> str | None:
    source_terms = clean_source_teaching_terms(
        normalize_string_list(line.get("source_key_points") or [])
        + split_semicolon_values(line.get("source_summary") or "")
        + normalize_string_list(knowledge_points)
    )
    blob = " ".join(
        [
            *source_terms,
            str(line.get("source_summary") or ""),
            str(line.get("purpose") or ""),
            str(line.get("material_summary") or ""),
            str(line.get("material_title") or ""),
        ]
    ).lower()
    if not any(token in blob for token in ["git", "版本控制", "snapshot", "快照", "commit", "提交", "branch", "分支", "暂存", "status", "工作区", "remote", "远程", "仓库"]):
        return None
    if any(token in blob for token in ["版本控制", "version control", "快照", "snapshot"]):
        return "git-snapshot-model"
    if any(token in blob for token in ["git add", "暂存", "git status", "工作区", "commit", "提交", "仓库"]):
        return "git-local-loop"
    if any(token in blob for token in ["branch", "分支", "remote", "远程"]):
        return "git-branch-remote"
    return None



def build_grounded_task_name(line: dict[str, Any], knowledge_points: list[str], topic: str) -> str:
    profile = grounded_task_profile(line, knowledge_points)
    if profile == "git-snapshot-model":
        return "用快照历史和分支指针理解 Git 如何记录变化"
    if profile == "git-local-loop":
        return "跑通一次 git status → git add → git commit 的最小闭环"
    if profile == "git-branch-remote":
        return "用 branch 和 remote 串起本地历史与协作入口"
    for candidate in [
        line.get("source_summary"),
        line.get("purpose"),
        *(line.get("source_examples") or []),
    ]:
        text = sanitize_today_user_text(candidate)
        if not text or looks_like_generic_project_task(text):
            continue
        if len(text) <= 24:
            return text
        if len(text) <= 40 and re.search(r"[动做改查读写提交切换同步解释判断连接串起完成练习验证复盘]", text):
            return shorten_today_text(text, limit=28)
    primary_points = normalize_today_display_list(knowledge_points, limit=2)
    if len(primary_points) >= 2:
        return f"在一个最小场景里串起 {primary_points[0]} 和 {primary_points[1]}"
    if primary_points:
        return f"围绕 {primary_points[0]} 完成一个最小任务"
    material_title = sanitize_today_user_text(line.get("material_title") or topic) or topic
    return f"围绕 {shorten_today_text(material_title, limit=18)} 完成一个最小任务"



def build_grounded_task_real_context(line: dict[str, Any], knowledge_points: list[str], topic: str) -> str:
    profile = grounded_task_profile(line, knowledge_points)
    if profile == "git-snapshot-model":
        return "刚接触 Git 时，最容易把版本控制理解成文件备份，而不是一条可追踪的快照历史。"
    if profile == "git-local-loop":
        return "第一次把修改写进 Git 历史时，最容易混淆工作区、暂存区和 commit 的边界。"
    if profile == "git-branch-remote":
        return "开始接触协作前，必须先把 branch、commit 和 remote 的连接关系说清楚。"
    for candidate in [line.get("source_summary"), line.get("purpose"), line.get("material_summary")]:
        text = sanitize_today_user_text(candidate)
        if text and not looks_like_generic_project_task(text):
            return text
    return sanitize_today_user_text(line.get("purpose") or line.get("material_summary") or f"围绕 {line.get('material_title') or topic} 里的真实场景推进。")



def build_grounded_task_blocker(line: dict[str, Any], related_points: list[dict[str, Any]], knowledge_points: list[str]) -> str:
    blocker_candidates = normalize_today_display_list(line.get("source_pitfalls") or [], limit=2)
    blocker_candidates += normalize_today_display_list([item.get("pitfall") for item in related_points], limit=2)
    for candidate in blocker_candidates:
        if candidate and not looks_like_today_noise(candidate):
            return candidate
    profile = grounded_task_profile(line, knowledge_points)
    if profile == "git-snapshot-model":
        return "容易把 commit、branch 和仓库当成分散名词，连不成同一个历史模型。"
    if profile == "git-local-loop":
        return "容易分不清哪些改动还在工作区、哪些已经进入暂存区，以及下一次 commit 会带走什么。"
    if profile == "git-branch-remote":
        return "容易把 branch、HEAD 和 remote 的关系混成同一件事。"
    return "容易只记住术语名字，却说不清它在当前任务里怎么用。"



def build_grounded_task_why_now(line: dict[str, Any], knowledge_points: list[str], topic: str) -> str:
    profile = grounded_task_profile(line, knowledge_points)
    if profile == "git-snapshot-model":
        return "因为如果今天不先建立 Git 的快照历史心智模型，后面的 commit、branch 和 remote 都会变成死记命令。"
    if profile == "git-local-loop":
        return "因为今天要先建立第一次本地提交的真实闭环，后面的 branch、remote 和协作关系才有落点。"
    if profile == "git-branch-remote":
        return "因为只有先把 branch 和 remote 的作用边界讲清楚，后续协作命令才不会混乱。"
    return sanitize_today_user_text(line.get("match_reason") or f"因为今天要围绕 {line.get('material_title') or topic} 这一段材料完成最小理解闭环。")



def build_grounded_task_how_to_apply(line: dict[str, Any], knowledge_points: list[str]) -> str:
    profile = grounded_task_profile(line, knowledge_points)
    if profile == "git-snapshot-model":
        return "试着只用“仓库 → commit → branch”解释一次改动为什么会留在历史里。"
    if profile == "git-local-loop":
        return "按“git status → git add → git commit → git status”走一遍，并解释每一步到底改变了哪里。"
    if profile == "git-branch-remote":
        return "先画出 commit、branch、HEAD、remote 的关系，再判断常见命令是在改指针还是在同步仓库。"
    checkpoints = normalize_string_list(line.get("checkpoints") or [])
    for checkpoint in checkpoints:
        text = sanitize_today_user_text(checkpoint)
        if text and len(text) >= 4 and text.lower() not in {"git", "python"}:
            return text
    return "先根据这段材料解释相关概念，再在网页练习题里验证是否能把知识点落到任务上下文。"



def dedupe_project_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str], int] = {}
    for task in tasks:
        task_name = sanitize_today_user_text(task.get("task_name"))
        knowledge_signature = " | ".join(normalize_today_display_list(task.get("knowledge_points") or [], limit=3))
        key = (task_name.lower(), knowledge_signature.lower())
        if key in index_by_key:
            existing = deduped[index_by_key[key]]
            merged_segment_ids = normalize_prompt_string_list(
                (existing.get("source_segment_ids") or []) + (task.get("source_segment_ids") or []),
                limit=6,
            )
            existing["source_segment_ids"] = merged_segment_ids
            continue
        index_by_key[key] = len(deduped)
        deduped.append(task)
    return deduped



def build_materials_used_entries(lesson_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in lesson_lines:
        if not isinstance(item, dict):
            continue
        reference = build_material_reference(item)
        key = (
            str(reference.get("material_title") or ""),
            str(reference.get("locator") or ""),
            str(reference.get("match_reason") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        entries.append(reference)
        if len(entries) >= 8:
            break
    return entries


def normalize_lesson_materials_used(values: Any, fallback: Any) -> list[dict[str, Any]]:
    fallback_items = [item for item in (fallback or []) if isinstance(item, dict)]
    if not isinstance(values, list):
        return fallback_items
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback_items[index] if index < len(fallback_items) else {}
        sections = normalize_today_sections(item.get("sections") or fallback_item.get("sections"), limit=4)
        material_title = sanitize_today_user_text(item.get("material_title") or fallback_item.get("material_title"))
        locator = build_today_locator(
            locator=item.get("locator") or fallback_item.get("locator"),
            chapter=item.get("chapter") or fallback_item.get("chapter"),
            pages=item.get("pages") or fallback_item.get("pages"),
            sections=sections or fallback_item.get("sections"),
        )
        if not material_title and not locator:
            continue
        normalized.append(
            {
                "segment_id": str(item.get("segment_id") or fallback_item.get("segment_id") or "").strip() or None,
                "material_title": material_title or sanitize_today_user_text(fallback_item.get("material_title") or "未命名资料") or "未命名资料",
                "locator": locator or sanitize_today_user_text(fallback_item.get("locator") or "待补充定位") or "待补充定位",
                "chapter": sanitize_today_user_text(item.get("chapter") or fallback_item.get("chapter")) or None,
                "pages": sanitize_today_user_text(item.get("pages") or fallback_item.get("pages")) or None,
                "sections": sections or normalize_today_sections(fallback_item.get("sections"), limit=4),
                "match_reason": sanitize_today_user_text(item.get("match_reason") or fallback_item.get("match_reason")) or None,
                "source_status": str(item.get("source_status") or fallback_item.get("source_status") or "llm-grounded").strip(),
                "material_source_name": sanitize_today_user_text(item.get("material_source_name") or fallback_item.get("material_source_name")) or None,
            }
        )
        if len(normalized) >= 8:
            break
    return normalized or fallback_items


def normalize_lesson_focus_points(values: Any, fallback: Any) -> list[dict[str, Any]]:
    fallback_items = [item for item in (fallback or []) if isinstance(item, dict)]
    if not isinstance(values, list):
        return fallback_items
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback_items[index] if index < len(fallback_items) else {}
        point = sanitize_today_user_text(item.get("point") or fallback_item.get("point"))
        if not point:
            continue
        normalized.append(
            {
                "point": point,
                "why_it_matters": sanitize_today_user_text(item.get("why_it_matters") or fallback_item.get("why_it_matters")),
                "mastery_check": sanitize_today_user_text(item.get("mastery_check") or fallback_item.get("mastery_check")),
                "source_segment_ids": normalize_prompt_string_list(item.get("source_segment_ids") or fallback_item.get("source_segment_ids"), limit=4),
                "related_tasks": normalize_today_display_list(item.get("related_tasks") or fallback_item.get("related_tasks"), limit=4),
            }
        )
        if len(normalized) >= 8:
            break
    return normalized or fallback_items


def normalize_lesson_today_focus(value: Any, fallback: Any) -> dict[str, Any]:
    fallback_dict = dict(fallback) if isinstance(fallback, dict) else {}
    candidate = dict(value) if isinstance(value, dict) else {}
    return {
        "summary": str(candidate.get("summary") or fallback_dict.get("summary") or "").strip(),
        "focus_points": normalize_lesson_focus_points(candidate.get("focus_points"), fallback_dict.get("focus_points")),
    }


def normalize_project_task_field(value: Any, fallback: Any, *, field: str) -> str:
    text = sanitize_today_user_text(value)
    fallback_text = sanitize_today_user_text(fallback)
    if not text:
        return fallback_text
    malformed_patterns = {
        "why_now": [
            r"因为今天是\s*的起点",
            r"为什么今天现在引入这些知识[:：]?$",
        ],
    }
    patterns = malformed_patterns.get(field, [])
    if any(re.search(pattern, text) for pattern in patterns):
        return fallback_text or text
    return text



def normalize_lesson_project_tasks(values: Any, fallback: Any) -> list[dict[str, Any]]:
    fallback_items = [item for item in (fallback or []) if isinstance(item, dict)]
    if not isinstance(values, list):
        return fallback_items
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback_items[index] if index < len(fallback_items) else {}
        task_name = sanitize_today_user_text(item.get("task_name") or fallback_item.get("task_name"))
        if not task_name:
            continue
        normalized.append(
            {
                "task_name": task_name,
                "real_context": normalize_project_task_field(item.get("real_context"), fallback_item.get("real_context"), field="real_context"),
                "blocker": normalize_project_task_field(item.get("blocker"), fallback_item.get("blocker"), field="blocker"),
                "why_now": normalize_project_task_field(item.get("why_now"), fallback_item.get("why_now"), field="why_now"),
                "knowledge_points": normalize_today_display_list(item.get("knowledge_points") or fallback_item.get("knowledge_points"), limit=6),
                "explanation": sanitize_today_user_text(item.get("explanation") or fallback_item.get("explanation")),
                "how_to_apply": normalize_project_task_field(item.get("how_to_apply"), fallback_item.get("how_to_apply"), field="how_to_apply"),
                "extension": sanitize_today_user_text(item.get("extension") or fallback_item.get("extension")),
                "source_segment_ids": normalize_prompt_string_list(item.get("source_segment_ids") or fallback_item.get("source_segment_ids"), limit=4),
                "source_status": str(item.get("source_status") or fallback_item.get("source_status") or "llm-grounded").strip(),
            }
        )
        if len(normalized) >= 8:
            break
    return normalized or fallback_items



def normalize_lesson_project_driven_explanation(value: Any, fallback: Any) -> dict[str, Any]:
    fallback_dict = dict(fallback) if isinstance(fallback, dict) else {}
    candidate = dict(value) if isinstance(value, dict) else {}
    return {
        "summary": str(candidate.get("summary") or fallback_dict.get("summary") or "").strip(),
        "tasks": normalize_lesson_project_tasks(candidate.get("tasks"), fallback_dict.get("tasks")),
    }


def normalize_lesson_review_suggestions(value: Any, fallback: Any) -> dict[str, Any]:
    fallback_dict = dict(fallback) if isinstance(fallback, dict) else {}
    candidate = dict(value) if isinstance(value, dict) else {}
    return {
        "summary": str(candidate.get("summary") or fallback_dict.get("summary") or "").strip(),
        "today_review": normalize_llm_text_list(candidate.get("today_review"), fallback_dict.get("today_review"), limit=6),
        "progress_review": normalize_llm_text_list(candidate.get("progress_review"), fallback_dict.get("progress_review"), limit=6),
        "next_actions": normalize_llm_text_list(candidate.get("next_actions"), fallback_dict.get("next_actions"), limit=6),
    }


def build_case_courseware(plan: dict[str, Any]) -> dict[str, Any]:
    today_focus = plan.get("today_focus") if isinstance(plan.get("today_focus"), dict) else {}
    focus_points = [item for item in (today_focus.get("focus_points") or []) if isinstance(item, dict)]
    project_driven_explanation = plan.get("project_driven_explanation") if isinstance(plan.get("project_driven_explanation"), dict) else {}
    project_tasks = [item for item in (project_driven_explanation.get("tasks") or []) if isinstance(item, dict)]
    materials_used = [item for item in (plan.get("materials_used") or []) if isinstance(item, dict)]
    flashcards = []
    for item in focus_points[:8]:
        point = sanitize_today_user_text(item.get("point"))
        if not point:
            continue
        flashcards.append(
            {
                "front": point,
                "prompt": sanitize_today_user_text(item.get("why_it_matters")) or f"今天为什么要掌握 {point}？",
                "mastery_check": sanitize_today_user_text(item.get("mastery_check")),
            }
        )
    first_task = project_tasks[0] if project_tasks else {}
    guided_steps = []
    for task in project_tasks[:6]:
        task_name = sanitize_today_user_text(task.get("task_name"))
        if not task_name:
            continue
        guided_steps.append(
            {
                "scene": task_name,
                "challenge": sanitize_today_user_text(task.get("blocker")),
                "teaching_move": sanitize_today_user_text(task.get("why_now")),
                "resolution": sanitize_today_user_text(task.get("how_to_apply") or task.get("explanation")),
                "knowledge_points": normalize_today_display_list(task.get("knowledge_points") or [], limit=6),
            }
        )
    review_sources = []
    for item in materials_used[:8]:
        title = sanitize_today_user_text(item.get("material_title"))
        if not title:
            continue
        review_sources.append(
            {
                "material_title": title,
                "locator": sanitize_today_user_text(item.get("locator")) or "待补充定位",
                "review_focus": sanitize_today_user_text(item.get("match_reason")) or (flashcards[0]["front"] if flashcards else "今日重点"),
            }
        )
    return {
        "knowledge_preview_flashcards": flashcards,
        "case_background": {
            "protagonist": "学习者",
            "situation": sanitize_today_user_text(first_task.get("real_context") or project_driven_explanation.get("summary") or today_focus.get("summary")),
            "problem_to_solve": sanitize_today_user_text(first_task.get("task_name") or plan.get("title") or "今日任务"),
        },
        "guided_story_practice": guided_steps,
        "review_sources": review_sources,
        "exercise_policy": {
            "embedded_questions": False,
            "question_module": "练习题由独立题目模块生成",
        },
    }


def normalize_lesson_case_courseware(value: Any, fallback_plan: dict[str, Any]) -> dict[str, Any]:
    fallback = build_case_courseware(fallback_plan)
    if not isinstance(value, dict):
        return fallback
    normalized = dict(fallback)
    for field in ("knowledge_preview_flashcards", "guided_story_practice", "review_sources"):
        if isinstance(value.get(field), list) and value.get(field):
            normalized[field] = value[field]
    if isinstance(value.get("case_background"), dict) and value.get("case_background"):
        normalized["case_background"] = value["case_background"]
    exercise_policy = value.get("exercise_policy") if isinstance(value.get("exercise_policy"), dict) else {}
    normalized["exercise_policy"] = {**normalized.get("exercise_policy", {}), **exercise_policy, "embedded_questions": False}
    return normalized


def find_related_project_task(focus_item: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    related_names = set(normalize_prompt_string_list(focus_item.get("related_tasks"), limit=4))
    segment_ids = set(normalize_prompt_string_list(focus_item.get("source_segment_ids"), limit=4))
    point = str(focus_item.get("point") or "").strip()
    for task in tasks:
        task_name = str(task.get("task_name") or "").strip()
        task_segments = set(normalize_prompt_string_list(task.get("source_segment_ids"), limit=4))
        knowledge_points = set(normalize_prompt_string_list(task.get("knowledge_points"), limit=8))
        if task_name and task_name in related_names:
            return task
        if segment_ids and task_segments.intersection(segment_ids):
            return task
        if point and point in knowledge_points:
            return task
    return tasks[0] if tasks else {}


def derive_today_lesson_focus_points(focus_points: list[dict[str, Any]], fallback: Any = None) -> list[str]:
    return normalize_today_display_list(
        [item.get("point") for item in focus_points] or fallback or [],
        limit=8,
    )



def derive_today_project_task_names(project_tasks: list[dict[str, Any]], fallback: Any = None) -> list[str]:
    return normalize_today_display_list(
        [item.get("task_name") for item in project_tasks] or fallback or [],
        limit=8,
    )



def derive_today_project_blockers(project_tasks: list[dict[str, Any]], fallback: Any = None) -> list[str]:
    return normalize_today_display_list(
        [item.get("blocker") for item in project_tasks] or fallback or [],
        limit=8,
    )



def derive_today_review_targets(focus_points: list[dict[str, Any]], review_suggestions: dict[str, Any], fallback: Any = None) -> list[str]:
    return normalize_today_display_list(
        [
            *(review_suggestions.get("today_review") or []),
            *(review_suggestions.get("progress_review") or []),
            *(review_suggestions.get("next_actions") or []),
            *[item.get("mastery_check") for item in focus_points],
            *(fallback or []),
        ],
        limit=8,
    )



def derive_grounded_session_theme(topic: str, lesson_focus_points: list[str], project_tasks: list[str], fallback: Any = None) -> str:
    for candidate in project_tasks[:2]:
        text = sanitize_today_user_text(candidate)
        if text and not looks_like_generic_project_task(text):
            return shorten_today_text(text, limit=36)
    for candidate in lesson_focus_points[:2]:
        text = sanitize_today_user_text(candidate)
        if text:
            return shorten_today_text(text, limit=36)
    fallback_text = sanitize_today_user_text(fallback) or sanitize_today_user_text(topic) or "今日学习"
    return shorten_today_text(fallback_text, limit=36)



def derive_grounded_new_learning_focus(lesson_focus_points: list[str], project_tasks: list[str], fallback: Any = None) -> list[str]:
    grounded_tasks = [
        sanitize_today_user_text(item)
        for item in project_tasks[:4]
        if sanitize_today_user_text(item) and not looks_like_generic_project_task(item)
    ]
    grounded = normalize_today_display_list(grounded_tasks + lesson_focus_points[:4], limit=6)
    if grounded:
        return grounded
    return normalize_today_display_list(fallback or [], limit=6)



def build_sanitized_mastery_targets(mastery_targets: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "reading_checklist": normalize_today_display_list(mastery_targets.get("reading_checklist") or [], limit=6),
        "session_exercises": normalize_today_display_list(mastery_targets.get("session_exercises") or [], limit=4),
        "applied_project": normalize_today_display_list(mastery_targets.get("applied_project") or [], limit=4),
        "reflection": normalize_today_display_list(mastery_targets.get("reflection") or [], limit=4),
    }



def refresh_today_teaching_brief(plan: dict[str, Any], fallback_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    brief = json.loads(json.dumps(fallback_brief or {}))
    today_focus = plan.get("today_focus") if isinstance(plan.get("today_focus"), dict) else {}
    focus_points = [item for item in (today_focus.get("focus_points") or []) if isinstance(item, dict)]
    project_driven_explanation = plan.get("project_driven_explanation") if isinstance(plan.get("project_driven_explanation"), dict) else {}
    project_tasks = [item for item in (project_driven_explanation.get("tasks") or []) if isinstance(item, dict)]
    review_suggestions = plan.get("review_suggestions") if isinstance(plan.get("review_suggestions"), dict) else {}

    lesson_focus_points = derive_today_lesson_focus_points(focus_points, plan.get("lesson_focus_points") or [])
    project_task_names = derive_today_project_task_names(project_tasks, plan.get("project_tasks") or [])
    project_blockers = derive_today_project_blockers(project_tasks, plan.get("project_blockers") or [])
    review_targets = derive_today_review_targets(focus_points, review_suggestions, plan.get("review_targets") or [])
    brief["materials_used"] = list(plan.get("materials_used") or [])
    brief["lesson_focus_points"] = lesson_focus_points
    brief["project_tasks"] = project_task_names
    brief["project_blockers"] = project_blockers
    brief["review_targets"] = review_targets
    brief["session_theme"] = derive_grounded_session_theme(
        str(brief.get("topic") or plan.get("goal_focus", {}).get("mainline") or "").strip() or "今日学习",
        lesson_focus_points,
        project_task_names,
        brief.get("session_theme") or plan.get("title"),
    )
    brief["new_learning_focus"] = derive_grounded_new_learning_focus(
        lesson_focus_points,
        project_task_names,
        brief.get("new_learning_focus") or [],
    )
    brief["mastery_targets"] = build_sanitized_mastery_targets(brief.get("mastery_targets") if isinstance(brief.get("mastery_targets"), dict) else {})
    brief["today_focus_summary"] = today_focus.get("summary") or None
    brief["project_summary"] = project_driven_explanation.get("summary") or None
    brief["review_summary"] = review_suggestions.get("summary") or None
    return brief


def synchronize_lesson_plan(plan: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(plan if isinstance(plan, dict) else {}))
    materials_used = [item for item in (updated.get("materials_used") or []) if isinstance(item, dict)]
    today_focus = updated.get("today_focus") if isinstance(updated.get("today_focus"), dict) else {}
    focus_points = [item for item in (today_focus.get("focus_points") or []) if isinstance(item, dict)]
    project_driven_explanation = updated.get("project_driven_explanation") if isinstance(updated.get("project_driven_explanation"), dict) else {}
    project_tasks = [item for item in (project_driven_explanation.get("tasks") or []) if isinstance(item, dict)]
    review_suggestions = updated.get("review_suggestions") if isinstance(updated.get("review_suggestions"), dict) else {}

    updated["lesson_focus_points"] = derive_today_lesson_focus_points(
        focus_points,
        updated.get("lesson_focus_points") or [],
    )
    updated["project_tasks"] = derive_today_project_task_names(
        project_tasks,
        updated.get("project_tasks") or [],
    )
    updated["project_blockers"] = derive_today_project_blockers(
        project_tasks,
        updated.get("project_blockers") or [],
    )
    updated["review_targets"] = derive_today_review_targets(
        focus_points,
        review_suggestions,
        updated.get("review_targets") or [],
    )

    content_summary = normalize_string_list(
        [
            today_focus.get("summary"),
            *[f"{item.get('point')}：{item.get('why_it_matters')}" for item in focus_points[:3]],
            *(updated.get("content_summary") or []),
        ]
    )[:4]
    updated["content_summary"] = content_summary

    derived_teaching_points: list[dict[str, Any]] = []
    for focus_item in focus_points:
        point = str(focus_item.get("point") or "").strip()
        if not point:
            continue
        related_task = find_related_project_task(focus_item, project_tasks)
        segment_ids = normalize_prompt_string_list(focus_item.get("source_segment_ids"), limit=4) or normalize_prompt_string_list(related_task.get("source_segment_ids"), limit=4)
        material_ref = next((item for item in materials_used if str(item.get("segment_id") or "") in segment_ids), {})
        derived_teaching_points.append(
            {
                "topic": point,
                "background": str(related_task.get("real_context") or focus_item.get("why_it_matters") or "").strip(),
                "core_question": str(related_task.get("why_now") or focus_item.get("mastery_check") or f"为什么今天需要先搞懂 {point}？").strip(),
                "explanation": str(related_task.get("explanation") or focus_item.get("why_it_matters") or "").strip(),
                "practical_value": str(focus_item.get("why_it_matters") or related_task.get("how_to_apply") or "").strip(),
                "pitfall": str(related_task.get("blocker") or "").strip(),
                "study_prompt": str(focus_item.get("mastery_check") or related_task.get("how_to_apply") or f"回到对应资料定位，确认 {point} 能否讲清楚并用出来。"),
                "source_status": str(related_task.get("source_status") or material_ref.get("source_status") or "llm-grounded").strip(),
                "segment_id": segment_ids[0] if segment_ids else None,
                "material_title": material_ref.get("material_title"),
            }
        )
    if derived_teaching_points:
        updated["teaching_points"] = derived_teaching_points

    if not updated.get("specific_tasks"):
        updated["specific_tasks"] = [
            {
                "segment_id": item.get("segment_id"),
                "label": item.get("material_title"),
                "chapter": item.get("chapter"),
                "pages": item.get("pages"),
                "sections": item.get("sections") or [],
                "purpose": item.get("match_reason"),
                "material_title": item.get("material_title"),
                "material_source_name": item.get("material_source_name"),
                "match_reason": item.get("match_reason"),
                "source_status": item.get("source_status"),
            }
            for item in materials_used
        ]

    reading_guidance = normalize_string_list(
        [
            "只回看今天实际用到的材料片段，不必泛读整本资料。",
            *[
                f"回看《{item.get('material_title') or '未命名资料'}》的 {item.get('locator') or '对应位置'}，核对相关知识点是否能独立解释。"
                for item in materials_used[:3]
            ],
            *(updated.get("reading_guidance") or []),
        ]
    )[:4]
    updated["reading_guidance"] = reading_guidance

    lesson_summary = normalize_string_list(
        [
            today_focus.get("summary"),
            review_suggestions.get("summary"),
            *[item.get("mastery_check") for item in focus_points[:2]],
            *(updated.get("lesson_summary") or []),
        ]
    )[:4]
    updated["lesson_summary"] = lesson_summary

    updated["lesson_intro"] = str(
        project_driven_explanation.get("summary")
        or updated.get("lesson_intro")
        or today_focus.get("summary")
        or "今天用一个或多个真实任务，把材料里的关键知识点串成一条主线。"
    ).strip()

    updated["exercise_plan"] = normalize_string_list(
        updated.get("exercise_plan")
        or updated.get("project_tasks")
        or updated.get("review_targets")
    )[:4]
    updated["practice_bridge"] = normalize_string_list(
        review_suggestions.get("next_actions")
        or updated.get("practice_bridge")
        or [
            "先读完上面的四段讲解，再进入网页练习题验证理解。",
            "做题卡住时，先回看对应任务里的 blocker 和解释，再继续作答。",
            "完成练习后，把今天仍不稳的点写进复习列表。",
        ]
    )[:4]

    completion_from_focus = [item.get("mastery_check") for item in focus_points]
    updated["completion_criteria"] = normalize_string_list(
        completion_from_focus + updated.get("review_targets", []) + (updated.get("completion_criteria") or [])
    )[:6]
    updated["feedback_request"] = normalize_string_list(
        updated.get("feedback_request")
        or [
            "学完后反馈：哪些知识点已经能讲清楚，哪些任务卡点还不稳。",
            "完成网页练习题后，再判断今日重点是否真正内化。",
            (
                "diagnostic session 完成后会自动停服、自动回写结果并重新进入 /learn-plan；若自动续跑失败，再执行页面展示的整条命令。"
                if str(updated.get('plan_execution_mode') or '') in {'diagnostic', 'test-diagnostic'}
                else "最后在 /learn-today Step 6 完成学后复盘并回写本次结果。"
            ),
        ]
    )[:4]
    updated["case_courseware"] = normalize_lesson_case_courseware(updated.get("case_courseware"), updated)
    updated["today_teaching_brief"] = refresh_today_teaching_brief(updated, updated.get("today_teaching_brief"))
    return updated


def build_today_teaching_brief(
    topic: str,
    plan_source: dict[str, Any],
    mastery_targets: dict[str, list[str]],
    materials_used: list[dict[str, Any]],
    lesson_focus_points: list[str],
    project_task_names: list[str],
    project_blockers: list[str],
    review_targets: list[str],
) -> dict[str, Any]:
    preference_state = plan_source.get("preference_state") if isinstance(plan_source.get("preference_state"), dict) else {}
    user_model = plan_source.get("user_model") if isinstance(plan_source.get("user_model"), dict) else {}
    goal_model = plan_source.get("goal_model") if isinstance(plan_source.get("goal_model"), dict) else {}
    sanitized_mastery_targets = build_sanitized_mastery_targets(mastery_targets)
    session_theme = derive_grounded_session_theme(
        topic,
        lesson_focus_points,
        project_task_names,
        plan_source.get("today_topic") or topic,
    )
    new_learning_focus = derive_grounded_new_learning_focus(
        lesson_focus_points,
        project_task_names,
        plan_source.get("new_learning") or [],
    )
    return {
        "topic": topic,
        "session_theme": session_theme,
        "current_stage": plan_source.get("current_stage"),
        "current_day": plan_source.get("day"),
        "execution_mode": plan_source.get("plan_execution_mode") or "normal",
        "mainline_goal": plan_source.get("mainline_goal") or goal_model.get("mainline_goal") or topic,
        "time_budget_today": plan_source.get("time_budget_today"),
        "learner_preferences": {
            "learning_style": normalize_string_list(preference_state.get("learning_style") or user_model.get("learning_style")),
            "practice_style": normalize_string_list(preference_state.get("practice_style") or user_model.get("practice_style")),
            "delivery_preference": normalize_string_list(preference_state.get("delivery_preference") or user_model.get("delivery_preference")),
        },
        "review_focus": normalize_string_list(plan_source.get("review") or []),
        "new_learning_focus": new_learning_focus,
        "exercise_focus": normalize_string_list(plan_source.get("exercise_focus") or []),
        "weak_points": normalize_string_list(
            plan_source.get("progress_review_debt") or plan_source.get("weakness_focus")
            or plan_source.get("learner_model_weaknesses") or []
        ),
        "learner_model_weaknesses": normalize_string_list(plan_source.get("learner_model_weaknesses") or []),
        "learner_model_review_debt": normalize_string_list(plan_source.get("learner_model_review_debt") or []),
        "plan_blockers": normalize_string_list(plan_source.get("plan_blockers") or []),
        "materials_used": materials_used,
        "lesson_focus_points": lesson_focus_points,
        "project_tasks": project_task_names,
        "project_blockers": project_blockers,
        "review_targets": review_targets,
        "mastery_targets": sanitized_mastery_targets,
        "language_policy": plan_source.get("language_policy") or {},
        "material_alignment": plan_source.get("material_alignment") or {},
        "coverage_ledger": [item for item in (plan_source.get("coverage_ledger") or []) if isinstance(item, dict)],
        "coverage_policy": {
            "avoid_repeating_mastered": True,
            "states": ["introduced", "practiced", "tested", "mastered", "repeated"],
        },
    }


def has_substantive_courseware_text(value: Any, *, min_chars: int = 6) -> bool:
    return len(sanitize_today_user_text(value)) >= min_chars


def courseware_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in (value or []) if isinstance(item, dict)]


def build_lesson_review(plan: dict[str, Any]) -> dict[str, Any]:
    materials_used = [item for item in (plan.get("materials_used") or []) if isinstance(item, dict)]
    today_focus = plan.get("today_focus") if isinstance(plan.get("today_focus"), dict) else {}
    focus_points = [item for item in (today_focus.get("focus_points") or []) if isinstance(item, dict)]
    project_driven_explanation = plan.get("project_driven_explanation") if isinstance(plan.get("project_driven_explanation"), dict) else {}
    project_tasks = [item for item in (project_driven_explanation.get("tasks") or []) if isinstance(item, dict)]
    review_suggestions = plan.get("review_suggestions") if isinstance(plan.get("review_suggestions"), dict) else {}
    review_targets = normalize_string_list(plan.get("review_targets") or [])
    execution_mode = str(plan.get("plan_execution_mode") or "normal")

    issues: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    fluff_markers = ["你可以考虑", "建议如下", "下面给出建议", "建议结构"]

    if not materials_used and execution_mode == "normal":
        issues.append("today-lesson.materials-used-missing")
        suggestions.append("补充今天实际引用的材料片段，并写清章节/页码/小节定位。")
    if materials_used and any(not str(item.get("locator") or "").strip() for item in materials_used):
        issues.append("today-lesson.material-locator-missing")
        suggestions.append("每条材料引用都要带定位信息，而不是只写材料名。")

    if not focus_points:
        issues.append("today-lesson.today-focus-missing")
        suggestions.append("明确列出今天必须掌握的知识点，并说明为什么今天要先掌握它。")
    elif not any(str(item.get("mastery_check") or "").strip() for item in focus_points):
        warnings.append("today-lesson.mastery-check-weak")
        suggestions.append("为每个重点知识补一条可判断是否掌握的标准。")

    if not project_tasks:
        # project_driven_explanation 现在是可选的——叙事内容由 lesson-html.json 承载
        pass
    else:
        if not any(normalize_prompt_string_list(item.get("knowledge_points"), limit=6) for item in project_tasks):
            warnings.append("today-lesson.project-knowledge-link-weak")
            suggestions.append("为每个任务明确绑定相关知识点，避免任务背景与知识讲解脱钩。")
        if not any(str(item.get("blocker") or "").strip() for item in project_tasks):
            warnings.append("today-lesson.project-blocker-weak")
            suggestions.append("明确每个任务会卡在哪里，再据此引入知识点。")

    today_review_raw = review_suggestions.get("today_review") or []
    progress_review_raw = review_suggestions.get("progress_review") or []
    # 兼容两种格式：纯 string 或 {focus, material, locator, ...} object
    today_review_strs = [r.get("focus") if isinstance(r, dict) else str(r) for r in (today_review_raw if isinstance(today_review_raw, list) else [])]
    progress_review_strs = [r.get("focus") if isinstance(r, dict) else str(r) for r in (progress_review_raw if isinstance(progress_review_raw, list) else [])]
    has_locator_detail = any(isinstance(r, dict) and r.get("locator") for r in (today_review_raw if isinstance(today_review_raw, list) else []))
    if not any(s.strip() for s in today_review_strs):
        issues.append("today-lesson.review-today-missing")
        suggestions.append("建议复习里要包含对今天内容的复盘，而不是只给泛泛提醒。")
    if execution_mode == "normal" and not any(s.strip() for s in progress_review_strs):
        issues.append("today-lesson.review-progress-missing")
        suggestions.append("建议复习要结合当前进度、旧知识债或下一步推进条件。")
    if today_review_strs and any(s.strip() for s in today_review_strs) and not has_locator_detail:
        warnings.append("today-lesson.review-locator-weak")
        suggestions.append("复习建议建议包含具体页码/段落定位，而非仅抽象建议。")
    if not review_targets:
        warnings.append("today-lesson.review-targets-weak")
        suggestions.append("补充 review targets，方便题目和后续 update 与今日讲解对齐。")

    text_fields = [
        str(plan.get("why_today") or "").strip(),
        str(plan.get("coach_explanation") or "").strip(),
        str(today_focus.get("summary") or "").strip(),
        str(project_driven_explanation.get("summary") or "").strip(),
        str(review_suggestions.get("summary") or "").strip(),
        *[str(item.get("why_it_matters") or "").strip() for item in focus_points],
        *[str(item.get("real_context") or "").strip() for item in project_tasks],
        *[str(item.get("why_now") or "").strip() for item in project_tasks],
    ]
    if any(any(marker in text for marker in fluff_markers) for text in text_fields if text):
        warnings.append("today-lesson.fluff-tone-detected")
        suggestions.append("去掉建议式套话，改成直接面向当前任务和阶段的正式讲解。")
    if project_tasks and not any(str(item.get("real_context") or "").strip() for item in project_tasks):
        issues.append("today-lesson.real-context-missing")
        suggestions.append("每个项目任务都要说明真实背景，避免只剩抽象知识点。")
    case_courseware = plan.get("case_courseware") if isinstance(plan.get("case_courseware"), dict) else None
    # case_courseware 现在是可选的——叙事内容由 lesson-html.json 承载
    if case_courseware:
        flashcards = courseware_items(case_courseware.get("knowledge_preview_flashcards"))
        case_background = case_courseware.get("case_background") if isinstance(case_courseware.get("case_background"), dict) else {}
        guided_steps = courseware_items(case_courseware.get("guided_story_practice"))
        review_sources = courseware_items(case_courseware.get("review_sources"))
        if flashcards and not all(has_substantive_courseware_text(item.get("mastery_check")) for item in flashcards):
            warnings.append("today-lesson.flashcard-mastery-check-missing")
            suggestions.append("课前知识预告里的每张知识卡都要有可判断的掌握检查。")
        if case_background and (
            not has_substantive_courseware_text(case_background.get("situation"), min_chars=10)
            or not has_substantive_courseware_text(case_background.get("problem_to_solve"), min_chars=6)
        ):
            issues.append("today-lesson.case-background-hollow")
            suggestions.append("案例背景要写清真实情境和要解决的问题，不能只保留空壳字段。")
        if (case_courseware.get("exercise_policy") or {}).get("embedded_questions"):
            issues.append("today-lesson.embedded-practice-questions")
            suggestions.append("练习题应由独立题目模块生成，不要默认写进课件。")
        if review_sources and not all(
            has_substantive_courseware_text(item.get("material_title"), min_chars=2)
            and has_substantive_courseware_text(item.get("locator"), min_chars=2)
            and has_substantive_courseware_text(item.get("review_focus"), min_chars=2)
            for item in review_sources
        ):
            warnings.append("today-lesson.review-source-incomplete")
            suggestions.append("回看资料要包含材料名、定位和复习重点。")
    if focus_points and not any(str(item.get("why_it_matters") or "").strip() for item in focus_points):
        warnings.append("today-lesson.why-it-matters-weak")
        suggestions.append("为 today_focus 补上为什么现在要掌握它，而不是只列名词。")

    if case_courseware:
        hollow_protagonist_patterns = [
            r"一个(?:开发|程序|工程|数据|运维|测试|前端|后端|全栈)(?:人员|工程师|者|师)",
            r"某个(?:项目|团队|公司|部门|产品|系统|平台|应用)",
            r"一个(?:项目|团队|公司|部门|产品|系统|平台|应用)",
            r"某(?:开发|公司|项目|团队|平台|系统)",
            r"你(?:是|在)一个",
            r"假设你是一个",
            r"一位(?:开发|程序|工程)",
        ]
        bg = case_courseware.get("case_background") if isinstance(case_courseware.get("case_background"), dict) else {}
        situation_text = str(bg.get("situation") or "")
        if situation_text and any(re.search(pattern, situation_text) for pattern in hollow_protagonist_patterns):
            warnings.append("today-lesson.hollow-protagonist")
            suggestions.append("案例背景避免使用空洞设定，改用有具体姓名、角色、时间、地点的真实场景。")

    valid = not issues
    confidence = 0.88 if not issues and not warnings else (0.72 if not issues else 0.46)
    return {
        "reviewer": "today-lesson-reviewer",
        "valid": valid,
        "issues": issues,
        "warnings": warnings,
        "suggestions": normalize_string_list(suggestions),
        "confidence": confidence,
        "evidence_adequacy": "sufficient" if not issues else "partial",
        "verdict": "ready" if valid else "needs-revision",
    }


def normalize_llm_daily_lesson_payload(candidate: Any, fallback_plan: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    normalized = json.loads(json.dumps(fallback_plan))
    for field in ["title", "current_stage", "study_mode", "why_today", "positioning", "coach_explanation"]:
        value = str(candidate.get(field) or "").strip()
        if value:
            normalized[field] = value
    normalized["materials_used"] = normalize_lesson_materials_used(candidate.get("materials_used"), fallback_plan.get("materials_used"))
    normalized["today_focus"] = normalize_lesson_today_focus(candidate.get("today_focus"), fallback_plan.get("today_focus"))
    normalized["project_driven_explanation"] = normalize_lesson_project_driven_explanation(
        candidate.get("project_driven_explanation"),
        fallback_plan.get("project_driven_explanation"),
    )
    normalized["review_suggestions"] = normalize_lesson_review_suggestions(candidate.get("review_suggestions"), fallback_plan.get("review_suggestions"))
    normalized["case_courseware"] = normalize_lesson_case_courseware(candidate.get("case_courseware"), normalized)
    normalized["goal_focus"] = normalize_llm_mapping(candidate.get("goal_focus"), fallback_plan.get("goal_focus"))
    normalized["preference_focus"] = normalize_llm_mapping(candidate.get("preference_focus"), fallback_plan.get("preference_focus"))
    normalized["material_alignment"] = normalize_llm_mapping(candidate.get("material_alignment"), fallback_plan.get("material_alignment"))
    normalized["specific_tasks"] = candidate.get("specific_tasks") if isinstance(candidate.get("specific_tasks"), list) and candidate.get("specific_tasks") else fallback_plan.get("specific_tasks") or []
    normalized["teaching_points"] = normalize_llm_teaching_points(candidate.get("teaching_points"), fallback_plan.get("teaching_points"))
    normalized["time_budget_today"] = candidate.get("time_budget_today") or fallback_plan.get("time_budget_today")
    normalized["plan_execution_mode"] = fallback_plan.get("plan_execution_mode")
    normalized["plan_blockers"] = fallback_plan.get("plan_blockers") or []
    normalized["lesson_generation_mode"] = "llm-grounded"
    normalized["source_trace"] = candidate.get("source_trace") or {"basis": "today_teaching_brief+grounding_context"}
    normalized = synchronize_lesson_plan(normalized)
    normalized["today_teaching_brief"] = refresh_today_teaching_brief(normalized, fallback_plan.get("today_teaching_brief") or {})
    return normalized


def build_daily_lesson_prompt(grounding_context: dict[str, Any], fallback_plan: dict[str, Any]) -> str:
    compact_grounding = {
        "topic": grounding_context.get("topic"),
        "current_stage": grounding_context.get("current_stage"),
        "current_day": grounding_context.get("current_day"),
        "today_topic": grounding_context.get("today_topic"),
        "mainline_goal": grounding_context.get("mainline_goal"),
        "review": grounding_context.get("review") or [],
        "new_learning": grounding_context.get("new_learning") or [],
        "exercise_focus": grounding_context.get("exercise_focus") or [],
        "weak_points": grounding_context.get("weak_points") or [],
        "time_budget_today": grounding_context.get("time_budget_today"),
        "plan_execution_mode": grounding_context.get("plan_execution_mode"),
        "plan_blockers": grounding_context.get("plan_blockers") or [],
        "session_objectives": grounding_context.get("session_objectives") or [],
        "learner_preferences": grounding_context.get("learner_preferences") or {},
        "goal_focus": grounding_context.get("goal_focus") or {},
        "mastery_targets": grounding_context.get("mastery_targets") or {},
        "selected_segments": [
            {
                "segment_id": item.get("segment_id"),
                "label": item.get("label"),
                "material_title": item.get("material_title"),
                "source_status": item.get("source_status"),
                "source_summary": item.get("source_summary"),
                "source_key_points": item.get("source_key_points") or [],
                "source_examples": item.get("source_examples") or [],
                "source_pitfalls": item.get("source_pitfalls") or [],
                "locator": item.get("locator") if isinstance(item.get("locator"), dict) else {},
            }
            for item in (grounding_context.get("selected_segments") or [])[:6]
            if isinstance(item, dict)
        ],
        "today_teaching_constraints": grounding_context.get("today_teaching_constraints") or {},
        "teaching_pattern": grounding_context.get("teaching_pattern") or "adaptive",
        "language_policy": grounding_context.get("language_policy") or fallback_plan.get("language_policy") or {},
    }
    compact_brief = fallback_plan.get("today_teaching_brief") or {}
    prompt_seed = {
        "title": fallback_plan.get("title"),
        "current_stage": fallback_plan.get("current_stage"),
        "study_mode": fallback_plan.get("study_mode"),
        "why_today": fallback_plan.get("why_today"),
        "materials_used": [
            {
                "material_title": item.get("material_title"),
                "locator": item.get("locator"),
                "match_reason": item.get("match_reason"),
                "source_status": item.get("source_status"),
            }
            for item in (fallback_plan.get("materials_used") or [])[:6]
            if isinstance(item, dict)
        ],
        "today_focus": fallback_plan.get("today_focus") or {},
        "project_driven_explanation": fallback_plan.get("project_driven_explanation") or {},
        "review_suggestions": fallback_plan.get("review_suggestions") or {},
    }
    language_policy = compact_grounding.get("language_policy") if isinstance(compact_grounding.get("language_policy"), dict) else {}
    return f"""你是一个学习教练。请基于给定的 compact_grounding_context、today_teaching_brief 与 fallback_four_part_lesson，生成 /learn-today 的正式讲解模型。

{language_policy_prompt_block(language_policy)}

{shared_style_prompt_block(audience='today 讲义与解释')}

硬性要求：
1. 只输出一个 JSON object，不要 Markdown，不要解释 JSON 外的文字。
2. 本 JSON 是 lesson-artifact.json 的运行时元数据，不承载完整课件正文；正式课件正文由独立的 lesson-html.json 承载，并通过 /long-output-html 渲染。
3. lesson-html.json 的正文应按三段教学框架组织：
   - Part 1 往期复习：复习上期学习内容、掌握情况、错题/薄弱点，以及它们如何引出本期内容。
   - Part 2 本期知识点讲解：围绕本期核心问题展开真实案例、逐步推理、代码/实验/反例和可验证掌握检查。
   - Part 3 本期内容回看：列出材料来源与回看重点，尽量精确到材料名、章节、页码、段落、section 或 locator；资料没有精确定位时必须说明限制，禁止编造。
4. 不限制 section 数量、字数、是否使用列表或代码块；允许表格、列表、callout、代码块、对照讲解。不要把课件写成固定的三幕故事模板。
5. materials_used 只能保留“材料名 + 章节/页码/小节/segment 定位 + 选择理由”的轻量引用；课件正文中可以适当引用 source_excerpt 中的原文关键句（不超过 150 字/处），但禁止大段复制材料正文。
6. today_focus 必须回答“今天到底要掌握什么、为什么今天先掌握它、怎样算掌握”。
7. review_suggestions 必须同时覆盖：
   - 对今日内容的复盘
   - 结合当前进度/旧知识债的复习建议
   - 下一步如何衔接网页练习题或后续 session
8. 如果 topic/domain 是 Git，只能围绕 Git 的快照、commit、暂存区、git add、git status、branch/remote 等上下文中出现的内容；不得混入 HTTP、JSON、日志、测试、部署等无关题材。
9. 优先吸收 compact_grounding_context 里的真实材料摘要、例子、坑点和 mastery target；fallback_four_part_lesson 只作为保底结构，不要机械改写它。
10. 讲解要像正式课程，不要写“你可以考虑”“下面是建议结构”这类提示语。
11. 若 fallback 文案里有“待补充”或空字段，必须结合 compact_grounding_context 重写成具体内容，不要原样保留。
12. 不要求生成 case_courseware；case_courseware 仅是旧版兼容字段。练习题由独立题目模块生成，不要把练习题默认嵌入课件。
13. 每个核心知识点必须至少关联一处材料来源；review_suggestions 中的回看项优先使用 material_title、locator、key_quote、review_focus 这类对象格式。

必须返回这些字段：
- title
- current_stage
- study_mode
- why_today
- materials_used
- today_focus
- review_suggestions
- source_trace

字段要求：
- materials_used: 数组；每项包含 material_title, locator；可选 segment_id, match_reason, source_status
- today_focus: 对象，包含 summary, focus_points
- today_focus.focus_points: 数组；每项包含 point, why_it_matters, mastery_check；可选 source_segment_ids
- review_suggestions: 对象，包含 summary, today_review, progress_review, next_actions；today_review 和 progress_review 的每一项推荐使用 focus/material/locator/key_quote 对象格式

COMPACT_GROUNDING_CONTEXT:
{json_for_prompt(compact_grounding, limit=9000)}

TODAY_TEACHING_BRIEF:
{json_for_prompt(compact_brief, limit=2500)}

FALLBACK_FOUR_PART_LESSON:
{json_for_prompt(prompt_seed, limit=5000)}
"""


def build_lesson_quality_artifact(plan: dict[str, Any], generation_trace: dict[str, Any] | None = None) -> dict[str, Any]:
    lesson_plan = synchronize_lesson_plan(dict(plan) if isinstance(plan, dict) else {})
    materials_used = [item for item in (lesson_plan.get("materials_used") or []) if isinstance(item, dict)]
    focus_points = [
        item for item in ((lesson_plan.get("today_focus") or {}).get("focus_points") or [])
        if isinstance(item, dict)
    ]
    project_tasks = [
        item for item in ((lesson_plan.get("project_driven_explanation") or {}).get("tasks") or [])
        if isinstance(item, dict)
    ]
    review_targets = normalize_string_list(lesson_plan.get("review_targets") or [])
    evidence = normalize_string_list(
        [
            *[
                f"材料：{item.get('material_title')} / {item.get('locator')}"
                for item in materials_used[:6]
                if item.get("material_title")
            ],
            *[item.get("point") for item in focus_points[:6]],
            *[item.get("task_name") for item in project_tasks[:6]],
            *review_targets[:6],
        ]
    )[:20]
    traceability_entries: list[dict[str, Any]] = []
    for item in materials_used[:8]:
        ref = str(item.get("segment_id") or item.get("material_title") or "").strip()
        if not ref:
            continue
        traceability_entries.append(
            build_traceability_entry(
                kind="material-segment",
                ref=ref,
                title=item.get("material_title") or ref,
                detail=item.get("match_reason") or (lesson_plan.get("today_focus") or {}).get("summary"),
                stage="lesson",
                status=item.get("source_status") or lesson_plan.get("lesson_generation_mode") or "ready",
                locator=item.get("locator"),
            )
        )
    if not traceability_entries:
        traceability_entries.append(
            build_traceability_entry(
                kind="lesson-plan",
                ref=str(lesson_plan.get("title") or lesson_plan.get("current_stage") or "lesson").strip() or "lesson",
                title=lesson_plan.get("title") or lesson_plan.get("current_stage") or "lesson",
                detail=lesson_plan.get("why_today") or lesson_plan.get("positioning"),
                stage="lesson",
                status=lesson_plan.get("lesson_generation_mode") or "fallback",
            )
        )

    generation = generation_trace if isinstance(generation_trace, dict) else lesson_plan.get("generation_trace")
    lesson_review = build_lesson_review(lesson_plan)
    resolved_confidence = normalize_confidence((generation or {}).get("confidence"), default=0.0)
    if resolved_confidence <= 0:
        resolved_confidence = normalize_confidence(lesson_review.get("confidence"), default=0.0)
    if resolved_confidence <= 0:
        resolved_confidence = 0.78 if not lesson_review.get("issues") else 0.46

    lesson_plan["case_courseware"] = normalize_lesson_case_courseware(lesson_plan.get("case_courseware"), lesson_plan)
    result = apply_quality_envelope(
        {**lesson_plan, "lesson_review": lesson_review},
        stage="lesson",
        generator="runtime-lesson-builder",
        evidence=evidence,
        confidence=resolved_confidence,
        quality_review=lesson_review,
        generation_trace=generation,
        traceability=traceability_entries,
    )
    result["lesson_review"] = dict(result.get("quality_review") or lesson_review)
    return result


def build_lesson_grounding_context(topic: str, plan_source: dict[str, Any], selected_segments: list[dict[str, Any]], mastery_targets: dict[str, list[str]]) -> dict[str, Any]:
    checkin = plan_source.get("today_progress_checkin") if isinstance(plan_source.get("today_progress_checkin"), dict) else {}
    preference_state = plan_source.get("preference_state") if isinstance(plan_source.get("preference_state"), dict) else {}
    user_model = plan_source.get("user_model") if isinstance(plan_source.get("user_model"), dict) else {}
    goal_model = plan_source.get("goal_model") if isinstance(plan_source.get("goal_model"), dict) else {}
    return {
        "topic": topic,
        "current_stage": plan_source.get("current_stage"),
        "current_day": plan_source.get("day"),
        "today_topic": plan_source.get("today_topic"),
        "mainline_goal": plan_source.get("mainline_goal") or goal_model.get("mainline_goal") or topic,
        "review": normalize_string_list(plan_source.get("review") or []),
        "new_learning": normalize_string_list(plan_source.get("new_learning") or []),
        "exercise_focus": normalize_string_list(plan_source.get("exercise_focus") or []),
        "weak_points": normalize_string_list(
            plan_source.get("progress_review_debt") or plan_source.get("weakness_focus")
            or plan_source.get("learner_model_weaknesses") or []
        ),
        "learner_model_weaknesses": normalize_string_list(plan_source.get("learner_model_weaknesses") or []),
        "learner_model_review_debt": normalize_string_list(plan_source.get("learner_model_review_debt") or []),
        "time_budget_today": plan_source.get("time_budget_today") or checkin.get("time_budget_today"),
        "plan_execution_mode": plan_source.get("plan_execution_mode") or "normal",
        "plan_blockers": normalize_string_list(plan_source.get("plan_blockers") or []),
        "session_objectives": normalize_string_list(plan_source.get("session_objectives") or []),
        "gating_decision": plan_source.get("gating_decision"),
        "learner_preferences": {
            "learning_style": normalize_string_list(preference_state.get("learning_style") or user_model.get("learning_style")),
            "practice_style": normalize_string_list(preference_state.get("practice_style") or user_model.get("practice_style")),
            "delivery_preference": normalize_string_list(preference_state.get("delivery_preference") or user_model.get("delivery_preference")),
        },
        "goal_focus": {
            "mainline": plan_source.get("mainline_goal") or goal_model.get("mainline_goal") or topic,
            "supporting": normalize_string_list(plan_source.get("supporting_capabilities") or goal_model.get("supporting_capabilities")),
            "enhancement": normalize_string_list(plan_source.get("enhancement_modules") or goal_model.get("enhancement_modules")),
        },
        "material_alignment": plan_source.get("material_alignment") or {},
        "coverage_ledger": [item for item in (plan_source.get("coverage_ledger") or []) if isinstance(item, dict)],
        "coverage_policy": {
            "avoid_repeating_mastered": True,
            "states": ["introduced", "practiced", "tested", "mastered", "repeated"],
        },
        "selected_segments": [
            {
                "segment_id": segment.get("segment_id"),
                "label": segment.get("label"),
                "material_title": segment.get("material_title"),
                "source_status": segment.get("source_status"),
                "source_summary": segment.get("source_summary"),
                "source_key_points": segment.get("source_key_points") or [],
                "source_examples": segment.get("source_examples") or [],
                "source_pitfalls": segment.get("source_pitfalls") or [],
                "source_excerpt": compact_source_text(segment.get("source_excerpt") or "", 2000),
                "locator": segment.get("locator") if isinstance(segment.get("locator"), dict) else {},
            }
            for segment in selected_segments
            if isinstance(segment, dict)
        ],
        "mastery_targets": mastery_targets,
        "language_policy": plan_source.get("language_policy") or {},
        "today_teaching_constraints": {
            "section_order": [
                "你阅读了哪些材料",
                "今日重点要掌握哪些知识",
                "项目驱动的知识点讲解和相关扩展",
                "建议复习",
            ],
            "project_driven_default": True,
            "materials_reference_only": True,
            "question_in_markdown": False,
        },
        "generation_mode": "grounded-local-context",
        "artifact_generation_mode": "external-required",
        "teaching_pattern": preference_state.get("teaching_pattern") or user_model.get("teaching_pattern") or "adaptive",
    }


def build_daily_lesson_plan(topic: str, plan_source: dict[str, Any], selected_segments: list[dict[str, Any]], mastery_targets: dict[str, list[str]]) -> dict[str, Any]:
    current_stage = plan_source.get("current_stage") or "未识别阶段"
    current_day = plan_source.get("day") or "未命名学习日"
    review = normalize_string_list(plan_source.get("review") or [])
    new_learning = normalize_string_list(plan_source.get("new_learning") or [])
    exercise_focus = normalize_string_list(plan_source.get("exercise_focus") or [])
    execution_mode = str(plan_source.get("plan_execution_mode") or "normal")
    plan_blockers = normalize_string_list(plan_source.get("plan_blockers") or [])

    lesson_lines: list[dict[str, Any]] = []
    teaching_points: list[dict[str, Any]] = []
    covered_topics: set[str] = set()
    content_summaries: list[str] = []
    preference_state = plan_source.get("preference_state") if isinstance(plan_source.get("preference_state"), dict) else {}
    learning_style = normalize_string_list(preference_state.get("learning_style") or (plan_source.get("user_model") or {}).get("learning_style"))
    practice_style = normalize_string_list(preference_state.get("practice_style") or (plan_source.get("user_model") or {}).get("practice_style"))
    delivery_preference = normalize_string_list(preference_state.get("delivery_preference") or (plan_source.get("user_model") or {}).get("delivery_preference"))
    for segment in selected_segments:
        locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
        sections = locator.get("sections") or []
        checkpoints = segment.get("checkpoints") or []
        lesson_line = {
            "segment_id": segment.get("segment_id"),
            "label": segment.get("label"),
            "chapter": locator.get("chapter"),
            "pages": locator.get("pages"),
            "sections": sections,
            "purpose": segment.get("purpose"),
            "checkpoints": checkpoints,
            "material_title": segment.get("material_title"),
            "material_summary": segment.get("material_summary"),
            "material_source_name": segment.get("material_source_name"),
            "material_source_type": segment.get("material_source_type"),
            "material_local_path": segment.get("material_local_path"),
            "material_kind": segment.get("material_kind"),
            "material_teaching_style": segment.get("material_teaching_style"),
            "target_clusters": segment.get("target_clusters") or [],
            "match_reason": segment.get("match_reason"),
            "source_status": segment.get("source_status") or "fallback-metadata",
            "source_summary": segment.get("source_summary") or "",
            "source_excerpt": segment.get("source_excerpt") or "",
            "source_examples": segment.get("source_examples") or [],
            "source_pitfalls": segment.get("source_pitfalls") or [],
            "source_key_points": segment.get("source_key_points") or [],
            "source_path": segment.get("source_path"),
            "source_kind": segment.get("source_kind"),
        }
        lesson_lines.append(lesson_line)
        segment_key_points = clean_source_teaching_terms(normalize_string_list(segment.get("source_key_points") or []))
        if segment.get("source_summary"):
            summary_terms = clean_source_teaching_terms(split_semicolon_values(segment.get("source_summary")))
            content_summaries.append("；".join(summary_terms) or str(segment.get("source_summary")))
        for item in (segment_key_points or clean_source_teaching_terms(normalize_string_list(sections)) or clean_source_teaching_terms(normalize_string_list(checkpoints)))[:6]:
            topic_name = str(item).strip()
            if not topic_name or topic_name in covered_topics:
                continue
            covered_topics.add(topic_name)
            source_status = str(segment.get("source_status") or "fallback-metadata")
            source_excerpt = str(segment.get("source_excerpt") or "").strip()
            if source_status == "extracted":
                background = f"今天先不要求你通读原资料；我先根据 {segment.get('material_title') or segment.get('label') or topic} 里和 {topic_name} 直接相关的例子，讲清楚它解决什么问题。"
                explanation = build_content_aware_explanation(topic_name, segment, source_excerpt)
                practical_value = f"资料原文这部分真正想让你掌握的是：{'；'.join(segment_key_points) or segment.get('source_summary') or segment.get('purpose') or topic}。学完后，你应该能把 {topic_name} 的方向、输入输出和边界讲清楚，并在题里用出来。"
                pitfall = build_content_aware_pitfall(topic_name, segment)
                study_prompt = f"如果你对我上面的讲解还有疑惑，再回原资料看 {segment.get('material_title') or '该资料'} 的 {locator.get('chapter') or '对应章节'}，重点盯 {topic_name} 附近的例子和说明。"
            else:
                material_kind = str(segment.get("material_kind") or "")
                teaching_style = str(segment.get("material_teaching_style") or "")
                background = f"今天使用的主线资料是 {segment.get('material_title') or segment.get('label') or topic}，其中 {topic_name} 是这段材料要解决的关键内容。"
                explanation = f"结合 {segment.get('material_source_name') or '当前资料'} 的这一段内容，先弄清 {topic_name} 的基本概念、典型输入输出形式，以及它在 {segment.get('label') or topic} 中承担什么作用。"
                study_prompt = f"阅读 {segment.get('material_title') or '这份资料'} 时，重点留意 {topic_name} 的定义、例子、适用场景，以及它与同段其它概念之间的区别。"
                if material_kind == "book" or teaching_style == "chapter-lecture":
                    background = f"今天使用的是书籍型主线资料 {segment.get('material_title') or segment.get('label') or topic}，这一段更适合按‘概念—例子—应用’的顺序去理解。"
                    explanation = f"把 {topic_name} 看成这一章节里的核心概念，先理解它在书中是怎样被引入的，再理解它如何和本章其它内容衔接。"
                    study_prompt = f"阅读 {segment.get('material_title') or '这本书'} 时，优先留意 {topic_name} 出现前后的例子、定义和章节过渡。"
                elif material_kind == "tutorial" or teaching_style == "step-by-step":
                    background = f"今天使用的是教程型资料 {segment.get('material_title') or segment.get('label') or topic}，这一段更像步骤讲解，需要边看边跟着思路走。"
                    explanation = f"把 {topic_name} 理解成教程里的一个操作步骤，先弄清它输入什么、输出什么、通常放在哪一步。"
                    study_prompt = f"阅读 {segment.get('material_title') or '这份教程'} 时，重点关注 {topic_name} 的步骤顺序、前置条件和执行结果。"
                elif material_kind == "reference" or teaching_style == "concept-reference":
                    background = f"今天使用的是参考资料 {segment.get('material_title') or segment.get('label') or topic}，这一段更适合按‘定义—接口—场景—边界’的顺序去读。"
                    explanation = f"把 {topic_name} 看成这份参考资料中的一个关键条目，先弄清它的定义，再看它通常和哪些接口、场景或约束一起出现。"
                    study_prompt = f"阅读 {segment.get('material_title') or '这份参考资料'} 时，重点留意 {topic_name} 的定义、典型用法、适用场景和使用边界。"
                practical_value = f"这段资料强调的是：{segment.get('material_summary') or segment.get('purpose') or topic}。掌握 {topic_name} 后，才能把这一段资料真正转成可用能力。"
                pitfall = f"学习 {topic_name} 时，要避免只记 API 或术语名字，而不理解它在这份资料里为什么重要、和相邻内容怎么配合。"
            teaching_points.append(
                {
                    "topic": topic_name,
                    "background": background,
                    "core_question": f"你需要先回答：{topic_name} 在 {segment.get('material_title') or topic} 这部分内容里，到底解决什么问题，为什么今天先学它？",
                    "explanation": explanation,
                    "practical_value": practical_value,
                    "pitfall": pitfall,
                    "study_prompt": study_prompt,
                    "source_status": source_status,
                    "segment_id": segment.get("segment_id"),
                    "material_title": segment.get("material_title"),
                }
            )

    if not teaching_points:
        for item in new_learning[:3]:
            teaching_points.append({
                "topic": item,
                "background": f"今天会把 {item} 作为新的推进点，它决定了后续能不能顺利进入下一层训练。",
                "core_question": f"阅读时要先想清楚：{item} 为什么会在今天出现，它补的是哪个能力缺口？",
                "explanation": f"今天需要重点理解 {item} 是什么、它解决什么问题、以及它和当前阶段任务的关系。",
                "practical_value": f"掌握 {item} 后，才能把 {topic} 的当前任务从‘会看’推进到‘会用’。",
                "pitfall": f"学习 {item} 时，要避免只记结论，不理解使用边界和实际场景。",
                "study_prompt": f"读资料时重点关注 {item} 的定义、典型使用方式，以及它与旧知识的衔接。",
                "source_status": "fallback-metadata",
                "segment_id": None,
                "material_title": None,
            })

    if not teaching_points:
        for item in review[:3]:
            teaching_points.append({
                "topic": item,
                "background": f"{item} 是你当前还不够稳的部分，所以今天要先把它补成可解释、可复用的知识。",
                "core_question": f"复习 {item} 时，先问自己：我之前为什么会在这里出错？是概念没懂，还是使用条件没搞清楚？",
                "explanation": f"今天先回看 {item}，把概念、用法和容易出错的地方重新讲清楚。",
                "practical_value": f"只有把 {item} 补稳，后续 {topic} 的推进才不会建立在不牢固的基础上。",
                "pitfall": f"复习 {item} 时，不要只看结果，要重新解释自己为什么这样做。",
                "study_prompt": f"读资料时重点回看 {item} 的定义、典型例子和反例，确认自己不是只会背结论。",
                "source_status": "fallback-metadata",
                "segment_id": None,
                "material_title": None,
            })

    completion_criteria = normalize_string_list(mastery_targets.get("reading_checklist") or [])
    completion_criteria += normalize_string_list(mastery_targets.get("session_exercises") or [])[:2]
    completion_criteria += normalize_string_list(mastery_targets.get("applied_project") or [])[:1]
    completion_criteria += normalize_string_list(mastery_targets.get("reflection") or [])[:1]

    material_alignment = plan_source.get("material_alignment") if isinstance(plan_source.get("material_alignment"), dict) else {}
    if not material_alignment and selected_segments:
        material_alignment = {
            "status": "aligned",
            "target_day_key": normalize_day_key(current_day),
            "selected_segment_ids": [str(item.get("segment_id")) for item in selected_segments if item.get("segment_id")],
            "material_ids": [str(item.get("material_id")) for item in selected_segments if item.get("material_id")],
            "match_reasons": [str(item.get("match_reason")) for item in selected_segments if item.get("match_reason")],
            "selection_mode": "metadata-fallback",
            "source_statuses": [str(item.get("source_status") or "fallback-metadata") for item in selected_segments],
            "fallback_reasons": [],
        }

    mode_description = describe_execution_mode(execution_mode, plan_source.get("mainline_goal") or topic)
    study_mode = "复习+推进" if review and new_learning else ("复习" if review else "推进")
    why_today = "先根据当前阶段、最近复习重点和新学习点安排当天内容，再结合掌握度检验决定是否推进。"
    coach_explanation = f"今天优先服务主线目标：{plan_source.get('mainline_goal') or topic}；在主线之外，只补 1 个支撑能力点，并仅在时间预算允许时触发增强模块。"
    positioning = f"当前处于 {current_stage}，今天围绕 {plan_source.get('today_topic') or topic} 安排学习。"
    practice_bridge = [
        "先消化上面的摘要和讲解，再进入练习页面做对应题目。",
        "做题时优先验证：你是否真的理解了今天这几个概念，而不是只记住名字。",
        "若练习卡住，再回到上面的讲解摘要或原资料定位处复看。",
    ]
    if learning_style:
        why_today += f" 当前已确认的学习风格：{'；'.join(learning_style)}。"
    if practice_style:
        coach_explanation += f" 当前优先练习方式：{'；'.join(practice_style)}。"
    if delivery_preference:
        coach_explanation += f" 讲练组织偏好：{'；'.join(delivery_preference)}。"
    if execution_mode != "normal":
        study_mode = mode_description["study_mode"]
        why_today = mode_description["why_today"]
        coach_explanation = mode_description["coach_explanation"]
        positioning = f"当前处于 {current_stage}，但计划执行模式为 {study_mode}。"
        practice_bridge = mode_description["practice_bridge"]
        if plan_blockers:
            blocker_title = {
                "clarification": "待补齐的澄清项",
                "research": "待确认的研究项",
                "diagnostic": "待完成的诊断项",
                "test-diagnostic": "待验证的诊断项",
                "prestudy": "待完成的确认项",
            }.get(execution_mode, "当前阻塞项")
            teaching_points.insert(0, {
                "topic": blocker_title,
                "background": "在进入正式学习前，系统检测到仍有关键 gate 未通过。",
                "core_question": "你需要先确认：这些前置条件是否已经补齐？",
                "explanation": "只有先补齐这些前置条件，后续路线和题目编排才不会建立在错误假设上。",
                "practical_value": "这一步是在为后续正式学习清路，而不是浪费时间。",
                "pitfall": "若跳过这些前置条件，后续 session 很容易继续沿着错误路径推进。",
                "study_prompt": "先逐条处理当前阻塞项，再决定是否进入正式主线学习。",
                "source_status": "fallback-metadata",
                "segment_id": None,
                "material_title": None,
            })
            completion_criteria = normalize_string_list(plan_blockers)
            completion_criteria += normalize_string_list(exercise_focus)[:2]
            completion_criteria += normalize_string_list(mastery_targets.get("reflection") or [])[:1]

    content_summary = content_summaries[:3] or [str(item.get("practical_value") or "") for item in teaching_points[:2] if item.get("practical_value")]
    lesson_generation_mode = "content-aware" if any(str(item.get("source_status") or "") == "extracted" for item in selected_segments) else "metadata-fallback"
    material_alignment["lesson_generation_mode"] = lesson_generation_mode

    materials_used = build_materials_used_entries(lesson_lines)
    task_map: dict[str, dict[str, Any]] = {}
    for line in lesson_lines:
        segment_id = str(line.get("segment_id") or "").strip() or f"line-{len(task_map) + 1}"
        related_points = [point for point in teaching_points if str(point.get("segment_id") or "").strip() == str(line.get("segment_id") or "").strip()]
        source_key_points = clean_source_teaching_terms(normalize_string_list(line.get("source_key_points") or []))
        knowledge_points = normalize_string_list([item.get("topic") for item in related_points] + source_key_points)[:4]
        blocker = normalize_string_list(line.get("source_pitfalls") or [])[:1]
        task_map[segment_id] = {
            "task_name": build_grounded_task_name(line, knowledge_points, topic),
            "real_context": build_grounded_task_real_context(line, knowledge_points, topic),
            "blocker": build_grounded_task_blocker(line, related_points, knowledge_points),
            "why_now": build_grounded_task_why_now(line, knowledge_points, topic),
            "knowledge_points": normalize_today_display_list(knowledge_points, limit=4),
            "explanation": sanitize_today_user_text(" ".join(str(item.get("explanation") or "").strip() for item in related_points[:2]).strip() or str(line.get("source_summary") or line.get("material_summary") or line.get("purpose") or "")),
            "how_to_apply": build_grounded_task_how_to_apply(line, knowledge_points),
            "extension": sanitize_today_user_text("；".join(normalize_string_list(line.get("target_clusters") or [])[:2]) or "完成当前任务后，再把相邻概念或下一步扩展连起来看。"),
            "source_segment_ids": [str(line.get("segment_id"))] if line.get("segment_id") else [],
            "source_status": str(line.get("source_status") or "fallback-metadata"),
        }
    project_tasks = dedupe_project_tasks(list(task_map.values()))
    if not project_tasks:
        for index, point in enumerate(teaching_points[:3], start=1):
            project_tasks.append(
                {
                    "task_name": sanitize_today_user_text(f"围绕 {point.get('topic') or topic} 建立可解释闭环"),
                    "real_context": sanitize_today_user_text(point.get("background") or f"把 {point.get('topic') or topic} 放进一个最小真实任务里，而不是孤立背概念。"),
                    "blocker": sanitize_today_user_text(point.get("pitfall") or "容易停留在术语层，不知道怎么用。"),
                    "why_now": sanitize_today_user_text(point.get("core_question") or f"因为今天要先让 {point.get('topic') or topic} 从‘看过’变成‘能解释、能判断、能应用’。"),
                    "knowledge_points": normalize_today_display_list([point.get("topic")] if point.get("topic") else [], limit=4),
                    "explanation": sanitize_today_user_text(point.get("explanation") or point.get("practical_value") or ""),
                    "how_to_apply": sanitize_today_user_text(point.get("study_prompt") or "先讲清楚，再进入练习题验证。"),
                    "extension": sanitize_today_user_text(point.get("practical_value") or "完成最小闭环后，再把相关知识点串到下一个任务里。"),
                    "source_segment_ids": [point.get("segment_id")] if point.get("segment_id") else [],
                    "source_status": point.get("source_status") or "fallback-metadata",
                }
            )

    focus_points = []
    for point in teaching_points[:6]:
        focus_points.append(
            {
                "point": str(point.get("topic") or "").strip(),
                "why_it_matters": str(point.get("practical_value") or point.get("background") or "").strip(),
                "mastery_check": str(point.get("study_prompt") or point.get("core_question") or "").strip(),
                "source_segment_ids": [str(point.get("segment_id"))] if point.get("segment_id") else [],
                "related_tasks": [
                    task.get("task_name")
                    for task in project_tasks
                    if str(point.get("topic") or "").strip() and str(point.get("topic") or "").strip() in normalize_string_list(task.get("knowledge_points") or [])
                ][:3],
            }
        )
    today_focus = {
        "summary": f"今天不是泛化浏览资料，而是先围绕 {plan_source.get('today_topic') or topic} 的真实任务，把这些知识点学成可解释、可判断、可作答的内容。",
        "focus_points": focus_points,
    }
    project_driven_explanation = {
        "summary": "今天默认按项目驱动来学：先看真实任务里会卡在哪里，再在那个位置引入知识点、讲清用法和扩展。",
        "tasks": project_tasks,
    }
    review_suggestions = {
        "summary": "复习时不要只回忆名词；要能回到今天的任务背景，说清为什么用、怎么用、什么时候别用。",
        "today_review": normalize_today_display_list(completion_criteria[:4] or [item.get("mastery_check") for item in focus_points[:3]], limit=6),
        "progress_review": normalize_today_display_list(review or plan_blockers or plan_source.get("progress_review_debt") or [], limit=4),
        "next_actions": normalize_today_display_list(practice_bridge + exercise_focus, limit=4),
    }

    plan = {
        "title": current_day,
        "current_stage": current_stage,
        "study_mode": study_mode,
        "positioning": positioning,
        "why_today": why_today,
        "coach_explanation": coach_explanation,
        "goal_focus": {
            "mainline": plan_source.get("mainline_goal") or topic,
            "supporting": normalize_string_list(plan_source.get("supporting_capabilities"))[:2],
            "enhancement": normalize_string_list(plan_source.get("enhancement_modules"))[:1],
        },
        "preference_focus": {
            "learning_style": learning_style,
            "practice_style": practice_style,
            "delivery_preference": delivery_preference,
        },
        "time_budget_today": plan_source.get("time_budget_today"),
        "lesson_intro": f"今天这一讲会把 {', '.join([item.get('topic') for item in teaching_points[:3] if item.get('topic')]) or topic} 放进真实任务里讲清楚，再带你回到材料定位与网页练习题。",
        "content_summary": content_summary,
        "lesson_generation_mode": lesson_generation_mode,
        "plan_execution_mode": execution_mode,
        "plan_blockers": plan_blockers,
        "language_policy": plan_source.get("language_policy") or {},
        "material_alignment": material_alignment,
        "specific_tasks": lesson_lines,
        "teaching_points": teaching_points,
        "reading_guidance": [
            "先确认今天到底在解决什么任务，再回看对应材料片段。",
            "回看材料时，只核对和今日任务相关的定义、例子、边界，不做泛读。",
            "确认自己能把任务背景、卡点和知识点的关系讲清楚后，再进入网页练习题。",
            "做题后再回头复盘：哪里是知识没懂，哪里是任务语境没连上。",
        ],
        "lesson_summary": [
            f"今天学完后，你至少要能把 {', '.join([item.get('point') for item in focus_points[:3] if item.get('point')]) or topic} 讲清楚，并知道它们为什么会在今天出现。",
            "如果你只能复述名词，却说不清它在任务里如何使用、如何避坑，就还不算掌握。",
            "真正完成的标志，是你能在网页练习题里把这些知识点和任务语境连起来。",
        ],
        "exercise_plan": exercise_focus,
        "practice_bridge": practice_bridge,
        "completion_criteria": completion_criteria,
        "feedback_request": [
            "学完后请反馈：哪些内容已经能讲清楚，哪些地方还卡。",
            "如完成练习或小项目，请贴代码、结论或运行结果。",
            (
                "diagnostic session 完成后会自动停服、自动回写结果并重新进入 /learn-plan；若自动续跑失败，再执行页面展示的整条命令。"
                if execution_mode in {'diagnostic', 'test-diagnostic'}
                else "最后在 /learn-today Step 6 完成学后复盘并回写本次结果。"
            ),
        ],
        "materials_used": materials_used,
        "today_focus": today_focus,
        "project_driven_explanation": project_driven_explanation,
        "review_suggestions": review_suggestions,
        "source_trace": {"basis": "selected_segments+plan_source+mastery_targets"},
    }
    plan = synchronize_lesson_plan(plan)
    plan["today_teaching_brief"] = build_today_teaching_brief(
        topic,
        plan_source,
        mastery_targets,
        plan.get("materials_used") or [],
        normalize_today_display_list(plan.get("lesson_focus_points") or [], limit=8),
        normalize_today_display_list(plan.get("project_tasks") or [], limit=8),
        normalize_today_display_list(plan.get("project_blockers") or [], limit=8),
        normalize_today_display_list(plan.get("review_targets") or [], limit=8),
    )
    return synchronize_lesson_plan(plan)


# DEPRECATED: 课件渲染已迁移到 long-output-html 管线。
# 保留此函数仅供 session_orchestrator.py 的 fallback 路径使用。
# 新代码应通过 --lesson-html-json + render_long_output_html.py 产出 lesson.html。
def render_daily_lesson_plan_markdown(plan: dict[str, Any]) -> str:
    title = str(plan.get("title") or "当日学习计划").strip()
    today_focus = plan.get("today_focus") if isinstance(plan.get("today_focus"), dict) else {}
    review_suggestions = plan.get("review_suggestions") if isinstance(plan.get("review_suggestions"), dict) else {}
    case_courseware = normalize_lesson_case_courseware(plan.get("case_courseware"), plan)
    flashcards = courseware_items(case_courseware.get("knowledge_preview_flashcards"))
    case_background = case_courseware.get("case_background") if isinstance(case_courseware.get("case_background"), dict) else {}
    guided_steps = courseware_items(case_courseware.get("guided_story_practice"))
    review_sources = courseware_items(case_courseware.get("review_sources"))
    exercise_policy = case_courseware.get("exercise_policy") if isinstance(case_courseware.get("exercise_policy"), dict) else {}

    positioning_lines = normalize_string_list(
        [
            plan.get("current_stage"),
            plan.get("why_today"),
            today_focus.get("summary"),
        ]
    )
    if not positioning_lines:
        positioning_lines = ["今天先用一个具体案例把知识点学成可解释、可验证、可作答的能力。"]

    preview_lines: list[str] = []
    for item in flashcards:
        front = sanitize_today_user_text(item.get("front")) or "今日知识点"
        prompt = sanitize_today_user_text(item.get("prompt")) or f"先想一想：{front} 解决什么问题？"
        mastery_check = sanitize_today_user_text(item.get("mastery_check"))
        preview_lines.append(f"- **{front}**：{prompt}")
        if mastery_check:
            preview_lines.append(f"  - 掌握检查：{mastery_check}")
    if not preview_lines:
        preview_lines = ["- 先浏览今天要掌握的关键词，暂时不要急着背答案。"]

    background_lines = [
        f"- 背景：{sanitize_today_user_text(case_background.get('situation')) or '今天的案例背景待补充。'}",
    ]
    protagonist = sanitize_today_user_text(case_background.get("protagonist"))
    if protagonist:
        background_lines.insert(0, f"- 角色：{protagonist}")

    problem_to_solve = sanitize_today_user_text(case_background.get("problem_to_solve")) or "今天要解决一个和当前知识点直接相关的问题。"
    question_module = sanitize_today_user_text(exercise_policy.get("question_module")) or "练习题由独立题目模块生成"
    problem_lines = [
        f"- {problem_to_solve}",
        f"- {question_module}，课件正文只负责讲清背景、知识和解题思路。",
    ]

    story_lines: list[str] = []
    for index, step in enumerate(guided_steps, start=1):
        scene = sanitize_today_user_text(step.get("scene")) or f"步骤 {index}"
        challenge = sanitize_today_user_text(step.get("challenge")) or "先观察这里会卡在哪里。"
        teaching_move = sanitize_today_user_text(step.get("teaching_move")) or "在这个卡点引入今天的新知识。"
        resolution = sanitize_today_user_text(step.get("resolution")) or "用今天的知识把问题解决掉。"
        knowledge_points = normalize_today_display_list(step.get("knowledge_points") or [], limit=6)
        story_lines.extend(
            [
                f"### {index}. {scene}",
                f"- 卡点：{challenge}",
                f"- 引入知识：{teaching_move}",
                f"- 解决方式：{resolution}",
                *( [f"- 相关知识点：{'；'.join(knowledge_points)}"] if knowledge_points else [] ),
                "",
            ]
        )
    if not story_lines:
        story_lines = ["- 暂无完整案例步骤，需补充场景、卡点、知识引入和解决方式。"]

    review_lines: list[str] = []
    for item in review_sources:
        title_text = sanitize_today_user_text(item.get("material_title")) or "未命名资料"
        locator = sanitize_today_user_text(item.get("locator")) or "待补充定位"
        review_focus = sanitize_today_user_text(item.get("review_focus")) or "今日重点"
        review_lines.append(f"- 《{title_text}》｜{locator}｜重点回看：{review_focus}")
    today_review = normalize_string_list(review_suggestions.get("today_review") or [])
    progress_review = normalize_string_list(review_suggestions.get("progress_review") or [])
    if today_review:
        review_lines.append("- 今日复盘：")
        review_lines.extend([f"  - {item}" for item in today_review])
    if progress_review:
        review_lines.append("- 结合当前进度的复习：")
        review_lines.extend([f"  - {item}" for item in progress_review])
    if not review_lines:
        review_lines = ["- 暂无回看资料，需补充材料名、定位和复习重点。"]

    blocks = [
        f"# {title}",
        "",
        "## 今日定位",
        "",
        *[f"- {line}" for line in positioning_lines],
        "",
        "## 课前知识预告",
        "",
        *preview_lines,
        "",
        "## 案例背景",
        "",
        *background_lines,
        "",
        "## 问题",
        "",
        *problem_lines,
        "",
        "## 跟着案例学",
        "",
        *story_lines,
        "## 回看资料",
        "",
        *review_lines,
        "",
    ]
    return "\n".join(blocks).rstrip() + "\n"


__all__ = [
    "build_daily_lesson_plan",
    "build_daily_lesson_prompt",
    "build_lesson_grounding_context",
    "build_lesson_quality_artifact",
    "describe_execution_mode",
    "json_for_prompt",
    "language_policy_prompt_block",
    "normalize_llm_daily_lesson_payload",
    "normalize_llm_mapping",
    "normalize_llm_teaching_points",
    "normalize_llm_text_list",
    "parse_json_from_llm_output",
    "render_daily_lesson_plan_markdown",
]