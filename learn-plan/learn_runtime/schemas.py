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
    "constraints",
    "examples",
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
    signature = str(item.get("function_signature") or "").strip()
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
    issues.extend(_validate_code_cases_argument_contract(item, "public_tests"))
    issues.extend(_validate_code_cases_argument_contract(item, "hidden_tests"))
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
    for field in ("scope_basis", "target_capability_ids", "target_concepts", "review_targets", "lesson_focus_points", "project_tasks", "project_blockers", "source_material_refs", "exclusions", "evidence"):
        if field in data and not isinstance(data.get(field), list):
            issues.append(f"question_scope.{field}_not_list")
    for field in ("difficulty_target", "minimum_pass_shape", "generation_trace"):
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
