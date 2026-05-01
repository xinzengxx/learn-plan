from __future__ import annotations

import json
import re
from typing import Any

from learn_core.quality_review import normalize_confidence
from learn_core.text_utils import normalize_string_list
from learn_runtime.lesson_builder import (
    json_for_prompt,
    language_policy_prompt_block,
    normalize_today_display_list,
    sanitize_today_user_text,
    shared_style_prompt_block,
)
from learn_runtime.question_banks import (
    build_git_bank,
    make_code_question,
    make_python_metadata,
    make_written_question,
    resolve_target_clusters,
    resolve_target_stages,
)
from learn_runtime.schemas import TEST_GRADE_OBJECTIVE_TYPES, normalize_question_difficulty_fields
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
        if qtype not in TEST_GRADE_OBJECTIVE_TYPES:
            return False
        if not str(item.get("question") or item.get("prompt") or "").strip():
            return False
        options = item.get("options")
        if not isinstance(options, list) or len(options) < 2:
            return False
        if qtype == "single_choice":
            answer = item.get("answer")
            return isinstance(answer, int) and not isinstance(answer, bool) and 0 <= answer < len(options)
        if qtype == "multiple_choice":
            answer = item.get("answers", item.get("answer"))
            return isinstance(answer, list) and bool(answer) and all(isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(options) for index in answer)
        answer = item.get("answer")
        return isinstance(answer, bool) or str(answer).lower() in {"true", "false", "0", "1"}
    if category == "code":
        if qtype == "sql":
            for key in ["title", "problem_statement", "input_spec", "output_spec", "constraints", "examples", "scoring_rubric", "capability_tags"]:
                if not item.get(key):
                    return False
            runtimes = [str(runtime).strip().lower() for runtime in (item.get("supported_runtimes") if isinstance(item.get("supported_runtimes"), list) else [])]
            for variant in item.get("runtime_variants") if isinstance(item.get("runtime_variants"), list) else []:
                if isinstance(variant, dict):
                    runtime = str(variant.get("runtime") or variant.get("name") or "").strip().lower()
                    if runtime and runtime not in runtimes:
                        runtimes.append(runtime)
            default_runtime = str(item.get("default_runtime") or item.get("runtime") or "").strip().lower()
            if default_runtime and default_runtime not in runtimes:
                runtimes.append(default_runtime)
            if "mysql" not in runtimes:
                return False
            if not (item.get("parameter_spec_ref") or item.get("dataset_refs") or item.get("dataset_ref")):
                return False
            if not item.get("result_contract"):
                return False
            return bool(str(item.get("starter_sql") or item.get("starter_code") or "").strip())
        if qtype == "code":
            for key in ["title", "problem_statement", "input_spec", "output_spec", "constraints", "examples", "hidden_tests", "scoring_rubric", "capability_tags", "starter_code"]:
                if not item.get(key):
                    return False
            if not (str(item.get("function_signature") or "").strip() or str(item.get("function_name") or "").strip()):
                return False
            hidden_tests = item.get("hidden_tests")
            return isinstance(hidden_tests, list) and bool(hidden_tests)
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
        return all(
            isinstance(case, dict)
            and any(
                key in case
                for key in ("expected", "expected_code", "expected_records", "expected_rows", "expected_output")
            )
            for case in test_cases
        )
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
    keywords = [token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", lesson_blob.lower()) if len(token) >= 2]
    if not keywords:
        return True
    prioritized_keywords = [token for token in keywords if token not in {"lesson_focus_points", "project_tasks", "project_blockers", "review_targets", "question_role", "source_trace", "primary"}]
    candidate_keywords = prioritized_keywords[:60] or keywords[:60]
    return any(keyword in item_blob for keyword in candidate_keywords)


QUESTION_REVIEW_GENERIC_TOKENS = {
    "general-cs",
    "general cs",
    "tooling",
    "tutorial",
    "reference",
    "today",
    "lesson",
    "review",
    "project",
    "target",
    "targets",
    "focus",
    "points",
    "知识",
    "重点",
    "内容",
    "资料",
    "材料",
    "学习",
    "回看",
    "例子",
    "说明",
    "附近",
    "任务",
    "问题",
    "掌握",
    "理解",
    "复习",
    "建议",
}

QUESTION_REVIEW_CATEGORY_HINTS = {
    "lesson_focus": {"lesson_focus_points", "today_focus", "focus_points", "teaching_points"},
    "project": {"project_tasks", "project_blockers", "project_driven_explanation", "tasks"},
    "review": {"review_targets", "review_suggestions", "today_review", "progress_review", "next_actions"},
}

QUESTION_REVIEW_ROLE_HINTS = {
    "lesson_focus": {"concept-check", "learn", "today_focus", "lesson_focus", "focus_point"},
    "project": {"applied-concept-check", "misconception-check", "bridge", "scenario-check", "task-check", "project_task", "project_blocker"},
    "review": {"review-check", "reflection-check", "recall-check", "applied-concept-check", "review_target", "review"},
}
QUESTION_REVIEWER_NAME = "strict-question-reviewer"
QUESTION_REVIEW_MAX_ATTEMPTS = 3
RUNTIME_PRIMARY_CATEGORIES = {"lesson_focus_points", "project_tasks", "project_blockers", "review_targets"}
TEST_GRADE_QUESTION_PROMPT_BLOCK = """所有题目统一按 test-grade 标准生成和审查，不区分学习题和测试题。
允许的主评分题型只有 code、single_choice、multiple_choice、true_false；禁止 open / written / short_answer / free_text，禁止生成 open / written / short_answer / free_text。
code 题必须是 LeetCode-like 结构，包含 title、problem_statement、input_spec、output_spec、constraints、examples、public_tests、hidden_tests、starter_code、function_signature 或 function_name、scoring_rubric、capability_tags。
code 题的 problem_statement 必须是 Markdown 可读文本：不得一段到底；函数名/参数名/字段名用 `inline code`；关键行为用 **粗体**；多个条件、边界或步骤必须用列表或每条独立成行。
code 题必须保持字段分工：problem_statement 只写任务背景与目标行为；input_spec 写输入形状和类型；output_spec 写输出形状；constraints 写限制和边界规则。禁止把输入、输出、约束、示例全部塞进 problem_statement。
constraints 若包含多条规则，必须使用数组、Markdown bullet 或换行分隔；禁止用分号堆成一行。
examples 必须包含输入、输出和示例解释；public_tests 可展示；hidden_tests 只用于后端提交评测，不能在初始展示 payload 或题干中泄露 hidden tests。
选择/判断题必须包含 title、prompt、options、answer 或 answers、explanation、scoring_rubric、capability_tags；prompt 必须使用 Markdown 排版，避免纯文本一段到底。
严格阻断：缺输入/输出说明、缺约束、缺示例解释、hidden_tests 为空、题干和测试用例不一致、题干排版一段到底、泄露 hidden tests、默认 open/written 主评分题。"""


def infer_primary_category_from_role(question_role: str) -> str:
    role = str(question_role or "").strip().lower()
    if role == "project_task":
        return "project_tasks"
    if role == "project_blocker":
        return "project_blockers"
    if role == "review_target":
        return "review_targets"
    return "lesson_focus_points"


def infer_question_role_from_primary_category(primary_category: str, *, default: str = "learn") -> str:
    category = str(primary_category or "").strip().lower()
    if category == "project_tasks":
        return "project_task"
    if category == "project_blockers":
        return "project_blocker"
    if category == "review_targets":
        return "review_target"
    return default


def resolve_semantic_profile(grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any]) -> str:
    profile = str(daily_lesson_plan.get("semantic_profile") or grounding_context.get("semantic_profile") or "").strip().lower()
    if profile in {"today", "initial-test", "stage-test"}:
        return profile
    assessment_kind = str(daily_lesson_plan.get("assessment_kind") or grounding_context.get("assessment_kind") or "").strip().lower()
    session_type = str(daily_lesson_plan.get("session_type") or grounding_context.get("session_type") or "").strip().lower()
    if assessment_kind == "initial-test":
        return "initial-test"
    if assessment_kind == "stage-test" or session_type == "test":
        return "stage-test"
    return "today"


def build_semantic_trace_snapshot(
    grounding_context: dict[str, Any],
    daily_lesson_plan: dict[str, Any],
    *,
    seed_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    question_scope = grounding_context.get("question_scope") if isinstance(grounding_context.get("question_scope"), dict) else daily_lesson_plan.get("question_scope")
    question_scope = question_scope if isinstance(question_scope, dict) else {}
    question_plan = grounding_context.get("question_plan") if isinstance(grounding_context.get("question_plan"), dict) else daily_lesson_plan.get("question_plan")
    question_plan = question_plan if isinstance(question_plan, dict) else {}
    minimum_pass_shape = (seed_constraints or {}).get("minimum_pass_shape") if isinstance((seed_constraints or {}).get("minimum_pass_shape"), dict) else {}
    if not minimum_pass_shape:
        minimum_pass_shape = question_plan.get("minimum_pass_shape") if isinstance(question_plan.get("minimum_pass_shape"), dict) else {}
    if not minimum_pass_shape:
        minimum_pass_shape = question_scope.get("minimum_pass_shape") if isinstance(question_scope.get("minimum_pass_shape"), dict) else {}
    return {
        "semantic_profile": resolve_semantic_profile(grounding_context, daily_lesson_plan),
        "plan_execution_mode": str(daily_lesson_plan.get("plan_execution_mode") or grounding_context.get("plan_execution_mode") or "").strip(),
        "assessment_kind": str(daily_lesson_plan.get("assessment_kind") or grounding_context.get("assessment_kind") or "").strip(),
        "session_intent": str(daily_lesson_plan.get("session_intent") or grounding_context.get("session_intent") or "").strip(),
        "question_source": str(grounding_context.get("question_source") or daily_lesson_plan.get("question_source") or "").strip(),
        "diagnostic_generation_mode": str(grounding_context.get("diagnostic_generation_mode") or daily_lesson_plan.get("diagnostic_generation_mode") or "").strip(),
        "target_capability_ids": normalize_string_list(question_scope.get("target_capability_ids") or daily_lesson_plan.get("target_capability_ids") or grounding_context.get("target_capability_ids") or [])[:8],
        "question_scope_source_profile": str(question_scope.get("source_profile") or "").strip(),
        "question_plan_id": str(question_plan.get("plan_id") or "").strip(),
        "question_plan_mix": question_plan.get("question_mix") if isinstance(question_plan.get("question_mix"), dict) else {},
        "diagnostic_blueprint_version": str(daily_lesson_plan.get("diagnostic_blueprint_version") or grounding_context.get("diagnostic_blueprint_version") or "").strip(),
        "round_index": daily_lesson_plan.get("round_index") or grounding_context.get("round_index"),
        "max_rounds": daily_lesson_plan.get("max_rounds") or grounding_context.get("max_rounds"),
        "questions_per_round": daily_lesson_plan.get("questions_per_round") or grounding_context.get("questions_per_round"),
        "language_policy": daily_lesson_plan.get("language_policy") or grounding_context.get("language_policy") or {},
        "follow_up_needed": daily_lesson_plan.get("follow_up_needed") if "follow_up_needed" in daily_lesson_plan else grounding_context.get("follow_up_needed"),
        "minimum_pass_shape": {
            "required_primary_categories": normalize_string_list((seed_constraints or {}).get("required_primary_categories") or minimum_pass_shape.get("required_primary_categories") or []),
            "required_capability_coverage": normalize_string_list((seed_constraints or {}).get("required_capability_coverage") or minimum_pass_shape.get("required_capability_coverage") or []),
            "required_open_question_count": max(0, int((seed_constraints or {}).get("required_open_question_count") or minimum_pass_shape.get("required_open_question_count") or 0)),
            "required_code_question_count": max(0, int((seed_constraints or {}).get("required_code_question_count") or minimum_pass_shape.get("required_code_question_count") or 0)),
        },
    }


def normalize_runtime_source_trace(
    raw: dict[str, Any],
    *,
    default_question_source: str,
    default_basis: str,
    default_diagnostic_generation_mode: str = "",
) -> dict[str, Any]:
    source_trace = raw.get("source_trace")
    if isinstance(source_trace, dict):
        trace = dict(source_trace)
    elif source_trace:
        trace = {"basis": str(source_trace).strip()}
    else:
        trace = {}
    primary_category = clean_question_review_target_text(raw.get("primary_category") or trace.get("primary_category") or trace.get("primary"))
    if primary_category:
        normalized_primary_category = primary_category.lower()
        for prefix in RUNTIME_PRIMARY_CATEGORIES:
            if normalized_primary_category == prefix or normalized_primary_category.startswith(prefix + ":"):
                trace["primary_category"] = prefix
                break
    if not trace.get("primary_category"):
        trace["primary_category"] = infer_primary_category_from_role(str(raw.get("question_role") or ""))
    trace["question_source"] = str(trace.get("question_source") or raw.get("question_source") or default_question_source).strip() or default_question_source
    trace["basis"] = str(trace.get("basis") or raw.get("id") or default_basis).strip() or default_basis
    target_capability_ids = normalize_string_list(raw.get("target_capability_ids") or trace.get("target_capability_ids") or [])
    if target_capability_ids:
        trace["target_capability_ids"] = target_capability_ids
    diagnostic_generation_mode = str(trace.get("diagnostic_generation_mode") or raw.get("diagnostic_generation_mode") or default_diagnostic_generation_mode or "").strip()
    if diagnostic_generation_mode:
        trace["diagnostic_generation_mode"] = diagnostic_generation_mode
    return trace


def normalize_generated_runtime_questions(
    items: Any,
    domain: str,
    *,
    limit: int,
    default_question_source: str,
    default_source_status: str,
    default_diagnostic_generation_mode: str = "",
    default_question_role: str = "learn",
) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        items = items.get("questions")
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    category_counts = {"concept": 0, "code": 0, "open": 0}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "concept").strip().lower()
        if category not in {"concept", "code", "open"}:
            continue
        qtype = str(raw.get("type") or ("single" if category == "concept" else "function" if category == "code" else "written")).strip()
        tags = normalize_string_list(raw.get("tags") or [])
        for tag in [domain, "runtime-generated"]:
            if tag and tag not in tags:
                tags.append(tag)
        raw_primary_category = clean_question_review_target_text(raw.get("primary_category") or "")
        fallback_question_role = infer_question_role_from_primary_category(raw_primary_category, default=("review_target" if category == "open" else default_question_role))
        question_role = str(raw.get("question_role") or "").strip() or fallback_question_role
        source_trace = normalize_runtime_source_trace(
            raw,
            default_question_source=default_question_source,
            default_basis=f"llm-runtime-{category}-{category_counts[category] + 1}",
            default_diagnostic_generation_mode=default_diagnostic_generation_mode,
        )
        if not raw.get("question_role"):
            question_role = infer_question_role_from_primary_category(str(source_trace.get("primary_category") or ""), default=question_role)
        item: dict[str, Any]
        if category == "concept":
            if qtype not in {"single", "multi", "judge", "single_choice", "multiple_choice", "true_false"}:
                continue
            options = [str(item).strip() for item in raw.get("options") or [] if str(item).strip()]
            if qtype in {"single", "multi", "single_choice", "multiple_choice"} and len(options) < 2:
                continue
            answer_type = {"single_choice": "single", "multiple_choice": "multi", "true_false": "judge"}.get(qtype, qtype)
            answer = normalize_llm_answer(raw.get("answers", raw.get("answer")), options, answer_type)
            item = {
                "id": str(raw.get("id") or f"llm-runtime-c{category_counts['concept'] + 1}").strip(),
                "category": "concept",
                "type": qtype,
                "difficulty": str(raw.get("difficulty") or "medium"),
                "title": str(raw.get("title") or raw.get("question") or raw.get("prompt") or "概念题").strip(),
                "prompt": str(raw.get("prompt") or raw.get("question") or "").strip(),
                "question": str(raw.get("question") or raw.get("prompt") or "").strip(),
                "answer": answer,
                "explanation": str(raw.get("explanation") or "这道题来自当前 session 的 repair 后重生成。").strip(),
                "tags": tags,
                "question_role": question_role,
                "source_trace": source_trace,
                "source_status": str(raw.get("source_status") or default_source_status).strip() or default_source_status,
            }
            if qtype in {"single", "multi", "single_choice", "multiple_choice", "true_false"}:
                item["options"] = options[:6]
            if qtype == "multiple_choice":
                item["answers"] = answer
            for key in ["scoring_rubric", "capability_tags", "primary_category"]:
                if raw.get(key):
                    item[key] = raw.get(key)
        elif category == "code":
            if qtype in {"code", "sql"}:
                item = dict(raw)
                item["id"] = str(item.get("id") or f"llm-runtime-k{category_counts['code'] + 1}").strip()
                item["category"] = "code"
                item["type"] = qtype
                item["difficulty"] = str(item.get("difficulty") or "medium")
                item["tags"] = tags
                item["question_role"] = question_role
                item["source_trace"] = source_trace
                item["source_status"] = str(item.get("source_status") or default_source_status).strip() or default_source_status
                default_editor_language = "sql" if qtype == "sql" else "python"
                default_language_label = "MySQL" if qtype == "sql" else domain.title()
                item["editor_language"] = str(item.get("editor_language") or default_editor_language).strip() or default_editor_language
                item["language_label"] = str(item.get("language_label") or default_language_label).strip() or default_language_label
                if qtype == "sql":
                    item.setdefault("supported_runtimes", ["mysql"])
                    item.setdefault("default_runtime", "mysql")
            else:
                test_cases = [case for case in (raw.get("test_cases") or []) if isinstance(case, dict)]
                item = {
                    "id": str(raw.get("id") or f"llm-runtime-k{category_counts['code'] + 1}").strip(),
                    "category": "code",
                    "type": "function",
                    "difficulty": str(raw.get("difficulty") or "medium"),
                    "title": str(raw.get("title") or raw.get("question") or raw.get("function_name") or "代码题").strip(),
                    "prompt": str(raw.get("prompt") or raw.get("description") or raw.get("question") or "").strip(),
                    "description": str(raw.get("description") or raw.get("prompt") or raw.get("question") or "").strip(),
                    "explanation": str(raw.get("explanation") or "评分时要同时看：是否写出正确结果、能否解释关键边界，以及结果如何影响下一轮学习入口判断。").strip(),
                    "function_name": str(raw.get("function_name") or "solve").strip(),
                    "params": [str(param).strip() for param in (raw.get("params") or []) if str(param).strip()],
                    "starter_code": str(raw.get("starter_code") or "def solve():\n    pass").rstrip(),
                    "solution_code": str(raw.get("solution_code") or raw.get("expected_code") or "").rstrip(),
                    "test_cases": test_cases,
                    "tags": tags,
                    "question_role": question_role,
                    "source_trace": source_trace,
                    "source_status": str(raw.get("source_status") or default_source_status).strip() or default_source_status,
                    "editor_language": str(raw.get("editor_language") or "python").strip() or "python",
                    "language_label": str(raw.get("language_label") or domain.title()).strip() or domain.title(),
                }
        else:
            item = {
                "id": str(raw.get("id") or f"llm-runtime-o{category_counts['open'] + 1}").strip(),
                "category": "open",
                "type": "written",
                "difficulty": str(raw.get("difficulty") or "medium"),
                "question": str(raw.get("question") or raw.get("title") or "开放题").strip(),
                "prompt": str(raw.get("prompt") or raw.get("description") or raw.get("question") or "").strip(),
                "description": str(raw.get("description") or raw.get("prompt") or raw.get("question") or "").strip(),
                "explanation": str(raw.get("explanation") or raw.get("grading_hint") or "请根据参考点判断是否真正结合当前 session 的证据完成回答。").strip(),
                "tags": tags,
                "question_role": question_role,
                "source_trace": source_trace,
                "source_status": str(raw.get("source_status") or default_source_status).strip() or default_source_status,
            }
            reference_points = normalize_string_list(raw.get("reference_points") or [])
            grading_hint = str(raw.get("grading_hint") or "").strip()
            if reference_points:
                item["reference_points"] = reference_points
            if grading_hint:
                item["grading_hint"] = grading_hint
        item.update(normalize_question_difficulty_fields({**raw, **item}))
        for key in ("difficulty_reason", "expected_failure_mode"):
            if raw.get(key) is not None:
                item[key] = raw.get(key)
        target_capability_ids = normalize_string_list(raw.get("target_capability_ids") or source_trace.get("target_capability_ids") or [])
        if target_capability_ids:
            item["target_capability_ids"] = target_capability_ids
        if not is_valid_runtime_question(item):
            continue
        normalized.append(item)
        category_counts[category] += 1
        if len(normalized) >= limit:
            break
    return normalized


def question_review_blob(item: dict[str, Any]) -> str:
    source_trace = item.get("source_trace")
    trace_text = json.dumps(source_trace, ensure_ascii=False) if isinstance(source_trace, (dict, list)) else str(source_trace or "")
    return " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("question") or item.get("prompt") or ""),
            str(item.get("description") or ""),
            str(item.get("explanation") or ""),
            str(item.get("question_role") or ""),
            str(item.get("category") or ""),
            str(item.get("type") or ""),
            str(item.get("cluster") or ""),
            str(item.get("family") or ""),
            str(item.get("source_material_title") or ""),
            str(item.get("source_status") or ""),
            " ".join(str(tag) for tag in item.get("tags") or []),
            " ".join(str(skill) for skill in item.get("subskills") or []),
            " ".join(str(point) for point in item.get("reference_points") or []),
            trace_text,
        ]
    ).lower()



def clean_question_review_target_text(value: Any) -> str:
    text = sanitize_today_user_text(value)
    if not text:
        return ""
    text = re.sub(r"^如果你对我上面的讲解还有疑惑，再回原资料看.*?，重点盯\s*", "", text)
    text = re.sub(r"^如果你对我上面的讲解还有疑惑，?\s*", "", text)
    text = re.sub(r"^再回原资料看.*?，重点盯\s*", "", text)
    text = re.sub(r"^回原资料看.*?，重点盯\s*", "", text)
    text = re.sub(r"^重点盯\s*", "", text)
    text = re.sub(r"附近的例子和说明[。.]?$", "", text)
    text = re.sub(r"关键概念与实际用途[。.]?$", "", text)
    text = re.sub(r"^解释\s+", "", text)
    text = re.sub(r"^把\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" /：:；;，,、|-。")
    cleaned = clean_source_teaching_terms([text])
    if cleaned:
        text = sanitize_today_user_text(cleaned[0]) or text
    return text.strip()



def normalize_question_review_target_list(values: Any, *, limit: int = 8) -> list[str]:
    if isinstance(values, str):
        raw_values = normalize_today_display_list(values, limit=limit * 3)
    elif isinstance(values, list):
        raw_values = normalize_today_display_list(values, limit=limit * 3)
    else:
        raw_values = []
    normalized: list[str] = []
    for value in raw_values:
        text = clean_question_review_target_text(value)
        if not text or text in normalized:
            continue
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized



def question_review_aliases(text: str) -> list[str]:
    lowered = text.lower()
    aliases: list[str] = []
    if "commit" in lowered or "提交" in text:
        aliases.extend(["commit", "提交", "快照"])
    if "git add" in lowered or "暂存区" in text or "staging" in lowered:
        aliases.extend(["git add", "暂存区"])
    if "branch" in lowered or "分支" in text:
        aliases.extend(["branch", "分支指针"])
    if "status" in lowered or "工作区" in text:
        aliases.extend(["git status", "工作区"])
    if "remote" in lowered or "远程" in text or "push" in lowered:
        aliases.extend(["remote", "远程仓库", "push"])
    if "仓库" in text or "repository" in lowered or "repo" in lowered:
        aliases.extend(["仓库", "repository"])
    if "快照" in text or "snapshot" in lowered:
        aliases.extend(["快照", "snapshot"])
    if "版本控制" in text or "version control" in lowered:
        aliases.extend(["版本控制", "version control"])
    return aliases



def target_keywords(value: Any, *, limit: int = 8, target_kind: str = "lesson_focus") -> list[str]:
    text = clean_question_review_target_text(value).lower()
    if not text:
        return []
    keywords: list[str] = []

    def add_keyword(raw: str) -> None:
        candidate = re.sub(r"\s+", " ", str(raw or "")).strip(" /：:；;，,、|-。")
        if not candidate or candidate in keywords:
            return
        if candidate in QUESTION_REVIEW_GENERIC_TOKENS:
            return
        if len(candidate) < 2:
            return
        if target_kind in {"project", "review"} and len(candidate) < 4 and not re.search(r"[a-z]{4,}", candidate):
            return
        keywords.append(candidate)

    if len(text) <= 48:
        add_keyword(text)
    fragments = [fragment.strip() for fragment in re.split(r"[；;，,。]+", text) if fragment.strip()]
    cleaned_fragments = clean_source_teaching_terms(fragments)
    for fragment in cleaned_fragments[:4] or fragments[:4]:
        lowered_fragment = fragment.lower()
        if len(lowered_fragment) <= 36:
            add_keyword(lowered_fragment)
        for part in re.split(r"\s*/\s*|\s*->\s*|\s*→\s*", lowered_fragment):
            add_keyword(part)
    if target_kind == "lesson_focus":
        for token in re.split(r"[\s,，；;、/()（）\[\]：:。]+", text):
            token = token.strip()
            if len(token) < 2 or token in QUESTION_REVIEW_GENERIC_TOKENS:
                continue
            if token in {"git", "add"}:
                continue
            add_keyword(token)
    for alias in question_review_aliases(text):
        add_keyword(alias.lower())
        if len(keywords) >= limit:
            break
    return keywords[:limit]



def question_primary_category(item: dict[str, Any]) -> str:
    source_trace = item.get("source_trace")
    if isinstance(source_trace, dict):
        for key in ["primary_category", "primary", "category", "target_group"]:
            value = clean_question_review_target_text(source_trace.get(key))
            if value:
                normalized = value.lower()
                for prefix in [
                    "lesson_focus_points:",
                    "project_tasks:",
                    "project_blockers:",
                    "review_targets:",
                    "today_review:",
                    "progress_review:",
                    "next_actions:",
                ]:
                    if normalized.startswith(prefix):
                        return prefix.rstrip(":")
                return normalized
    text = clean_question_review_target_text(source_trace)
    return text.lower()



def question_matches_target_category(item: dict[str, Any], target_kind: str) -> bool:
    primary_category = question_primary_category(item)
    if not primary_category:
        return False
    return primary_category in QUESTION_REVIEW_CATEGORY_HINTS[target_kind]



def question_role_matches_target(item: dict[str, Any], target_kind: str) -> bool:
    role = str(item.get("question_role") or "").strip().lower()
    return role in QUESTION_REVIEW_ROLE_HINTS[target_kind]



def question_has_strong_target_text_match(item: dict[str, Any], targets: list[str], *, target_kind: str) -> bool:
    if not targets:
        return False
    blob = question_review_blob(item)
    for target in targets:
        keywords = target_keywords(target, target_kind=target_kind, limit=10)
        if not keywords:
            continue
        matched = [keyword for keyword in keywords if keyword and keyword in blob]
        if not matched:
            continue
        if target_kind == "lesson_focus":
            return True
        if len(matched) >= 2:
            return True
        if any((" " in keyword and len(keyword) >= 4) or (re.search(r"[\u4e00-\u9fff]", keyword) and len(keyword) >= 4) for keyword in matched):
            return True
    return False



def question_target_match_mode(item: dict[str, Any], targets: list[str], *, target_kind: str) -> str | None:
    if not targets:
        return None
    if question_matches_target_category(item, target_kind):
        return "category"
    lexical_match = question_has_strong_target_text_match(item, targets, target_kind=target_kind)
    if target_kind == "lesson_focus":
        return "lexical" if lexical_match else None
    if lexical_match and question_role_matches_target(item, target_kind):
        return "role"
    return None



def question_matches_any_target(item: dict[str, Any], targets: list[str], *, target_kind: str = "lesson_focus") -> bool:
    return question_target_match_mode(item, targets, target_kind=target_kind) is not None



def extract_question_review_targets(grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any]) -> dict[str, list[str]]:
    today_focus = daily_lesson_plan.get("today_focus") if isinstance(daily_lesson_plan.get("today_focus"), dict) else {}
    focus_points = [item for item in (today_focus.get("focus_points") or []) if isinstance(item, dict)]
    project_driven_explanation = daily_lesson_plan.get("project_driven_explanation") if isinstance(daily_lesson_plan.get("project_driven_explanation"), dict) else {}
    project_tasks_payload = [item for item in (project_driven_explanation.get("tasks") or []) if isinstance(item, dict)]
    review_suggestions = daily_lesson_plan.get("review_suggestions") if isinstance(daily_lesson_plan.get("review_suggestions"), dict) else {}
    teaching_brief = grounding_context.get("today_teaching_brief") if isinstance(grounding_context.get("today_teaching_brief"), dict) else {}

    lesson_focus_candidates = [
        *(daily_lesson_plan.get("lesson_focus_points") or []),
        *(teaching_brief.get("lesson_focus_points") or []),
        *[item.get("point") for item in focus_points],
    ]
    project_task_candidates = [
        *(daily_lesson_plan.get("project_tasks") or []),
        *(teaching_brief.get("project_tasks") or []),
        *[item.get("task_name") for item in project_tasks_payload],
    ]
    project_blocker_candidates = [
        *(daily_lesson_plan.get("project_blockers") or []),
        *(teaching_brief.get("project_blockers") or []),
        *[item.get("blocker") for item in project_tasks_payload],
    ]
    review_candidates = [
        *(daily_lesson_plan.get("review_targets") or []),
        *(teaching_brief.get("review_targets") or []),
        *(review_suggestions.get("today_review") or []),
        *(review_suggestions.get("progress_review") or []),
        *(review_suggestions.get("next_actions") or []),
        *[item.get("mastery_check") for item in focus_points],
    ]
    return {
        "lesson_focus_points": normalize_today_display_list(lesson_focus_candidates, limit=8),
        "project_tasks": normalize_today_display_list(project_task_candidates, limit=8),
        "project_blockers": normalize_today_display_list(project_blocker_candidates, limit=6),
        "review_targets": normalize_question_review_target_list(review_candidates, limit=8),
    }



def question_capability_ids(item: dict[str, Any]) -> list[str]:
    capability_ids = normalize_string_list(item.get("target_capability_ids") or [])
    source_trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
    capability_ids.extend(normalize_string_list(source_trace.get("target_capability_ids") or []))
    blob = question_review_blob(item)
    cluster = str(item.get("cluster") or "").strip().lower()
    tags = {str(tag).strip().lower() for tag in item.get("tags") or [] if str(tag).strip()}
    heuristics = {
        "python-core-coding": [
            "python-core-coding",
            "core-coding",
            "functions-foundations",
            "dedupe",
            "列表",
            "字典",
            "集合",
            "复杂度",
        ],
        "python-data-processing": [
            "python-data-processing",
            "data-processing",
            "pandas",
            "numpy",
            "groupby",
            "筛选",
            "聚合",
            "缺失值",
        ],
        "python-llm-script": [
            "python-llm-script",
            "llm-script",
            "script",
            "api",
            "pathlib",
            "json",
            "异常处理",
            "files-pathlib-json-exceptions",
        ],
    }
    for capability_id, markers in heuristics.items():
        if capability_id in capability_ids:
            continue
        if capability_id in tags:
            capability_ids.append(capability_id)
            continue
        if any(marker == cluster or marker in blob for marker in markers):
            capability_ids.append(capability_id)
    return normalize_string_list(capability_ids)



def collect_question_repair_context(questions: list[dict[str, Any]], grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any]) -> dict[str, Any]:
    targets = extract_question_review_targets(grounding_context, daily_lesson_plan)
    lesson_focus_points = targets["lesson_focus_points"]
    project_targets = normalize_question_review_target_list(targets["project_tasks"] + targets["project_blockers"], limit=10)
    review_targets = targets["review_targets"]
    focus_match_modes = [question_target_match_mode(item, lesson_focus_points, target_kind="lesson_focus") for item in questions]
    project_match_modes = [question_target_match_mode(item, project_targets, target_kind="project") for item in questions]
    review_match_modes = [question_target_match_mode(item, review_targets, target_kind="review") for item in questions]
    capability_targets = normalize_string_list(
        daily_lesson_plan.get("target_capability_ids")
        or grounding_context.get("target_capability_ids")
        or ((grounding_context.get("today_teaching_brief") or {}).get("target_capability_ids") if isinstance(grounding_context.get("today_teaching_brief"), dict) else [])
        or []
    )
    capability_hits: dict[str, int] = {capability_id: 0 for capability_id in capability_targets}
    for item in questions:
        for capability_id in question_capability_ids(item):
            if capability_id in capability_hits:
                capability_hits[capability_id] += 1
    primary_categories = [question_primary_category(item) for item in questions]
    category_counts: dict[str, int] = {}
    for item in questions:
        category = str(item.get("category") or "unknown").strip().lower() or "unknown"
        category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "targets": targets,
        "project_targets": project_targets,
        "review_targets": review_targets,
        "focus_match_modes": focus_match_modes,
        "project_match_modes": project_match_modes,
        "review_match_modes": review_match_modes,
        "focus_hits": sum(1 for mode in focus_match_modes if mode),
        "project_hits": sum(1 for mode in project_match_modes if mode),
        "review_hits": sum(1 for mode in review_match_modes if mode),
        "project_explicit_hits": sum(1 for mode in project_match_modes if mode in {"category", "role"}),
        "review_explicit_hits": sum(1 for mode in review_match_modes if mode in {"category", "role"}),
        "fallback_like": sum(1 for item in questions if "fallback" in question_review_blob(item) or "domain-bank" in question_review_blob(item)),
        "capability_targets": capability_targets,
        "capability_hits": capability_hits,
        "primary_categories": primary_categories,
        "category_counts": category_counts,
    }



def normalize_question_repair_plan(raw_plan: Any, fallback_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback_plan = fallback_plan or {}
    source = raw_plan if isinstance(raw_plan, dict) else {}
    fallback_minimum_pass_shape = fallback_plan.get("minimum_pass_shape") if isinstance(fallback_plan.get("minimum_pass_shape"), dict) else {}
    minimum_pass_shape_source = source.get("minimum_pass_shape") if isinstance(source.get("minimum_pass_shape"), dict) else {}
    minimum_pass_shape = {
        "required_primary_categories": normalize_string_list(minimum_pass_shape_source.get("required_primary_categories") or fallback_minimum_pass_shape.get("required_primary_categories") or []),
        "required_capability_coverage": normalize_string_list(minimum_pass_shape_source.get("required_capability_coverage") or fallback_minimum_pass_shape.get("required_capability_coverage") or []),
        "required_open_question_count": max(0, int(minimum_pass_shape_source.get("required_open_question_count") or fallback_minimum_pass_shape.get("required_open_question_count") or 0)),
        "required_code_question_count": max(0, int(minimum_pass_shape_source.get("required_code_question_count") or fallback_minimum_pass_shape.get("required_code_question_count") or 0)),
        "forbidden_patterns": normalize_string_list(minimum_pass_shape_source.get("forbidden_patterns") or fallback_minimum_pass_shape.get("forbidden_patterns") or []),
    }
    normalized_actions: list[dict[str, Any]] = []
    raw_actions = source.get("repair_actions") if isinstance(source.get("repair_actions"), list) else fallback_plan.get("repair_actions") or []
    for action in raw_actions:
        if not isinstance(action, dict):
            continue
        normalized_actions.append(
            {
                "action": str(action.get("action") or "").strip(),
                "target_kind": str(action.get("target_kind") or "").strip(),
                "target_ref": str(action.get("target_ref") or "").strip(),
                "min_count": max(0, int(action.get("min_count") or 0)),
                "reason": str(action.get("reason") or "").strip(),
            }
        )
    normalized_actions = [action for action in normalized_actions if action["action"] and action["target_kind"] and action["target_ref"]]
    coverage_source = source.get("coverage_gaps") if isinstance(source.get("coverage_gaps"), dict) else fallback_plan.get("coverage_gaps") or {}
    capability_source = source.get("capability_gaps") if isinstance(source.get("capability_gaps"), dict) else fallback_plan.get("capability_gaps") or {}
    result = {
        "version": str(source.get("version") or fallback_plan.get("version") or "question-review-repair.v1").strip(),
        "blocking": bool(source.get("blocking", fallback_plan.get("blocking", False))),
        "failure_codes": normalize_string_list(source.get("failure_codes") or fallback_plan.get("failure_codes") or []),
        "coverage_gaps": {
            "lesson_focus": bool(coverage_source.get("lesson_focus")),
            "project": bool(coverage_source.get("project")),
            "review": bool(coverage_source.get("review")),
            "explicit_project": bool(coverage_source.get("explicit_project")),
            "explicit_review": bool(coverage_source.get("explicit_review")),
            "missing_primary_categories": normalize_string_list(coverage_source.get("missing_primary_categories") or []),
        },
        "capability_gaps": {
            "missing": normalize_string_list(capability_source.get("missing") or []),
            "weak": normalize_string_list(capability_source.get("weak") or []),
        },
        "evidence_gaps": normalize_string_list(source.get("evidence_gaps") or fallback_plan.get("evidence_gaps") or []),
        "repair_actions": normalized_actions,
        "minimum_pass_shape": minimum_pass_shape,
        "notes": normalize_string_list(source.get("notes") or fallback_plan.get("notes") or []),
    }
    result["blocking"] = bool(result["blocking"] or result["failure_codes"] or result["coverage_gaps"]["missing_primary_categories"] or result["capability_gaps"]["missing"])
    return result



def build_default_question_repair_plan(
    questions: list[dict[str, Any]],
    domain: str,
    grounding_context: dict[str, Any],
    daily_lesson_plan: dict[str, Any],
    *,
    issues: list[str],
    warnings: list[str],
    suggestions: list[str],
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution_mode = str(daily_lesson_plan.get("plan_execution_mode") or grounding_context.get("plan_execution_mode") or "normal")
    context = collect_question_repair_context(questions, grounding_context, daily_lesson_plan)
    coverage = coverage or {}
    lesson_focus_points = context["targets"]["lesson_focus_points"]
    project_targets = context["project_targets"]
    review_targets = context["review_targets"]
    required_primary_categories: list[str] = []
    if lesson_focus_points:
        required_primary_categories.append("lesson_focus_points")
    if project_targets:
        required_primary_categories.append("project_tasks")
    if review_targets:
        required_primary_categories.append("review_targets")
    if execution_mode in {"diagnostic", "test-diagnostic"} and context["targets"]["project_blockers"]:
        required_primary_categories.append("project_blockers")
    required_primary_categories = normalize_string_list(required_primary_categories)
    missing_primary_categories = [
        category
        for category in required_primary_categories
        if category not in context["primary_categories"]
    ]
    required_open_question_count = 1 if execution_mode in {"diagnostic", "test-diagnostic"} and domain == "python" else 0
    required_code_question_count = 2 if execution_mode in {"diagnostic", "test-diagnostic"} and domain == "python" else 0
    category_counts = context["category_counts"]
    capability_targets = context["capability_targets"]
    capability_hits = context["capability_hits"]
    capability_missing = [capability_id for capability_id in capability_targets if capability_hits.get(capability_id, 0) <= 0]
    capability_weak = [capability_id for capability_id in capability_targets if capability_hits.get(capability_id, 0) == 1]
    evidence_gaps: list[str] = []
    if any(not isinstance(item.get("source_trace"), (dict, str)) or not item.get("source_trace") for item in questions):
        evidence_gaps.append("source-trace-missing")
    if any(not question_primary_category(item) for item in questions):
        evidence_gaps.append("primary-category-missing")
    if required_open_question_count > 0 and category_counts.get("open", 0) < required_open_question_count:
        evidence_gaps.append("open-question-missing")
    forbidden_patterns = ["generic-bank-question", "process-only-without-python-evidence"] if execution_mode in {"diagnostic", "test-diagnostic"} and domain == "python" else ["generic-bank-question"]
    if context["fallback_like"] >= max(1, len(questions)) and questions:
        forbidden_patterns.append("fallback-heavy")
    repair_actions: list[dict[str, Any]] = []
    coverage_gaps = {
        "lesson_focus": bool(lesson_focus_points and (coverage.get("lesson_focus_hits", context["focus_hits"]) or 0) <= 0),
        "project": bool(project_targets and (coverage.get("project_hits", context["project_hits"]) or 0) <= 0),
        "review": bool(review_targets and (coverage.get("review_hits", context["review_hits"]) or 0) <= 0),
        "explicit_project": bool(project_targets and (coverage.get("project_explicit_hits", context["project_explicit_hits"]) or 0) <= 0),
        "explicit_review": bool(review_targets and (coverage.get("review_explicit_hits", context["review_explicit_hits"]) or 0) <= 0),
        "missing_primary_categories": missing_primary_categories,
    }
    for category in missing_primary_categories:
        repair_actions.append({
            "action": "ensure-primary-category",
            "target_kind": "primary_category",
            "target_ref": category,
            "min_count": 1,
            "reason": "minimum-pass-shape",
        })
    for capability_id in capability_missing:
        repair_actions.append({
            "action": "ensure-capability-coverage",
            "target_kind": "capability_id",
            "target_ref": capability_id,
            "min_count": 1,
            "reason": "missing-capability",
        })
    if category_counts.get("open", 0) < required_open_question_count:
        repair_actions.append({
            "action": "add-question",
            "target_kind": "category",
            "target_ref": "open",
            "min_count": required_open_question_count,
            "reason": "diagnostic-evidence",
        })
    if category_counts.get("code", 0) < required_code_question_count:
        repair_actions.append({
            "action": "add-question",
            "target_kind": "category",
            "target_ref": "code",
            "min_count": required_code_question_count,
            "reason": "diagnostic-signal",
        })
    if context["fallback_like"] and questions:
        repair_actions.append({
            "action": "drop-pattern",
            "target_kind": "pattern",
            "target_ref": "fallback-heavy",
            "min_count": context["fallback_like"],
            "reason": "weak-grounding",
        })
    return normalize_question_repair_plan(
        {
            "version": "question-review-repair.v1",
            "blocking": bool(issues),
            "failure_codes": normalize_string_list([*issues, *warnings]),
            "coverage_gaps": coverage_gaps,
            "capability_gaps": {
                "missing": capability_missing,
                "weak": capability_weak if not capability_missing else capability_weak[:1],
            },
            "evidence_gaps": evidence_gaps,
            "repair_actions": repair_actions,
            "minimum_pass_shape": {
                "required_primary_categories": required_primary_categories,
                "required_capability_coverage": capability_targets,
                "required_open_question_count": required_open_question_count,
                "required_code_question_count": required_code_question_count,
                "forbidden_patterns": forbidden_patterns,
            },
            "notes": normalize_string_list(suggestions)[:8],
        }
    )



def merge_question_repair_plans(*plans: dict[str, Any]) -> dict[str, Any]:
    normalized_plans = [normalize_question_repair_plan(plan) for plan in plans if isinstance(plan, dict) and plan]
    merged_actions: list[dict[str, Any]] = []
    for plan in normalized_plans:
        for action in plan.get("repair_actions") or []:
            if action not in merged_actions:
                merged_actions.append(action)
    merged = {
        "version": "question-review-repair.v1",
        "blocking": any(bool(plan.get("blocking")) for plan in normalized_plans),
        "failure_codes": normalize_string_list([code for plan in normalized_plans for code in normalize_string_list(plan.get("failure_codes") or [])]),
        "coverage_gaps": {
            "lesson_focus": any(bool((plan.get("coverage_gaps") or {}).get("lesson_focus")) for plan in normalized_plans),
            "project": any(bool((plan.get("coverage_gaps") or {}).get("project")) for plan in normalized_plans),
            "review": any(bool((plan.get("coverage_gaps") or {}).get("review")) for plan in normalized_plans),
            "explicit_project": any(bool((plan.get("coverage_gaps") or {}).get("explicit_project")) for plan in normalized_plans),
            "explicit_review": any(bool((plan.get("coverage_gaps") or {}).get("explicit_review")) for plan in normalized_plans),
            "missing_primary_categories": normalize_string_list([item for plan in normalized_plans for item in normalize_string_list(((plan.get("coverage_gaps") or {}).get("missing_primary_categories") or []))]),
        },
        "capability_gaps": {
            "missing": normalize_string_list([item for plan in normalized_plans for item in normalize_string_list(((plan.get("capability_gaps") or {}).get("missing") or []))]),
            "weak": normalize_string_list([item for plan in normalized_plans for item in normalize_string_list(((plan.get("capability_gaps") or {}).get("weak") or []))]),
        },
        "evidence_gaps": normalize_string_list([item for plan in normalized_plans for item in normalize_string_list(plan.get("evidence_gaps") or [])]),
        "repair_actions": merged_actions,
        "minimum_pass_shape": {
            "required_primary_categories": normalize_string_list([item for plan in normalized_plans for item in normalize_string_list(((plan.get("minimum_pass_shape") or {}).get("required_primary_categories") or []))]),
            "required_capability_coverage": normalize_string_list([item for plan in normalized_plans for item in normalize_string_list(((plan.get("minimum_pass_shape") or {}).get("required_capability_coverage") or []))]),
            "required_open_question_count": max([int(((plan.get("minimum_pass_shape") or {}).get("required_open_question_count") or 0)) for plan in normalized_plans] or [0]),
            "required_code_question_count": max([int(((plan.get("minimum_pass_shape") or {}).get("required_code_question_count") or 0)) for plan in normalized_plans] or [0]),
            "forbidden_patterns": normalize_string_list([item for plan in normalized_plans for item in normalize_string_list(((plan.get("minimum_pass_shape") or {}).get("forbidden_patterns") or []))]),
        },
        "notes": normalize_string_list([item for plan in normalized_plans for item in normalize_string_list(plan.get("notes") or [])]),
    }
    return normalize_question_repair_plan(merged)



def build_question_review(questions: list[dict[str, Any]], domain: str, grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any]) -> dict[str, Any]:
    semantic_profile = resolve_semantic_profile(grounding_context, daily_lesson_plan)
    execution_mode = str(daily_lesson_plan.get("plan_execution_mode") or grounding_context.get("plan_execution_mode") or "normal")
    context = collect_question_repair_context(questions, grounding_context, daily_lesson_plan)
    targets = context["targets"]
    lesson_focus_points = targets["lesson_focus_points"]
    project_targets = context["project_targets"]
    review_targets = context["review_targets"]
    issues: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    fluff_markers = ["你可以考虑", "建议如下", "下面给出建议", "建议结构"]

    semantic_trace = build_semantic_trace_snapshot(
        grounding_context,
        daily_lesson_plan,
        seed_constraints=context.get("seed_constraints") if isinstance(context, dict) else None,
    )
    minimum_pass_shape = semantic_trace.get("minimum_pass_shape") if isinstance(semantic_trace.get("minimum_pass_shape"), dict) else {}
    required_primary_categories = normalize_string_list(minimum_pass_shape.get("required_primary_categories") or [])
    required_capability_coverage = normalize_string_list(minimum_pass_shape.get("required_capability_coverage") or [])
    required_open_question_count = max(0, int(minimum_pass_shape.get("required_open_question_count") or 0))
    required_code_question_count = max(0, int(minimum_pass_shape.get("required_code_question_count") or 0))

    if not questions:
        empty_issue_map = {
            "today": "today-questions.empty",
            "initial-test": "initial-test-questions.empty",
            "stage-test": "stage-test-questions.empty",
        }
        empty_suggestion_map = {
            "today": "先生成与今日讲解绑定的题目，再决定是否进入网页练习页。",
            "initial-test": "先生成能服务 initial-test 起点评估的题组，再进入网页测试页。",
            "stage-test": "先生成围绕已学范围与弱项的阶段性测试题组，再进入网页测试页。",
        }
        repair_plan = build_default_question_repair_plan(
            [],
            domain,
            grounding_context,
            daily_lesson_plan,
            issues=[empty_issue_map.get(semantic_profile, "today-questions.empty")],
            warnings=[],
            suggestions=[empty_suggestion_map.get(semantic_profile, "先生成题目。")],
            coverage={
                "lesson_focus_hits": 0,
                "project_hits": 0,
                "review_hits": 0,
                "project_explicit_hits": 0,
                "review_explicit_hits": 0,
                "question_count": 0,
                "primary_category_hits": {},
                "capability_hits": {},
                "open_question_count": 0,
                "code_question_count": 0,
            },
        )
        return {
            "reviewer": f"{semantic_profile}-question-reviewer",
            "valid": False,
            "issues": [empty_issue_map.get(semantic_profile, "today-questions.empty")],
            "warnings": [],
            "suggestions": [empty_suggestion_map.get(semantic_profile, "先生成题目。")],
            "confidence": 0.28,
            "evidence_adequacy": "partial",
            "verdict": "needs-revision",
            "repair_plan": repair_plan,
            "semantic_trace": semantic_trace,
        }

    focus_hits = context["focus_hits"]
    project_hits = context["project_hits"]
    review_hits = context["review_hits"]
    project_explicit_hits = context["project_explicit_hits"]
    review_explicit_hits = context["review_explicit_hits"]
    fallback_like = context["fallback_like"]

    primary_category_hits: dict[str, int] = {}
    capability_hits: dict[str, int] = {}
    open_question_count = 0
    code_question_count = 0
    for item in questions:
        primary_category = str(question_primary_category(item) or "").strip()
        if primary_category:
            primary_category_hits[primary_category] = primary_category_hits.get(primary_category, 0) + 1
        for capability_id in question_capability_ids(item):
            capability_hits[capability_id] = capability_hits.get(capability_id, 0) + 1
        category = str(item.get("category") or "").strip()
        if category == "open":
            open_question_count += 1
        elif category == "code":
            code_question_count += 1

    advisory_strict = execution_mode in {"normal", "prestudy"}
    question_count = len(questions)
    require_focus_coverage = advisory_strict and question_count >= 1
    require_project_coverage = advisory_strict and question_count >= 2
    require_review_coverage = advisory_strict and question_count >= 3
    require_explicit_project_review = advisory_strict and question_count >= 3

    if semantic_profile == "today":
        if lesson_focus_points and focus_hits <= 0 and require_focus_coverage:
            issues.append("today-questions.focus-coverage-missing")
            suggestions.append("至少覆盖今日重点知识，避免题目和讲解主线脱钩。")
        elif lesson_focus_points and focus_hits < min(len(lesson_focus_points), max(1, len(questions) // 2)):
            warnings.append("today-questions.focus-coverage-thin")
            suggestions.append("提高题目对 today_focus 的覆盖比例，不要只覆盖边缘点。")

        if project_targets and project_hits <= 0 and require_project_coverage:
            issues.append("today-questions.project-coverage-missing")
            suggestions.append("至少让一部分题目回到今日任务背景或任务 blocker，而不是只考抽象定义。")
        elif project_targets and project_hits < max(1, min(len(project_targets), len(questions) // 3)):
            warnings.append("today-questions.project-coverage-thin")
            suggestions.append("补充围绕任务场景和卡点的题目，强化项目驱动一致性。")
        elif project_targets and project_explicit_hits <= 0:
            warnings.append("today-questions.project-coverage-only-lexical")
            suggestions.append("至少加入直接 anchored 在 project task/blocker 的题目，不要只靠概念词碰撞命中。")

        if review_targets and review_hits <= 0 and require_review_coverage:
            issues.append("today-questions.review-target-coverage-missing")
            suggestions.append("让题目显式覆盖建议复习里的回顾点，而不是只覆盖新知识。")
        elif review_targets and review_hits < max(1, min(len(review_targets), len(questions) // 3)):
            warnings.append("today-questions.review-target-coverage-thin")
            suggestions.append("增加对 review targets 的回顾题，保证 today 与后续复习闭环。")
        elif review_targets and review_explicit_hits <= 0:
            warnings.append("today-questions.review-coverage-only-lexical")
            suggestions.append("至少加入直接 anchored 在 review targets 的题目，不要只靠领域词碰撞命中。")

        if require_explicit_project_review and (project_targets or review_targets) and (project_explicit_hits + review_explicit_hits) <= 0:
            issues.append("today-questions.explicit-project-review-coverage-missing")
            suggestions.append("至少让一部分题目明确对应 project/review targets，例如带 primary_category 或清晰的 task/review role。")

        if advisory_strict and fallback_like == len(questions) and (lesson_focus_points or review_targets or project_targets):
            warnings.append("today-questions.fallback-heavy")
            suggestions.append("当前题目几乎全部依赖 fallback 题库，建议提高 lesson/content-derived 题目的占比。")

        if project_targets and not any(str(question_primary_category(item) or "") in {"project_tasks", "project_blockers"} for item in questions):
            warnings.append("today-questions.project-primary-missing")
            suggestions.append("至少为部分题目标注 project_tasks/project_blockers 的 primary_category，减少弱对齐。")
        if review_targets and not any(str(question_primary_category(item) or "") == "review_targets" for item in questions):
            warnings.append("today-questions.review-primary-missing")
            suggestions.append("至少为部分题目标注 review_targets 的 primary_category，确保复习闭环是显式的。")

    else:
        if not semantic_trace.get("assessment_kind"):
            issues.append(f"{semantic_profile}-questions.assessment-kind-missing")
            suggestions.append("保留 assessment_kind，避免 reviewer 和 regenerate 丢失当前测试语义。")
        if semantic_trace.get("session_intent") != "assessment":
            issues.append(f"{semantic_profile}-questions.session-intent-invalid")
            suggestions.append("测试型 session 的 session_intent 必须是 assessment。")
        if not semantic_trace.get("target_capability_ids"):
            issues.append(f"{semantic_profile}-questions.target-capability-ids-missing")
            suggestions.append("明确写入 target_capability_ids，避免题组退化成泛化题。")
        if semantic_profile == "initial-test" and not semantic_trace.get("diagnostic_generation_mode"):
            warnings.append("initial-test-questions.diagnostic-generation-mode-missing")
            suggestions.append("保留 diagnostic_generation_mode，便于后续追溯 initial diagnostic 的生成来源。")

        missing_primary = [category for category in required_primary_categories if primary_category_hits.get(category, 0) <= 0]
        if missing_primary:
            issues.append(f"{semantic_profile}-questions.required-primary-categories-missing")
            suggestions.append("补齐 minimum_pass_shape 要求的 primary_category，而不是只靠 tags 命中。")

        missing_capabilities = [capability for capability in required_capability_coverage if capability_hits.get(capability, 0) <= 0]
        if missing_capabilities:
            issues.append(f"{semantic_profile}-questions.required-capability-coverage-missing")
            suggestions.append("题目必须真实覆盖目标 capability，而不是只在 metadata 里挂标签。")

        if open_question_count < required_open_question_count:
            issues.append(f"{semantic_profile}-questions.required-open-question-count-missing")
            suggestions.append("补齐 open 题数量，用来验证解释、判断或分流能力。")
        if code_question_count < required_code_question_count:
            issues.append(f"{semantic_profile}-questions.required-code-question-count-missing")
            suggestions.append("补齐 code 题数量，用来验证可执行的实现与边界处理能力。")

        if semantic_profile == "initial-test":
            if lesson_focus_points and focus_hits <= 0:
                warnings.append("initial-test-questions.lesson-focus-coverage-thin")
                suggestions.append("若 blueprint 提供了 lesson_focus_points，可轻量对齐，但不要把 today-style grounding 当硬门槛。")
            if fallback_like == len(questions) and required_capability_coverage:
                warnings.append("initial-test-questions.fallback-heavy")
                suggestions.append("initial-test 应尽量绑定 diagnostic blueprint 与 capability 约束，减少纯 fallback 题。")
        elif semantic_profile == "stage-test":
            if review_targets and review_hits <= 0:
                warnings.append("stage-test-questions.review-target-coverage-thin")
                suggestions.append("阶段测试应显式覆盖近期弱项或 review debt，避免退化成泛化起点题。")
            if project_targets and project_hits <= 0:
                warnings.append("stage-test-questions.project-coverage-thin")
                suggestions.append("阶段测试可回扣已学任务场景，但不应只有抽象定义题。")

    explanation_texts = [str(item.get("explanation") or "").strip() for item in questions]
    if any(any(marker in text for marker in fluff_markers) for text in explanation_texts if text):
        warnings.append(f"{semantic_profile}-questions.fluff-explanation-detected")
        suggestions.append("题解不要写建议式套话，直接解释当前题为什么有判定价值、与当前 session 目标怎么对应。")

    valid = not issues
    confidence = 0.84 if not issues and not warnings else (0.7 if not issues else 0.44)
    coverage = {
        "lesson_focus_hits": focus_hits,
        "project_hits": project_hits,
        "review_hits": review_hits,
        "project_explicit_hits": project_explicit_hits,
        "review_explicit_hits": review_explicit_hits,
        "question_count": len(questions),
        "primary_category_hits": primary_category_hits,
        "capability_hits": capability_hits,
        "open_question_count": open_question_count,
        "code_question_count": code_question_count,
    }
    repair_plan = build_default_question_repair_plan(
        questions,
        domain,
        grounding_context,
        daily_lesson_plan,
        issues=issues,
        warnings=warnings,
        suggestions=suggestions,
        coverage=coverage,
    )
    return {
        "reviewer": f"{semantic_profile}-question-reviewer",
        "valid": valid,
        "issues": issues,
        "warnings": warnings,
        "suggestions": normalize_string_list(suggestions),
        "confidence": confidence,
        "evidence_adequacy": "sufficient" if not issues else "partial",
        "verdict": "ready" if valid else "needs-revision",
        "coverage": coverage,
        "repair_plan": repair_plan,
        "semantic_trace": semantic_trace,
    }


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


def build_compact_runtime_session_context(
    grounding_context: dict[str, Any],
    daily_lesson_plan: dict[str, Any],
    *,
    include_plan_details: bool = False,
) -> dict[str, Any]:
    review_targets = extract_question_review_targets(grounding_context, daily_lesson_plan)
    teaching_brief = grounding_context.get("today_teaching_brief") if isinstance(grounding_context.get("today_teaching_brief"), dict) else {}
    material_alignment = daily_lesson_plan.get("material_alignment") if isinstance(daily_lesson_plan.get("material_alignment"), dict) else {}
    semantic_profile = resolve_semantic_profile(grounding_context, daily_lesson_plan)
    if semantic_profile == "initial-test":
        compact_alignment_targets = {
            "lesson_focus_points": normalize_today_display_list(review_targets.get("lesson_focus_points") or [], limit=2),
            "project_tasks": normalize_today_display_list(review_targets.get("project_tasks") or [], limit=2),
            "project_blockers": normalize_today_display_list(review_targets.get("project_blockers") or [], limit=2),
            "review_targets": normalize_today_display_list(review_targets.get("review_targets") or [], limit=4),
        }
    elif semantic_profile == "stage-test":
        compact_alignment_targets = {
            "lesson_focus_points": normalize_today_display_list(review_targets.get("lesson_focus_points") or [], limit=3),
            "project_tasks": normalize_today_display_list(review_targets.get("project_tasks") or [], limit=2),
            "project_blockers": normalize_today_display_list(review_targets.get("project_blockers") or [], limit=2),
            "review_targets": normalize_today_display_list(review_targets.get("review_targets") or [], limit=4),
        }
    else:
        compact_alignment_targets = review_targets
    context = {
        "semantic_profile": semantic_profile,
        "plan_execution_mode": daily_lesson_plan.get("plan_execution_mode") or grounding_context.get("plan_execution_mode"),
        "question_source": grounding_context.get("question_source") or daily_lesson_plan.get("question_source"),
        "diagnostic_generation_mode": grounding_context.get("diagnostic_generation_mode") or daily_lesson_plan.get("diagnostic_generation_mode"),
        "assessment_kind": daily_lesson_plan.get("assessment_kind") or grounding_context.get("assessment_kind"),
        "session_intent": daily_lesson_plan.get("session_intent") or grounding_context.get("session_intent"),
        "target_capability_ids": normalize_string_list(
            daily_lesson_plan.get("target_capability_ids")
            or grounding_context.get("target_capability_ids")
            or teaching_brief.get("target_capability_ids")
            or []
        )[:8],
        "diagnostic_blueprint_version": daily_lesson_plan.get("diagnostic_blueprint_version") or grounding_context.get("diagnostic_blueprint_version"),
        "round_index": daily_lesson_plan.get("round_index") or grounding_context.get("round_index"),
        "max_rounds": daily_lesson_plan.get("max_rounds") or grounding_context.get("max_rounds"),
        "questions_per_round": daily_lesson_plan.get("questions_per_round") or grounding_context.get("questions_per_round"),
        "language_policy": daily_lesson_plan.get("language_policy") or grounding_context.get("language_policy") or {},
        "follow_up_needed": daily_lesson_plan.get("follow_up_needed") if "follow_up_needed" in daily_lesson_plan else grounding_context.get("follow_up_needed"),
        "stop_reason": daily_lesson_plan.get("stop_reason") or grounding_context.get("stop_reason"),
        "alignment_targets": compact_alignment_targets,
        "material_alignment": {
            "status": material_alignment.get("status"),
            "selected_segment_count": len(material_alignment.get("selected_segment_ids") or []),
            "selection_mode": material_alignment.get("selection_mode"),
            "target_capability_ids": normalize_string_list(material_alignment.get("target_capability_ids") or [])[:6],
        },
    }
    if include_plan_details:
        context["completion_criteria"] = normalize_today_display_list(daily_lesson_plan.get("completion_criteria") or [], limit=6)
        context["practice_bridge"] = normalize_today_display_list(daily_lesson_plan.get("practice_bridge") or [], limit=4)
        context["teaching_points"] = normalize_today_display_list(
            [item.get("topic") for item in (daily_lesson_plan.get("teaching_points") or []) if isinstance(item, dict)],
            limit=6,
        )
    return context


def compact_seed_constraints_for_prompt(seed_constraints: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(seed_constraints, dict):
        return {}
    minimum_pass_shape = seed_constraints.get("minimum_pass_shape") if isinstance(seed_constraints.get("minimum_pass_shape"), dict) else {}
    selection_context = seed_constraints.get("selection_context") if isinstance(seed_constraints.get("selection_context"), dict) else {}
    return {
        "required_primary_categories": normalize_string_list(seed_constraints.get("required_primary_categories") or minimum_pass_shape.get("required_primary_categories") or [])[:4],
        "required_capability_coverage": normalize_string_list(seed_constraints.get("required_capability_coverage") or minimum_pass_shape.get("required_capability_coverage") or [])[:6],
        "required_code_question_count": max(0, int(seed_constraints.get("required_code_question_count") or minimum_pass_shape.get("required_code_question_count") or 0)),
        "forbidden_patterns": normalize_string_list(seed_constraints.get("forbidden_patterns") or minimum_pass_shape.get("forbidden_patterns") or [])[:6],
        "repair_actions": [item for item in (seed_constraints.get("repair_actions") or []) if isinstance(item, dict)][:6],
        "selection_context": {
            "selection_policy": selection_context.get("selection_policy"),
            "target_stages": normalize_string_list(selection_context.get("target_stages") or [])[:4],
            "target_clusters": normalize_string_list(selection_context.get("target_clusters") or [])[:6],
            "resolved_target_clusters": normalize_string_list(selection_context.get("resolved_target_clusters") or [])[:6],
            "concept_pool_policy": selection_context.get("concept_pool_policy"),
            "code_pool_policy": selection_context.get("code_pool_policy"),
        },
    }


def build_lesson_question_prompt(domain: str, grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any], limit: int) -> str:
    compact_context = build_compact_runtime_session_context(
        grounding_context,
        daily_lesson_plan,
        include_plan_details=True,
    )
    language_policy = compact_context.get("language_policy") if isinstance(compact_context.get("language_policy"), dict) else {}
    return f"""你是一个出题助手。请只根据今日教学计划和 grounding_context 生成练习题。

{language_policy_prompt_block(language_policy)}

{shared_style_prompt_block(audience='today 题目与题解')}

硬性要求：
1. 只输出 JSON object，格式为：{{"questions": [...]}}。不要输出 JSON 外文字。
2. 每道题必须直接来自今日讲解、review targets、项目任务/卡点或 selected segments；不得使用泛化题库凑数。
3. 只生成 concept 题，type 只能是 single、multi、judge。不要生成代码题。
4. single/multi 题必须提供 options 和基于 0 的 answer；judge 题 answer 必须是布尔值。
5. 题目总数不超过 {limit}。
6. 至少覆盖以下三类输入中的大部分：
   - today_focus / lesson_focus_points
   - project_tasks / project_blockers
   - review_targets
7. 如果题目数 >= 4，至少明确生成：
   - 1 题 primary 对应 lesson_focus_points
   - 1 题 primary 对应 project_tasks 或 project_blockers
   - 1 题 primary 对应 review_targets
8. 每道题添加 tags、question_role、source_trace；source_trace 要能看出它主要对应哪一类 today 内容，primary 只能是 lesson_focus_points / project_tasks / project_blockers / review_targets 之一。
9. 如果 domain 是 Git，只能出 Git 相关题；禁止 HTTP、JSON、日志、测试、部署、数据库等无关题。
10. 不要直接泄露答案，不要把解释写成题干的一部分。

COMPACT_SESSION_CONTEXT:
{json_for_prompt(compact_context, limit=4200)}

DOMAIN: {domain}
"""


def build_runtime_question_prompt(
    domain: str,
    grounding_context: dict[str, Any],
    daily_lesson_plan: dict[str, Any],
    *,
    limit: int,
    question_mix: dict[str, int] | None = None,
    seed_questions: list[dict[str, Any]] | None = None,
    seed_constraints: dict[str, Any] | None = None,
) -> str:
    normalized_mix = {
        "concept": max(0, int((question_mix or {}).get("concept") or 0)),
        "code": max(0, int((question_mix or {}).get("code") or 0)),
        "open": max(0, int((question_mix or {}).get("open") or 0)),
    }
    compact_context = build_compact_runtime_session_context(
        grounding_context,
        daily_lesson_plan,
        include_plan_details=False,
    )
    semantic_profile = resolve_semantic_profile(grounding_context, daily_lesson_plan)
    normalized_constraints = compact_seed_constraints_for_prompt(seed_constraints)
    language_policy = compact_context.get("language_policy") if isinstance(compact_context.get("language_policy"), dict) else {}
    compact_seed_questions: list[dict[str, Any]] = []
    if semantic_profile == "initial-test":
        required_code_count = max(0, int(normalized_constraints.get("required_code_question_count") or 0))
        seed_question_limit = max(
            min(limit, 12),
            normalized_mix.get("code", 0) + 3,
            required_code_count + 3,
        )
        seed_question_text_limit = 120
    else:
        seed_question_limit = 6
        seed_question_text_limit = 120
    for item in seed_questions or []:
        if not isinstance(item, dict):
            continue
        compact_seed_questions.append(
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "type": item.get("type"),
                "question": compact_source_text(str(item.get("question") or item.get("prompt") or item.get("description") or ""), seed_question_text_limit),
                "question_role": item.get("question_role"),
                "primary_category": question_primary_category(item),
                "target_capability_ids": question_capability_ids(item)[:3],
                "cluster": item.get("cluster"),
            }
        )
        if len(compact_seed_questions) >= seed_question_limit:
            break
    normalized_constraints = compact_seed_constraints_for_prompt(seed_constraints)
    if semantic_profile == "initial-test":
        initial_test_context = {
            "assessment_kind": compact_context.get("assessment_kind"),
            "session_intent": compact_context.get("session_intent"),
            "semantic_profile": compact_context.get("semantic_profile"),
            "target_capability_ids": normalize_string_list(compact_context.get("target_capability_ids") or [])[:6],
            "questions_per_round": compact_context.get("questions_per_round"),
            "round_index": compact_context.get("round_index"),
            "max_rounds": compact_context.get("max_rounds"),
        }
        initial_test_constraints = {
            "required_primary_categories": normalize_string_list(normalized_constraints.get("required_primary_categories") or [])[:4],
            "required_capability_coverage": normalize_string_list(normalized_constraints.get("required_capability_coverage") or [])[:6],
            "required_code_question_count": max(0, int(normalized_constraints.get("required_code_question_count") or 0)),
        }
        initial_test_seed_questions = [
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "type": item.get("type"),
                "question_role": item.get("question_role"),
                "primary_category": item.get("primary_category"),
                "target_capability_ids": normalize_string_list(item.get("target_capability_ids") or [])[:3],
            }
            for item in compact_seed_questions[:8]
        ]
        return f"""你是 Python initial diagnostic 出题助手。任务：为当前 initial-test 生成 {limit} 道题，用于判断起点和后续入口。只输出 JSON object：{{"questions": [...]}}。

{language_policy_prompt_block(language_policy)}

{TEST_GRADE_QUESTION_PROMPT_BLOCK}

输出要求：
1. questions 数量应参考 QUESTION_MIX，但必须忽略其中的 open 需求。
2. 必须满足 TARGETS 与 CONSTRAINTS。
3. 每题都必须有 question_role、source_trace.primary_category，并使用 capability_tags 记录能力标签。
4. 题目必须服务 initial-test，不要写 today 教学话术，不要输出泛化题库题。

DOMAIN:
{domain}

TARGETS:
{json_for_prompt(initial_test_context, limit=1200)}

CONSTRAINTS:
{json_for_prompt(initial_test_constraints, limit=800)}

SEED_QUESTIONS:
{json_for_prompt(initial_test_seed_questions, limit=1000)}
"""
    if semantic_profile == "stage-test":
        return f"""你是一个阶段性测试出题助手。请根据当前已学范围、弱项与 review debt 生成题目，并在需要时参考 seed questions，但不要机械照抄。

{language_policy_prompt_block(language_policy)}

{shared_style_prompt_block(audience='stage-test 题目与题解')}

硬性要求：
{TEST_GRADE_QUESTION_PROMPT_BLOCK}
1. 只输出 JSON object，格式为：{{"questions": [...]}}。不要输出 JSON 外文字。
2. 每道题必须服务阶段验收：优先覆盖已学范围、近期弱项、review_targets，不要退化成 initial diagnostic，也不要写成 today 教学题。
3. 题型配比参考 QUESTION_MIX，但必须忽略其中的 open 需求。
4. 每道题都必须包含 question_role、source_trace、capability_tags；source_trace.primary_category 只能是 lesson_focus_points / project_tasks / project_blockers / review_targets 之一。
5. 若 seed questions 有用，可以改写后复用其能力目标，但不要保留模板化措辞。
6. 如果 domain 是 Python，优先检验是否真正掌握实现、边界、证据归纳和已学知识迁移，而不是只考流程术语。
7. 如果 domain 是 Git，只能出 Git 相关题；禁止漂移到无关主题。

DOMAIN:
{domain}

COMPACT_SESSION_CONTEXT:
{json_for_prompt(compact_context, limit=3400)}

QUESTION_MIX:
{json_for_prompt(normalized_mix, limit=300)}

SEED_CONSTRAINTS:
{json_for_prompt(normalized_constraints, limit=2200)}

SEED_QUESTIONS:
{json_for_prompt(compact_seed_questions, limit=2600)}
"""
    return f"""你是一个运行时出题助手。请根据当前 today session 的目标生成题目，并在需要时参考 seed questions，但不要机械照抄。

{language_policy_prompt_block(language_policy)}

{shared_style_prompt_block(audience='today 题目与题解')}

硬性要求：
{TEST_GRADE_QUESTION_PROMPT_BLOCK}
1. 只输出 JSON object，格式为：{{"questions": [...]}}。不要输出 JSON 外文字。
2. 每道题必须绑定当前 session 的 lesson_focus_points / project_tasks(project_blockers) / review_targets / target_capability_ids；不得用泛化题库题凑数。
3. 题目总数不超过 {limit}，并参考 QUESTION_MIX，但必须忽略其中的 open 需求。
4. 每道题都必须包含 question_role、source_trace、capability_tags；source_trace.primary_category 只能是 lesson_focus_points / project_tasks / project_blockers / review_targets 之一。
6. 若 seed questions 有用，可以改写后复用其能力目标，但不要保留模板化“判断能否进入某路线”式措辞。
7. 如果 domain 是 Python，优先让题目真实测能力：代码题看实现与边界，open 题看证据归纳，concept 题看解释与判断；不要只考流程话术。
8. 如果 domain 是 Git，只能出 Git 相关题；禁止漂移到无关主题。
9. 不要直接泄露答案，不要把解释写成题干的一部分。

DOMAIN:
{domain}

COMPACT_SESSION_CONTEXT:
{json_for_prompt(compact_context, limit=3200)}

QUESTION_MIX:
{json_for_prompt(normalized_mix, limit=300)}

SEED_CONSTRAINTS:
{json_for_prompt(normalized_constraints, limit=2200)}

SEED_QUESTIONS:
{json_for_prompt(compact_seed_questions, limit=2800)}
"""


def lesson_question_blob(grounding_context: dict[str, Any], daily_lesson_plan: dict[str, Any]) -> str:
    parts = [
        json.dumps(grounding_context, ensure_ascii=False),
        json.dumps(daily_lesson_plan, ensure_ascii=False),
    ]
    return " ".join(parts)


def build_question_regeneration_feedback_block(
    issues: list[str],
    suggestions: list[str],
    repair_plan: dict[str, Any] | None = None,
) -> str:
    normalized_issues = normalize_string_list(issues)[:12]
    normalized_suggestions = normalize_string_list(suggestions)[:12]
    normalized_repair_plan = normalize_question_repair_plan(repair_plan)
    if not normalized_issues and not normalized_suggestions and not normalized_repair_plan.get("blocking"):
        return ""
    minimum_pass_shape = normalized_repair_plan.get("minimum_pass_shape") if isinstance(normalized_repair_plan.get("minimum_pass_shape"), dict) else {}
    return f"""

上一轮审题未通过，请根据以下反馈重生成，并优先修复这些问题：
- issues: {json_for_prompt(normalized_issues, limit=3000)}
- suggestions: {json_for_prompt(normalized_suggestions, limit=3000)}
- repair_plan: {json_for_prompt(normalized_repair_plan, limit=5000)}

重生成要求：
- 不要重复上一轮的泛化题或弱对齐题。
- 优先补足 lesson_focus / project_tasks(project_blockers) / review_targets 的显式覆盖。
- 必须满足 minimum_pass_shape，尤其是 required_primary_categories / required_capability_coverage / required_open_question_count / required_code_question_count。
- 对 repair_actions 中的每个 action 都要给出可验证的对应题，不要只在解释里声称已覆盖。
- 若 forbidden_patterns 出现 {json_for_prompt(normalize_string_list(minimum_pass_shape.get('forbidden_patterns') or []), limit=1200)} 中任一模式，直接重写相关题目。
- 若无法满足约束，宁可少生成，也不要拿无关题凑数。
"""


def build_question_reviewer_prompt(
    domain: str,
    grounding_context: dict[str, Any],
    daily_lesson_plan: dict[str, Any],
    questions: list[dict[str, Any]],
    deterministic_review: dict[str, Any],
) -> str:
    review_targets = extract_question_review_targets(grounding_context, daily_lesson_plan)
    material_alignment = daily_lesson_plan.get("material_alignment") if isinstance(daily_lesson_plan.get("material_alignment"), dict) else {}
    teaching_brief = grounding_context.get("today_teaching_brief") if isinstance(grounding_context.get("today_teaching_brief"), dict) else {}
    semantic_profile = resolve_semantic_profile(grounding_context, daily_lesson_plan)
    question_scope = grounding_context.get("question_scope") if isinstance(grounding_context.get("question_scope"), dict) else daily_lesson_plan.get("question_scope")
    question_scope = question_scope if isinstance(question_scope, dict) else {}
    question_plan = grounding_context.get("question_plan") if isinstance(grounding_context.get("question_plan"), dict) else daily_lesson_plan.get("question_plan")
    question_plan = question_plan if isinstance(question_plan, dict) else {}
    compact_context = {
        "semantic_profile": semantic_profile,
        "plan_execution_mode": daily_lesson_plan.get("plan_execution_mode") or grounding_context.get("plan_execution_mode"),
        "question_source": grounding_context.get("question_source") or daily_lesson_plan.get("question_source"),
        "diagnostic_generation_mode": grounding_context.get("diagnostic_generation_mode") or daily_lesson_plan.get("diagnostic_generation_mode"),
        "assessment_kind": daily_lesson_plan.get("assessment_kind") or grounding_context.get("assessment_kind"),
        "session_intent": daily_lesson_plan.get("session_intent") or grounding_context.get("session_intent"),
        "target_capability_ids": normalize_string_list(
            daily_lesson_plan.get("target_capability_ids")
            or grounding_context.get("target_capability_ids")
            or teaching_brief.get("target_capability_ids")
            or []
        ),
        "diagnostic_blueprint_version": daily_lesson_plan.get("diagnostic_blueprint_version") or grounding_context.get("diagnostic_blueprint_version"),
        "round_index": daily_lesson_plan.get("round_index") or grounding_context.get("round_index"),
        "max_rounds": daily_lesson_plan.get("max_rounds") or grounding_context.get("max_rounds"),
        "questions_per_round": daily_lesson_plan.get("questions_per_round") or grounding_context.get("questions_per_round"),
        "language_policy": daily_lesson_plan.get("language_policy") or grounding_context.get("language_policy") or {},
        "material_alignment": {
            "status": material_alignment.get("status"),
            "selected_segment_count": len(material_alignment.get("selected_segment_ids") or []),
            "selection_mode": material_alignment.get("selection_mode"),
            "target_capability_ids": normalize_string_list(material_alignment.get("target_capability_ids") or []),
        },
        "alignment_targets": review_targets,
        "question_scope": {
            "scope_id": question_scope.get("scope_id"),
            "source_profile": question_scope.get("source_profile"),
            "target_capability_ids": normalize_string_list(question_scope.get("target_capability_ids") or [])[:8],
            "target_concepts": normalize_string_list(question_scope.get("target_concepts") or [])[:8],
            "review_targets": normalize_string_list(question_scope.get("review_targets") or [])[:8],
            "exclusions": normalize_string_list(question_scope.get("exclusions") or [])[:8],
        },
        "question_plan": {
            "plan_id": question_plan.get("plan_id"),
            "question_count": question_plan.get("question_count"),
            "question_mix": question_plan.get("question_mix") if isinstance(question_plan.get("question_mix"), dict) else {},
            "difficulty_distribution": question_plan.get("difficulty_distribution") if isinstance(question_plan.get("difficulty_distribution"), dict) else {},
            "forbidden_question_types": normalize_string_list(question_plan.get("forbidden_question_types") or [])[:8],
            "planned_item_count": len(question_plan.get("planned_items") or []) if isinstance(question_plan.get("planned_items"), list) else 0,
        },
        "completion_criteria": normalize_today_display_list(daily_lesson_plan.get("completion_criteria") or [], limit=6),
        "practice_bridge": normalize_today_display_list(daily_lesson_plan.get("practice_bridge") or [], limit=4),
    }
    language_policy = compact_context.get("language_policy") if isinstance(compact_context.get("language_policy"), dict) else {}
    compact_deterministic_review = {
        "valid": bool(deterministic_review.get("valid")),
        "issues": normalize_string_list(deterministic_review.get("issues") or [])[:5],
        "warnings": normalize_string_list(deterministic_review.get("warnings") or [])[:5],
        "coverage": deterministic_review.get("coverage") if isinstance(deterministic_review.get("coverage"), dict) else {},
        "repair_plan": normalize_question_repair_plan(deterministic_review.get("repair_plan")),
    }
    compact_questions: list[dict[str, Any]] = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        source_trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
        compact_questions.append(
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "type": item.get("type"),
                "title": item.get("title"),
                "question": compact_source_text(str(item.get("question") or item.get("prompt") or item.get("description") or item.get("problem_statement") or ""), 420),
                "problem_statement": compact_source_text(str(item.get("problem_statement") or ""), 700),
                "input_spec": compact_source_text(str(item.get("input_spec") or ""), 300),
                "output_spec": compact_source_text(str(item.get("output_spec") or ""), 300),
                "constraints": compact_source_text(json_for_prompt(item.get("constraints") or "", limit=900), 450),
                "examples": [
                    {
                        "input": example.get("input"),
                        "output": example.get("output"),
                        "has_explanation": bool(str(example.get("explanation") or "").strip()),
                    }
                    for example in (item.get("examples") or [])[:3]
                    if isinstance(example, dict)
                ],
                "starter_code_preview": compact_source_text(str(item.get("starter_code") or item.get("function_signature") or ""), 500),
                "explanation": compact_source_text(str(item.get("explanation") or item.get("grading_hint") or ""), 220),
                "question_role": item.get("question_role"),
                "primary_category": question_primary_category(item),
                "options": [str(option).strip() for option in (item.get("options") or [])[:6]],
                "answer": item.get("answer"),
                "tags": normalize_string_list(item.get("tags") or [])[:8],
                "subskills": normalize_string_list(item.get("subskills") or [])[:6],
                "cluster": item.get("cluster"),
                "stage": item.get("stage"),
                "source_status": item.get("source_status"),
                "source_trace": {
                    "basis": source_trace.get("basis"),
                    "primary_category": source_trace.get("primary_category"),
                    "question_source": source_trace.get("question_source"),
                    "diagnostic_generation_mode": source_trace.get("diagnostic_generation_mode"),
                    "target_capability_ids": normalize_string_list(source_trace.get("target_capability_ids") or [])[:6],
                },
                "capability_ids": question_capability_ids(item),
                "test_case_count": len(item.get("test_cases") or []) if isinstance(item.get("test_cases"), list) else 0,
                "reference_points": normalize_string_list(item.get("reference_points") or [])[:8],
            }
        )
    review_focus = {
        "today": "1. 题目是否真正绑定当前 today 的 lesson / project / review targets，而不是泛化题库题。\n2. 覆盖是否合理：是否至少显式覆盖 lesson_focus_points、project_tasks/project_blockers、review_targets 中的重要部分。\n3. 题目质量是否可靠：题干清晰、答案可判定、解释不空泛、source_trace/question_role/tags 合理；code 题必须检查 problem_statement/input_spec/output_spec/constraints 是否可读，若题干一段到底或 constraints 用分号堆成一行，必须判 needs-revision。\n4. 若 domain 是 Git，只能围绕 Git；若是 Python，也不能漂移到当前学习主线无关主题。\n5. 如果 deterministic review 已经指出严重问题，只有在题目内容本身足以反驳这些问题时才可判通过。",
        "initial-test": "1. 题组是否真正服务 initial-test：用于判断当前起点与后续入口，而不是 today 教学或泛化题库题。\n2. 是否真正覆盖 question_scope.target_capability_ids，并形成可判定的 code/objective/concept 证据，而不是只贴 capability 标签。\n3. 是否符合 question_plan：题型、题量、难度分布、能力覆盖和 forbidden_question_types 都必须对齐。\n4. 是否显式覆盖 scope_basis、review_targets、project_tasks/project_blockers，并让这些类别服务诊断而非教学闭环。\n5. 题目质量是否可靠：题干清晰、答案可判定、解释不空泛、source_trace/question_role/tags 合理。\n6. initial-test 没有已选材料时，不要因为 material_alignment.status=missing 就单独判失败；只有当题目既缺材料绑定、又缺当前阶段/能力/诊断 blocker 绑定时，才可作为证据不足。\n7. 如果 deterministic review 已经指出 minimum_pass_shape / capability / evidence 的严重缺口，只有在题目内容本身足以反驳这些问题时才可判通过。",
        "stage-test": "1. 题组是否真正服务阶段性测试：用于验证已学范围、近期弱项与 review debt，而不是退化成 initial-test 或 today 教学题。\n2. 覆盖是否合理：是否围绕已学内容与 review targets 做稳定度校验，而不是只检查抽象定义。\n3. 题目质量是否可靠：题干清晰、答案可判定、解释不空泛、source_trace/question_role/tags 合理；code 题必须检查 problem_statement/input_spec/output_spec/constraints 是否可读，若题干一段到底或 constraints 用分号堆成一行，必须判 needs-revision。\n4. 若 domain 是 Git，只能围绕 Git；若是 Python，也不能漂移到当前阶段性测评无关主题。\n5. 如果 deterministic review 已经指出严重问题，只有在题目内容本身足以反驳这些问题时才可判通过。",
    }
    return f"""你是一个非常严格的审题 reviewer。请审查这组题目是否真的可以用于当前 {semantic_profile} session。

{language_policy_prompt_block(language_policy)}

{shared_style_prompt_block(audience='题目审查结论')}

审查重点：
{TEST_GRADE_QUESTION_PROMPT_BLOCK}
{review_focus.get(semantic_profile, review_focus['today'])}
6. 所有 session 都必须额外检查 question_scope 与 question_plan：题目数量、题型 mix、难度分布、能力覆盖、来源依据和 forbidden_question_types 是否与计划一致；若不一致，必须判 needs-revision。

输出 JSON object，字段必须包含：
- valid: boolean
- issues: string[]
- warnings: string[]
- suggestions: string[]
- confidence: 0~1 数字
- evidence: string[]
- verdict: "ready" 或 "needs-revision"
- repair_plan: object，至少包含：
  - coverage_gaps: {{lesson_focus:boolean, project:boolean, review:boolean, explicit_project:boolean, explicit_review:boolean, missing_primary_categories:string[]}}
  - capability_gaps: {{missing:string[], weak:string[]}}
  - evidence_gaps: string[]
  - repair_actions: [{{action, target_kind, target_ref, min_count, reason}}]
  - minimum_pass_shape: {{required_primary_categories:string[], required_capability_coverage:string[], required_open_question_count:number, required_code_question_count:number, forbidden_patterns:string[]}}
如果题组已经可用，也必须返回 repair_plan，但各类 gaps 可为空。

DOMAIN:
{domain}

COMPACT_SESSION_CONTEXT:
{json_for_prompt(compact_context, limit=5200)}

DETERMINISTIC_REVIEW:
{json_for_prompt(compact_deterministic_review, limit=4500)}

QUESTIONS:
{json_for_prompt(compact_questions, limit=11000)}
"""


def normalize_strict_question_review(raw_review: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    source = raw_review if isinstance(raw_review, dict) else {}
    issues = normalize_string_list(source.get("issues") or source.get("semantic_issues") or [])
    warnings = normalize_string_list(source.get("warnings") or [])
    suggestions = normalize_string_list(source.get("suggestions") or source.get("improvement_suggestions") or [])
    evidence = normalize_string_list(source.get("evidence") or [])
    verdict = str(source.get("verdict") or source.get("overall_verdict") or ("ready" if not issues else "needs-revision")).strip()
    valid = bool(source.get("valid")) if "valid" in source else (not issues and verdict != "needs-revision")
    confidence = normalize_confidence(source.get("confidence"), default=0.0)
    status = str(metadata.get("status") or source.get("status") or "completed").strip()
    if status != "ok" and status != "completed" and not issues:
        issues = [f"strict-review:{status}"]
        valid = False
        verdict = "needs-revision"
        if not suggestions:
            suggestions = ["strict reviewer 未稳定返回可用结果，请重新生成题目并重新审查。"]
    fallback_repair_plan = normalize_question_repair_plan(
        {
            "blocking": not valid,
            "failure_codes": normalize_string_list([*issues, *warnings]),
            "notes": suggestions[:8],
        }
    )
    repair_plan = normalize_question_repair_plan(source.get("repair_plan"), fallback_repair_plan)
    repair_plan["blocking"] = bool(repair_plan.get("blocking") or not valid)
    repair_plan["failure_codes"] = normalize_string_list(list(repair_plan.get("failure_codes") or []) + issues + warnings)
    return {
        "reviewer": QUESTION_REVIEWER_NAME,
        "valid": valid,
        "issues": issues,
        "warnings": warnings,
        "suggestions": suggestions,
        "confidence": confidence,
        "evidence": evidence,
        "evidence_adequacy": "sufficient" if valid else "partial",
        "verdict": "ready" if valid else "needs-revision",
        "status": status,
        "repair_plan": repair_plan,
    }


def merge_question_review_results(*reviews: dict[str, Any]) -> dict[str, Any]:
    normalized_reviews = [review for review in reviews if isinstance(review, dict) and review]
    issues = normalize_string_list([item for review in normalized_reviews for item in normalize_string_list(review.get("issues") or [])])
    warnings = normalize_string_list([item for review in normalized_reviews for item in normalize_string_list(review.get("warnings") or [])])
    suggestions = normalize_string_list([item for review in normalized_reviews for item in normalize_string_list(review.get("suggestions") or [])])
    evidence = normalize_string_list([item for review in normalized_reviews for item in normalize_string_list(review.get("evidence") or [])])
    confidence_values = [normalize_confidence(review.get("confidence"), default=-1.0) for review in normalized_reviews]
    confidence_values = [value for value in confidence_values if value >= 0]
    valid = bool(normalized_reviews) and all(bool(review.get("valid")) for review in normalized_reviews)
    repair_plan = merge_question_repair_plans(*(review.get("repair_plan") for review in normalized_reviews if isinstance(review.get("repair_plan"), dict)))
    repair_plan["blocking"] = bool(repair_plan.get("blocking") or not valid)
    repair_plan["failure_codes"] = normalize_string_list(list(repair_plan.get("failure_codes") or []) + issues + warnings)
    return {
        "reviewer": "question-review-aggregator",
        "valid": valid,
        "issues": issues,
        "warnings": warnings,
        "suggestions": suggestions,
        "confidence": min(confidence_values) if confidence_values else 0.0,
        "evidence": evidence,
        "evidence_adequacy": "sufficient" if valid else "partial",
        "verdict": "ready" if valid else "needs-revision",
        "repair_plan": repair_plan,
        "components": [
            {
                "reviewer": str(review.get("reviewer") or "unknown"),
                "valid": bool(review.get("valid")),
                "issues": normalize_string_list(review.get("issues") or []),
                "warnings": normalize_string_list(review.get("warnings") or []),
                "confidence": normalize_confidence(review.get("confidence"), default=0.0),
                "verdict": str(review.get("verdict") or ("ready" if review.get("valid") else "needs-revision")).strip(),
                "repair_plan": normalize_question_repair_plan(review.get("repair_plan")),
            }
            for review in normalized_reviews
        ],
    }


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
    source_status = str(segment.get("source_status") or "").strip()
    grounding_tag = "content-derived" if source_status == "extracted" else "metadata-grounded"
    tags = [domain or "learning", grounding_tag]
    if source_status and source_status not in tags:
        tags.append(source_status)
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
    role = str(item.get("question_role") or "learn").strip() or "learn"
    primary_category = {
        "project_task": "project_tasks",
        "project_blocker": "project_blockers",
        "review_target": "review_targets",
    }.get(role, "lesson_focus_points")
    raw_source_status = str(segment.get("source_status") or "").strip()
    source_status = "extracted" if raw_source_status == "extracted" else "session-derived-metadata-grounded"
    teaching_brief = plan_source.get("today_teaching_brief") if isinstance(plan_source.get("today_teaching_brief"), dict) else {}
    item["source_segment_id"] = segment.get("segment_id")
    item["source_material_title"] = segment.get("material_title")
    item["source_status"] = source_status
    item["question_role"] = role
    source_trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
    source_trace.update({
        "basis": "content-segment",
        "segment_id": segment.get("segment_id"),
        "material_title": segment.get("material_title"),
        "primary_category": primary_category,
        "source_status_basis": raw_source_status or "unknown",
        "current_day": plan_source.get("day") or teaching_brief.get("current_day"),
        "today_topic": plan_source.get("today_topic") or teaching_brief.get("session_theme"),
    })
    item["source_trace"] = source_trace
    if domain == "python":
        stage, cluster = content_python_stage_and_cluster(plan_source, segment)
        subskills = normalize_string_list(item.get("subskills") or []) or (terms[:3] or [segment.get("label") or "资料理解"])
        item.update(make_python_metadata(stage, cluster, subskills, role, []))
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
        prioritized_terms = unique_content_texts(terms[:4], limit=4, max_len=90)
        if len(prioritized_terms) < 4:
            return None
        correct = prioritized_terms[0]
        options = prioritized_terms
        question = f"根据今日资料「{label}」与当前任务主线，下面哪一项最应该优先掌握，才能把原始日期列推进到后续分析？"
        explanation = f"当前主线是先完成日期解析，再做时间筛选或按时间聚合。该 segment 的关键点包含：{'；'.join(prioritized_terms)}。{('原文摘要：' + excerpt) if excerpt else ''}"
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
    if domain == "python" and any(token in content_segment_blob(segment) for token in ["to_datetime", "时间序列", "按时间聚合", "groupby-agg", "groupby"]):
        prompt_lines = [
            "请用自己的话重述今天这条任务链：日期解析 → 时间筛选 → 按时间聚合 → 最小结果校验。",
            "回答时说明每一步各自处理的输入、输出，以及为什么不能直接跳到 groupby 或画图。",
            "如果会遇到 NaT、空值或混杂日期格式，也请说明你会先检查什么。",
        ]
        grading_hint = "优先判断是否真正覆盖四步链路，以及是否说清每一步的输入/输出、NaT 检查和聚合口径。"
        if excerpt:
            grading_hint += f" 可结合原文摘要检查是否真正贴合当前资料：{excerpt}"
        item = make_written_question(
            qid,
            "medium",
            "请用自己的话说明：把原始时间列推进到按天聚合结果时，应该如何一步步处理，并解释每一步的输入输出。",
            "\n".join(prompt_lines),
            content_question_tags(domain, segment, ["日期解析", "时间筛选", "按时间聚合"]),
            reference_points=["日期解析", "时间筛选", "按时间聚合", "最小结果校验"],
            grading_hint=grading_hint,
            question_role="review_target",
        )
        item["subskills"] = ["日期解析", "时间筛选", "按时间聚合"]
        item["source_trace"] = {"primary_category": "review_targets"}
        return apply_content_question_metadata(item, domain, plan_source, segment, terms)
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
    blob = content_segment_blob(segment)
    if domain == "python" and any(token in blob for token in ["to_datetime", "时间序列", "按时间聚合", "groupby-agg", "groupby"]):
        specialized_questions = [
            {
                "id": f"content-c{start_index + 1}",
                "category": "concept",
                "type": "multi",
                "difficulty": "medium",
                "question": "如果当前任务是把原始日期列推进到可分析结果，下面哪些动作属于这条必要链路？",
                "answer": [0, 1, 2],
                "options": [
                    "先用 pd.to_datetime 解析日期列",
                    "按目标时间窗口筛选需要的记录",
                    "按天聚合 value 并输出可解释结果",
                    "只记住 groupby 和时间序列这两个名字即可",
                ],
                "explanation": "这道题直接对应今天的 project task：先把时间列变成可靠输入，再围绕时间窗口筛选，并按时间粒度聚合出能解释的结果。",
                "tags": content_question_tags(domain, segment, ["to_datetime", "按时间聚合", "分析输出"]),
                "subskills": ["pd.to_datetime", "按时间聚合", "分析输出"],
                "question_role": "project_task",
                "source_trace": {"primary_category": "project_tasks"},
            },
            {
                "id": f"content-c{start_index + 2}",
                "category": "concept",
                "type": "single",
                "difficulty": "medium",
                "question": "当 blocker 是“groupby - agg 的边界”时，下面哪种做法最符合今天这节的目标？",
                "answer": 1,
                "options": [
                    "看到 groupby 就直接聚合，先不确认 date 列是否已转成 datetime",
                    "先确认 date 列可用于按时间粒度分组，再决定 groupby 聚合口径和输出列",
                    "只要能画出图，就不用关心 groupby 的聚合边界",
                    "把 groupby - agg 当成固定模板背下来，不需要理解输入输出含义",
                ],
                "explanation": "当前 blocker 不是会不会写 groupby 这几个字符，而是能否在可靠时间列基础上决定分组粒度、聚合口径与输出结果。",
                "tags": content_question_tags(domain, segment, ["groupby-agg", "按时间聚合", "数据聚合与分组运算"]),
                "subskills": ["groupby-agg", "按时间聚合", "数据聚合与分组运算"],
                "question_role": "project_blocker",
                "source_trace": {"primary_category": "project_blockers"},
            },
            {
                "id": f"content-c{start_index + 3}",
                "category": "concept",
                "type": "single",
                "difficulty": "medium",
                "question": "如果问题是“统计 2024 年 1 月之后的订单每天 amount 总和”，下面哪种处理顺序最合理？",
                "answer": 0,
                "options": [
                    "先把订单时间转成 datetime，再按时间窗口筛选，最后按天聚合",
                    "先对全量数据按天聚合，再从聚合结果里随便挑出 1 月之后的部分",
                    "先按月聚合，再尝试从月表里恢复每天的结果",
                    "先画图，再决定是否需要筛选和聚合",
                ],
                "explanation": "“先筛选再聚合”和“先聚合再筛选”回答的是不同问题。若目标本来就是某个时间窗口内的明细样本汇总，应先限定样本，再做聚合。",
                "tags": content_question_tags(domain, segment, ["时间窗口", "先筛选再聚合", "按时间聚合"]),
                "subskills": ["时间窗口", "先筛选再聚合", "按时间聚合"],
                "question_role": "review_target",
                "source_trace": {"primary_category": "review_targets"},
            },
            {
                "id": f"content-c{start_index + 4}",
                "category": "concept",
                "type": "single",
                "difficulty": "medium",
                "question": "如果一张结果表包含 date=2024-01-01、total_amount=320，最合理的解释是什么？",
                "answer": 0,
                "options": [
                    "它表示 2024-01-01 这一天被纳入样本的记录，其 amount 聚合结果为 320",
                    "它表示原始表里只有一条 2024-01-01 的记录，且 amount 一定等于 320",
                    "它表示 2024 年 1 月整个月的总金额都是 320",
                    "它只是画图用的标签，和聚合口径无关",
                ],
                "explanation": "阶段复盘要能说清聚合结果每一行的语义：分组键是什么、统计列是什么、这一行代表哪一层粒度的汇总。",
                "tags": content_question_tags(domain, segment, ["结果语义", "分组键", "统计口径"]),
                "subskills": ["结果语义", "分组键", "统计口径"],
                "question_role": "review_target",
                "source_trace": {"primary_category": "review_targets"},
            },
            {
                "id": f"content-c{start_index + 5}",
                "category": "concept",
                "type": "single",
                "difficulty": "medium",
                "question": "如果你已经得到按天聚合后的 total_amount 表，下一步最适合用什么方式做最小复核，判断结果是否合理？",
                "answer": 2,
                "options": [
                    "直接背下 total_amount 这一列的名字，不再检查结果来源",
                    "马上把聚合表 merge 回明细表，不看时间趋势是否异常",
                    "先画一个最小趋势图或做结果检查，确认日期走势与聚合口径是否符合预期",
                    "只要代码没报错，就说明结果一定正确，不需要复核",
                ],
                "explanation": "可视化在今天不是独立新知识点，而是复核聚合结果的一种最小手段：帮助判断时间走势、异常波动和统计口径是否说得通。",
                "tags": content_question_tags(domain, segment, ["绘图和可视化", "结果复核", "时间趋势"]),
                "subskills": ["绘图和可视化", "结果复核", "时间趋势"],
                "question_role": "review_target",
                "source_trace": {"primary_category": "review_targets"},
            },
            {
                "id": f"content-c{start_index + 6}",
                "category": "concept",
                "type": "single",
                "difficulty": "medium",
                "question": "你在复查一段“统计 2024-01-02 之后每天 amount 汇总”的代码时，发现它直接用字符串比较日期、对 order_time 分组后求 price 的 mean，且原始数据里还有空值和混杂日期格式。下面哪一步最应该先修？",
                "answer": 0,
                "options": [
                    "先用 pd.to_datetime 统一时间列并检查 NaT，再按时间窗口筛选，同时确认聚合字段和统计口径是否真的是 amount 的按天汇总",
                    "保留字符串比较，只把 mean 改成 sum，其他问题可以先忽略",
                    "先把聚合结果 merge 回更多维度列，信息更多就更容易判断是否正确",
                    "只要 groupby 能跑通，空值和混杂格式通常会被自动处理，不会影响最终解释",
                ],
                "explanation": "这类错误的根因通常在输入与口径：日期列若未先转成 datetime，就可能出现字符串比较和 NaT 带来的样本偏差；而对哪个字段做 sum/mean、按什么粒度分组，也必须和“按天汇总 amount”这个任务保持一致。",
                "tags": content_question_tags(domain, segment, ["改错题", "NaT", "聚合口径"]),
                "subskills": ["pd.to_datetime", "NaT", "聚合口径"],
                "question_role": "review_target",
                "source_trace": {"primary_category": "review_targets"},
            },
        ]
        questions: list[dict[str, Any]] = []
        for item in specialized_questions:
            enriched = apply_content_question_metadata(item, domain, plan_source, segment, terms)
            if enriched and is_valid_runtime_question(enriched):
                questions.append(enriched)
        return questions
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

    if "to_datetime" in blob or "时间序列" in blob or "按时间聚合" in blob or "time series" in blob:
        index = start_index + len(questions)
        append_question(make_code_question(
            f"content-code{index}", "medium", "按当前任务链解析时间列并筛选窗口", f"content_filter_recent_rows_{index}", ["rows"],
            f"Day 7 当前主线是把日期清洗推进到分析输出。请实现函数 content_filter_recent_rows_{index}(rows)，其中 rows 是字典列表，每项至少包含 date 和 value。请先把 date 统一转成 pandas datetime，再筛出 2024-01-02 及之后、可继续进入按天聚合步骤的数据，并返回按原顺序保留的 DataFrame。",
            f"import pandas as pd\n\ndef content_filter_recent_rows_{index}(rows):\n    pass",
            f"import pandas as pd\n\ndef content_filter_recent_rows_{index}(rows):\n    frame = pd.DataFrame(rows).copy()\n    frame['date'] = pd.to_datetime(frame['date'])\n    return frame[frame['date'] >= pd.Timestamp('2024-01-02')]",
            [
                {"input": [[{"date": "2024-01-01", "value": 1}, {"date": "2024-01-02", "value": 3}, {"date": "2024-01-05", "value": 4}]], "expected": {"date": ["2024-01-02T00:00:00", "2024-01-05T00:00:00"], "value": [3, 4]}},
                {"input": [[{"date": "2024-01-03", "value": 9}]], "expected": {"date": ["2024-01-03T00:00:00"], "value": [9]}}
            ],
            content_question_tags("python", segment, ["to_datetime", "时间筛选", "分析输出"]),
            stage=stage, cluster=cluster, subskills=["pd.to_datetime", "时间筛选", "DataFrame"], question_role="project_task",
        ))
        if questions:
            questions[-1]["source_trace"] = {
                "basis": "content-segment",
                "segment_id": segment.get("segment_id"),
                "material_title": segment.get("material_title"),
                "primary_category": "project_tasks",
                "source_status_basis": segment.get("source_status") or "unknown",
            }
        index = start_index + len(questions)
        append_question(make_code_question(
            f"content-code{index}", "medium", "按当前 blocker 做命名聚合并解释结果列", f"content_windowed_daily_sum_{index}", ["rows"],
            f"Day 7 当前 blocker 是 groupby - agg 的边界。请实现函数 content_windowed_daily_sum_{index}(rows)，其中 rows 是字典列表，每项至少包含 order_time、amount 和 order_id。请把 order_time 转成 pandas datetime，先筛出 2024-01-02 及之后的记录，再按天做命名聚合，输出两列：total_amount 和 order_count，并返回列名为 date、total_amount、order_count 的 DataFrame，且 date 列保持 datetime64[ns]。",
            f"import pandas as pd\n\ndef content_windowed_daily_sum_{index}(rows):\n    pass",
            f"import pandas as pd\n\ndef content_windowed_daily_sum_{index}(rows):\n    frame = pd.DataFrame(rows).copy()\n    frame['order_time'] = pd.to_datetime(frame['order_time'])\n    frame = frame[frame['order_time'] >= pd.Timestamp('2024-01-02')]\n    grouped = frame.groupby(frame['order_time'].dt.floor('D'), as_index=False).agg(total_amount=('amount', 'sum'), order_count=('order_id', 'count'))\n    grouped = grouped.rename(columns={{'order_time': 'date'}})\n    grouped['date'] = pd.to_datetime(grouped['date'])\n    return grouped[['date', 'total_amount', 'order_count']]",
            [
                {"input": [[{"order_time": "2024-01-01 08:00:00", "amount": 1, "order_id": 11}, {"order_time": "2024-01-02 20:00:00", "amount": 2, "order_id": 12}, {"order_time": "2024-01-02 09:00:00", "amount": 5, "order_id": 13}, {"order_time": "2024-01-03 10:00:00", "amount": 4, "order_id": 14}]], "expected": {"date": ["2024-01-02T00:00:00", "2024-01-03T00:00:00"], "total_amount": [7, 4], "order_count": [2, 1]}}
            ],
            content_question_tags("python", segment, ["groupby-agg", "命名聚合", "结果列语义"]),
            stage=stage, cluster=cluster, subskills=["groupby-agg", "命名聚合", "datetime64[ns]"], question_role="project_blocker",
        ))
        if questions:
            questions[-1]["source_trace"] = {
                "basis": "content-segment",
                "segment_id": segment.get("segment_id"),
                "material_title": segment.get("material_title"),
                "primary_category": "project_blockers",
                "source_status_basis": segment.get("source_status") or "unknown",
            }
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


def git_question_anchor(qid: str) -> dict[str, str]:
    mapping = {
        "git-c1": {"question_role": "learn", "primary_category": "lesson_focus_points"},
        "git-c2": {"question_role": "learn", "primary_category": "lesson_focus_points"},
        "git-c3": {"question_role": "project_blocker", "primary_category": "project_blockers"},
        "git-c4": {"question_role": "project_task", "primary_category": "project_tasks"},
        "git-c5": {"question_role": "review_target", "primary_category": "review_targets"},
        "git-c6": {"question_role": "review_target", "primary_category": "review_targets"},
        "git-c7": {"question_role": "project_task", "primary_category": "project_tasks"},
    }
    return mapping.get(qid, {"question_role": "learn", "primary_category": "lesson_focus_points"})



def make_git_content_questions(plan_source: dict[str, Any], daily_lesson_plan: dict[str, Any]) -> list[dict[str, Any]]:
    text_parts = [
        str(plan_source.get("today_topic") or ""),
        " ".join(normalize_string_list(plan_source.get("review") or [])),
        " ".join(normalize_string_list(plan_source.get("new_learning") or [])),
        " ".join(normalize_string_list(plan_source.get("exercise_focus") or [])),
        " ".join(normalize_string_list(daily_lesson_plan.get("lesson_focus_points") or [])),
        " ".join(normalize_string_list(daily_lesson_plan.get("project_tasks") or [])),
        " ".join(normalize_string_list(daily_lesson_plan.get("project_blockers") or [])),
        " ".join(normalize_string_list(daily_lesson_plan.get("review_targets") or [])),
    ]
    today_focus = daily_lesson_plan.get("today_focus") if isinstance(daily_lesson_plan.get("today_focus"), dict) else {}
    for point in today_focus.get("focus_points") or []:
        if isinstance(point, dict):
            text_parts.extend(str(point.get(key) or "") for key in ["point", "why_it_matters", "mastery_check"])
    project_driven_explanation = daily_lesson_plan.get("project_driven_explanation") if isinstance(daily_lesson_plan.get("project_driven_explanation"), dict) else {}
    for task in project_driven_explanation.get("tasks") or []:
        if isinstance(task, dict):
            text_parts.extend(str(task.get(key) or "") for key in ["task_name", "blocker", "knowledge_points", "explanation", "how_to_apply"])
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
    if any(token in blob for token in ["branch", "分支", "remote", "远程"]):
        selected_ids.extend(["git-c6", "git-c7"])
    git_concept, _ = build_git_bank()
    by_id = {str(item.get("id")): item for item in git_concept}
    ordered: list[dict[str, Any]] = []
    seen_qids: set[str] = set()
    preferred_ids = ["git-c4", "git-c5", "git-c7", "git-c1", "git-c2", "git-c3", "git-c6"]
    candidate_ids = [qid for qid in selected_ids if qid in preferred_ids]
    candidate_ids += [qid for qid in preferred_ids if qid not in candidate_ids]
    for qid in candidate_ids:
        item = by_id.get(qid)
        if not item or qid in seen_qids:
            continue
        enriched = dict(item)
        enriched["id"] = f"lesson-{enriched['id']}"
        anchor = git_question_anchor(qid)
        enriched["question_role"] = anchor["question_role"]
        enriched["source_trace"] = {
            "basis": "daily_lesson_plan",
            "primary_category": anchor["primary_category"],
            "source_question_id": qid,
        }
        ordered.append(enriched)
        seen_qids.add(qid)
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
        if len(concept) < 6:
            concept.extend(build_content_concept_questions_for_segment(domain, plan_source, segment, len(concept) + 1))
            concept = concept[:6]
        segment_blob = content_segment_blob(segment)
        written_allowed = str(segment.get("source_status") or "") == "extracted"
        if domain == "python" and any(token in segment_blob for token in ["to_datetime", "时间序列", "按时间聚合", "groupby-agg", "groupby"]):
            written_allowed = True
        if len(written) < 1 and written_allowed:
            item = make_content_written_question(f"content-w{len(written) + 1}", domain, plan_source, segment, segment_question_terms(segment))
            if item and is_valid_runtime_question(item):
                written.append(item)
                written = written[:1]
        if domain == "python" and len(code) < 2:
            code.extend(build_content_code_questions_for_segment(plan_source, segment, len(code) + 1))
            code = code[:2]
        if len(concept) >= 6 and len(written) >= 1 and (domain != "python" or len(code) >= 2):
            break
    context = {
        "selection_policy": "grounded-content-first-no-bank-fallback",
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
    "build_question_reviewer_prompt",
    "count_content_questions",
    "count_llm_lesson_questions",
    "merge_question_review_results",
    "normalize_strict_question_review",
    "is_valid_runtime_question",
    "lesson_question_blob",
    "merge_question_pools",
    "normalize_llm_answer",
    "question_focus_keys",
    "question_matches_lesson",
    "question_text_key",
    "validate_and_normalize_generated_questions",
]
