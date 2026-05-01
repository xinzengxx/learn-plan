from __future__ import annotations

import os
import re
from typing import Any

from .display_values import safe_repr, sql_result_display

MAX_SQL_ROWS = 100
MAX_FAILED_CASE_SUMMARIES = 3
BLOCKED_SQL_TOKENS = {
    "alter",
    "call",
    "create",
    "delete",
    "drop",
    "grant",
    "insert",
    "load",
    "merge",
    "replace",
    "revoke",
    "truncate",
    "update",
}


class MySQLRuntimeError(RuntimeError):
    pass


def validate_select_query(sql: str) -> str:
    text = str(sql or "").strip()
    if not text:
        raise MySQLRuntimeError("SQL 不能为空")
    if text.endswith(";"):
        text = text[:-1].strip()
    if ";" in text:
        raise MySQLRuntimeError("只允许单条 SELECT/WITH 查询")
    lowered = _strip_sql_strings(text).lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise MySQLRuntimeError("MySQL runtime 只允许 SELECT 或 WITH ... SELECT 查询")
    for token in BLOCKED_SQL_TOKENS:
        if re.search(rf"\b{token}\b", lowered):
            raise MySQLRuntimeError(f"MySQL runtime 不允许执行 {token.upper()} 语句")
    if re.search(r"\binto\s+outfile\b", lowered) or re.search(r"\binto\s+dumpfile\b", lowered):
        raise MySQLRuntimeError("MySQL runtime 不允许导出文件")
    return text


def _strip_sql_strings(sql: str) -> str:
    chars: list[str] = []
    quote: str | None = None
    escaped = False
    for char in sql:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            chars.append(" ")
            continue
        if char in {"'", '"'}:
            quote = char
            chars.append(" ")
        else:
            chars.append(char)
    return "".join(chars)


def mysql_config(runtime_context: dict[str, Any] | None) -> dict[str, Any]:
    runtime = runtime_context.get("mysql_runtime") if isinstance(runtime_context, dict) else {}
    config = runtime.get("config") if isinstance(runtime, dict) and isinstance(runtime.get("config"), dict) else {}
    password_env = str(config.get("password_env") or "LEARN_MYSQL_PASSWORD")
    return {
        "host": config.get("host") or os.environ.get("LEARN_MYSQL_HOST") or "127.0.0.1",
        "port": int(config.get("port") or os.environ.get("LEARN_MYSQL_PORT") or 3306),
        "user": config.get("user") or os.environ.get("LEARN_MYSQL_USER") or "root",
        "password": os.environ.get(password_env) or os.environ.get("LEARN_MYSQL_PASSWORD") or "",
        "database": config.get("database") or os.environ.get("LEARN_MYSQL_DATABASE") or None,
        "connect_timeout": int(config.get("connect_timeout") or 5),
        "read_timeout": int(config.get("read_timeout") or 10),
        "write_timeout": int(config.get("write_timeout") or 10),
    }


def connect_mysql(runtime_context: dict[str, Any] | None):
    try:
        import pymysql
    except ImportError as exc:
        raise MySQLRuntimeError("MySQL runtime requires PyMySQL，请先安装 pymysql。") from exc
    config = mysql_config(runtime_context)
    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=config["connect_timeout"],
        read_timeout=config["read_timeout"],
        write_timeout=config["write_timeout"],
    )


def execute_select(connection: Any, sql: str) -> dict[str, Any]:
    query = validate_select_query(sql)
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchmany(MAX_SQL_ROWS + 1)
        columns = [item[0] for item in (cursor.description or [])]
    truncated = len(rows) > MAX_SQL_ROWS
    visible_rows = [list(row) if isinstance(row, tuple) else row for row in rows[:MAX_SQL_ROWS]]
    return {
        "columns": columns,
        "rows": visible_rows,
        "row_count": len(visible_rows),
        "truncated": truncated,
        "display": sql_result_display(columns, visible_rows, row_count=len(visible_rows), truncated=truncated),
    }


def run_sql_preview(question: dict[str, Any], sql: str, runtime_context: dict[str, Any] | None) -> dict[str, Any]:
    cases = _question_cases(question, runtime_context, visibility="public")[:5]
    if not cases:
        cases = [{"case_id": "public-preview", "category": "public", "parameters": {}}]
    run_cases: list[dict[str, Any]] = []
    has_error = False
    try:
        connection = connect_mysql(runtime_context)
    except Exception as exc:
        return _sql_error_result(str(exc))
    try:
        for index, case in enumerate(cases):
            item = _run_sql_case(connection, question, case, sql, runtime_context, include_private=True)
            has_error = has_error or bool(item.get("error"))
            item["case"] = index + 1
            item["category"] = "public"
            run_cases.append(item)
    finally:
        connection.close()
    first = run_cases[0] if run_cases else {}
    return {
        "ok": not has_error,
        "all_passed": all(item.get("passed") is not False and not item.get("error") for item in run_cases),
        "returncode": -1 if has_error else 0,
        "stdout": "",
        "stderr": "\n".join(str(item.get("error") or "") for item in run_cases if item.get("error")),
        "result_repr": first.get("actual_repr", ""),
        "run_cases": run_cases,
        "error": "；".join(str(item.get("error") or "") for item in run_cases if item.get("error")),
    }


def submit_sql(question: dict[str, Any], sql: str, runtime_context: dict[str, Any] | None) -> dict[str, Any]:
    cases = _question_cases(question, runtime_context, visibility="all")
    if not cases:
        cases = [{"case_id": "submit", "category": "public", "parameters": {}}]
    failed_case_summaries: list[dict[str, Any]] = []
    failure_types: list[str] = []
    passed_count = 0
    passed_public_count = 0
    passed_hidden_count = 0
    total_public_count = 0
    total_hidden_count = 0
    try:
        connection = connect_mysql(runtime_context)
    except Exception as exc:
        error = str(exc)
        return {
            "all_passed": False,
            "passed_count": 0,
            "total_count": len(cases),
            "passed_public_count": 0,
            "total_public_count": sum(1 for case in cases if _case_category(case) != "hidden"),
            "passed_hidden_count": 0,
            "total_hidden_count": sum(1 for case in cases if _case_category(case) == "hidden"),
            "failed_case_summaries": [{"case": 1, "category": "public", "passed": False, "error": error}],
            "failure_types": [error],
            "results": [{"case": 1, "category": "public", "passed": False, "error": error}],
        }
    try:
        for index, case in enumerate(cases):
            category = _case_category(case)
            if category == "hidden":
                total_hidden_count += 1
            else:
                total_public_count += 1
            result = _run_sql_case(connection, question, case, sql, runtime_context, include_private=category != "hidden")
            passed = bool(result.get("passed")) and not result.get("error")
            if passed:
                passed_count += 1
                if category == "hidden":
                    passed_hidden_count += 1
                else:
                    passed_public_count += 1
                continue
            error = _safe_failure_type(str(result.get("error") or "wrong_answer"), category)
            if error not in failure_types:
                failure_types.append(error)
            if len(failed_case_summaries) < MAX_FAILED_CASE_SUMMARIES:
                failed_case_summaries.append(_failed_case_summary(index + 1, category, error, result, case))
    finally:
        connection.close()
    return {
        "all_passed": passed_count == len(cases),
        "passed_count": passed_count,
        "total_count": len(cases),
        "passed_public_count": passed_public_count,
        "total_public_count": total_public_count,
        "passed_hidden_count": passed_hidden_count,
        "total_hidden_count": total_hidden_count,
        "failed_case_summaries": failed_case_summaries,
        "failure_types": failure_types,
        "results": failed_case_summaries,
    }


def _run_sql_case(connection: Any, question: dict[str, Any], case: dict[str, Any], sql: str, runtime_context: dict[str, Any] | None, *, include_private: bool) -> dict[str, Any]:
    try:
        rewritten_sql = rewrite_logical_tables(sql, _table_mapping(question, case, runtime_context))
        actual = execute_select(connection, rewritten_sql)
        expected = _expected_result(connection, question, case, runtime_context)
        passed = None if expected is None else _results_equal(actual, expected)
        result = {
            "passed": passed,
            "input": _public_case_input(case),
            "actual_repr": _result_repr(actual),
            "actualDisplay": actual["display"],
            "stdout": "",
            "stderr": "",
            "traceback": "",
            "error": "" if passed is not False else "wrong_answer",
        }
        if include_private and expected is not None:
            result["expected_repr"] = _result_repr(expected)
            result["expectedDisplay"] = expected["display"]
        return result
    except Exception as exc:
        return {
            "passed": False,
            "input": _public_case_input(case) if include_private else None,
            "actual_repr": "",
            "stdout": "",
            "stderr": "",
            "traceback": "",
            "error": str(exc),
        }


def _sql_error_result(error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "all_passed": False,
        "returncode": -1,
        "stdout": "",
        "stderr": error,
        "result_repr": "",
        "run_cases": [{"case": 1, "category": "public", "passed": False, "actual_repr": "", "error": error}],
        "error": error,
    }


def question_cases(question: dict[str, Any], runtime_context: dict[str, Any] | None, *, visibility: str) -> list[dict[str, Any]]:
    return _question_cases(question, runtime_context, visibility=visibility)


def case_category(case: dict[str, Any]) -> str:
    return _case_category(case)


def _question_cases(question: dict[str, Any], runtime_context: dict[str, Any] | None, *, visibility: str) -> list[dict[str, Any]]:
    artifact_cases: list[dict[str, Any]] = []
    fallback_cases: list[dict[str, Any]] = []
    artifact = runtime_context.get("parameter_artifact") if isinstance(runtime_context, dict) else None
    question_id = str(question.get("id") or "")
    if isinstance(artifact, dict):
        if isinstance(artifact.get("questions"), list):
            for entry in artifact.get("questions") or []:
                if not isinstance(entry, dict):
                    continue
                entry_qid = str(entry.get("question_id") or entry.get("id") or "")
                if entry_qid != question_id:
                    continue
                for case in entry.get("cases") or []:
                    if isinstance(case, dict):
                        artifact_cases.append({**case, "question_id": question_id})
        if isinstance(artifact.get("cases"), list):
            for case in artifact.get("cases") or []:
                if isinstance(case, dict) and str(case.get("question_id") or "") == question_id:
                    artifact_cases.append(case)
    for key, category in (("public_tests", "public"), ("hidden_tests", "hidden")):
        for case in question.get(key) or []:
            if isinstance(case, dict):
                fallback_cases.append({**case, "category": case.get("category") or category, "visibility": case.get("visibility") or category})
    cases = artifact_cases or fallback_cases
    if visibility == "all":
        return cases
    return [case for case in cases if _case_category(case) == visibility]


def _case_category(case: dict[str, Any]) -> str:
    return str(case.get("visibility") or case.get("category") or "public").strip().lower() or "public"


def build_python_call_case(case: dict[str, Any], runtime_context: dict[str, Any] | None) -> dict[str, Any]:
    bindings = case.get("parameters") if isinstance(case.get("parameters"), (dict, list)) else case.get("bindings")
    if bindings is None:
        return case
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    if isinstance(bindings, list):
        args = [_python_binding_value(item, runtime_context, case) for item in bindings]
    elif isinstance(bindings, dict):
        kwargs = {str(name): _python_binding_value(value, runtime_context, case) for name, value in bindings.items()}
    result = {key: value for key, value in case.items() if key not in {"parameters", "bindings"}}
    if args:
        result["args"] = args
    if kwargs:
        result["kwargs"] = kwargs
    return result


def _python_binding_value(binding: Any, runtime_context: dict[str, Any] | None, case: dict[str, Any]) -> Any:
    if not isinstance(binding, dict):
        return binding
    if "value" in binding:
        return binding.get("value")
    if "literal" in binding:
        return binding.get("literal")
    if binding.get("dataset_ref"):
        return reconstruct_dataset_value(str(binding.get("dataset_ref")), runtime_context, _case_category(case))
    return binding


def reconstruct_dataset_value(dataset_ref: str, runtime_context: dict[str, Any] | None, visibility: str) -> Any:
    materialized = runtime_context.get("materialized_datasets") if isinstance(runtime_context, dict) else None
    if not isinstance(materialized, dict):
        raise MySQLRuntimeError("缺少 materialized_datasets，无法重建 DataFrame/Series 参数")
    dataset = _find_materialized_dataset(materialized, dataset_ref, visibility)
    if not dataset:
        raise MySQLRuntimeError(f"找不到已物化数据集: {dataset_ref}")
    connection = connect_mysql(runtime_context)
    try:
        rows = _fetch_dataset_rows(connection, dataset)
    finally:
        connection.close()
    kind = str(dataset.get("kind") or "").strip().lower()
    if kind == "series":
        return _rows_to_series(rows, dataset)
    return _rows_to_dataframe(rows, dataset)


def _public_case_input(case: dict[str, Any]) -> Any:
    bindings = case.get("parameters") if isinstance(case.get("parameters"), (dict, list)) else case.get("bindings")
    if bindings is not None:
        return _safe_public_bindings(bindings)
    return case.get("input") or case.get("args") or case.get("kwargs") or ""


def _safe_public_bindings(value: Any) -> Any:
    if isinstance(value, list):
        return [_safe_public_bindings(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, dict) and item.get("dataset_ref"):
                result[str(key)] = {"dataset_ref": item.get("dataset_ref")}
            else:
                result[str(key)] = item
        return result
    return value


def _expected_result(connection: Any, question: dict[str, Any], case: dict[str, Any], runtime_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if case.get("expected_sql"):
        query = rewrite_logical_tables(str(case.get("expected_sql") or ""), _table_mapping(question, case, runtime_context))
        return execute_select(connection, query)
    if case.get("reference_sql"):
        query = rewrite_logical_tables(str(case.get("reference_sql") or ""), _table_mapping(question, case, runtime_context))
        return execute_select(connection, query)
    for key in ("expected", "expected_rows", "expected_records"):
        if key in case:
            return _literal_expected(case.get(key))
    if question.get("reference_sql") or question.get("solution_sql"):
        query = rewrite_logical_tables(str(question.get("reference_sql") or question.get("solution_sql") or ""), _table_mapping(question, case, runtime_context))
        return execute_select(connection, query)
    return None


def _literal_expected(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("columns"), list) and isinstance(value.get("rows"), list):
        columns = [str(column) for column in value.get("columns") or []]
        rows = value.get("rows") or []
    elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
        columns = list(value[0].keys()) if value else []
        rows = [[item.get(column) for column in columns] for item in value]
    else:
        columns = []
        rows = value if isinstance(value, list) else [[value]]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": False,
        "display": sql_result_display(columns, rows, row_count=len(rows), truncated=False),
    }


def _results_equal(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return _normalized_result(actual) == _normalized_result(expected)


def _normalized_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "columns": [str(column) for column in result.get("columns") or []],
        "rows": [[_normalize_scalar(value) for value in row] if isinstance(row, (list, tuple)) else _normalize_scalar(row) for row in result.get("rows") or []],
    }


def _normalize_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return safe_repr(value)


def _result_repr(result: dict[str, Any]) -> str:
    return safe_repr({"columns": result.get("columns") or [], "rows": result.get("rows") or []})


def _safe_failure_type(error: str, category: str) -> str:
    if category == "hidden" and error != "wrong_answer":
        return "runtime_error"
    return error


def _failed_case_summary(case_number: int, category: str, error: str, result: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "case": case_number,
        "category": category,
        "passed": False,
        "error": error,
        "capability_tags": case.get("capability_tags", []) if isinstance(case.get("capability_tags"), list) else [],
    }
    if category != "hidden":
        summary.update(
            {
                "input": result.get("input"),
                "expected_repr": result.get("expected_repr", ""),
                "actual_repr": result.get("actual_repr", ""),
                "expectedDisplay": result.get("expectedDisplay"),
                "actualDisplay": result.get("actualDisplay"),
            }
        )
    return summary


def _table_mapping(question: dict[str, Any], case: dict[str, Any], runtime_context: dict[str, Any] | None) -> dict[str, str]:
    materialized = runtime_context.get("materialized_datasets") if isinstance(runtime_context, dict) else None
    if not isinstance(materialized, dict):
        return {}
    dataset_refs = set(_dataset_refs_for_case(question, case))
    category = _case_category(case)
    mapping: dict[str, str] = {}
    for dataset in materialized.get("datasets") or materialized.get("materialized_datasets") or []:
        if not isinstance(dataset, dict):
            continue
        visibility = str(dataset.get("visibility") or "").strip().lower()
        if visibility and visibility != category:
            continue
        dataset_id = str(dataset.get("dataset_id") or dataset.get("id") or dataset.get("dataset_ref") or "").strip()
        if dataset_refs and dataset_id and dataset_id not in dataset_refs:
            continue
        logical_name = str(dataset.get("logical_name") or dataset.get("table_name") or dataset_id or "").strip()
        physical_table = str(dataset.get("physical_table") or dataset.get("physical_name") or dataset.get("table") or "").strip()
        if logical_name and physical_table:
            mapping[logical_name] = physical_table
    return mapping


def _find_materialized_dataset(materialized: dict[str, Any], dataset_ref: str, visibility: str) -> dict[str, Any] | None:
    for dataset in materialized.get("datasets") or materialized.get("materialized_datasets") or []:
        if not isinstance(dataset, dict):
            continue
        dataset_id = str(dataset.get("dataset_id") or dataset.get("id") or dataset.get("dataset_ref") or "")
        dataset_visibility = str(dataset.get("visibility") or "").strip().lower()
        if dataset_id == dataset_ref and (not dataset_visibility or dataset_visibility == visibility):
            return dataset
    return None


def _fetch_dataset_rows(connection: Any, dataset: dict[str, Any]) -> list[dict[str, Any]]:
    physical_table = str(dataset.get("physical_table") or dataset.get("physical_name") or dataset.get("table") or "").strip()
    if not _safe_identifier_path(physical_table):
        raise MySQLRuntimeError("materialized dataset physical table name is invalid")
    columns = [str(column.get("name") or "") for column in dataset.get("columns") or [] if isinstance(column, dict) and str(column.get("name") or "").strip()]
    if not columns:
        raise MySQLRuntimeError("materialized dataset 缺少 columns metadata")
    query = f"SELECT {', '.join(_quote_identifier_path(column) for column in columns)} FROM {_quote_identifier_path(physical_table)} ORDER BY `__row_order`"
    with connection.cursor() as cursor:
        cursor.execute(query)
        raw_rows = cursor.fetchall() if hasattr(cursor, "fetchall") else cursor.fetchmany(MAX_SQL_ROWS + 1)
    return [dict(zip(columns, list(row) if isinstance(row, tuple) else row)) for row in raw_rows]


def _rows_to_dataframe(rows: list[dict[str, Any]], dataset: dict[str, Any]) -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise MySQLRuntimeError("Python tabular runtime requires pandas，请先安装 pandas。") from exc
    columns = [str(column.get("name") or "") for column in dataset.get("columns") or [] if isinstance(column, dict) and str(column.get("name") or "").strip()]
    return pd.DataFrame(rows, columns=columns)


def _rows_to_series(rows: list[dict[str, Any]], dataset: dict[str, Any]) -> Any:
    frame = _rows_to_dataframe(rows, dataset)
    metadata = dataset.get("reconstruction") if isinstance(dataset.get("reconstruction"), dict) else {}
    value_column = str(metadata.get("value_column") or "")
    if not value_column:
        columns = [column for column in frame.columns if column != "__row_order"]
        value_column = str(columns[0]) if columns else "value"
    name = metadata.get("series_name") if metadata.get("series_name") is not None else value_column
    return frame[value_column].rename(name)


def _dataset_refs_for_case(question: dict[str, Any], case: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    raw_refs = question.get("dataset_refs") if isinstance(question.get("dataset_refs"), list) else []
    refs.extend(str(item) for item in raw_refs if str(item).strip())
    if question.get("dataset_ref"):
        refs.append(str(question.get("dataset_ref")))
    bindings = case.get("parameters") if isinstance(case.get("parameters"), (dict, list)) else case.get("bindings")
    entries = bindings.values() if isinstance(bindings, dict) else bindings if isinstance(bindings, list) else []
    for item in entries:
        if isinstance(item, dict) and item.get("dataset_ref"):
            refs.append(str(item.get("dataset_ref")))
    return refs


def rewrite_logical_tables(sql: str, mapping: dict[str, str]) -> str:
    rewritten = str(sql or "")
    for logical_name, physical_table in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if not _safe_identifier_path(physical_table):
            raise MySQLRuntimeError("materialized dataset physical table name is invalid")
        quoted = _quote_identifier_path(physical_table)
        pattern = re.compile(rf"(?<![\w`])`?{re.escape(logical_name)}`?(?![\w`])")
        rewritten = pattern.sub(quoted, rewritten)
    return rewritten


def _safe_identifier_path(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)?", value))


def _quote_identifier_path(value: str) -> str:
    return ".".join(f"`{part}`" for part in value.split("."))
