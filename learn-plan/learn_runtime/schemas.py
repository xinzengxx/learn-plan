from __future__ import annotations

import ast
import traceback
from typing import Any


MAX_FAILED_CASE_SUMMARIES = 3

TEST_GRADE_OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}
CANONICAL_QUESTION_TYPES = {"code", *TEST_GRADE_OBJECTIVE_TYPES}
LEGACY_OBJECTIVE_TYPE_MAP = {
    "single": "single_choice",
    "multi": "multiple_choice",
    "judge": "true_false",
}
BLOCKED_FREE_TEXT_TYPES = {"open", "written", "short_answer", "free_text"}
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


def validate_test_grade_question(item: dict[str, Any]) -> list[str]:
    if not isinstance(item, dict):
        return ["question.not_object"]
    qtype = str(item.get("type") or "").strip()
    category = str(item.get("category") or "").strip()
    if qtype in BLOCKED_FREE_TEXT_TYPES or category in BLOCKED_FREE_TEXT_TYPES:
        return ["question.open_not_allowed_by_default"]
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


def ensure_progress_basic(data: dict[str, Any]) -> None:
    issues = validate_progress_basic(data)
    if issues:
        raise ValueError(issues[0])
