from __future__ import annotations

import json
import re
from typing import Any

from learn_core.text_utils import normalize_string_list
from learn_runtime.lesson_builder import json_for_prompt, run_claude_json_generation
from learn_runtime.question_banks import (
    build_git_bank,
    make_code_question,
    make_python_metadata,
    make_written_question,
    resolve_target_clusters,
    resolve_target_stages,
)
from learn_runtime.source_grounding import (
    build_content_aware_pitfall,
    clean_source_teaching_terms,
    compact_source_text,
    source_brief_has_substance,
)


def is_valid_runtime_question(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if not str(item.get("id") or "").strip():
        return False
    category = str(item.get("category") or "").strip()
    qtype = str(item.get("type") or "").strip()
    if category == "concept":
        if qtype not in {"single", "multi", "judge"}:
            return False
        if not str(item.get("question") or "").strip():
            return False
        if qtype in {"single", "multi"}:
            options = item.get("options")
            if not isinstance(options, list) or len(options) < 2:
                return False
            if qtype == "single":
                answer = item.get("answer")
                return isinstance(answer, int) and not isinstance(answer, bool) and 0 <= answer < len(options)
            answer = item.get("answer")
            return isinstance(answer, list) and bool(answer) and all(isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(options) for index in answer)
        answer = item.get("answer")
        return isinstance(answer, bool) or str(answer).lower() in {"true", "false", "0", "1"}
    if category == "code":
        if qtype != "function":
            return False
        for key in ["title", "function_name", "starter_code", "test_cases"]:
            if not item.get(key):
                return False
        if not str(item.get("prompt") or item.get("description") or "").strip():
            return False
        test_cases = item.get("test_cases")
        if not isinstance(test_cases, list) or not test_cases:
            return False
        return all(isinstance(case, dict) and ("expected" in case or "expected_code" in case) for case in test_cases)
    if category == "open":
        if qtype != "written":
            return False
        if not str(item.get("question") or "").strip():
            return False
        if not str(item.get("prompt") or item.get("description") or "").strip():
            return False
        reference_points = item.get("reference_points")
        grading_hint = str(item.get("grading_hint") or "").strip()
        has_reference_points = isinstance(reference_points, list) and any(str(point).strip() for point in reference_points)
        return has_reference_points or bool(grading_hint) or bool(str(item.get("explanation") or "").strip())
    return False


def question_text_key(item: dict[str, Any]) -> str:
    text = str(item.get("question") or item.get("prompt") or item.get("title") or "")
    return re.sub(r"\s+", "", text.lower())


def question_focus_keys(item: dict[str, Any]) -> set[str]:
    if str(item.get("category") or "") != "code":
        return set()
    blob = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("prompt") or ""),
            " ".join(str(tag) for tag in item.get("tags") or []),
            " ".join(str(skill) for skill in item.get("subskills") or []),
        ]
    ).lower()
    markers = {
        "read_text": ["read_text", "path.read_text"],
        "write_text": ["write_text", "path.write_text"],
        "json.loads": ["json.loads", "反序列化"],
        "json.dumps": ["json.dumps", "序列化"],
        "csv_split": ["csv", "split", "分隔文本"],
        "try_except": ["try-except", "filenotfounderror", "jsondecodeerror", "异常"],
    }
    return {key for key, needles in markers.items() if any(needle in blob for needle in needles)}


def merge_question_pools(pools: list[list[dict[str, Any]]], *, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    seen_code_focus: set[str] = set()
    for pool in pools:
        for item in pool:
            if not is_valid_runtime_question(item):
                continue
            qid = str(item.get("id") or "")
            text_key = question_text_key(item)
            focus_keys = question_focus_keys(item)
            if qid in seen_ids or (text_key and text_key in seen_texts):
                continue
            if focus_keys and focus_keys.issubset(seen_code_focus):
                continue
            merged.append(item)
            seen_ids.add(qid)
            seen_code_focus.update(focus_keys)
            if text_key:
                seen_texts.add(text_key)
            if len(merged) >= limit:
                return merged
    return merged


def count_content_questions(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if str(item.get("id") or "").startswith("content-"))


def count_llm_lesson_questions(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if str(item.get("id") or "").startswith("llm-lesson-"))


def normalize_llm_answer(value: Any, options: list[str], qtype: str) -> Any:
    if qtype == "judge":
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"true", "1", "yes", "对", "正确", "是"}
    if qtype == "single":
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        text = str(value or "").strip()
        for index, option in enumerate(options):
            if text == str(option).strip():
                return index
        return -1
    if isinstance(value, list):
        answers: list[int] = []
        for item in value:
            if isinstance(item, int) and not isinstance(item, bool):
                answers.append(item)
                continue
            text = str(item or "").strip()
            for index, option in enumerate(options):
                if text == str(option).strip():
                    answers.append(index)
                    break
        return answers
    return []


def question_matches_lesson(item: dict[str, Any], domain: str, lesson_blob: str) -> bool:
    item_blob = " ".join(
        [
            str(item.get("question") or ""),
            str(item.get("explanation") or ""),
            " ".join(str(tag) for tag in item.get("tags") or []),
        ]
    ).lower()
    if domain == "git":
        return any(token in item_blob for token in ["git", "commit", "add", "status", "branch", "分支", "提交", "暂存", "快照", "工作区", "仓库", "版本"])
    keywords = [token for token in re.split(r"[\s,，；;、/()（）\[\]：:。]+", lesson_blob.lower()) if len(token) >= 3]
    if not keywords:
        return True
    return any(keyword in item_blob for keyword in keywords[:40])


def validate_and_normalize_generated_questions(items: Any, domain: str, lesson_blob: str, *, limit: int = 5) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        items = items.get("questions")
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        qtype = str(raw.get("type") or "single").strip()
        if qtype not in {"single", "multi", "judge"}:
            continue
        options = [str(item).strip() for item in raw.get("options") or [] if str(item).strip()]
        if qtype in {"single", "multi"} and len(options) < 2:
            continue
        answer = normalize_llm_answer(raw.get("answer"), options, qtype)
        tags = normalize_string_list(raw.get("tags") or [])
        for tag in [domain, "lesson-derived"]:
            if tag and tag not in tags:
                tags.append(tag)
        item = {
            "id": f"llm-lesson-c{len(normalized) + 1}",
            "category": "concept",
            "type": qtype,
            "difficulty": str(raw.get("difficulty") or "medium"),
            "question": str(raw.get("question") or "").strip(),
            "answer": answer,
            "explanation": str(raw.get("explanation") or "这道题来自今日讲解内容。").strip(),
            "tags": tags,
            "question_role": str(raw.get("question_role") or "learn"),
            "source_trace": raw.get("source_trace") or raw.get("lesson_point_id") or "daily_lesson_plan",
        }
        if qtype in {"single", "multi"}:
            item["options"] = options[:6]
        if not is_valid_runtime_question(item):
            continue
        if not question_matches_lesson(item, domain, lesson_blob):
            continue
        normalized.append(item)
        if len(normalized) >= limit:
            break
    return normalized


def build_lesson_question_prompt(domain: str, grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any], limit: int) -> str:
    return f"""你是一个出题助手。请只根据今日教学计划和 grounding_context 生成练习题。

硬性要求：
1. 只输出 JSON object，格式为：{{"questions": [...]}}。不要输出 JSON 外文字。
2. 每道题必须直接来自今日讲解、复习点或 source_excerpt；不得使用泛化题库凑数。
3. 只生成 concept 题，type 只能是 single、multi、judge。不要生成代码题。
4. single/multi 题必须提供 options 和基于 0 的 answer；judge 题 answer 必须是布尔值。
5. 题目总数不超过 {limit}。
6. 如果 domain 是 Git，只能出 Git 相关题；禁止 HTTP、JSON、日志、测试、部署、数据库等无关题。
7. 每道题添加 tags、question_role、source_trace。

DOMAIN: {domain}

GROUNDING_CONTEXT:
{json_for_prompt(grounding_context, limit=11000)}

DAILY_LESSON_PLAN:
{json_for_prompt(daily_lesson_plan, limit=11000)}
"""


def lesson_question_blob(grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any]) -> str:
    parts = [
        json.dumps(grounding_context, ensure_ascii=False),
        json.dumps(daily_lesson_plan, ensure_ascii=False),
    ]
    return " ".join(parts)


def generate_questions_from_lesson_with_llm(domain: str, grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any], *, limit: int = 5) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prompt = build_lesson_question_prompt(domain, grounding_context, daily_lesson_plan, limit)
    raw_payload, metadata = run_claude_json_generation(prompt)
    questions = validate_and_normalize_generated_questions(raw_payload, domain, lesson_question_blob(grounding_context, daily_lesson_plan), limit=limit)
    if not questions:
        return [], metadata
    return questions, {**metadata, "mode": "llm-lesson-derived", "generated_count": len(questions)}


CONTENT_QUESTION_DISTRACTORS = [
    "只记住术语名称，不解释它解决的问题",
    "跳过资料例子，直接背最终答案",
    "忽略输入、输出和边界条件",
    "把相邻概念混成同一个概念，不区分使用场景",
]



def clean_content_question_text(value: Any, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def unique_content_texts(values: Any, *, limit: int = 8, max_len: int = 100) -> list[str]:
    if isinstance(values, str):
        iterable = [values]
    else:
        iterable = values or []
    result: list[str] = []
    for value in iterable:
        text = clean_content_question_text(value, max_len)
        if not text or text in result:
            continue
        result.append(text)
        if len(result) >= limit:
            break
    return result


def segment_question_label(segment: dict[str, Any]) -> str:
    locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
    bits = [segment.get("material_title")]
    if locator.get("chapter"):
        bits.append(locator.get("chapter"))
    else:
        bits.append(segment.get("label"))
    return clean_content_question_text(" / ".join(str(bit) for bit in bits if bit), 90) or "今日资料"


def segment_question_terms(segment: dict[str, Any]) -> list[str]:
    locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
    raw_terms: list[str] = []
    for values in [
        segment.get("source_key_points") or [],
        locator.get("sections") or [],
        segment.get("checkpoints") or [],
    ]:
        raw_terms.extend(unique_content_texts(values, limit=8, max_len=80))
    return unique_content_texts(clean_source_teaching_terms(raw_terms), limit=8, max_len=80)


def content_question_tags(domain: str, segment: dict[str, Any], terms: list[str]) -> list[str]:
    tags = [domain or "learning", "content-derived"]
    for value in normalize_string_list(segment.get("target_clusters") or []) + terms[:3]:
        text = clean_content_question_text(value, 40)
        if text and text not in tags:
            tags.append(text)
    return tags


def content_python_stage_and_cluster(plan_source: dict[str, Any], segment: dict[str, Any]) -> tuple[str, str]:
    stages = resolve_target_stages(plan_source)
    clusters = normalize_string_list(segment.get("target_clusters") or []) + resolve_target_clusters(plan_source)
    return stages[0] if stages else "stage1", clusters[0] if clusters else "content-derived"


def apply_content_question_metadata(item: dict[str, Any], domain: str, plan_source: dict[str, Any], segment: dict[str, Any], terms: list[str]) -> dict[str, Any]:
    item["source_segment_id"] = segment.get("segment_id")
    item["source_material_title"] = segment.get("material_title")
    item["source_status"] = segment.get("source_status") or "fallback-metadata"
    item["question_role"] = item.get("question_role") or "learn"
    if domain == "python":
        stage, cluster = content_python_stage_and_cluster(plan_source, segment)
        item.update(make_python_metadata(stage, cluster, terms[:3] or [segment.get("label") or "资料理解"], "learn", []))
    else:
        item["family"] = domain or "general"
        clusters = normalize_string_list(segment.get("target_clusters") or [])
        item["cluster"] = clusters[0] if clusters else (clean_content_question_text(segment.get("label"), 60) or "content-derived")
        item["subskills"] = terms[:3]
    return item


def make_content_single_question(qid: str, domain: str, plan_source: dict[str, Any], segment: dict[str, Any], terms: list[str]) -> dict[str, Any] | None:
    if not terms:
        return None
    label = segment_question_label(segment)
    excerpt = compact_source_text(segment.get("source_excerpt") or segment.get("source_summary") or segment.get("purpose") or "", 180)
    term_blob = " ".join(terms).lower()
    if domain == "python" and "read_text" in term_blob and "json.loads" in term_blob:
        question = f"根据今日资料「{label}」的 number_reader / greet_user 示例，为什么通常先调用 Path.read_text()，再调用 json.loads()？"
        options = [
            "read_text() 先读取文件中的 JSON 文本，json.loads() 再把这个字符串还原为 Python 对象",
            "read_text() 会自动把 JSON 文件解析成 Python 对象，json.loads() 只是打印结果",
            "json.loads() 必须接收 Path 对象本身，而不是文件内容字符串",
            "write_text() 会读取文件内容，read_text() 只负责写入字符串",
        ]
        explanation = "资料示例中先用 path.read_text() 得到 JSON 格式字符串，再把 contents 交给 json.loads(contents) 恢复为列表或用户名。"
    elif domain == "python" and "json.dumps" in term_blob and "write_text" in term_blob:
        question = f"根据今日资料「{label}」的 remember_me / number_writer 示例，json.dumps() 与 Path.write_text() 的分工是什么？"
        options = [
            "json.dumps() 把 Python 对象转成 JSON 字符串，Path.write_text() 负责把字符串写入文件",
            "Path.write_text() 负责把 Python 对象转成 JSON，json.dumps() 负责写文件",
            "二者都只用于读取 JSON 文件，不负责保存数据",
            "json.dumps() 只能处理路径字符串，不能处理列表或用户名",
        ]
        explanation = "资料示例先用 json.dumps(username) 或 json.dumps(numbers) 得到可保存的字符串，再用 path.write_text(contents) 写入文件。"
    else:
        correct = terms[0]
        options = unique_content_texts([correct] + CONTENT_QUESTION_DISTRACTORS, limit=4, max_len=90)
        question = f"根据今日资料「{label}」，下面哪一项最应该作为这段内容的理解重点？"
        explanation = f"这道题来自 selected segment 的内容提取。材料关键点包含：{'；'.join(terms[:3])}。{('原文摘要：' + excerpt) if excerpt else ''}"
    if len(options) < 4:
        return None
    item = {
        "id": qid,
        "category": "concept",
        "type": "single",
        "difficulty": "medium",
        "question": question,
        "answer": 0,
        "options": options,
        "explanation": explanation,
        "tags": content_question_tags(domain, segment, terms),
    }
    return apply_content_question_metadata(item, domain, plan_source, segment, terms)


def make_content_multi_question(qid: str, domain: str, plan_source: dict[str, Any], segment: dict[str, Any], terms: list[str]) -> dict[str, Any] | None:
    if len(terms) < 2:
        return None
    options = unique_content_texts(terms[:2] + CONTENT_QUESTION_DISTRACTORS[:2], limit=4, max_len=90)
    if len(options) < 4:
        return None
    label = segment_question_label(segment)
    item = {
        "id": qid,
        "category": "concept",
        "type": "multi",
        "difficulty": "medium",
        "question": f"根据今日资料「{label}」的材料提取结果，哪些项属于这段内容的关键学习点？",
        "answer": [0, 1],
        "options": options,
        "explanation": f"这些关键点直接来自该 segment 的 source_key_points / sections / checkpoints：{'；'.join(terms[:4])}。",
        "tags": content_question_tags(domain, segment, terms),
    }
    return apply_content_question_metadata(item, domain, plan_source, segment, terms)


def make_content_judge_question(qid: str, domain: str, plan_source: dict[str, Any], segment: dict[str, Any], terms: list[str]) -> dict[str, Any] | None:
    if not terms:
        return None
    pitfall = unique_content_texts(segment.get("source_pitfalls") or [], limit=1, max_len=80)
    raw_statement = pitfall[0] if pitfall else ""
    if not raw_statement or "[[PAGE" in raw_statement or len(raw_statement) > 70:
        raw_statement = build_content_aware_pitfall(terms[0], segment)
    statement = clean_content_question_text(raw_statement, 90)
    label = segment_question_label(segment)
    item = {
        "id": qid,
        "category": "concept",
        "type": "judge",
        "difficulty": "easy",
        "question": f"判断：学习今日资料「{label}」中的「{terms[0]}」时，{statement}",
        "answer": True,
        "explanation": f"这是根据该 segment 的常见误区 / 检查点生成的判断题；重点不是背术语，而是结合资料例子说明使用场景和边界。",
        "tags": content_question_tags(domain, segment, terms),
    }
    return apply_content_question_metadata(item, domain, plan_source, segment, terms)


def make_content_written_question(qid: str, domain: str, plan_source: dict[str, Any], segment: dict[str, Any], terms: list[str]) -> dict[str, Any] | None:
    if not terms:
        return None
    label = segment_question_label(segment)
    checkpoints = unique_content_texts(segment.get("checkpoints") or [], limit=3, max_len=80)
    examples = unique_content_texts(segment.get("source_examples") or [], limit=2, max_len=80)
    reference_points = unique_content_texts([*terms[:3], *checkpoints[:2], *examples[:1]], limit=4, max_len=80)
    if not reference_points:
        return None
    excerpt = compact_source_text(segment.get("source_excerpt") or segment.get("source_summary") or segment.get("purpose") or "", 180)
    prompt_lines = [
        f"请用自己的话解释今日资料「{label}」的核心内容。",
        f"回答时尽量覆盖：{'；'.join(reference_points[:3])}。",
    ]
    if examples:
        prompt_lines.append(f"如可以，请结合资料中的例子或场景：{examples[0]}。")
    grading_hint = f"优先判断是否覆盖关键点：{'；'.join(reference_points)}。"
    if excerpt:
        grading_hint += f" 可结合原文摘要检查是否真正理解：{excerpt}"
    item = make_written_question(
        qid,
        "medium",
        f"请解释今日资料「{label}」的核心内容，并说明它在当前主题中的作用。",
        "\n".join(prompt_lines),
        content_question_tags(domain, segment, terms),
        reference_points=reference_points,
        grading_hint=grading_hint,
        question_role="learn",
    )
    return apply_content_question_metadata(item, domain, plan_source, segment, terms)


def build_content_concept_questions_for_segment(domain: str, plan_source: dict[str, Any], segment: dict[str, Any], start_index: int) -> list[dict[str, Any]]:
    terms = segment_question_terms(segment)
    if not terms or not source_brief_has_substance(segment):
        return []
    builders = [make_content_single_question, make_content_multi_question, make_content_judge_question]
    questions: list[dict[str, Any]] = []
    for offset, builder in enumerate(builders):
        item = builder(f"content-c{start_index + offset}", domain, plan_source, segment, terms)
        if item and is_valid_runtime_question(item):
            questions.append(item)
    return questions


def content_segment_blob(segment: dict[str, Any]) -> str:
    locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
    values = [
        segment.get("label"),
        segment.get("purpose"),
        segment.get("source_summary"),
        segment.get("source_excerpt"),
        " ".join(normalize_string_list(segment.get("source_examples") or [])),
        " ".join(normalize_string_list(segment.get("source_key_points") or [])),
        " ".join(normalize_string_list(segment.get("checkpoints") or [])),
        " ".join(normalize_string_list(locator.get("sections") or [])),
    ]
    return " ".join(str(value or "") for value in values).lower()


def build_content_code_questions_for_segment(plan_source: dict[str, Any], segment: dict[str, Any], start_index: int) -> list[dict[str, Any]]:
    blob = content_segment_blob(segment)
    if not source_brief_has_substance(segment):
        return []
    stage, cluster = content_python_stage_and_cluster(plan_source, segment)
    questions: list[dict[str, Any]] = []

    def append_question(item: dict[str, Any]) -> None:
        if len(questions) >= 2:
            return
        if is_valid_runtime_question(item):
            questions.append(item)

    if "read_text" in blob or "path.read_text" in blob:
        index = start_index + len(questions)
        append_question(make_code_question(
            f"content-code{index}", "easy", "读取资料示例中的文本", f"content_read_text_{index}", ["path_str"],
            f"今日资料提到了 Path.read_text()。请实现函数 content_read_text_{index}(path_str)，使用 pathlib.Path(path_str).read_text() 读取并返回文本内容。",
            f"from pathlib import Path\n\ndef content_read_text_{index}(path_str):\n    pass",
            f"from pathlib import Path\n\ndef content_read_text_{index}(path_str):\n    return Path(path_str).read_text()",
            [
                {"input": ["note.txt"], "expected": "hello\n", "files": {"note.txt": "hello\n"}},
                {"input": ["empty.txt"], "expected": "", "files": {"empty.txt": ""}},
            ],
            ["python", "content-derived", "pathlib", "Path.read_text"],
            stage=stage, cluster=cluster, subskills=["pathlib.Path", "read_text", "文本读取"], question_role="learn",
        ))
    if "write_text" in blob or "path.write_text" in blob:
        index = start_index + len(questions)
        append_question(make_code_question(
            f"content-code{index}", "easy", "写入资料示例中的文本", f"content_write_text_{index}", ["path_str", "message"],
            f"今日资料提到了 Path.write_text()。请实现函数 content_write_text_{index}(path_str, message)，把 message 写入 path_str 指向的文件，并返回写入字符数。",
            f"from pathlib import Path\n\ndef content_write_text_{index}(path_str, message):\n    pass",
            f"from pathlib import Path\n\ndef content_write_text_{index}(path_str, message):\n    return Path(path_str).write_text(message)",
            [
                {"input": ["out.txt", "hello"], "expected": 5},
                {"input": ["empty_out.txt", ""], "expected": 0},
            ],
            ["python", "content-derived", "pathlib", "Path.write_text"],
            stage=stage, cluster=cluster, subskills=["pathlib.Path", "write_text", "文本写入"], question_role="learn",
        ))
    if "json.loads" in blob:
        index = start_index + len(questions)
        append_question(make_code_question(
            f"content-code{index}", "medium", "解析资料示例中的 JSON 字符串", f"content_load_json_{index}", ["raw"],
            f"今日资料提到了 json.loads()。请实现函数 content_load_json_{index}(raw)，把 JSON 字符串解析为 Python 对象并返回。",
            f"import json\n\ndef content_load_json_{index}(raw):\n    pass",
            f"import json\n\ndef content_load_json_{index}(raw):\n    return json.loads(raw)",
            [
                {"input": ['{\"name\": \"Ada\"}'], "expected": {"name": "Ada"}},
                {"input": ['[1, 2, 3]'], "expected": [1, 2, 3]},
            ],
            ["python", "content-derived", "json.loads", "JSON"],
            stage=stage, cluster=cluster, subskills=["json.loads", "JSON 反序列化"], question_role="learn",
        ))
    if "json.dumps" in blob:
        index = start_index + len(questions)
        append_question(make_code_question(
            f"content-code{index}", "medium", "序列化资料示例中的 Python 对象", f"content_dump_json_{index}", ["data"],
            f"今日资料提到了 json.dumps()。请实现函数 content_dump_json_{index}(data)，使用 json.dumps(data, ensure_ascii=False) 返回 JSON 字符串。",
            f"import json\n\ndef content_dump_json_{index}(data):\n    pass",
            f"import json\n\ndef content_dump_json_{index}(data):\n    return json.dumps(data, ensure_ascii=False)",
            [
                {"input": [{"theme": "dark"}], "expected": '{"theme": "dark"}'},
                {"input": [{"name": "重庆"}], "expected": '{"name": "重庆"}'},
            ],
            ["python", "content-derived", "json.dumps", "JSON"],
            stage=stage, cluster=cluster, subskills=["json.dumps", "JSON 序列化", "ensure_ascii"], question_role="learn",
        ))
    if "csv" in blob or "split" in blob:
        index = start_index + len(questions)
        append_question(make_code_question(
            f"content-code{index}", "easy", "清洗资料示例中的分隔文本", f"content_split_fields_{index}", ["row"],
            f"今日资料涉及分隔文本/CSV 预处理。请实现函数 content_split_fields_{index}(row)，按逗号切分字符串，并去掉每个字段首尾空白。",
            f"def content_split_fields_{index}(row):\n    pass",
            f"def content_split_fields_{index}(row):\n    return [part.strip() for part in row.split(',')]",
            [
                {"input": ["alice, 18, Chongqing"], "expected": ["alice", "18", "Chongqing"]},
                {"input": [" one , two "], "expected": ["one", "two"]},
            ],
            ["python", "content-derived", "CSV", "split", "strip"],
            stage=stage, cluster=cluster, subskills=["split", "strip", "CSV 预处理"], question_role="bridge",
        ))
    return questions


def make_git_content_questions(plan_source: dict[str, Any], daily_lesson_plan: dict[str, Any]) -> list[dict[str, Any]]:
    text_parts = [
        str(plan_source.get("today_topic") or ""),
        " ".join(normalize_string_list(plan_source.get("review") or [])),
        " ".join(normalize_string_list(plan_source.get("new_learning") or [])),
        " ".join(normalize_string_list(plan_source.get("exercise_focus") or [])),
    ]
    for point in daily_lesson_plan.get("teaching_points") or []:
        if isinstance(point, dict):
            text_parts.extend(str(point.get(key) or "") for key in ["topic", "explanation", "pitfall", "practical_value"])
    blob = " ".join(text_parts).lower()
    selected_ids: list[str] = []
    if any(token in blob for token in ["快照", "snapshot", "commit", "提交"]):
        selected_ids.extend(["git-c1", "git-c3"])
    if any(token in blob for token in ["add", "暂存", "staging"]):
        selected_ids.extend(["git-c2", "git-c3"])
    if any(token in blob for token in ["status", "工作区", "working"]):
        selected_ids.append("git-c5")
    if any(token in blob for token in ["最小", "闭环", "workflow", "流程"]):
        selected_ids.extend(["git-c4", "git-c7"])
    if any(token in blob for token in ["branch", "分支"]):
        selected_ids.append("git-c6")
    git_concept, _ = build_git_bank()
    by_id = {str(item.get("id")): item for item in git_concept}
    ordered = []
    for qid in selected_ids or ["git-c1", "git-c2", "git-c4", "git-c5"]:
        item = by_id.get(qid)
        if item and item not in ordered:
            enriched = dict(item)
            enriched["id"] = f"lesson-{enriched['id']}"
            enriched["question_role"] = "learn"
            enriched["source_trace"] = "daily_lesson_plan"
            ordered.append(enriched)
        if len(ordered) >= 4:
            break
    return ordered


def build_content_driven_questions(domain: str, plan_source: dict[str, Any], selected_segments: list[dict[str, Any]], daily_lesson_plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    concept: list[dict[str, Any]] = []
    code: list[dict[str, Any]] = []
    written: list[dict[str, Any]] = []
    if domain == "git":
        concept.extend(make_git_content_questions(plan_source, daily_lesson_plan))
    source_segment_ids: list[str] = []
    attempted_segments = 0
    for segment in selected_segments:
        if not isinstance(segment, dict):
            continue
        if not source_brief_has_substance(segment) or not segment_question_terms(segment):
            continue
        attempted_segments += 1
        if segment.get("segment_id"):
            source_segment_ids.append(str(segment.get("segment_id")))
        if len(concept) < 4:
            concept.extend(build_content_concept_questions_for_segment(domain, plan_source, segment, len(concept) + 1))
            concept = concept[:4]
        if len(written) < 2:
            item = make_content_written_question(f"content-w{len(written) + 1}", domain, plan_source, segment, segment_question_terms(segment))
            if item and is_valid_runtime_question(item):
                written.append(item)
                written = written[:2]
        if domain == "python" and len(code) < 2:
            code.extend(build_content_code_questions_for_segment(plan_source, segment, len(code) + 1))
            code = code[:2]
        if len(concept) >= 4 and len(written) >= 2 and (domain != "python" or len(code) >= 2):
            break
    context = {
        "selection_policy": "content-derived-first+bank-fallback",
        "lesson_generation_mode": daily_lesson_plan.get("lesson_generation_mode"),
        "attempted_segments": attempted_segments,
        "source_segment_ids": source_segment_ids,
        "generated_concept_count": len(concept),
        "generated_code_count": len(code),
        "generated_written_count": len(written),
    }
    return concept, code, written, context




__all__ = [
    "build_content_driven_questions",
    "make_git_content_questions",
    "build_content_code_questions_for_segment",
    "content_segment_blob",
    "build_content_concept_questions_for_segment",
    "make_content_judge_question",
    "make_content_multi_question",
    "make_content_single_question",
    "make_content_written_question",
    "apply_content_question_metadata",
    "content_python_stage_and_cluster",
    "content_question_tags",
    "segment_question_terms",
    "segment_question_label",
    "unique_content_texts",
    "clean_content_question_text",
    "build_lesson_question_prompt",
    "count_content_questions",
    "count_llm_lesson_questions",
    "generate_questions_from_lesson_with_llm",
    "is_valid_runtime_question",
    "lesson_question_blob",
    "merge_question_pools",
    "normalize_llm_answer",
    "question_focus_keys",
    "question_matches_lesson",
    "question_text_key",
    "validate_and_normalize_generated_questions",
]
