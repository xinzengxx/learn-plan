from __future__ import annotations

import ast
import traceback
from typing import Any


MAX_FAILED_CASE_SUMMARIES = 3

TEST_GRADE_OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}
CANONICAL_QUESTION_TYPES = {"code", "sql", *TEST_GRADE_OBJECTIVE_TYPES}
LEGACY_OBJECTIVE_TYPE_MAP = {
    "single": "single_choice",
    "multi": "multiple_choice",
    "judge": "true_false",
}
BLOCKED_FREE_TEXT_TYPES = {"open", "written", "short_answer", "free_text"}
FORBIDDEN_TEST_GRADE_TYPES = set(BLOCKED_FREE_TEXT_TYPES)
QUESTION_SCOPE_SCHEMA_VERSION = "learn-plan.question_scope.v1"
QUESTION_PLAN_SCHEMA_VERSION = "learn-plan.question_plan.v1"
PARAMETER_SPEC_SCHEMA_VERSION = "learn-plan.parameter_spec.v1"
PARAMETER_ARTIFACT_SCHEMA_VERSION = "learn-plan.parameter_artifact.v1"
DATASET_ARTIFACT_SCHEMA_VERSION = "learn-plan.dataset_artifact.v1"
QUESTION_SCOPE_SOURCE_PROFILES = {"today-lesson", "initial-diagnostic", "history-stage-test"}
RUNTIME_NAMES = {"python", "mysql"}
PARAMETER_VALUE_TYPES = {"json", "python_literal", "dataframe", "series", "sql_table", "ndarray", "tensor"}
DATASET_KINDS = {"dataframe", "series", "sql_table"}
TABULAR_PARAMETER_TYPES = {"dataframe", "series", "sql_table"}
VISIBILITY_VALUES = {"public", "hidden"}
DIFFICULTY_LEVEL_ORDER = ["basic", "medium", "upper_medium", "hard"]
DIFFICULTY_LEVELS = set(DIFFICULTY_LEVEL_ORDER)
DIFFICULTY_LABELS = {
    "basic": "基础题",
    "medium": "中等题",
    "upper_medium": "中难题",
    "hard": "难题",
}
DIFFICULTY_DEFAULT_SCORES = {
    "basic": 1,
    "medium": 2,
    "upper_medium": 3,
    "hard": 4,
}
TRANSFER_DISTANCE_VALUES = {"direct", "near", "far"}
IMPLEMENTATION_COMPLEXITY_VALUES = {"none", "single_step", "multi_step", "stateful"}
TRAP_DENSITY_VALUES = {"low", "medium", "high"}
OPTION_DIAGNOSTIC_ROLES = {"correct_concept", "distractor", "edge_case", "prerequisite_probe", "wording_probe", "question_quality"}
OPTION_DIAGNOSTIC_RELEVANCE_VALUES = {"primary", "supporting", "related"}
NEW_QUESTION_SOURCES = {"agent-injected", "runtime-generated", "harness-injected", "runtime-normalized"}
LOW_INFORMATION_OPTION_MARKERS = ("以上都对", "以上皆对", "以上都不对", "以上皆不对", "都对", "都不对", "都有可能", "无法判断")
SYNTHETIC_DIAGNOSTIC_QUESTIONS = {"你为什么认为这个选项成立或不成立？"}
DIFFICULTY_ALIASES = {
    "easy": "basic",
    "基础": "basic",
    "基础题": "basic",
    "basic": "basic",
    "medium": "medium",
    "中等": "medium",
    "中等题": "medium",
    "进阶": "medium",
    "upper-medium": "upper_medium",
    "upper_medium": "upper_medium",
    "upper medium": "upper_medium",
    "uppermedium": "upper_medium",
    "中难": "upper_medium",
    "中难题": "upper_medium",
    "中上": "upper_medium",
    "hard": "hard",
    "困难": "hard",
    "难题": "hard",
    "挑战": "hard",
}
REQUIRED_DIFFICULTY_FIELDS = [
    "difficulty_level",
    "difficulty_label",
    "difficulty_score",
    "difficulty_reason",
    "expected_failure_mode",
]
REQUIRED_CODE_QUESTION_FIELDS = [
    "problem_statement",
    "input_spec",
    "output_spec",
    "calculation_spec",
    "constraints",
    "examples",
    "public_tests",
    "hidden_tests",
    "scoring_rubric",
    "capability_tags",
]
REQUIRED_OBJECTIVE_QUESTION_FIELDS = [
    "title",
    "prompt",
    "options",
    "explanation",
    "scoring_rubric",
    "capability_tags",
]
QUESTION_AUTHORING_METADATA_FIELDS = {
    "assessment_intent",
    "knowledge_scope",
    "question_type_rationale",
    "coverage_units",
    "difficulty_profile",
}
TRUE_FALSE_REQUIRED_COVERAGE_UNITS = {"statement", "truth_rationale", "boundary_or_counterexample"}
CODE_COVERAGE_UNIT_TYPES = {"subtask", "test", "test_case", "public_test", "hidden_test", "rubric", "rubric_item"}
REQUIRED_SUBMIT_RESULT_FIELDS = [
    "question_id",
    "question_type",
    "status",
    "passed_public_count",
    "total_public_count",
    "passed_hidden_count",
    "total_hidden_count",
    "failed_case_summaries",
    "failure_types",
    "capability_tags",
    "submitted_at",
]


REQUIRED_QUESTIONS_TOP_LEVEL = [
    "date",
    "topic",
    "mode",
    "session_type",
    "session_intent",
    "assessment_kind",
    "test_mode",
    "language_policy",
    "plan_source",
    "materials",
    "questions",
]

REQUIRED_PROGRESS_TOP_LEVEL = [
    "date",
    "topic",
    "session",
    "summary",
    "context",
    "reading_progress",
    "material_alignment",
    "mastery_checks",
    "artifacts",
    "reflection",
    "learning_state",
    "progression",
    "update_history",
    "questions",
    "result_summary",
]

REQUIRED_PROGRESS_CONTEXT_FIELDS = [
    "plan_execution_mode",
    "session_intent",
    "assessment_kind",
    "round_index",
    "max_rounds",
    "questions_per_round",
    "follow_up_needed",
    "stop_reason",
    "plan_source_snapshot",
]

REQUIRED_PROGRESS_SESSION_FIELDS = [
    "type",
    "intent",
    "assessment_kind",
    "plan_execution_mode",
    "test_mode",
    "round_index",
    "max_rounds",
    "questions_per_round",
    "follow_up_needed",
    "stop_reason",
    "status",
    "started_at",
    "finished_at",
    "plan_path",
    "resume_topic",
    "resume_goal",
    "resume_level",
    "resume_schedule",
    "resume_preference",
    "materials",
    "source_kind",
]


def normalize_question_type(value: Any) -> str:
    qtype = str(value or "").strip()
    return LEGACY_OBJECTIVE_TYPE_MAP.get(qtype, qtype)


def normalize_difficulty_level(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    key = text.lower().replace("-", "_").replace(" ", "_")
    return DIFFICULTY_ALIASES.get(key) or DIFFICULTY_ALIASES.get(text.lower())


def difficulty_rank(value: Any) -> int:
    level = normalize_difficulty_level(value)
    if not level:
        return -1
    return DIFFICULTY_LEVEL_ORDER.index(level)


def compare_difficulty_levels(left: Any, right: Any) -> int:
    return difficulty_rank(left) - difficulty_rank(right)


def _normalize_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result >= 0 else default


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "是", "需要", "组合", "combined", "combination"}


def _normalize_enum(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in allowed else default


def normalize_difficulty_dimensions(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    return {
        "knowledge_point_count": _normalize_non_negative_int(data.get("knowledge_point_count"), 0),
        "requires_concept_combination": _normalize_bool(data.get("requires_concept_combination") or data.get("concept_combination")),
        "reasoning_steps": _normalize_non_negative_int(data.get("reasoning_steps"), 0),
        "boundary_condition_count": _normalize_non_negative_int(data.get("boundary_condition_count"), 0),
        "transfer_distance": _normalize_enum(data.get("transfer_distance"), TRANSFER_DISTANCE_VALUES, "direct"),
        "implementation_complexity": _normalize_enum(data.get("implementation_complexity"), IMPLEMENTATION_COMPLEXITY_VALUES, "none"),
        "trap_density": _normalize_enum(data.get("trap_density"), TRAP_DENSITY_VALUES, "low"),
    }


def difficulty_dimensions_present(value: Any) -> bool:
    return isinstance(value, dict) and any(key in value for key in (
        "knowledge_point_count",
        "requires_concept_combination",
        "concept_combination",
        "reasoning_steps",
        "boundary_condition_count",
        "transfer_distance",
        "implementation_complexity",
        "trap_density",
    ))


def validate_difficulty_dimensions(value: Any, *, context: str = "difficulty_dimensions") -> list[str]:
    if not isinstance(value, dict):
        return [f"{context}.not_object"]
    issues: list[str] = []
    for field in ("knowledge_point_count", "reasoning_steps", "boundary_condition_count"):
        if field in value:
            try:
                number = int(value.get(field))
            except (TypeError, ValueError):
                issues.append(f"{context}.{field}_invalid")
                continue
            if number < 0:
                issues.append(f"{context}.{field}_invalid")
    if "transfer_distance" in value and _normalize_enum(value.get("transfer_distance"), TRANSFER_DISTANCE_VALUES, "") not in TRANSFER_DISTANCE_VALUES:
        issues.append(f"{context}.transfer_distance_invalid")
    if "implementation_complexity" in value and _normalize_enum(value.get("implementation_complexity"), IMPLEMENTATION_COMPLEXITY_VALUES, "") not in IMPLEMENTATION_COMPLEXITY_VALUES:
        issues.append(f"{context}.implementation_complexity_invalid")
    if "trap_density" in value and _normalize_enum(value.get("trap_density"), TRAP_DENSITY_VALUES, "") not in TRAP_DENSITY_VALUES:
        issues.append(f"{context}.trap_density_invalid")
    return issues


def infer_min_difficulty_from_dimensions(value: Any) -> str:
    dimensions = normalize_difficulty_dimensions(value)
    level = "basic"

    def raise_to(candidate: str) -> None:
        nonlocal level
        if compare_difficulty_levels(candidate, level) > 0:
            level = candidate

    knowledge_points = dimensions["knowledge_point_count"]
    reasoning_steps = dimensions["reasoning_steps"]
    boundary_count = dimensions["boundary_condition_count"]
    if knowledge_points >= 2 or reasoning_steps >= 2 or boundary_count >= 2:
        raise_to("medium")
    if dimensions["transfer_distance"] == "near":
        raise_to("medium")
    if dimensions["requires_concept_combination"] and knowledge_points >= 2:
        raise_to("medium")
    if dimensions["implementation_complexity"] in {"single_step", "multi_step", "stateful"} and (reasoning_steps >= 2 or boundary_count >= 2):
        raise_to("medium")

    if knowledge_points >= 3 or reasoning_steps >= 4 or boundary_count >= 4:
        raise_to("upper_medium")
    if dimensions["requires_concept_combination"] and (knowledge_points >= 3 or reasoning_steps >= 3):
        raise_to("upper_medium")
    if dimensions["implementation_complexity"] in {"multi_step", "stateful"}:
        raise_to("upper_medium")
    if dimensions["trap_density"] == "high":
        raise_to("upper_medium")

    if dimensions["transfer_distance"] == "far":
        raise_to("hard")
    if dimensions["implementation_complexity"] == "stateful" and (knowledge_points >= 3 or boundary_count >= 3):
        raise_to("hard")
    if knowledge_points >= 5 or reasoning_steps >= 6 or boundary_count >= 6:
        raise_to("hard")
    return level


def _normalize_string_list_value(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [text for item in value if (text := str(item or "").strip())]
    text = str(value or "").strip()
    return [text] if text else []


def _planned_item_requires_combination(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return text not in {"", "none", "false", "0", "no", "否", "无需", "不需要", "single", "separate"}


def _planned_item_difficulty_dimensions(planned: dict[str, Any]) -> dict[str, Any] | None:
    raw = planned.get("difficulty_dimensions")
    if difficulty_dimensions_present(raw):
        return raw
    knowledge_ids = _normalize_string_list_value(
        planned.get("knowledge_point_ids")
        or planned.get("knowledge_points")
        or planned.get("target_concepts")
        or []
    )
    if not knowledge_ids and planned.get("combination_requirement") is None:
        return None
    return {
        "knowledge_point_count": len(knowledge_ids),
        "requires_concept_combination": _planned_item_requires_combination(planned.get("combination_requirement")),
    }


def normalize_question_difficulty_fields(item: dict[str, Any]) -> dict[str, Any]:
    raw_level = item.get("difficulty_level") or item.get("difficulty")
    level = normalize_difficulty_level(raw_level)
    result: dict[str, Any] = {}
    if level:
        result["difficulty_level"] = level
        result["difficulty"] = level
        result["difficulty_label"] = str(item.get("difficulty_label") or DIFFICULTY_LABELS[level]).strip()
        try:
            result["difficulty_score"] = int(item.get("difficulty_score") or DIFFICULTY_DEFAULT_SCORES[level])
        except (TypeError, ValueError):
            result["difficulty_score"] = item.get("difficulty_score")
    for key in ("difficulty_reason", "expected_failure_mode"):
        if key in item:
            result[key] = item.get(key)
    return result


def validate_question_difficulty_fields(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.difficulty.not_object"]
    for field in REQUIRED_DIFFICULTY_FIELDS:
        if not _has_non_empty_value(item, field):
            issues.append(f"question.difficulty.{field}_missing")
    level = normalize_difficulty_level(item.get("difficulty_level"))
    if not level:
        issues.append("question.difficulty.level_invalid")
    legacy_level = normalize_difficulty_level(item.get("difficulty")) if item.get("difficulty") else None
    if level and legacy_level and legacy_level != level:
        issues.append("question.difficulty.legacy_conflict")
    label = str(item.get("difficulty_label") or "").strip()
    if level and label and label != DIFFICULTY_LABELS[level]:
        issues.append("question.difficulty.label_mismatch")
    try:
        score = int(item.get("difficulty_score"))
    except (TypeError, ValueError):
        score = 0
    if score not in {1, 2, 3, 4}:
        issues.append("question.difficulty.score_invalid")
    elif level and score != DIFFICULTY_DEFAULT_SCORES[level]:
        issues.append("question.difficulty.score_mismatch")
    return issues


def _has_non_empty_value(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    if value in (None, ""):
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _case_has_expected(case: Any) -> bool:
    if not isinstance(case, dict):
        return False
    return any(key in case for key in ("expected", "expected_output", "expected_rows", "expected_records", "expected_code"))


def _function_parameter_names(item: dict[str, Any]) -> list[str]:
    return _parameter_names_from_signature(str(item.get("function_signature") or "").strip())


def _parameter_names_from_signature(signature: str) -> list[str]:
    signature = signature.strip()
    if not signature:
        return []
    expression = signature if signature.startswith("def ") else f"def {signature}:\n    pass"
    try:
        module = ast.parse(expression)
    except SyntaxError:
        return []
    if not module.body or not isinstance(module.body[0], ast.FunctionDef):
        return []
    args = module.body[0].args
    return [arg.arg for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs] if arg.arg != "self"]


def _starter_code_parameter_names(item: dict[str, Any]) -> list[str]:
    starter_code = str(item.get("starter_code") or "").strip()
    if not starter_code:
        return []
    try:
        module = ast.parse(starter_code)
    except SyntaxError:
        return []
    function_name = str(item.get("function_name") or "").strip()
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and (not function_name or node.name == function_name):
            args = node.args
            return [arg.arg for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs] if arg.arg != "self"]
    return []


def _case_argument_contract_valid(case: Any, parameter_names: list[str], single_object_input: bool) -> bool:
    if not isinstance(case, dict) or not _case_has_expected(case):
        return False
    has_args = "args" in case or "args_code" in case
    has_kwargs = "kwargs" in case or "kwargs_code" in case
    has_input = "input" in case or "input_code" in case
    if sum(1 for present in (has_args, has_kwargs, has_input) if present) != 1:
        return False
    parameter_count = len(parameter_names)
    if has_args:
        if "args" in case:
            args = case.get("args")
            if not isinstance(args, list):
                return False
            if parameter_count > 0 and len(args) != parameter_count:
                return False
        return True
    if has_kwargs:
        if "kwargs" in case:
            kwargs = case.get("kwargs")
            if not isinstance(kwargs, dict):
                return False
            if parameter_names and set(kwargs.keys()) != set(parameter_names):
                return False
        return True
    if has_input:
        if single_object_input or parameter_count <= 1:
            return True
        return False
    return False


def _validate_code_cases_argument_contract(item: dict[str, Any], field: str) -> list[str]:
    cases = item.get(field) if isinstance(item.get(field), list) else []
    parameter_names = _function_parameter_names(item)
    single_object_input = bool(item.get("single_object_input"))
    if any(not _case_argument_contract_valid(case, parameter_names, single_object_input) for case in cases):
        return [f"question.code.{field}.argument_contract_invalid"]
    return []


def _build_case_call(case: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    if "args" in case:
        args = case.get("args")
        if not isinstance(args, list):
            raise TypeError("args must be list")
        return args, {}
    if "kwargs" in case:
        kwargs = case.get("kwargs")
        if not isinstance(kwargs, dict):
            raise TypeError("kwargs must be object")
        return [], kwargs
    if "input" in case:
        return [case.get("input")], {}
    return [], {}


def _case_expected(case: dict[str, Any], namespace: dict[str, Any]) -> Any:
    if case.get("expected_code") is not None:
        return eval(str(case.get("expected_code")), namespace, namespace)
    for key in ("expected", "expected_output", "expected_rows", "expected_records"):
        if key in case:
            return case.get(key)
    return None


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return "<unreprable>"


def _compare_values(actual: Any, expected: Any) -> bool:
    if hasattr(actual, "equals") and callable(actual.equals):
        try:
            return bool(actual.equals(expected))
        except Exception:
            pass
    try:
        compared = actual == expected
        if isinstance(compared, bool):
            return compared
    except Exception:
        pass
    return _safe_repr(actual) == _safe_repr(expected)


def preflight_code_question_tests(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.code.preflight.not_object"]
    solution_code = str(item.get("solution_code") or item.get("expected_code") or item.get("reference_solution") or "").strip()
    if not solution_code:
        return ["question.code.preflight.solution_missing"]
    function_name = str(item.get("function_name") or "").strip()
    if not function_name:
        signature_names = _function_parameter_names(item)
        signature = str(item.get("function_signature") or "").strip()
        if signature and "(" in signature:
            function_name = signature.split("(", 1)[0].replace("def ", "").strip()
        if not function_name and signature_names:
            function_name = str(item.get("id") or "")
    try:
        namespace: dict[str, Any] = {}
        exec(solution_code, namespace, namespace)
        func = namespace[function_name]
    except Exception as exc:
        return [f"question.code.preflight.solution_runtime_error:{''.join(traceback.format_exception_only(type(exc), exc)).strip()}"]
    for field, category in (("public_tests", "public"), ("hidden_tests", "hidden")):
        cases = item.get(field) if isinstance(item.get(field), list) else []
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                issues.append(f"question.code.preflight.{category}.{index}.argument_contract")
                continue
            try:
                args, kwargs = _build_case_call(case)
                expected = _case_expected(case, namespace)
                actual = func(*args, **kwargs)
            except Exception:
                issues.append(f"question.code.preflight.{category}.{index}.runtime_error")
                continue
            if not _compare_values(actual, expected):
                issues.append(f"question.code.preflight.{category}.{index}.wrong_answer")
    return issues


def validate_code_question_contract(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.code.not_object"]
    if str(item.get("type") or "").strip() != "code" or str(item.get("category") or "").strip() != "code":
        issues.append("question.code.type_invalid")
    if not str(item.get("id") or "").strip():
        issues.append("question.code.id_missing")
    if not str(item.get("title") or "").strip():
        issues.append("question.code.title_missing")
    for field in REQUIRED_CODE_QUESTION_FIELDS:
        if not _has_non_empty_value(item, field):
            issues.append(f"question.code.{field}_missing")
    examples = item.get("examples") if isinstance(item.get("examples"), list) else []
    if examples and not all(isinstance(example, dict) and example.get("input") is not None and "output" in example and str(example.get("explanation") or "").strip() for example in examples):
        issues.append("question.code.examples_invalid")
    hidden_tests = item.get("hidden_tests") if isinstance(item.get("hidden_tests"), list) else []
    if hidden_tests and not all(_case_has_expected(case) for case in hidden_tests):
        issues.append("question.code.hidden_tests_invalid")
    public_tests = item.get("public_tests") if isinstance(item.get("public_tests"), list) else []
    if public_tests and not all(_case_has_expected(case) for case in public_tests):
        issues.append("question.code.public_tests_invalid")
    if not (str(item.get("function_signature") or "").strip() or str(item.get("function_name") or "").strip()):
        issues.append("question.code.function_signature_missing")
    if not str(item.get("starter_code") or "").strip():
        issues.append("question.code.starter_code_missing")
    signature_params = _function_parameter_names(item)
    starter_params = _starter_code_parameter_names(item)
    if signature_params and starter_params and signature_params != starter_params:
        issues.append("question.code.starter_code_signature_mismatch")
    issues.extend(_validate_code_cases_argument_contract(item, "public_tests"))
    issues.extend(_validate_code_cases_argument_contract(item, "hidden_tests"))
    return issues


def _normalize_confidence_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 1:
        return None
    return number


def _diagnostic_ref_ids(value: Any) -> list[str]:
    values = value if isinstance(value, list) else []
    ids: list[str] = []
    for item in values:
        if isinstance(item, dict):
            ref_id = str(item.get("id") or item.get("knowledge_point_id") or item.get("misconception_id") or "").strip()
        else:
            ref_id = str(item or "").strip()
        if ref_id:
            ids.append(ref_id)
    return ids


def _validate_diagnostic_refs(value: Any, *, context: str, require_relevance: bool = False) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"{context}.not_list"]
    issues: list[str] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            if not item.strip():
                issues.append(f"{context}.{index}.id_missing")
            continue
        if not isinstance(item, dict):
            issues.append(f"{context}.{index}.not_object")
            continue
        ref_id = str(item.get("id") or item.get("knowledge_point_id") or item.get("misconception_id") or "").strip()
        if not ref_id:
            issues.append(f"{context}.{index}.id_missing")
        if "confidence" in item and _normalize_confidence_float(item.get("confidence")) is None:
            issues.append(f"{context}.{index}.confidence_invalid")
        relevance = str(item.get("relevance") or "").strip()
        if require_relevance and relevance not in OPTION_DIAGNOSTIC_RELEVANCE_VALUES:
            issues.append(f"{context}.{index}.relevance_invalid")
    return issues


def _is_low_information_option(value: Any) -> bool:
    text = str(value or "").strip().replace(" ", "")
    return any(marker in text for marker in LOW_INFORMATION_OPTION_MARKERS)


def _is_new_question_artifact(item: dict[str, Any]) -> bool:
    source_trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
    candidates = {
        str(item.get("source_status") or "").strip(),
        str(item.get("question_source") or "").strip(),
        str(source_trace.get("question_source") or "").strip(),
        str(source_trace.get("diagnostic_generation_mode") or "").strip(),
    }
    return bool(candidates & NEW_QUESTION_SOURCES)


def validate_option_diagnostics_contract(item: dict[str, Any]) -> list[str]:
    qtype = str(item.get("type") or "").strip()
    if qtype not in {"single_choice", "multiple_choice"}:
        return []
    options = item.get("options") if isinstance(item.get("options"), list) else []
    diagnostics = item.get("option_diagnostics")
    if not isinstance(diagnostics, list) or not diagnostics:
        return ["question.objective.option_diagnostics_missing"]
    issues: list[str] = []
    if any(_is_low_information_option(option) for option in options):
        issues.append("question.objective.options.low_information_option")
    if len(diagnostics) != len(options):
        issues.append("question.objective.option_diagnostics_count_mismatch")
    seen_indices: set[int] = set()
    for entry_index, diagnostic in enumerate(diagnostics):
        context = f"question.objective.option_diagnostics.{entry_index}"
        if not isinstance(diagnostic, dict):
            issues.append(f"{context}.not_object")
            continue
        index = diagnostic.get("index")
        option_text = str(options[index] if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(options) else "").strip()
        if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(options):
            issues.append(f"{context}.index_invalid")
        elif index in seen_indices:
            issues.append(f"{context}.index_duplicate")
        else:
            seen_indices.add(index)
        for field in ("claim", "diagnostic_role", "evidence_span"):
            if not str(diagnostic.get(field) or "").strip():
                issues.append(f"{context}.{field}_missing")
        role = str(diagnostic.get("diagnostic_role") or "").strip()
        if role and role not in OPTION_DIAGNOSTIC_ROLES:
            issues.append(f"{context}.diagnostic_role_invalid")
        if "confidence" in diagnostic and _normalize_confidence_float(diagnostic.get("confidence")) is None:
            issues.append(f"{context}.confidence_invalid")
        knowledge_ids = _diagnostic_ref_ids(diagnostic.get("knowledge_point_ids"))
        if not knowledge_ids and role != "question_quality":
            issues.append(f"{context}.knowledge_point_ids_missing")
        misconception_ids = _diagnostic_ref_ids(diagnostic.get("misconception_ids"))
        if role == "distractor" and not misconception_ids:
            issues.append(f"{context}.distractor_misconception_missing")
        issues.extend(_validate_diagnostic_refs(diagnostic.get("knowledge_point_ids"), context=f"{context}.knowledge_point_ids", require_relevance=True))
        issues.extend(_validate_diagnostic_refs(diagnostic.get("prerequisite_ids"), context=f"{context}.prerequisite_ids"))
        issues.extend(_validate_diagnostic_refs(diagnostic.get("misconception_ids"), context=f"{context}.misconception_ids"))
        diagnostic_question = str(diagnostic.get("diagnostic_question") or "").strip()
        if not diagnostic_question:
            issues.append(f"{context}.diagnostic_question_missing")
        elif diagnostic_question in SYNTHETIC_DIAGNOSTIC_QUESTIONS or bool(diagnostic.get("synthetic")) or bool(diagnostic.get("fallback_generated")):
            issues.append(f"{context}.synthetic_or_template_question")
        claim = str(diagnostic.get("claim") or "").strip()
        evidence_span = str(diagnostic.get("evidence_span") or "").strip()
        if option_text and (claim in {f"选项表达的命题：{option_text}", f"选项 {option_text} 关于列表可变性的判断。"} or evidence_span == f"选项文本：{option_text}"):
            issues.append(f"{context}.synthetic_or_template_evidence")
    if len(seen_indices) != len(options):
        issues.append("question.objective.option_diagnostics_index_coverage_missing")
    return issues


def _question_authoring_metadata_present(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    return any(_has_non_empty_value(item, field) for field in QUESTION_AUTHORING_METADATA_FIELDS)


def validate_question_knowledge_scope(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.authoring.knowledge_scope.not_object"]
    scope = item.get("knowledge_scope")
    if not isinstance(scope, dict) or not scope:
        return ["question.authoring.knowledge_scope_missing"]
    knowledge_ids = _diagnostic_ref_ids(scope.get("knowledge_point_ids") or scope.get("knowledge_points"))
    if not knowledge_ids:
        issues.append("question.authoring.knowledge_scope.knowledge_point_ids_missing")
    issues.extend(_validate_diagnostic_refs(scope.get("knowledge_point_ids") or scope.get("knowledge_points"), context="question.authoring.knowledge_scope.knowledge_point_ids", require_relevance=False))
    issues.extend(_validate_diagnostic_refs(scope.get("prerequisite_ids"), context="question.authoring.knowledge_scope.prerequisite_ids"))
    issues.extend(_validate_diagnostic_refs(scope.get("misconception_ids"), context="question.authoring.knowledge_scope.misconception_ids"))
    source_trace = scope.get("source_trace") or scope.get("evidence") or item.get("source_trace") or item.get("evidence_types")
    if not source_trace:
        issues.append("question.authoring.knowledge_scope.source_evidence_missing")
    return issues


def validate_question_type_rationale(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.authoring.question_type_rationale.not_object"]
    rationale = item.get("question_type_rationale")
    if not isinstance(rationale, dict) or not rationale:
        return ["question.authoring.question_type_rationale_missing"]
    qtype = str(item.get("type") or "").strip()
    rationale_type = str(rationale.get("type") or rationale.get("question_type") or "").strip()
    if rationale_type and rationale_type != qtype:
        issues.append("question.authoring.question_type_rationale.type_mismatch")
    for field in ("reason", "assessment_fit"):
        if not str(rationale.get(field) or "").strip():
            issues.append(f"question.authoring.question_type_rationale.{field}_missing")
    if not str(item.get("assessment_intent") or rationale.get("assessment_intent") or "").strip():
        issues.append("question.authoring.assessment_intent_missing")
    return issues


def _coverage_unit_type(unit: dict[str, Any]) -> str:
    return str(unit.get("unit_type") or unit.get("type") or unit.get("kind") or "").strip()


def _coverage_unit_difficulty(unit: dict[str, Any]) -> str | None:
    return normalize_difficulty_level(unit.get("difficulty_level") or unit.get("difficulty"))


def _validate_coverage_unit_refs(unit: dict[str, Any], *, context: str) -> list[str]:
    issues: list[str] = []
    knowledge_ids = _diagnostic_ref_ids(unit.get("knowledge_point_ids") or unit.get("knowledge_points"))
    if not knowledge_ids:
        issues.append(f"{context}.knowledge_point_ids_missing")
    issues.extend(_validate_diagnostic_refs(unit.get("knowledge_point_ids") or unit.get("knowledge_points"), context=f"{context}.knowledge_point_ids", require_relevance=False))
    issues.extend(_validate_diagnostic_refs(unit.get("prerequisite_ids"), context=f"{context}.prerequisite_ids"))
    issues.extend(_validate_diagnostic_refs(unit.get("misconception_ids"), context=f"{context}.misconception_ids"))
    if not str(unit.get("diagnostic_value") or unit.get("rationale") or unit.get("evidence_span") or unit.get("test_intent") or "").strip():
        issues.append(f"{context}.diagnostic_value_missing")
    difficulty = _coverage_unit_difficulty(unit)
    if not difficulty:
        issues.append(f"{context}.difficulty_level_missing")
    return issues


def validate_coverage_units_contract(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.authoring.coverage_units.not_object"]
    qtype = str(item.get("type") or "").strip()
    category = str(item.get("category") or "").strip()
    units = item.get("coverage_units")
    if not isinstance(units, list) or not units:
        return ["question.authoring.coverage_units_missing"]
    for index, unit in enumerate(units):
        context = f"question.authoring.coverage_units.{index}"
        if not isinstance(unit, dict):
            issues.append(f"{context}.not_object")
            continue
        issues.extend(_validate_coverage_unit_refs(unit, context=context))

    if qtype in {"single_choice", "multiple_choice"}:
        options = item.get("options") if isinstance(item.get("options"), list) else []
        seen_option_indices: set[int] = set()
        for index, unit in enumerate(units):
            if not isinstance(unit, dict):
                continue
            option_index = unit.get("option_index", unit.get("index"))
            context = f"question.authoring.coverage_units.{index}"
            if not isinstance(option_index, int) or isinstance(option_index, bool) or option_index < 0 or option_index >= len(options):
                issues.append(f"{context}.option_index_invalid")
                continue
            seen_option_indices.add(option_index)
            role = str(unit.get("diagnostic_role") or "").strip()
            if role and role not in OPTION_DIAGNOSTIC_ROLES:
                issues.append(f"{context}.diagnostic_role_invalid")
            if role == "distractor" and not str(unit.get("distractor_rationale") or unit.get("misconception_rationale") or "").strip():
                issues.append(f"{context}.distractor_rationale_missing")
            if role == "distractor" and not _diagnostic_ref_ids(unit.get("misconception_ids")):
                issues.append(f"{context}.distractor_misconception_missing")
        if len(seen_option_indices) != len(options):
            issues.append("question.authoring.coverage_units.option_coverage_missing")
    elif qtype == "true_false":
        unit_types = {_coverage_unit_type(unit) for unit in units if isinstance(unit, dict)}
        missing_types = TRUE_FALSE_REQUIRED_COVERAGE_UNITS - unit_types
        if missing_types:
            issues.append("question.authoring.coverage_units.true_false_units_missing:" + ",".join(sorted(missing_types)))
    elif qtype in {"code", "sql"} or category == "code":
        if not any(_coverage_unit_type(unit) in CODE_COVERAGE_UNIT_TYPES for unit in units if isinstance(unit, dict)):
            issues.append("question.authoring.coverage_units.code_test_or_rubric_unit_missing")
    return issues


def validate_question_difficulty_profile(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.authoring.difficulty_profile.not_object"]
    profile = item.get("difficulty_profile")
    if not isinstance(profile, dict) or not profile:
        return ["question.authoring.difficulty_profile_missing"]
    claimed = normalize_difficulty_level(item.get("difficulty_level") or item.get("difficulty"))
    profile_level = normalize_difficulty_level(profile.get("difficulty_level") or profile.get("actual_difficulty_level") or profile.get("claimed_difficulty_level"))
    target_level = normalize_difficulty_level(profile.get("target_difficulty_level"))
    if not profile_level:
        issues.append("question.authoring.difficulty_profile.difficulty_level_missing")
    if claimed and profile_level and claimed != profile_level:
        issues.append("question.authoring.difficulty_profile.level_mismatch")
    if target_level and profile_level and compare_difficulty_levels(profile_level, target_level) > 0:
        issues.append("question.authoring.difficulty_profile.above_target")
    if not str(profile.get("difficulty_reason") or profile.get("reason") or item.get("difficulty_reason") or "").strip():
        issues.append("question.authoring.difficulty_profile.reason_missing")
    if not str(profile.get("expected_failure_mode") or item.get("expected_failure_mode") or "").strip():
        issues.append("question.authoring.difficulty_profile.expected_failure_mode_missing")
    dimensions = profile.get("difficulty_dimensions") or item.get("difficulty_dimensions")
    if difficulty_dimensions_present(dimensions):
        issues.extend(validate_difficulty_dimensions(dimensions, context="question.authoring.difficulty_profile.difficulty_dimensions"))
        computed = infer_min_difficulty_from_dimensions(dimensions)
        if profile_level and compare_difficulty_levels(profile_level, computed) < 0:
            issues.append(f"question.authoring.difficulty_profile.below_computed_min:{computed}")
    units = item.get("coverage_units") if isinstance(item.get("coverage_units"), list) else []
    profile_units = profile.get("coverage_units") if isinstance(profile.get("coverage_units"), list) else []
    unit_source = profile_units or units
    for index, unit in enumerate(unit_source):
        if not isinstance(unit, dict):
            continue
        unit_level = _coverage_unit_difficulty(unit)
        if not unit_level:
            issues.append(f"question.authoring.difficulty_profile.coverage_units.{index}.difficulty_level_missing")
        if target_level and unit_level and compare_difficulty_levels(unit_level, target_level) > 0:
            issues.append(f"question.authoring.difficulty_profile.coverage_units.{index}.above_target")
    return issues


def validate_question_authoring_metadata(item: dict[str, Any]) -> list[str]:
    if not isinstance(item, dict):
        return ["question.authoring.not_object"]
    if not _question_authoring_metadata_present(item) and not _is_new_question_artifact(item):
        return []
    issues: list[str] = []
    for field in QUESTION_AUTHORING_METADATA_FIELDS:
        if not _has_non_empty_value(item, field):
            issues.append(f"question.authoring.{field}_missing")
    issues.extend(validate_question_knowledge_scope(item))
    issues.extend(validate_question_type_rationale(item))
    issues.extend(validate_coverage_units_contract(item))
    issues.extend(validate_question_difficulty_profile(item))
    return issues


def validate_objective_question_contract(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.objective.not_object"]
    qtype = str(item.get("type") or "").strip()
    if qtype not in TEST_GRADE_OBJECTIVE_TYPES:
        issues.append("question.objective.type_invalid")
    if not str(item.get("id") or "").strip():
        issues.append("question.objective.id_missing")
    for field in REQUIRED_OBJECTIVE_QUESTION_FIELDS:
        if not _has_non_empty_value(item, field):
            issues.append(f"question.objective.{field}_missing")
    options = item.get("options") if isinstance(item.get("options"), list) else []
    if qtype in {"single_choice", "multiple_choice"} and len(options) < 2:
        issues.append("question.objective.options_invalid")
    if qtype == "true_false" and len(options) not in {0, 2}:
        issues.append("question.objective.options_invalid")
    if qtype == "single_choice" and not isinstance(item.get("answer"), int):
        issues.append("question.objective.answer_missing")
    if qtype == "multiple_choice" and not isinstance(item.get("answers", item.get("answer")), list):
        issues.append("question.objective.answers_missing")
    if qtype == "true_false" and not isinstance(item.get("answer"), (bool, int, str)):
        issues.append("question.objective.answer_missing")
    issues.extend(validate_option_diagnostics_contract(item))
    return issues


def _runtime_values(value: Any) -> list[str]:
    runtimes = value if isinstance(value, list) else [value]
    result: list[str] = []
    for runtime in runtimes:
        text = str(runtime or "").strip().lower()
        if text and text not in result:
            result.append(text)
    return result


def _question_supported_runtimes(item: dict[str, Any]) -> list[str]:
    runtimes = _runtime_values(item.get("supported_runtimes"))
    variants = item.get("runtime_variants") if isinstance(item.get("runtime_variants"), list) else []
    for variant in variants:
        if isinstance(variant, dict):
            runtime = str(variant.get("runtime") or variant.get("name") or "").strip().lower()
            if runtime and runtime not in runtimes:
                runtimes.append(runtime)
    default_runtime = str(item.get("default_runtime") or item.get("runtime") or "").strip().lower()
    if default_runtime and default_runtime not in runtimes:
        runtimes.append(default_runtime)
    return runtimes


def validate_question_runtime_contract(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.runtime.not_object"]
    qid = str(item.get("id") or "<missing-id>").strip()
    runtimes = _question_supported_runtimes(item)
    if runtimes:
        invalid = [runtime for runtime in runtimes if runtime not in RUNTIME_NAMES]
        if invalid:
            issues.append(f"{qid}: question.runtime.unsupported:{','.join(invalid)}")
    variants = item.get("runtime_variants")
    if variants is not None:
        if not isinstance(variants, list) or not variants:
            issues.append(f"{qid}: question.runtime_variants_invalid")
        else:
            for index, variant in enumerate(variants):
                if not isinstance(variant, dict):
                    issues.append(f"{qid}: question.runtime_variants.{index}.not_object")
                    continue
                runtime = str(variant.get("runtime") or variant.get("name") or "").strip().lower()
                if runtime not in RUNTIME_NAMES:
                    issues.append(f"{qid}: question.runtime_variants.{index}.runtime_invalid")
    default_runtime = str(item.get("default_runtime") or "").strip().lower()
    if default_runtime and runtimes and default_runtime not in runtimes:
        issues.append(f"{qid}: question.default_runtime_not_supported")
    return issues


def validate_sql_question_contract(item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(item, dict):
        return ["question.sql.not_object"]
    if str(item.get("type") or "").strip() != "sql" or str(item.get("category") or "").strip() != "code":
        issues.append("question.sql.type_invalid")
    if not str(item.get("id") or "").strip():
        issues.append("question.sql.id_missing")
    for field in ("title", "problem_statement", "input_spec", "output_spec", "constraints", "examples", "scoring_rubric", "capability_tags"):
        if not _has_non_empty_value(item, field):
            issues.append(f"question.sql.{field}_missing")
    runtimes = _question_supported_runtimes(item)
    if "mysql" not in runtimes:
        issues.append("question.sql.mysql_runtime_missing")
    if any(runtime not in {"mysql"} for runtime in runtimes):
        issues.append("question.sql.non_mysql_runtime_not_supported")
    if not str(item.get("starter_sql") or item.get("starter_code") or "").strip():
        issues.append("question.sql.starter_sql_missing")
    if not _has_non_empty_value(item, "result_contract"):
        issues.append("question.sql.result_contract_missing")
    if not (item.get("parameter_spec_ref") or item.get("dataset_refs") or item.get("dataset_ref")):
        issues.append("question.sql.dataset_ref_missing")
    return issues


def validate_test_grade_question(item: dict[str, Any]) -> list[str]:
    if not isinstance(item, dict):
        return ["question.not_object"]
    qtype = str(item.get("type") or "").strip()
    category = str(item.get("category") or "").strip()
    if qtype in BLOCKED_FREE_TEXT_TYPES or category in BLOCKED_FREE_TEXT_TYPES:
        return ["question.open_not_allowed_by_default"]
    if qtype == "sql":
        return validate_sql_question_contract(item)
    if qtype == "code" or category == "code":
        return validate_code_question_contract(item)
    if qtype in LEGACY_OBJECTIVE_TYPE_MAP or category in LEGACY_OBJECTIVE_TYPE_MAP:
        return ["question.test_grade_type_invalid"]
    if qtype in TEST_GRADE_OBJECTIVE_TYPES:
        return validate_objective_question_contract(item)
    return ["question.test_grade_type_invalid"]


def validate_submit_result_contract(result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(result, dict):
        return ["submit_result.not_object"]
    for field in REQUIRED_SUBMIT_RESULT_FIELDS:
        if not _has_non_empty_value(result, field):
            issues.append(f"submit_result.{field}_missing")
    failed_cases = result.get("failed_case_summaries") if isinstance(result.get("failed_case_summaries"), list) else []
    if len(failed_cases) > MAX_FAILED_CASE_SUMMARIES:
        issues.append("submit_result.failed_case_summaries_too_many")
    for index, case in enumerate(failed_cases[:MAX_FAILED_CASE_SUMMARIES]):
        if not isinstance(case, dict):
            issues.append(f"submit_result.failed_case_summaries.{index}.not_object")
            continue
        for field in ("category", "input", "expected", "actual", "error"):
            if field not in case or case.get(field) in (None, ""):
                issues.append(f"submit_result.failed_case_summaries.{index}.{field}_missing")
    return issues


def _list_has_non_empty_value(value: Any) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def _validate_question_scope_semantics(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    source_profile = str(data.get("source_profile") or "").strip()
    session_type = str(data.get("session_type") or "").strip()
    session_intent = str(data.get("session_intent") or "").strip()
    assessment_kind = data.get("assessment_kind")
    if source_profile == "today-lesson":
        if session_type != "today":
            issues.append("question_scope.today.session_type_invalid")
        if session_intent != "learning":
            issues.append("question_scope.today.session_intent_invalid")
        if assessment_kind not in (None, ""):
            issues.append("question_scope.today.assessment_kind_must_be_null")
        if not (_list_has_non_empty_value(data.get("lesson_focus_points")) or _list_has_non_empty_value(data.get("target_concepts"))):
            issues.append("question_scope.today.focus_missing")
    elif source_profile == "initial-diagnostic":
        if session_type != "test":
            issues.append("question_scope.initial.session_type_invalid")
        if session_intent != "assessment":
            issues.append("question_scope.initial.session_intent_invalid")
        if assessment_kind != "initial-test":
            issues.append("question_scope.initial.assessment_kind_invalid")
        if not _list_has_non_empty_value(data.get("target_capability_ids")):
            issues.append("question_scope.initial.target_capability_ids_missing")
        if not _list_has_non_empty_value(data.get("scope_basis")):
            issues.append("question_scope.initial.scope_basis_missing")
        if not isinstance(data.get("diagnostic_strategy"), dict):
            issues.append("question_scope.initial.diagnostic_strategy_missing")
        if not _list_has_non_empty_value(data.get("target_knowledge_point_ids")):
            issues.append("question_scope.initial.target_knowledge_point_ids_missing")
    elif source_profile == "history-stage-test":
        if session_type != "test":
            issues.append("question_scope.history.session_type_invalid")
        if session_intent != "assessment":
            issues.append("question_scope.history.session_intent_invalid")
        if assessment_kind != "stage-test":
            issues.append("question_scope.history.assessment_kind_invalid")
        if not (_list_has_non_empty_value(data.get("target_capability_ids")) or _list_has_non_empty_value(data.get("review_targets"))):
            issues.append("question_scope.history.targets_missing")
        basis_blob = " ".join(str(item) for item in (data.get("scope_basis") or []))
        if not any(token in basis_blob for token in ("progress", "learner_model", "history", "learn-plan", "学习记录", "历史")):
            issues.append("question_scope.history.scope_basis_missing_history")
    return issues


def validate_question_scope_basic(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict) or not data:
        return ["question_scope.not_object"]
    required_fields = [
        "schema_version",
        "scope_id",
        "source_profile",
        "session_type",
        "session_intent",
        "assessment_kind",
        "test_mode",
        "topic",
        "language_policy",
        "scope_basis",
        "target_capability_ids",
        "target_concepts",
        "target_knowledge_point_ids",
        "diagnostic_strategy",
        "review_targets",
        "lesson_focus_points",
        "project_tasks",
        "project_blockers",
        "source_material_refs",
        "difficulty_target",
        "minimum_pass_shape",
        "exclusions",
        "evidence",
        "generation_trace",
    ]
    for field in required_fields:
        if field not in data:
            issues.append(f"question_scope.{field}_missing")
    if data.get("schema_version") != QUESTION_SCOPE_SCHEMA_VERSION:
        issues.append("question_scope.schema_version_invalid")
    if str(data.get("source_profile") or "").strip() not in QUESTION_SCOPE_SOURCE_PROFILES:
        issues.append("question_scope.source_profile_invalid")
    if str(data.get("session_type") or "").strip() not in {"today", "test"}:
        issues.append("question_scope.session_type_invalid")
    if str(data.get("session_intent") or "").strip() not in {"learning", "assessment"}:
        issues.append("question_scope.session_intent_invalid")
    if not isinstance(data.get("language_policy"), dict) or not str((data.get("language_policy") or {}).get("user_facing_language") or "").strip():
        issues.append("question_scope.language_policy_invalid")
    for field in ("scope_basis", "target_capability_ids", "target_concepts", "target_knowledge_point_ids", "review_targets", "lesson_focus_points", "project_tasks", "project_blockers", "source_material_refs", "exclusions", "evidence"):
        if field in data and not isinstance(data.get(field), list):
            issues.append(f"question_scope.{field}_not_list")
    for field in ("difficulty_target", "diagnostic_strategy", "minimum_pass_shape", "generation_trace"):
        if field in data and not isinstance(data.get(field), dict):
            issues.append(f"question_scope.{field}_not_object")
    minimum_pass_shape = data.get("minimum_pass_shape") if isinstance(data.get("minimum_pass_shape"), dict) else {}
    try:
        required_open_count = int(minimum_pass_shape.get("required_open_question_count") or 0)
    except (TypeError, ValueError):
        required_open_count = 0
    if required_open_count > 0:
        issues.append("question_scope.minimum_pass_shape.open_not_allowed_by_test_grade")
    issues.extend(_validate_question_scope_semantics(data))
    return issues


def validate_question_plan_basic(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict) or not data:
        return ["question_plan.not_object"]
    required_fields = [
        "schema_version",
        "plan_id",
        "scope_id",
        "source_profile",
        "session_type",
        "session_intent",
        "assessment_kind",
        "test_mode",
        "topic",
        "question_count",
        "question_mix",
        "difficulty_distribution",
        "diagnostic_value",
        "early_stop_policy",
        "planned_items",
        "coverage_matrix",
        "minimum_pass_shape",
        "forbidden_question_types",
        "generation_guidance",
        "review_checklist",
        "evidence",
        "generation_trace",
    ]
    for field in required_fields:
        if field not in data:
            issues.append(f"question_plan.{field}_missing")
    if data.get("schema_version") != QUESTION_PLAN_SCHEMA_VERSION:
        issues.append("question_plan.schema_version_invalid")
    if str(data.get("source_profile") or "").strip() not in QUESTION_SCOPE_SOURCE_PROFILES:
        issues.append("question_plan.source_profile_invalid")
    if str(data.get("session_type") or "").strip() not in {"today", "test"}:
        issues.append("question_plan.session_type_invalid")
    if str(data.get("session_intent") or "").strip() not in {"learning", "assessment"}:
        issues.append("question_plan.session_intent_invalid")
    try:
        question_count = int(data.get("question_count"))
    except (TypeError, ValueError):
        question_count = 0
    if question_count <= 0:
        issues.append("question_plan.question_count_invalid")
    question_mix = data.get("question_mix") if isinstance(data.get("question_mix"), dict) else {}
    if not question_mix:
        issues.append("question_plan.question_mix_missing")
    mix_total = 0
    for raw_type, raw_count in question_mix.items():
        qtype = normalize_question_type(raw_type)
        if qtype in FORBIDDEN_TEST_GRADE_TYPES:
            issues.append("question_plan.question_mix.forbidden_type")
        if qtype not in CANONICAL_QUESTION_TYPES and qtype not in {"concept"}:
            issues.append(f"question_plan.question_mix.unknown_type:{raw_type}")
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            issues.append(f"question_plan.question_mix.count_invalid:{raw_type}")
            continue
        if count < 0:
            issues.append(f"question_plan.question_mix.count_invalid:{raw_type}")
            continue
        mix_total += count
    if question_count > 0 and mix_total != question_count:
        issues.append("question_plan.question_mix.count_mismatch")
    difficulty_distribution = data.get("difficulty_distribution") if isinstance(data.get("difficulty_distribution"), dict) else {}
    if not difficulty_distribution:
        issues.append("question_plan.difficulty_distribution_missing")
    difficulty_total = 0
    for raw_level, raw_count in difficulty_distribution.items():
        level = normalize_difficulty_level(raw_level)
        if not level:
            issues.append(f"question_plan.difficulty_distribution.level_invalid:{raw_level}")
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            issues.append(f"question_plan.difficulty_distribution.count_invalid:{raw_level}")
            continue
        if count < 0:
            issues.append(f"question_plan.difficulty_distribution.count_invalid:{raw_level}")
            continue
        difficulty_total += count
    if question_count > 0 and difficulty_total != question_count:
        issues.append("question_plan.difficulty_distribution.count_mismatch")
    forbidden_types = data.get("forbidden_question_types") if isinstance(data.get("forbidden_question_types"), list) else []
    normalized_forbidden = {normalize_question_type(item) for item in forbidden_types}
    if not FORBIDDEN_TEST_GRADE_TYPES.issubset(normalized_forbidden):
        issues.append("question_plan.forbidden_question_types_incomplete")
    for field in ("planned_items", "coverage_matrix", "forbidden_question_types", "generation_guidance", "review_checklist", "evidence"):
        if field in data and not isinstance(data.get(field), list):
            issues.append(f"question_plan.{field}_not_list")
    if "diagnostic_value" in data and not isinstance(data.get("diagnostic_value"), dict):
        issues.append("question_plan.diagnostic_value_not_object")
    if "early_stop_policy" in data and not isinstance(data.get("early_stop_policy"), dict):
        issues.append("question_plan.early_stop_policy_not_object")
    if str(data.get("source_profile") or "").strip() == "initial-diagnostic":
        diagnostic_value = data.get("diagnostic_value") if isinstance(data.get("diagnostic_value"), dict) else {}
        if not diagnostic_value:
            issues.append("question_plan.initial.diagnostic_value_missing")
        else:
            if not _list_has_non_empty_value(diagnostic_value.get("target_knowledge_point_ids")):
                issues.append("question_plan.initial.diagnostic_value.target_knowledge_point_ids_missing")
            if not _list_has_non_empty_value(diagnostic_value.get("prerequisite_probe_chain")):
                issues.append("question_plan.initial.diagnostic_value.prerequisite_probe_chain_missing")
            if not _list_has_non_empty_value(diagnostic_value.get("expected_information_gain")):
                issues.append("question_plan.initial.diagnostic_value.expected_information_gain_missing")
        early_stop = data.get("early_stop_policy") if isinstance(data.get("early_stop_policy"), dict) else {}
        if not early_stop:
            issues.append("question_plan.initial.early_stop_policy_missing")
        elif not _list_has_non_empty_value(early_stop.get("stop_when")):
            issues.append("question_plan.initial.early_stop_policy.stop_when_missing")
    planned_items = data.get("planned_items") if isinstance(data.get("planned_items"), list) else []
    for index, planned in enumerate(planned_items):
        if not isinstance(planned, dict):
            issues.append(f"question_plan.planned_items.{index}.not_object")
            continue
        target = planned.get("target_difficulty_level") or planned.get("difficulty_level") or planned.get("difficulty")
        normalized_target = normalize_difficulty_level(target)
        if target is not None and not normalized_target:
            issues.append(f"question_plan.planned_items.{index}.target_difficulty_level_invalid")
        dimensions = _planned_item_difficulty_dimensions(planned)
        if dimensions is not None:
            issues.extend(validate_difficulty_dimensions(dimensions, context=f"question_plan.planned_items.{index}.difficulty_dimensions"))
        if normalized_target and dimensions is not None and not validate_difficulty_dimensions(dimensions):
            computed = infer_min_difficulty_from_dimensions(dimensions)
            if compare_difficulty_levels(normalized_target, computed) < 0:
                issues.append(f"question_plan.planned_items.{index}.target_difficulty_underestimated:{normalized_target}/{computed}")
    for field in ("minimum_pass_shape", "generation_trace"):
        if field in data and not isinstance(data.get(field), dict):
            issues.append(f"question_plan.{field}_not_object")
    minimum_pass_shape = data.get("minimum_pass_shape") if isinstance(data.get("minimum_pass_shape"), dict) else {}
    try:
        required_open_count = int(minimum_pass_shape.get("required_open_question_count") or 0)
    except (TypeError, ValueError):
        required_open_count = 0
    if required_open_count > 0:
        issues.append("question_plan.minimum_pass_shape.open_not_allowed_by_test_grade")
    return issues


def _payload_questions(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _parameter_entries(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _case_visibility(case: dict[str, Any]) -> str:
    return str(case.get("visibility") or case.get("category") or "").strip().lower()


PARAMETER_SCHEMA_KINDS = {"int", "float", "number", "bool", "str", "string", "none", "null", "json", "list", "array", "tuple", "dict", "object", "union"}
SCALAR_PARAMETER_SCHEMA_KINDS = {"int", "float", "number", "bool", "str", "string", "none", "null", "json"}


def validate_parameter_schema_node(value: Any, *, context: str = "parameter_schema") -> list[str]:
    if not isinstance(value, dict):
        return [f"{context}.not_object"]
    issues: list[str] = []
    kind = str(value.get("kind") or value.get("type") or "").strip().lower().replace("-", "_")
    if kind not in PARAMETER_SCHEMA_KINDS:
        issues.append(f"{context}.kind_invalid")
        return issues
    if kind in {"list", "array"}:
        element = value.get("element") or value.get("items")
        if not isinstance(element, dict):
            issues.append(f"{context}.element_missing")
        else:
            issues.extend(validate_parameter_schema_node(element, context=f"{context}.element"))
    elif kind == "tuple":
        items = value.get("items")
        if not isinstance(items, list) or not items:
            issues.append(f"{context}.items_missing")
        else:
            for index, item in enumerate(items):
                issues.extend(validate_parameter_schema_node(item, context=f"{context}.items.{index}"))
    elif kind in {"dict", "object"}:
        fields = value.get("fields")
        key_schema = value.get("key") or value.get("keys")
        value_schema = value.get("value") or value.get("values")
        if fields is not None:
            if not isinstance(fields, dict) or not fields:
                issues.append(f"{context}.fields_invalid")
            else:
                for field_name, field_schema in fields.items():
                    if not str(field_name or "").strip():
                        issues.append(f"{context}.fields.name_missing")
                        continue
                    issues.extend(validate_parameter_schema_node(field_schema, context=f"{context}.fields.{field_name}"))
        elif key_schema is not None or value_schema is not None:
            if key_schema is not None:
                issues.extend(validate_parameter_schema_node(key_schema, context=f"{context}.key"))
            if value_schema is None:
                issues.append(f"{context}.value_missing")
            else:
                issues.extend(validate_parameter_schema_node(value_schema, context=f"{context}.value"))
        elif kind == "dict":
            issues.append(f"{context}.value_missing")
    elif kind == "union":
        any_of = value.get("any_of") or value.get("one_of") or value.get("types")
        if not isinstance(any_of, list) or len(any_of) < 2:
            issues.append(f"{context}.any_of_invalid")
        else:
            for index, option in enumerate(any_of):
                if isinstance(option, str):
                    option = {"kind": option}
                issues.extend(validate_parameter_schema_node(option, context=f"{context}.any_of.{index}"))
    for numeric_field in ("min", "max", "min_length", "max_length"):
        if numeric_field in value:
            try:
                float(value.get(numeric_field))
            except (TypeError, ValueError):
                issues.append(f"{context}.{numeric_field}_invalid")
    if "allowed_values" in value and not isinstance(value.get("allowed_values"), list):
        issues.append(f"{context}.allowed_values_invalid")
    return issues


def _parameter_schema_kind(value: dict[str, Any]) -> str:
    return str(value.get("kind") or value.get("type") or "").strip().lower().replace("-", "_")


def _schema_options(value: dict[str, Any]) -> list[Any]:
    options = value.get("any_of") or value.get("one_of") or value.get("types")
    return options if isinstance(options, list) else []


def _value_violates_scalar_schema(value: Any, kind: str) -> bool:
    if kind in {"none", "null"}:
        return value is not None
    if kind == "bool":
        return not isinstance(value, bool)
    if kind == "int":
        return not (isinstance(value, int) and not isinstance(value, bool))
    if kind in {"float", "number"}:
        return not (isinstance(value, (int, float)) and not isinstance(value, bool))
    if kind in {"str", "string"}:
        return not isinstance(value, str)
    return False


def _value_schema_mismatch_paths(value: Any, schema: Any, *, path: str = "$") -> list[str]:
    if not isinstance(schema, dict):
        return [path]
    kind = _parameter_schema_kind(schema)
    if schema.get("nullable") is True and value is None:
        return []
    if "allowed_values" in schema and isinstance(schema.get("allowed_values"), list) and value not in schema.get("allowed_values", []):
        return [path]
    if kind in SCALAR_PARAMETER_SCHEMA_KINDS:
        mismatches = [] if kind == "json" or not _value_violates_scalar_schema(value, kind) else [path]
    elif kind in {"list", "array"}:
        if not isinstance(value, list):
            return [path]
        element = schema.get("element") or schema.get("items")
        mismatches = []
        if isinstance(element, dict):
            for index, item in enumerate(value):
                mismatches.extend(_value_schema_mismatch_paths(item, element, path=f"{path}[{index}]"))
    elif kind == "tuple":
        items = schema.get("items") if isinstance(schema.get("items"), list) else []
        if not isinstance(value, (list, tuple)) or len(value) != len(items):
            return [path]
        mismatches = []
        for index, item_schema in enumerate(items):
            mismatches.extend(_value_schema_mismatch_paths(value[index], item_schema, path=f"{path}[{index}]"))
    elif kind in {"dict", "object"}:
        if not isinstance(value, dict):
            return [path]
        fields = schema.get("fields")
        mismatches = []
        if isinstance(fields, dict) and fields:
            for field_name, field_schema in fields.items():
                field_key = str(field_name)
                optional = isinstance(field_schema, dict) and bool(field_schema.get("optional"))
                if field_key not in value:
                    if not optional:
                        mismatches.append(f"{path}.{field_key}")
                    continue
                mismatches.extend(_value_schema_mismatch_paths(value[field_key], field_schema, path=f"{path}.{field_key}"))
        else:
            key_schema = schema.get("key") or schema.get("keys")
            value_schema = schema.get("value") or schema.get("values")
            if isinstance(key_schema, dict):
                for key in value:
                    mismatches.extend(_value_schema_mismatch_paths(key, key_schema, path=f"{path}.<key>"))
            if isinstance(value_schema, dict):
                for key, item in value.items():
                    mismatches.extend(_value_schema_mismatch_paths(item, value_schema, path=f"{path}.{key}"))
    elif kind == "union":
        for option in _schema_options(schema):
            option_schema = {"kind": option} if isinstance(option, str) else option
            if not _value_schema_mismatch_paths(value, option_schema, path=path):
                return []
        return [path]
    else:
        return [path]
    for numeric_field, comparator in (("min", lambda left, right: left < right), ("max", lambda left, right: left > right)):
        if numeric_field in schema and isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                if comparator(float(value), float(schema.get(numeric_field))):
                    mismatches.append(path)
            except (TypeError, ValueError):
                pass
    if "min_length" in schema and hasattr(value, "__len__"):
        try:
            if len(value) < int(schema.get("min_length")):
                mismatches.append(path)
        except (TypeError, ValueError):
            pass
    if "max_length" in schema and hasattr(value, "__len__"):
        try:
            if len(value) > int(schema.get("max_length")):
                mismatches.append(path)
        except (TypeError, ValueError):
            pass
    return list(dict.fromkeys(mismatches))


def _parameter_schema_tokens(schema: Any, *, include_constraints: bool = False) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    kind = _parameter_schema_kind(schema)
    tokens: set[str] = set()
    if kind:
        tokens.add(kind)
    if include_constraints:
        for value in schema.get("allowed_values") if isinstance(schema.get("allowed_values"), list) else []:
            tokens.add(str(value).strip().lower())
        for field in ("min", "max", "min_length", "max_length"):
            if field in schema:
                tokens.add(str(schema.get(field)).strip().lower())
    if kind in {"list", "array"}:
        tokens.add("list")
        tokens.update(_parameter_schema_tokens(schema.get("element") or schema.get("items"), include_constraints=include_constraints))
    elif kind == "tuple":
        tokens.add("tuple")
        for item in schema.get("items") or []:
            tokens.update(_parameter_schema_tokens(item, include_constraints=include_constraints))
    elif kind in {"dict", "object"}:
        tokens.add("dict")
        fields = schema.get("fields")
        if isinstance(fields, dict):
            for field_name, field_schema in fields.items():
                tokens.add(str(field_name).strip().lower())
                tokens.update(_parameter_schema_tokens(field_schema, include_constraints=include_constraints))
        else:
            tokens.update(_parameter_schema_tokens(schema.get("key") or schema.get("keys"), include_constraints=include_constraints))
            tokens.update(_parameter_schema_tokens(schema.get("value") or schema.get("values"), include_constraints=include_constraints))
    elif kind == "union":
        tokens.add("union")
        for option in _schema_options(schema):
            tokens.update(_parameter_schema_tokens({"kind": option} if isinstance(option, str) else option, include_constraints=include_constraints))
    return {token for token in tokens if token and token not in {"union", "json"}}


OUTPUT_FIELD_CONSTRAINT_HINTS = ("code", "status", "state", "label", "type", "category", "class", "rank", "score", "level", "count", "index", "id")


def _schema_has_range_or_enum(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    return any(field in schema for field in ("allowed_values", "min", "max", "min_length", "max_length"))


def _output_schema_range_requirement_issues(schema: Any, *, path: str = "$") -> list[str]:
    if not isinstance(schema, dict):
        return []
    issues: list[str] = []
    kind = _parameter_schema_kind(schema)
    if path != "$" and not path.endswith("[]") and not path.endswith(".<value>"):
        field_name = path.rsplit(".", 1)[-1].lower()
        if not str(schema.get("description") or "").strip():
            issues.append(f"question.code.output_schema.description_missing:{path}")
        if any(hint in field_name for hint in OUTPUT_FIELD_CONSTRAINT_HINTS) and not _schema_has_range_or_enum(schema):
            issues.append(f"question.code.output_schema.range_missing:{path}")
    if kind in {"list", "array"}:
        issues.extend(_output_schema_range_requirement_issues(schema.get("element") or schema.get("items"), path=f"{path}[]"))
    elif kind == "tuple":
        for index, item in enumerate(schema.get("items") or []):
            issues.extend(_output_schema_range_requirement_issues(item, path=f"{path}[{index}]"))
    elif kind in {"dict", "object"}:
        fields = schema.get("fields")
        if isinstance(fields, dict):
            for field_name, field_schema in fields.items():
                issues.extend(_output_schema_range_requirement_issues(field_schema, path=f"{path}.{field_name}"))
        else:
            issues.extend(_output_schema_range_requirement_issues(schema.get("value") or schema.get("values"), path=f"{path}.<value>"))
    elif kind == "union":
        for index, option in enumerate(_schema_options(schema)):
            option_schema = {"kind": option} if isinstance(option, str) else option
            issues.extend(_output_schema_range_requirement_issues(option_schema, path=f"{path}.any_of.{index}"))
    return issues


def _input_spec_contains_schema_token(input_spec: str, token: str) -> bool:
    text = input_spec.lower()
    aliases = {
        "array": ["array", "list", "数组", "列表"],
        "list": ["list", "array", "列表", "数组"],
        "tuple": ["tuple", "元组"],
        "dict": ["dict", "object", "mapping", "字典", "对象"],
        "object": ["object", "dict", "字段", "对象", "字典"],
        "int": ["int", "integer", "整数"],
        "float": ["float", "number", "数值", "数字", "浮点"],
        "number": ["number", "float", "int", "数值", "数字"],
        "bool": ["bool", "boolean", "布尔"],
        "str": ["str", "string", "字符串"],
        "string": ["str", "string", "字符串"],
        "none": ["none", "null", "空值"],
        "null": ["none", "null", "空值"],
    }
    return any(alias.lower() in text for alias in aliases.get(token, [token]))


def _example_parameter_values(item: dict[str, Any], example: Any, parameter_names: list[str]) -> dict[str, Any]:
    if not isinstance(example, dict) or "input" not in example:
        return {}
    value = example.get("input")
    if isinstance(value, dict) and all(name in value for name in parameter_names):
        return {name: value.get(name) for name in parameter_names}
    if len(parameter_names) == 1:
        return {parameter_names[0]: value}
    if isinstance(value, list) and len(value) == len(parameter_names):
        return dict(zip(parameter_names, value))
    return {}


def _case_parameter_values(item: dict[str, Any], case: Any, parameter_names: list[str]) -> dict[str, Any]:
    if not isinstance(case, dict):
        return {}
    if isinstance(case.get("kwargs"), dict):
        return {name: case["kwargs"].get(name) for name in parameter_names if name in case["kwargs"]}
    if isinstance(case.get("args"), list) and len(case["args"]) == len(parameter_names):
        return dict(zip(parameter_names, case["args"]))
    if "input" in case and (len(parameter_names) == 1 or bool(item.get("single_object_input"))):
        return {parameter_names[0]: case.get("input")} if parameter_names else {}
    return {}


def _example_output_value(example: Any) -> tuple[bool, Any]:
    if isinstance(example, dict) and "output" in example:
        return True, example.get("output")
    return False, None


def _case_expected_literal(case: Any) -> tuple[bool, Any]:
    if not isinstance(case, dict):
        return False, None
    for key in ("expected", "expected_output", "expected_rows", "expected_records"):
        if key in case:
            return True, case.get(key)
    return False, None


def _validate_output_values_against_schema(item: dict[str, Any], output_schema: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for field, extractor in (
        ("examples", _example_output_value),
        ("public_tests", _case_expected_literal),
        ("hidden_tests", _case_expected_literal),
    ):
        values = item.get(field) if isinstance(item.get(field), list) else []
        for entry in values:
            present, value = extractor(entry)
            if not present:
                continue
            mismatches = _value_schema_mismatch_paths(value, output_schema)
            for path in mismatches[:3]:
                issues.append(f"question.code.{field}.output_type_mismatch:{path}")
    return issues


def validate_code_question_parameter_spec_contract(item: dict[str, Any], question_spec: dict[str, Any] | None) -> list[str]:
    qid = str(item.get("id") or "<missing-id>").strip()
    if not isinstance(question_spec, dict):
        return [f"question.code.parameter_spec_missing:{qid}"]
    issues: list[str] = []
    parameter_names = _function_parameter_names(item)
    parameters = question_spec.get("parameters") if isinstance(question_spec.get("parameters"), list) else []
    parameter_by_name = {
        str(parameter.get("name") or parameter.get("parameter_name") or "").strip(): parameter
        for parameter in parameters
        if isinstance(parameter, dict) and str(parameter.get("name") or parameter.get("parameter_name") or "").strip()
    }
    for name in parameter_names:
        if name not in parameter_by_name:
            issues.append(f"question.code.parameter_spec.parameter_missing:{name}")
    input_spec = str(item.get("input_spec") or "")
    for name in parameter_names:
        parameter = parameter_by_name.get(name)
        if not isinstance(parameter, dict):
            continue
        schema = parameter.get("schema")
        if schema is None:
            issues.append(f"question.code.parameter_spec.schema_missing:{name}")
            continue
        if name.lower() not in input_spec.lower():
            issues.append(f"question.code.input_spec.schema_coverage_missing:{name}:parameter_name")
        for token in sorted(_parameter_schema_tokens(schema)):
            if not _input_spec_contains_schema_token(input_spec, token):
                issues.append(f"question.code.input_spec.schema_coverage_missing:{name}:{token}")
        for field, extractor in (
            ("examples", _example_parameter_values),
            ("public_tests", _case_parameter_values),
            ("hidden_tests", _case_parameter_values),
        ):
            values = item.get(field) if isinstance(item.get(field), list) else []
            for entry in values:
                extracted = extractor(item, entry, parameter_names)
                if name not in extracted:
                    issues.append(f"question.code.{field}.type_mismatch:{name}:missing")
                    continue
                mismatches = _value_schema_mismatch_paths(extracted[name], schema)
                for path in mismatches[:3]:
                    issues.append(f"question.code.{field}.type_mismatch:{name}:{path}")
    output_schema = question_spec.get("output_schema")
    if not isinstance(output_schema, dict):
        issues.append(f"question.code.output_schema_missing:{qid}")
        return issues
    issues.extend(_output_schema_range_requirement_issues(output_schema))
    output_spec = str(item.get("output_spec") or "")
    for token in sorted(_parameter_schema_tokens(output_schema, include_constraints=True)):
        if not _input_spec_contains_schema_token(output_spec, token):
            issues.append(f"question.code.output_spec.schema_coverage_missing:{token}")
    issues.extend(_validate_output_values_against_schema(item, output_schema))
    return issues


def validate_parameter_spec_basic(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict) or not data:
        return ["parameter_spec.not_object"]
    if data.get("schema_version") != PARAMETER_SPEC_SCHEMA_VERSION:
        issues.append("parameter_spec.schema_version_invalid")
    questions = data.get("questions") if isinstance(data.get("questions"), list) else data.get("parameter_specs")
    if not isinstance(questions, list):
        issues.append("parameter_spec.questions_not_list")
        return issues
    seen_questions: set[str] = set()
    for q_index, question in enumerate(questions):
        if not isinstance(question, dict):
            issues.append(f"parameter_spec.questions.{q_index}.not_object")
            continue
        question_id = str(question.get("question_id") or question.get("id") or "").strip()
        if not question_id:
            issues.append(f"parameter_spec.questions.{q_index}.question_id_missing")
        elif question_id in seen_questions:
            issues.append(f"parameter_spec.questions.{q_index}.question_id_duplicate")
        else:
            seen_questions.add(question_id)
        runtimes = _runtime_values(question.get("supported_runtimes") or question.get("runtimes"))
        if not runtimes:
            issues.append(f"parameter_spec.questions.{q_index}.supported_runtimes_missing")
        invalid_runtimes = [runtime for runtime in runtimes if runtime not in RUNTIME_NAMES]
        if invalid_runtimes:
            issues.append(f"parameter_spec.questions.{q_index}.supported_runtimes_invalid:{','.join(invalid_runtimes)}")
        default_runtime = str(question.get("default_runtime") or "").strip().lower()
        if default_runtime and default_runtime not in runtimes:
            issues.append(f"parameter_spec.questions.{q_index}.default_runtime_not_supported")
        variants = question.get("runtime_variants")
        if variants is not None and not isinstance(variants, list):
            issues.append(f"parameter_spec.questions.{q_index}.runtime_variants_not_list")
        output_schema = question.get("output_schema")
        if output_schema is not None:
            issues.extend(validate_parameter_schema_node(output_schema, context=f"parameter_spec.questions.{q_index}.output_schema"))
        parameters = question.get("parameters") if isinstance(question.get("parameters"), list) else question.get("params")
        if not isinstance(parameters, list):
            issues.append(f"parameter_spec.questions.{q_index}.parameters_not_list")
            continue
        seen_parameters: set[str] = set()
        for p_index, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                issues.append(f"parameter_spec.questions.{q_index}.parameters.{p_index}.not_object")
                continue
            name = str(parameter.get("name") or parameter.get("parameter_name") or "").strip()
            ptype = str(parameter.get("type") or parameter.get("value_type") or "").strip().lower()
            if not name:
                issues.append(f"parameter_spec.questions.{q_index}.parameters.{p_index}.name_missing")
            elif name in seen_parameters:
                issues.append(f"parameter_spec.questions.{q_index}.parameters.{p_index}.name_duplicate")
            else:
                seen_parameters.add(name)
            if ptype not in PARAMETER_VALUE_TYPES:
                issues.append(f"parameter_spec.questions.{q_index}.parameters.{p_index}.type_invalid")
            schema = parameter.get("schema")
            if schema is not None:
                issues.extend(validate_parameter_schema_node(schema, context=f"parameter_spec.questions.{q_index}.parameters.{p_index}.schema"))
    return issues


def validate_parameter_artifact_basic(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict) or not data:
        return ["parameter_artifact.not_object"]
    if data.get("schema_version") != PARAMETER_ARTIFACT_SCHEMA_VERSION:
        issues.append("parameter_artifact.schema_version_invalid")
    question_cases: list[tuple[str, Any]] = []
    if isinstance(data.get("questions"), list):
        for q_index, question in enumerate(data.get("questions") or []):
            if not isinstance(question, dict):
                issues.append(f"parameter_artifact.questions.{q_index}.not_object")
                continue
            question_id = str(question.get("question_id") or question.get("id") or "").strip()
            if not question_id:
                issues.append(f"parameter_artifact.questions.{q_index}.question_id_missing")
            cases = question.get("cases") if isinstance(question.get("cases"), list) else []
            if not isinstance(question.get("cases"), list):
                issues.append(f"parameter_artifact.questions.{q_index}.cases_not_list")
            for case in cases:
                question_cases.append((question_id, case))
    elif isinstance(data.get("cases"), list):
        for case in data.get("cases") or []:
            question_id = str(case.get("question_id") or "").strip() if isinstance(case, dict) else ""
            question_cases.append((question_id, case))
    else:
        issues.append("parameter_artifact.cases_missing")
        return issues
    seen_cases: set[tuple[str, str]] = set()
    for index, (question_id, case) in enumerate(question_cases):
        if not isinstance(case, dict):
            issues.append(f"parameter_artifact.cases.{index}.not_object")
            continue
        resolved_question_id = question_id or str(case.get("question_id") or "").strip()
        if not resolved_question_id:
            issues.append(f"parameter_artifact.cases.{index}.question_id_missing")
        case_id = str(case.get("case_id") or case.get("id") or "").strip()
        if not case_id:
            issues.append(f"parameter_artifact.cases.{index}.case_id_missing")
        case_key = (resolved_question_id, case_id)
        if resolved_question_id and case_id and case_key in seen_cases:
            issues.append(f"parameter_artifact.cases.{index}.case_id_duplicate")
        elif resolved_question_id and case_id:
            seen_cases.add(case_key)
        visibility = _case_visibility(case)
        if visibility not in VISIBILITY_VALUES:
            issues.append(f"parameter_artifact.cases.{index}.visibility_invalid")
        bindings = case.get("parameters") if isinstance(case.get("parameters"), (dict, list)) else case.get("bindings")
        if not isinstance(bindings, (dict, list)):
            issues.append(f"parameter_artifact.cases.{index}.parameters_missing")
    return issues


def validate_dataset_artifact_basic(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict) or not data:
        return ["dataset_artifact.not_object"]
    if data.get("schema_version") != DATASET_ARTIFACT_SCHEMA_VERSION:
        issues.append("dataset_artifact.schema_version_invalid")
    datasets = data.get("datasets")
    if not isinstance(datasets, list):
        issues.append("dataset_artifact.datasets_not_list")
        return issues
    seen_dataset_ids: set[str] = set()
    for d_index, dataset in enumerate(datasets):
        if not isinstance(dataset, dict):
            issues.append(f"dataset_artifact.datasets.{d_index}.not_object")
            continue
        dataset_id = str(dataset.get("dataset_id") or dataset.get("id") or "").strip()
        if not dataset_id:
            issues.append(f"dataset_artifact.datasets.{d_index}.dataset_id_missing")
        elif dataset_id in seen_dataset_ids:
            issues.append(f"dataset_artifact.datasets.{d_index}.dataset_id_duplicate")
        else:
            seen_dataset_ids.add(dataset_id)
        kind = str(dataset.get("kind") or "").strip().lower()
        if kind not in DATASET_KINDS:
            issues.append(f"dataset_artifact.datasets.{d_index}.kind_invalid")
        visibility = str(dataset.get("visibility") or "").strip().lower()
        if visibility not in VISIBILITY_VALUES:
            issues.append(f"dataset_artifact.datasets.{d_index}.visibility_invalid")
        if not str(dataset.get("logical_name") or "").strip():
            issues.append(f"dataset_artifact.datasets.{d_index}.logical_name_missing")
        columns = dataset.get("columns")
        if not isinstance(columns, list):
            issues.append(f"dataset_artifact.datasets.{d_index}.columns_not_list")
        else:
            for c_index, column in enumerate(columns):
                if not isinstance(column, dict):
                    issues.append(f"dataset_artifact.datasets.{d_index}.columns.{c_index}.not_object")
                    continue
                if not str(column.get("name") or "").strip():
                    issues.append(f"dataset_artifact.datasets.{d_index}.columns.{c_index}.name_missing")
                if not str(column.get("dtype") or column.get("mysql_type") or "").strip():
                    issues.append(f"dataset_artifact.datasets.{d_index}.columns.{c_index}.type_missing")
        rows = dataset.get("rows")
        if not isinstance(rows, list):
            issues.append(f"dataset_artifact.datasets.{d_index}.rows_not_list")
        views = dataset.get("views")
        if views is not None and not isinstance(views, list):
            issues.append(f"dataset_artifact.datasets.{d_index}.views_not_list")
        metadata = dataset.get("reconstruction") or dataset.get("reconstruction_metadata") or dataset.get("pandas_metadata")
        if kind in {"dataframe", "series"} and not isinstance(metadata, dict):
            issues.append(f"dataset_artifact.datasets.{d_index}.reconstruction_metadata_missing")
    return issues


def validate_questions_basic(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in REQUIRED_QUESTIONS_TOP_LEVEL:
        if key not in data:
            issues.append(f"questions.json 缺少字段: {key}")
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        issues.append("questions 必须是非空列表")
        return issues
    ids: set[str] = set()
    for item in questions:
        qid = item.get("id") if isinstance(item, dict) else None
        if not qid:
            issues.append("存在题目缺少 id")
            continue
        if qid in ids:
            issues.append(f"存在重复题目 id: {qid}")
        ids.add(qid)
    return issues


def validate_progress_basic(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in REQUIRED_PROGRESS_TOP_LEVEL:
        if key not in data:
            issues.append(f"progress.json 缺少字段: {key}")
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    if not session:
        issues.append("progress.json session 必须是 object")
    for key in REQUIRED_PROGRESS_SESSION_FIELDS:
        if key not in session:
            issues.append(f"progress.json session 缺少字段: {key}")
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    if not context:
        issues.append("progress.json context 必须是 object")
    for key in REQUIRED_PROGRESS_CONTEXT_FIELDS:
        if key not in context:
            issues.append(f"progress.json context 缺少字段: {key}")
    return issues


def ensure_questions_basic(data: dict[str, Any]) -> None:
    issues = validate_questions_basic(data)
    if issues:
        raise ValueError(issues[0])


def ensure_question_scope_basic(data: dict[str, Any]) -> None:
    issues = validate_question_scope_basic(data)
    if issues:
        raise ValueError(issues[0])


def ensure_question_plan_basic(data: dict[str, Any]) -> None:
    issues = validate_question_plan_basic(data)
    if issues:
        raise ValueError(issues[0])


def ensure_parameter_spec_basic(data: dict[str, Any]) -> None:
    issues = validate_parameter_spec_basic(data)
    if issues:
        raise ValueError(issues[0])


def ensure_parameter_artifact_basic(data: dict[str, Any]) -> None:
    issues = validate_parameter_artifact_basic(data)
    if issues:
        raise ValueError(issues[0])


def ensure_dataset_artifact_basic(data: dict[str, Any]) -> None:
    issues = validate_dataset_artifact_basic(data)
    if issues:
        raise ValueError(issues[0])


def ensure_progress_basic(data: dict[str, Any]) -> None:
    issues = validate_progress_basic(data)
    if issues:
        raise ValueError(issues[0])
