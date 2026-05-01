from __future__ import annotations

import re
from typing import Any

from learn_core.quality_review import apply_quality_envelope, build_traceability_entry, normalize_confidence
from learn_core.text_utils import normalize_string_list
from learn_runtime.question_generation import (
    build_semantic_trace_snapshot,
    is_valid_runtime_question,
    normalize_question_repair_plan,
)
from learn_runtime.schemas import (
    DIFFICULTY_LEVEL_ORDER,
    DIFFICULTY_LEVELS,
    TABULAR_PARAMETER_TYPES,
    normalize_difficulty_level,
    preflight_code_question_tests,
    REQUIRED_QUESTIONS_TOP_LEVEL,
    validate_question_difficulty_fields,
    validate_question_plan_basic,
    validate_question_runtime_contract,
    validate_question_scope_basic,
    validate_questions_basic,
    validate_test_grade_question,
)


REQUIRED_TOP_LEVEL = REQUIRED_QUESTIONS_TOP_LEVEL
FALLBACK_SOURCE_STATUSES = {"fallback-metadata", "metadata-fallback", "domain-bank-fallback", "bank-fallback"}
CJK_RE = re.compile(r"[一-鿿]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'\-]{2,}\b")
CODEISH_RE = re.compile(r"(`[^`]+`|\b[a-zA-Z_][\w.]*\(|\b[a-zA-Z_][\w]*_[\w_]*\b|/[\w./-]+|\b\w+\.py\b|\b[A-Z][A-Za-z0-9]*(?:API|SDK|CLI)\b)")


def _normalize_language_policy(value: Any) -> dict[str, Any]:
    policy = value if isinstance(value, dict) else {}
    user_facing_language = str(policy.get("user_facing_language") or "").strip()
    return {
        "user_facing_language": user_facing_language,
        "localization_required": bool(policy.get("localization_required", True)),
    }


def _strip_codeish_text(value: str) -> str:
    return CODEISH_RE.sub(" ", value)


def _visible_text_language_warning(text: Any, expected_language: str, label: str) -> str | None:
    value = _strip_codeish_text(str(text or "").strip())
    if len(value) < 24:
        return None
    cjk_count = len(CJK_RE.findall(value))
    latin_count = len(LATIN_WORD_RE.findall(value))
    if expected_language.lower().startswith("zh") and latin_count >= 8 and cjk_count < 4:
        return f"{label}: 用户可见文本疑似未遵守中文 language_policy"
    if expected_language.lower().startswith("en") and cjk_count >= 8 and latin_count < 4:
        return f"{label}: 用户可见文本疑似未遵守英文 language_policy"
    return None


def _collect_question_language_warnings(item: dict[str, Any], expected_language: str) -> list[str]:
    qid = str(item.get("id") or "<missing-id>")
    warnings: list[str] = []
    for key in ("title", "question", "prompt", "description", "explanation", "grading_hint"):
        warning = _visible_text_language_warning(item.get(key), expected_language, f"{qid}.{key}")
        if warning:
            warnings.append(warning)
    for index, option in enumerate(item.get("options") or []):
        warning = _visible_text_language_warning(option, expected_language, f"{qid}.options[{index}]")
        if warning:
            warnings.append(warning)
    for index, point in enumerate(item.get("reference_points") or []):
        warning = _visible_text_language_warning(point, expected_language, f"{qid}.reference_points[{index}]")
        if warning:
            warnings.append(warning)
    return warnings


def question_source_marker(item: dict[str, Any]) -> str:
    source_trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
    if source_trace:
        return str(source_trace.get("question_source") or source_trace.get("diagnostic_generation_mode") or source_trace.get("segment_id") or "source_trace")
    for key in ("source_status", "source_segment_id", "source_material_title", "material_segment_id"):
        value = item.get(key)
        if value:
            return str(value)
    tags = normalize_string_list(item.get("tags"))
    if "content-derived" in tags:
        return str(item.get("source_status") or "content-derived")
    if "lesson-derived" in tags:
        return "daily_lesson_plan"
    return "missing-source-trace"


def question_has_answer_and_explanation(item: dict[str, Any]) -> bool:
    category = str(item.get("category") or "")
    if category == "concept":
        return "answer" in item and bool(str(item.get("explanation") or "").strip())
    if category == "code" and str(item.get("type") or "").strip() == "sql":
        return bool(item.get("solution_sql") or item.get("reference_sql") or item.get("explanation") or item.get("result_contract"))
    if category == "code":
        return bool(item.get("solution_code") or item.get("expected_code") or item.get("explanation"))
    if category == "open":
        reference_points = item.get("reference_points")
        has_reference_points = isinstance(reference_points, list) and any(str(point).strip() for point in reference_points)
        has_grading_hint = bool(str(item.get("grading_hint") or "").strip())
        has_explanation = bool(str(item.get("explanation") or "").strip())
        return has_reference_points or has_grading_hint or has_explanation
    return False



def _strip_fenced_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def _has_readable_markdown_layout(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    meaningful_lines = [line.strip() for line in value.splitlines() if line.strip()]
    has_block = bool(re.search(r"\n\s*\n", value) or re.search(r"```", value))
    has_list = bool(re.search(r"^\s*[-*]\s+", value, re.MULTILINE) or re.search(r"^\s*\d+[.)]\s+", value, re.MULTILINE))
    has_inline = bool(re.search(r"`[^`]+`", value) or re.search(r"\*\*.+?\*\*", value))
    has_multiline = len(meaningful_lines) >= 2
    return has_block or has_list or (has_inline and has_multiline)


def _has_overlong_plain_line(text: str, *, limit: int = 180) -> bool:
    plain = _strip_fenced_code(str(text or ""))
    return any(len(line.strip()) > limit for line in plain.splitlines() if line.strip())


def _constraints_are_readable(value: Any) -> bool:
    if isinstance(value, list):
        return len([item for item in value if str(item).strip()]) >= 1
    text = str(value or "").strip()
    if not text:
        return False
    if re.search(r"^\s*[-*]\s+", text, re.MULTILINE) or re.search(r"^\s*\d+[.)]\s+", text, re.MULTILINE):
        return True
    if len([line for line in text.splitlines() if line.strip()]) >= 2:
        return True
    return text.count("；") + text.count(";") <= 1


def question_traceability_status(item: dict[str, Any], marker: str) -> str:
    source_status = str(item.get("source_status") or "").strip()
    if source_status:
        return source_status
    tags = normalize_string_list(item.get("tags"))
    if "lesson-derived" in tags:
        return "lesson-derived"
    if "content-derived" in tags:
        return "content-derived"
    if marker in FALLBACK_SOURCE_STATUSES or "fallback" in marker:
        return "bank-fallback"
    return "derived"


def question_traceability_locator(item: dict[str, Any]) -> str | None:
    for key in ("source_segment_id", "material_segment_id"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    source_trace = item.get("source_trace")
    if isinstance(source_trace, dict):
        for key in ("segment_id", "source_segment_id", "material_segment_id"):
            value = str(source_trace.get(key) or "").strip()
            if value:
                return value
    return None


def _normalize_difficulty_level_list(value: Any) -> list[str]:
    levels: list[str] = []
    raw_values = value if isinstance(value, list) else [value]
    for raw in raw_values:
        level = normalize_difficulty_level(raw)
        if level and level not in levels:
            levels.append(level)
    return levels


def _difficulty_target_from_payload(plan_source: dict[str, Any], selection_context: dict[str, Any]) -> dict[str, Any]:
    target = selection_context.get("difficulty_target") if isinstance(selection_context.get("difficulty_target"), dict) else None
    if target is None:
        target = plan_source.get("difficulty_target") if isinstance(plan_source.get("difficulty_target"), dict) else None
    return dict(target or {})


def _distribution_target_for_category(target: dict[str, Any], category: str) -> dict[str, int]:
    distribution = target.get("recommended_distribution") if isinstance(target.get("recommended_distribution"), dict) else {}
    raw = distribution.get(category) if isinstance(distribution.get(category), dict) else distribution
    result: dict[str, int] = {}
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        level = normalize_difficulty_level(key)
        if not level:
            continue
        try:
            expected = int(value)
        except (TypeError, ValueError):
            continue
        if expected > 0:
            result[level] = expected
    return result


def _allowed_levels_for_category(target: dict[str, Any], category: str) -> list[str]:
    allowed_range = target.get("allowed_range") if isinstance(target.get("allowed_range"), dict) else {}
    if category in allowed_range:
        return _normalize_difficulty_level_list(allowed_range.get(category))
    if category in target:
        return _normalize_difficulty_level_list(target.get(category))
    return _normalize_difficulty_level_list(target.get("allowed_levels"))


def validate_question_item(item: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["题目不是 object"]
    qid = str(item.get("id") or "<missing-id>")
    difficulty_issues = validate_question_difficulty_fields(item)
    if difficulty_issues:
        issues.extend(f"{qid}: {issue}" for issue in difficulty_issues)
    test_grade_issues = validate_test_grade_question(item)
    if test_grade_issues:
        issues.extend(f"{qid}: {issue}" for issue in test_grade_issues)
    runtime_issues = validate_question_runtime_contract(item)
    if runtime_issues:
        issues.extend(runtime_issues)
    if not is_valid_runtime_question(item) and not test_grade_issues:
        issues.append(f"{qid}: schema 不合法")
    if not question_has_answer_and_explanation(item):
        issues.append(f"{qid}: 缺少答案或解析/参考解")
    # 概念题排版校验：question 字段必须有至少一个 markdown 格式元素
    if str(item.get("category") or "").strip() == "concept":
        qtext = str(item.get("question") or item.get("prompt") or "")
        has_markdown = bool(
            re.search(r"```", qtext) or  # 代码块
            re.search(r"\*\*.*?\*\*", qtext) or  # 粗体
            re.search(r"^[-*]\s+", qtext, re.MULTILINE) or  # 无序列表
            re.search(r"^\d+[.)]\s+", qtext, re.MULTILINE) or  # 有序列表
            re.search(r"^#{1,3}\s+", qtext, re.MULTILINE) or  # 标题
            len(qtext.splitlines()) >= 3  # 至少 3 段（含空行分隔）
        )
        if not has_markdown:
            issues.append(f"{qid}: 概念题 question 字段为纯文本一段到底，必须使用 Markdown 排版（粗体/代码块/列表/多段分隔）")
    # 代码题排版校验：结构化字段不能为空，题干必须可扫读
    if str(item.get("category") or "").strip() == "code":
        problem_statement = str(item.get("problem_statement") or "")
        constraints_value = item.get("constraints")
        ps_len = len(problem_statement)
        is_len = len(str(item.get("input_spec") or ""))
        os_len = len(str(item.get("output_spec") or ""))
        cs_len = len("\n".join(str(v) for v in constraints_value) if isinstance(constraints_value, list) else str(constraints_value or ""))
        if not _has_readable_markdown_layout(problem_statement):
            issues.append(f"{qid}: 代码题 problem_statement 为纯文本一段到底（{ps_len}字符），必须使用 Markdown 排版——用空行、列表、粗体、内联代码或代码块组织题面")
        if _has_overlong_plain_line(problem_statement):
            issues.append(f"{qid}: 代码题 problem_statement 存在过长单行，必须把条件/边界拆成多行或列表")
        if is_len < 10 or os_len < 10 or cs_len < 10:
            issues.append(f"{qid}: 代码题的 input_spec/output_spec/constraints 不能为空或过短（各≥10字符）。禁止把所有内容只写进 problem_statement，必须拆分到各自独立的结构化字段")
        if not _constraints_are_readable(constraints_value):
            issues.append(f"{qid}: 代码题 constraints 必须用数组、Markdown 列表或换行表达多条规则，禁止用分号堆成一行")
    marker = question_source_marker(item)
    if not marker or marker == "missing-source-trace":
        issues.append(f"{qid}: 缺少可追踪来源：需要 source_trace / source_segment_id / material_segment_id / lesson-derived / content-derived / diagnostic capability trace")
    if str(item.get("question_role") or "").strip() == "":
        tags = normalize_string_list(item.get("tags"))
        if "content-derived" in tags or "lesson-derived" in tags:
            issues.append(f"{qid}: 内容生成题缺少 question_role")
    return issues


def _question_scope_from_payload(plan_source: dict[str, Any], selection_context: dict[str, Any]) -> dict[str, Any]:
    value = plan_source.get("question_scope") if isinstance(plan_source.get("question_scope"), dict) else selection_context.get("question_scope")
    return dict(value or {}) if isinstance(value, dict) else {}


def _question_plan_from_payload(plan_source: dict[str, Any], selection_context: dict[str, Any]) -> dict[str, Any]:
    value = plan_source.get("question_plan") if isinstance(plan_source.get("question_plan"), dict) else selection_context.get("question_plan")
    return dict(value or {}) if isinstance(value, dict) else {}


def _question_type_key(item: dict[str, Any]) -> str:
    qtype = str(item.get("type") or "").strip()
    if qtype == "sql":
        return "sql"
    if str(item.get("category") or "").strip() == "code" or qtype == "code":
        return "code"
    return qtype or str(item.get("category") or "unknown").strip() or "unknown"


def _question_capabilities(item: dict[str, Any]) -> list[str]:
    source_trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
    return normalize_string_list(
        item.get("target_capability_ids")
        or source_trace.get("target_capability_ids")
        or item.get("capability_tags")
        or []
    )


def _validate_scope_plan_alignment(
    data: dict[str, Any],
    questions: list[Any],
    category_counts: dict[str, int],
    difficulty_counts: dict[str, int],
    capability_counts: dict[str, int],
    plan_source: dict[str, Any],
    selection_context: dict[str, Any],
) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    question_scope = _question_scope_from_payload(plan_source, selection_context)
    question_plan = _question_plan_from_payload(plan_source, selection_context)
    if not question_scope:
        issues.append("缺少 question_scope：必须先生成 question-scope.json")
        return issues, warnings
    if not question_plan:
        issues.append("缺少 question_plan：必须先生成 question-plan.json")
        return issues, warnings
    issues.extend(validate_question_scope_basic(question_scope))
    issues.extend(validate_question_plan_basic(question_plan))
    for field in ("session_type", "session_intent", "assessment_kind", "test_mode"):
        payload_value = data.get(field)
        scope_value = question_scope.get(field)
        plan_value = question_plan.get(field)
        if scope_value != payload_value:
            issues.append(f"question_scope.{field}_mismatch")
        if plan_value != payload_value:
            issues.append(f"question_plan.{field}_mismatch")
    if str(question_plan.get("scope_id") or "").strip() != str(question_scope.get("scope_id") or "").strip():
        issues.append("question_plan.scope_id_mismatch")
    try:
        expected_count = int(question_plan.get("question_count") or 0)
    except (TypeError, ValueError):
        expected_count = 0
    if expected_count and expected_count != len(questions):
        issues.append(f"question_plan.question_count_mismatch:{len(questions)}/{expected_count}")
    actual_type_counts: dict[str, int] = {}
    for item in questions:
        if isinstance(item, dict):
            key = _question_type_key(item)
            actual_type_counts[key] = actual_type_counts.get(key, 0) + 1
    question_mix = question_plan.get("question_mix") if isinstance(question_plan.get("question_mix"), dict) else {}
    for raw_type, raw_expected in question_mix.items():
        key = "code" if str(raw_type) == "code" else str(raw_type)
        try:
            expected = int(raw_expected)
        except (TypeError, ValueError):
            continue
        actual = actual_type_counts.get(key, 0)
        if actual != expected:
            issues.append(f"question_plan.question_mix_mismatch:{key}:{actual}/{expected}")
    difficulty_distribution = question_plan.get("difficulty_distribution") if isinstance(question_plan.get("difficulty_distribution"), dict) else {}
    for raw_level, raw_expected in difficulty_distribution.items():
        level = normalize_difficulty_level(raw_level)
        if not level:
            continue
        try:
            expected = int(raw_expected)
        except (TypeError, ValueError):
            continue
        actual = difficulty_counts.get(level, 0)
        if actual != expected:
            issues.append(f"question_plan.difficulty_distribution_mismatch:{level}:{actual}/{expected}")
    forbidden_types = set(normalize_string_list(question_plan.get("forbidden_question_types") or []))
    for key, count in actual_type_counts.items():
        if key in forbidden_types and count > 0:
            issues.append(f"question_plan.forbidden_question_type_used:{key}")
    target_capability_ids = normalize_string_list(question_scope.get("target_capability_ids") or [])
    if data.get("session_type") == "test" and target_capability_ids:
        missing = [capability_id for capability_id in target_capability_ids if capability_counts.get(capability_id, 0) <= 0]
        if missing:
            issues.append("question_scope.target_capability_ids_uncovered:" + ",".join(missing[:6]))
    planned_items = question_plan.get("planned_items") if isinstance(question_plan.get("planned_items"), list) else []
    if planned_items and len(planned_items) != len(questions):
        warnings.append(f"question_plan.planned_items_count_mismatch:{len(questions)}/{len(planned_items)}")
    return issues, warnings


def summarize_question_repair_plan(review: dict[str, Any]) -> dict[str, Any]:
    repair_plan = normalize_question_repair_plan(review.get("repair_plan")) if isinstance(review, dict) else normalize_question_repair_plan({})
    coverage_gaps = repair_plan.get("coverage_gaps") if isinstance(repair_plan.get("coverage_gaps"), dict) else {}
    capability_gaps = repair_plan.get("capability_gaps") if isinstance(repair_plan.get("capability_gaps"), dict) else {}
    minimum_pass_shape = repair_plan.get("minimum_pass_shape") if isinstance(repair_plan.get("minimum_pass_shape"), dict) else {}
    missing_shape: list[str] = []
    for key in ("lesson_focus", "project", "review", "explicit_project", "explicit_review"):
        if bool(coverage_gaps.get(key)):
            missing_shape.append(f"coverage:{key}")
    for category in normalize_string_list(coverage_gaps.get("missing_primary_categories") or []):
        missing_shape.append(f"primary_category:{category}")
    for capability_id in normalize_string_list(capability_gaps.get("missing") or []):
        missing_shape.append(f"capability:{capability_id}")
    required_open_question_count = int(minimum_pass_shape.get("required_open_question_count") or 0)
    required_code_question_count = int(minimum_pass_shape.get("required_code_question_count") or 0)
    if required_open_question_count > 0:
        missing_shape.append(f"required_open_question_count:{required_open_question_count}")
    if required_code_question_count > 0:
        missing_shape.append(f"required_code_question_count:{required_code_question_count}")
    forbidden_patterns = normalize_string_list(minimum_pass_shape.get("forbidden_patterns") or [])
    if forbidden_patterns:
        missing_shape.append("forbidden_patterns:" + ",".join(forbidden_patterns[:4]))
    failure_summary = normalize_string_list(
        [
            *[f"failure_code:{code}" for code in normalize_string_list(repair_plan.get("failure_codes") or [])[:8]],
            *[f"evidence_gap:{gap}" for gap in normalize_string_list(repair_plan.get("evidence_gaps") or [])[:8]],
            *missing_shape[:12],
        ]
    )
    return {
        "blocking": bool(repair_plan.get("blocking")),
        "failure_summary": failure_summary,
        "minimum_pass_shape": minimum_pass_shape,
        "coverage_gaps": coverage_gaps,
        "capability_gaps": capability_gaps,
        "repair_actions": repair_plan.get("repair_actions") if isinstance(repair_plan.get("repair_actions"), list) else [],
    }


def _runtime_context_validation_issues(data: dict[str, Any], questions: list[Any]) -> list[str]:
    issues: list[str] = []
    sql_questions = [item for item in questions if isinstance(item, dict) and str(item.get("type") or "").strip() == "sql"]
    runtime_context = data.get("runtime_context") if isinstance(data.get("runtime_context"), dict) else {}
    if not runtime_context:
        if sql_questions:
            issues.append("runtime_context.missing_for_sql_questions")
        return issues
    question_ids = {str(item.get("id") or "").strip() for item in questions if isinstance(item, dict) and str(item.get("id") or "").strip()}
    parameter_spec = runtime_context.get("parameter_spec") if isinstance(runtime_context.get("parameter_spec"), dict) else {}
    parameter_questions = parameter_spec.get("questions") if isinstance(parameter_spec.get("questions"), list) else []
    parameter_question_ids: set[str] = set()
    tabular_dataset_refs: set[str] = set()
    for index, question_spec in enumerate(parameter_questions):
        if not isinstance(question_spec, dict):
            continue
        question_id = str(question_spec.get("question_id") or question_spec.get("id") or "").strip()
        if question_id:
            parameter_question_ids.add(question_id)
            if question_id not in question_ids:
                issues.append(f"runtime_context.parameter_spec.unknown_question:{question_id}")
        parameters = question_spec.get("parameters") if isinstance(question_spec.get("parameters"), list) else []
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            ptype = str(parameter.get("type") or parameter.get("value_type") or "").strip().lower()
            dataset_ref = str(parameter.get("dataset_ref") or parameter.get("dataset_view_ref") or "").strip()
            if ptype in TABULAR_PARAMETER_TYPES and not dataset_ref:
                issues.append(f"runtime_context.parameter_spec.{question_id or index}.dataset_ref_missing")
            if dataset_ref:
                tabular_dataset_refs.add(dataset_ref)
    dataset_artifact = runtime_context.get("dataset_artifact") if isinstance(runtime_context.get("dataset_artifact"), dict) else {}
    datasets = dataset_artifact.get("datasets") if isinstance(dataset_artifact.get("datasets"), list) else []
    dataset_ids = {str(dataset.get("dataset_id") or dataset.get("id") or "").strip() for dataset in datasets if isinstance(dataset, dict)}
    for dataset_ref in sorted(tabular_dataset_refs):
        if dataset_ref not in dataset_ids:
            issues.append(f"runtime_context.dataset_ref_unresolved:{dataset_ref}")
    for item in questions:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id") or "").strip()
        if str(item.get("type") or "").strip() == "sql" and qid not in parameter_question_ids:
            issues.append(f"{qid}: runtime_context.parameter_spec_missing")
    return issues


def validate_questions_payload(data: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = validate_questions_basic(data)
    warnings: list[str] = []

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        questions = []
    issues.extend(_runtime_context_validation_issues(data, questions))

    language_policy = _normalize_language_policy(data.get("language_policy"))
    if not language_policy.get("user_facing_language"):
        issues.append("questions.json 缺少有效 language_policy.user_facing_language")
    plan_source = data.get("plan_source") if isinstance(data.get("plan_source"), dict) else {}
    selection_context = data.get("selection_context") if isinstance(data.get("selection_context"), dict) else {}
    plan_language_policy = _normalize_language_policy(plan_source.get("language_policy"))
    selection_language_policy = _normalize_language_policy(selection_context.get("language_policy"))
    if plan_language_policy.get("user_facing_language") and language_policy.get("user_facing_language") and plan_language_policy.get("user_facing_language") != language_policy.get("user_facing_language"):
        issues.append("questions.json language_policy 与 plan_source.language_policy 不一致")
    if selection_language_policy.get("user_facing_language") and language_policy.get("user_facing_language") and selection_language_policy.get("user_facing_language") != language_policy.get("user_facing_language"):
        warnings.append("selection_context.language_policy 与顶层 language_policy 不一致")
    grounding_context = plan_source.get("lesson_grounding_context") if isinstance(plan_source.get("lesson_grounding_context"), dict) else {}
    daily_lesson_plan = selection_context.get("daily_lesson_plan") if isinstance(selection_context.get("daily_lesson_plan"), dict) else {}
    semantic_trace = build_semantic_trace_snapshot(grounding_context, daily_lesson_plan)
    semantic_profile = str(semantic_trace.get("semantic_profile") or "today").strip() or "today"
    minimum_pass_shape = semantic_trace.get("minimum_pass_shape") if isinstance(semantic_trace.get("minimum_pass_shape"), dict) else {}
    required_primary_categories = normalize_string_list(minimum_pass_shape.get("required_primary_categories") or [])
    required_capability_coverage = normalize_string_list(minimum_pass_shape.get("required_capability_coverage") or [])
    required_open_question_count = max(0, int(minimum_pass_shape.get("required_open_question_count") or 0))
    required_code_question_count = max(0, int(minimum_pass_shape.get("required_code_question_count") or 0))

    ids: set[str] = set()
    source_markers: list[str] = []
    fallback_count = 0
    category_counts: dict[str, int] = {}
    difficulty_counts: dict[str, int] = {level: 0 for level in DIFFICULTY_LEVEL_ORDER}
    difficulty_by_category: dict[str, dict[str, int]] = {}
    primary_category_counts: dict[str, int] = {}
    capability_counts: dict[str, int] = {}
    traceability: list[dict[str, Any]] = []
    difficulty_target = _difficulty_target_from_payload(plan_source, selection_context)

    for item in questions:
        if isinstance(item, dict):
            qid = str(item.get("id") or "")
            category = str(item.get("category") or "unknown")
            category_counts[category] = category_counts.get(category, 0) + 1
            level = normalize_difficulty_level(item.get("difficulty_level") or item.get("difficulty"))
            if level:
                difficulty_counts[level] = difficulty_counts.get(level, 0) + 1
                if category not in difficulty_by_category:
                    difficulty_by_category[category] = {item_level: 0 for item_level in DIFFICULTY_LEVEL_ORDER}
                difficulty_by_category[category][level] = difficulty_by_category[category].get(level, 0) + 1
                allowed_levels = _allowed_levels_for_category(difficulty_target, category)
                if allowed_levels and level not in allowed_levels:
                    issues.append(f"{qid}: difficulty_level={level} 超出 {category} 允许范围: {', '.join(allowed_levels)}")
            source_trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
            primary_category = str(item.get("primary_category") or source_trace.get("primary_category") or "").strip()
            if primary_category:
                primary_category_counts[primary_category] = primary_category_counts.get(primary_category, 0) + 1
            for capability_id in _question_capabilities(item):
                capability_counts[capability_id] = capability_counts.get(capability_id, 0) + 1
            if not qid:
                issues.append("存在题目缺少 id")
            elif qid in ids:
                issues.append(f"存在重复题目 id: {qid}")
            else:
                ids.add(qid)
            marker = question_source_marker(item)
            source_markers.append(marker)
            if marker in FALLBACK_SOURCE_STATUSES or "fallback" in marker:
                fallback_count += 1
            traceability.append(
                build_traceability_entry(
                    kind="question",
                    ref=qid or marker or "question",
                    title=item.get("title") or item.get("question") or item.get("prompt") or qid or "question",
                    detail=item.get("question_role") or category,
                    stage="questions",
                    status=question_traceability_status(item, marker),
                    locator=question_traceability_locator(item),
                )
            )
        if isinstance(item, dict) and language_policy.get("localization_required") and language_policy.get("user_facing_language"):
            warnings.extend(_collect_question_language_warnings(item, str(language_policy.get("user_facing_language") or "")))
        issues.extend(validate_question_item(item))
        if isinstance(item, dict) and str(item.get("type") or "").strip() in {"code", "function"}:
            issues.extend(f"{str(item.get('id') or '<missing-id>')}: {issue}" for issue in preflight_code_question_tests(item))

    content_generation = selection_context.get("content_question_generation") if isinstance(selection_context.get("content_question_generation"), dict) else {}
    grounded_generation_shortfalls = normalize_string_list(content_generation.get("grounded_generation_shortfalls") or [])
    bank_fallback_used = bool(content_generation.get("bank_fallback_used"))
    question_generation_mode = str(plan_source.get("question_generation_mode") or "").strip()
    deterministic_question_review = plan_source.get("deterministic_question_review") if isinstance(plan_source.get("deterministic_question_review"), dict) else {}
    strict_question_review = plan_source.get("strict_question_review") if isinstance(plan_source.get("strict_question_review"), dict) else {}
    aggregated_question_review = plan_source.get("question_review") if isinstance(plan_source.get("question_review"), dict) else {}
    deterministic_repair_summary = summarize_question_repair_plan(deterministic_question_review)
    strict_repair_summary = summarize_question_repair_plan(strict_question_review)
    aggregated_repair_summary = summarize_question_repair_plan(aggregated_question_review)

    missing_trace_count = sum(1 for marker in source_markers if marker == "missing-source-trace")
    if missing_trace_count:
        issues.append(f"存在 {missing_trace_count} 道题缺少可靠 source grounding")
    if questions and fallback_count == len(questions):
        issues.append("所有题目均为 fallback 来源，未能形成可靠 source grounding")
    if questions and not category_counts.get("concept"):
        warnings.append("本次 payload 没有 concept 题")
    if bank_fallback_used:
        issues.append("当前配置不允许题库兜底，但检测到 bank fallback")
    if grounded_generation_shortfalls:
        issues.append("grounded 题目生成不足：" + "；".join(grounded_generation_shortfalls))
    if question_generation_mode == "grounded-generation-missing":
        issues.append("question_generation_mode=grounded-generation-missing，当前应阻断并重生成")

    scope_plan_issues, scope_plan_warnings = _validate_scope_plan_alignment(
        data,
        questions,
        category_counts,
        difficulty_counts,
        capability_counts,
        plan_source,
        selection_context,
    )
    issues.extend(scope_plan_issues)
    warnings.extend(scope_plan_warnings)

    for category, actual_levels in sorted(difficulty_by_category.items()):
        expected_distribution = _distribution_target_for_category(difficulty_target, category)
        for level, expected_count in sorted(expected_distribution.items()):
            actual_count = actual_levels.get(level, 0)
            if actual_count != expected_count:
                issues.append(f"{category} 难度分布不符合目标: {level} {actual_count}/{expected_count}")

    difficulty_review = strict_question_review.get("difficulty_review") if isinstance(strict_question_review.get("difficulty_review"), dict) else {}
    if difficulty_review and not bool(difficulty_review.get("valid", True)):
        review_issues = normalize_string_list(difficulty_review.get("issues") or [])
        issues.append("strict_question_review difficulty_review 未通过" + ("：" + "；".join(review_issues[:4]) if review_issues else ""))
    aggregated_difficulty_review = aggregated_question_review.get("difficulty_review") if isinstance(aggregated_question_review.get("difficulty_review"), dict) else {}
    if aggregated_difficulty_review and not bool(aggregated_difficulty_review.get("valid", True)):
        review_issues = normalize_string_list(aggregated_difficulty_review.get("issues") or [])
        issues.append("question_review difficulty_review 未通过" + ("：" + "；".join(review_issues[:4]) if review_issues else ""))

    if semantic_profile in {"initial-test", "stage-test"}:
        if not semantic_trace.get("assessment_kind"):
            issues.append(f"{semantic_profile} 缺少 assessment_kind")
        if semantic_trace.get("session_intent") != "assessment":
            issues.append(f"{semantic_profile} 的 session_intent 必须为 assessment")
        if not semantic_trace.get("target_capability_ids"):
            issues.append(f"{semantic_profile} 缺少 target_capability_ids")
        if semantic_profile == "initial-test" and not semantic_trace.get("diagnostic_generation_mode"):
            issues.append("initial-test 缺少 diagnostic_generation_mode")

        missing_primary_categories = [category for category in required_primary_categories if primary_category_counts.get(category, 0) <= 0]
        if missing_primary_categories:
            issues.append(f"{semantic_profile} 缺少 required_primary_categories: {', '.join(missing_primary_categories[:6])}")
        missing_capability_coverage = [capability for capability in required_capability_coverage if capability_counts.get(capability, 0) <= 0]
        if missing_capability_coverage:
            issues.append(f"{semantic_profile} 缺少 required_capability_coverage: {', '.join(missing_capability_coverage[:6])}")
        if category_counts.get("open", 0) < required_open_question_count:
            issues.append(f"{semantic_profile} open 题数量不足: {category_counts.get('open', 0)}/{required_open_question_count}")
        if category_counts.get("code", 0) < required_code_question_count:
            issues.append(f"{semantic_profile} code 题数量不足: {category_counts.get('code', 0)}/{required_code_question_count}")

    if strict_question_review and not bool(strict_question_review.get("valid")):
        strict_issues = normalize_string_list(strict_question_review.get("issues") or [])
        strict_failure_summary = strict_repair_summary.get("failure_summary") if isinstance(strict_repair_summary, dict) else []
        issues.append(
            "strict_question_review 未通过"
            + ("：" + "；".join(strict_issues[:4]) if strict_issues else "")
            + ("；repair=" + "，".join(normalize_string_list(strict_failure_summary)[:4]) if strict_failure_summary else "")
        )
    if deterministic_question_review and not bool(deterministic_question_review.get("valid")):
        deterministic_issues = normalize_string_list(deterministic_question_review.get("issues") or [])
        deterministic_failure_summary = deterministic_repair_summary.get("failure_summary") if isinstance(deterministic_repair_summary, dict) else []
        issues.append(
            "deterministic_question_review 未通过"
            + ("：" + "；".join(deterministic_issues[:4]) if deterministic_issues else "")
            + ("；repair=" + "，".join(normalize_string_list(deterministic_failure_summary)[:4]) if deterministic_failure_summary else "")
        )
    if aggregated_question_review and not bool(aggregated_question_review.get("valid")):
        aggregated_issues = normalize_string_list(aggregated_question_review.get("issues") or [])
        aggregated_failure_summary = aggregated_repair_summary.get("failure_summary") if isinstance(aggregated_repair_summary, dict) else []
        issues.append(
            "question_review 聚合结论未通过"
            + ("：" + "；".join(aggregated_issues[:4]) if aggregated_issues else "")
            + ("；repair=" + "，".join(normalize_string_list(aggregated_failure_summary)[:6]) if aggregated_failure_summary else "")
        )

    evidence = normalize_string_list(
        [
            *[f"semantic_profile={semantic_profile}"],
            *([f"language_policy={language_policy.get('user_facing_language')}"] if language_policy.get("user_facing_language") else []),
            *([f"assessment_kind={semantic_trace.get('assessment_kind')}"] if semantic_trace.get("assessment_kind") else []),
            *([f"session_intent={semantic_trace.get('session_intent')}"] if semantic_trace.get("session_intent") else []),
            *([f"diagnostic_generation_mode={semantic_trace.get('diagnostic_generation_mode')}"] if semantic_trace.get("diagnostic_generation_mode") else []),
            *[f"题目总数 {len(questions)}"],
            *[f"fallback 题数 {fallback_count}"],
            *[f"类别 {key}:{value}" for key, value in sorted(category_counts.items())],
            *[f"难度 {key}:{value}" for key, value in sorted(difficulty_counts.items()) if value],
            *([f"required_primary_categories={','.join(required_primary_categories[:6])}"] if required_primary_categories else []),
            *([f"required_capability_coverage={','.join(required_capability_coverage[:6])}"] if required_capability_coverage else []),
            *([f"strict_review={strict_question_review.get('verdict')}"] if strict_question_review else []),
            *([f"deterministic_review={deterministic_question_review.get('verdict')}"] if deterministic_question_review else []),
            *([f"strict_repair={'|'.join(normalize_string_list(strict_repair_summary.get('failure_summary') or [])[:3])}"] if strict_question_review else []),
            *([f"deterministic_repair={'|'.join(normalize_string_list(deterministic_repair_summary.get('failure_summary') or [])[:3])}"] if deterministic_question_review else []),
            *([f"aggregated_repair={'|'.join(normalize_string_list(aggregated_repair_summary.get('failure_summary') or [])[:4])}"] if aggregated_question_review else []),
            *source_markers[:6],
        ]
    )[:24]

    confidence = 0.85 if not issues else 0.35
    if warnings:
        confidence = min(confidence, 0.65)
    if questions and fallback_count == len(questions):
        confidence = min(confidence, 0.45)

    result = {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "question_count": len(questions),
        "category_counts": category_counts,
        "difficulty_counts": {key: value for key, value in difficulty_counts.items() if value},
        "difficulty_by_category": difficulty_by_category,
        "primary_category_counts": primary_category_counts,
        "capability_counts": capability_counts,
        "fallback_count": fallback_count,
        "source_markers": source_markers[:20],
        "semantic_trace": semantic_trace,
        "repair_summary": {
            "deterministic": deterministic_repair_summary,
            "strict": strict_repair_summary,
            "aggregated": aggregated_repair_summary,
        },
    }

    if aggregated_repair_summary.get("failure_summary"):
        for item in normalize_string_list(aggregated_repair_summary.get("failure_summary") or [])[:8]:
            traceability.append(
                build_traceability_entry(
                    kind="repair-gap",
                    ref=item,
                    title=item,
                    detail="question_review.repair_plan",
                    stage="questions",
                    status="needs-revision",
                )
            )

    traceability.append(
        build_traceability_entry(
            kind="session-semantics",
            ref=semantic_profile,
            title=semantic_profile,
            detail=(semantic_trace.get("assessment_kind") or semantic_trace.get("session_intent") or "session-semantics"),
            stage="questions",
            status="validated" if not issues else "needs-revision",
        )
    )

    return apply_quality_envelope(
        result,
        stage="questions",
        generator="runtime-question-validation",
        evidence=evidence,
        confidence=confidence,
        quality_review={
            "reviewer": "runtime-question-quality-gate",
            "valid": not issues,
            "issues": issues,
            "warnings": warnings,
            "confidence": confidence,
            "evidence_adequacy": "sufficient" if not issues else "partial",
            "verdict": "ready" if not issues else "needs-revision",
        },
        generation_trace={
            "stage": "questions",
            "generator": "runtime-question-validation",
            "status": "validated",
            "question_count": len(questions),
            "fallback_count": fallback_count,
            "semantic_profile": semantic_profile,
            "assessment_kind": semantic_trace.get("assessment_kind"),
            "session_intent": semantic_trace.get("session_intent"),
        },
        traceability=traceability[:24],
    )


def ensure_questions_payload_quality(data: dict[str, Any]) -> dict[str, Any]:
    result = validate_questions_payload(data)
    review = result.get("quality_review") if isinstance(result.get("quality_review"), dict) else {}
    issues = normalize_string_list(review.get("issues") or result.get("issues"))
    if not bool(review.get("valid", result.get("valid"))):
        raise ValueError("questions.json 质量校验失败: " + "；".join(issues[:8]))
    return result


__all__ = [
    "FALLBACK_SOURCE_STATUSES",
    "REQUIRED_TOP_LEVEL",
    "ensure_questions_payload_quality",
    "question_has_answer_and_explanation",
    "question_source_marker",
    "question_traceability_locator",
    "question_traceability_status",
    "validate_question_item",
    "validate_questions_payload",
]
