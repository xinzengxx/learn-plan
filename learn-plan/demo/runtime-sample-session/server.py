#!/usr/bin/env python3
"""
learn-plan 本地服务器
用途：为题集.html 提供题目、进度、运行与判题 API，解决浏览器 file:// 协议无法读写本地文件的限制。
启动方式：conda run -n base python server.py
访问地址：http://localhost:8080
"""

import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


def resolve_port() -> int:
    raw = os.environ.get("LEARN_PLAN_PORT") or "8080"
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 8080


PORT = resolve_port()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "templates" else BASE_DIR
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)
PROGRESS_FILE = os.path.join(BASE_DIR, "progress.json")
QUESTIONS_FILE = os.path.join(BASE_DIR, "questions.json")
HTML_FILE = os.path.join(BASE_DIR, "题集.html")
CONDA_ENV = "base"
RESULT_PREFIX = "__LEARN_CODE_RESULT__="
HEATMAP_DAYS = 35
MAX_FAILED_CASE_SUMMARIES = 3
MAX_PUBLIC_PREVIEW_ROWS = 10
MAX_PUBLIC_PREVIEW_COLUMNS = 20
MAX_DISPLAY_CELL_CHARS = 160

last_heartbeat_at = time.time()
shutdown_requested = False
server_instance = None


def get_sessions_dir():
    return os.path.dirname(BASE_DIR)


def get_heatmap_level(attempted):
    if attempted <= 0:
        return 0
    if attempted <= 2:
        return 1
    if attempted <= 4:
        return 2
    if attempted <= 7:
        return 3
    return 4


def build_heatmap_data(days=HEATMAP_DAYS):
    sessions_dir = get_sessions_dir()
    progress_by_date = {}
    if os.path.isdir(sessions_dir):
        for entry in os.listdir(sessions_dir):
            progress_path = os.path.join(sessions_dir, entry, "progress.json")
            if not os.path.isfile(progress_path):
                continue
            try:
                with open(progress_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            date = data.get("date") or entry
            summary = data.get("summary") or {}
            attempted = int(summary.get("attempted") or 0)
            correct = int(summary.get("correct") or 0)
            total = int(summary.get("total") or 0)
            progress_by_date[date] = {
                "date": date,
                "attempted": attempted,
                "correct": correct,
                "total": total,
                "level": get_heatmap_level(attempted),
            }

    today = time.strftime("%Y-%m-%d")
    base = time.strptime(today, "%Y-%m-%d")
    base_ts = time.mktime(base)
    items = []
    for offset in range(days - 1, -1, -1):
        day_ts = base_ts - offset * 86400
        day = time.strftime("%Y-%m-%d", time.localtime(day_ts))
        items.append(progress_by_date.get(day, {
            "date": day,
            "attempted": 0,
            "correct": 0,
            "total": 0,
            "level": 0,
        }))
    return {"days": days, "items": items}


def mark_alive():
    global last_heartbeat_at
    last_heartbeat_at = time.time()


def load_questions_data():
    if not os.path.exists(QUESTIONS_FILE):
        return {}
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_display_safe_questions_payload(data):
    source = data if isinstance(data, dict) else {}
    runtime_context = source.get("runtime_context") if isinstance(source.get("runtime_context"), dict) else {}
    payload = dict(source)
    payload.pop("runtime_context", None)
    safe_questions = []
    for item in payload.get("questions") or []:
        if not isinstance(item, dict):
            safe_questions.append(item)
            continue
        safe_item = dict(item)
        dataset_description = build_public_dataset_description(item, runtime_context)
        example_displays = build_public_example_displays(item, runtime_context, dataset_description)
        for key in (
            "answer", "answers", "explanation", "reference_points", "grading_hint", "solution_code", "solution_sql",
            "reference_sql", "hidden_tests", "hidden_dataset_refs", "dataset_refs", "dataset_ref", "parameter_spec_ref",
            "difficulty_reason", "expected_failure_mode", "runtime_context",
        ):
            safe_item.pop(key, None)
        if dataset_description:
            safe_item["dataset_description"] = dataset_description
        else:
            safe_item.pop("dataset_description", None)
        if example_displays:
            safe_item["example_displays"] = example_displays
        else:
            safe_item.pop("example_displays", None)
        safe_questions.append(safe_item)
    payload["questions"] = safe_questions
    return payload


def build_public_dataset_description(question, runtime_context):
    if not isinstance(question, dict) or not isinstance(runtime_context, dict):
        return None
    dataset_artifact = runtime_context.get("dataset_artifact") if isinstance(runtime_context.get("dataset_artifact"), dict) else {}
    public_datasets = _question_public_datasets(question, runtime_context, dataset_artifact)
    if not public_datasets:
        return None
    tables = []
    for dataset in public_datasets:
        table = _safe_dataset_table(dataset)
        if table:
            tables.append(table)
    if not tables:
        return None
    table_names = {table["name"] for table in tables}
    return {
        "relationships": _safe_dataset_relationships(question, runtime_context, table_names),
        "tables": tables,
    }


def build_public_example_displays(question, runtime_context, dataset_description=None):
    if not isinstance(question, dict):
        return []
    public_cases = _question_public_cases(question, runtime_context)
    if not public_cases:
        return []
    examples = []
    source_examples = question.get("examples") if isinstance(question.get("examples"), list) else []
    for index, case in enumerate(public_cases[:5]):
        if not isinstance(case, dict):
            continue
        source_example = source_examples[index] if index < len(source_examples) and isinstance(source_examples[index], dict) else {}
        example = {
            "title": f"示例 {index + 1}",
            "explanation": str(case.get("note") or source_example.get("explanation") or "").strip(),
        }
        expected = case.get("expected", source_example.get("output"))
        if _has_dataset_example_input(question, dataset_description):
            example["input_kind"] = "tables"
            example["input_tables"] = list((dataset_description or {}).get("tables") or [])
            example["outputDisplay"] = _example_output_display(expected)
        else:
            example["input_kind"] = "parameters"
            example["input_parameters"] = _safe_example_parameters(question, case)
            example["outputDisplay"] = _example_output_display(expected)
        if not example["explanation"]:
            example.pop("explanation", None)
        examples.append(example)
    return examples


def _question_public_cases(question, runtime_context):
    question_id = str(question.get("id") or "")
    parameter_artifact = runtime_context.get("parameter_artifact") if isinstance(runtime_context.get("parameter_artifact"), dict) else {}
    cases = [case for case in _parameter_artifact_cases_for_question(parameter_artifact, question_id) if _is_public_case(case)]
    if cases:
        return cases
    public_tests = question.get("public_tests") if isinstance(question.get("public_tests"), list) else []
    return [case for case in public_tests if isinstance(case, dict) and _is_public_case(case)]


def _is_public_case(case):
    if not isinstance(case, dict):
        return False
    visibility = str(case.get("visibility") or case.get("category") or "public").strip().lower()
    return visibility != "hidden"


def _has_dataset_example_input(question, dataset_description):
    return bool(isinstance(dataset_description, dict) and dataset_description.get("tables") and str(question.get("type") or "").strip().lower() in {"sql", "code"})


def _safe_example_parameters(question, case):
    names = _function_parameter_names(question)
    parameters = []
    if isinstance(case.get("kwargs"), dict):
        for key, value in case.get("kwargs").items():
            parameters.append(_safe_example_parameter(str(key), value))
    elif isinstance(case.get("args"), list):
        for index, value in enumerate(case.get("args") or []):
            name = names[index] if index < len(names) else f"输入 {index + 1}"
            parameters.append(_safe_example_parameter(name, value))
    elif "input" in case:
        input_value = case.get("input")
        if isinstance(input_value, dict) and not names:
            for key, value in input_value.items():
                parameters.append(_safe_example_parameter(str(key), value))
        else:
            parameters.append(_safe_example_parameter(names[0] if names else "输入", input_value))
    return parameters


def _safe_example_parameter(name, value):
    return {
        "name": str(name or "输入")[:MAX_DISPLAY_CELL_CHARS],
        "valueDisplay": display_value(value),
    }


def _function_parameter_names(question):
    signature = str(question.get("function_signature") or "")
    names = []
    if "(" in signature and ")" in signature:
        raw = signature.split("(", 1)[1].split(")", 1)[0]
        for part in raw.split(","):
            text = part.strip()
            if not text or text in {"/", "*"}:
                continue
            text = text.lstrip("*").split(":", 1)[0].split("=", 1)[0].strip()
            if text and text not in {"self", "cls"}:
                names.append(text)
    if names:
        return names
    input_spec = str(question.get("input_spec") or "")
    first_line = input_spec.strip().splitlines()[0] if input_spec.strip() else ""
    candidate = first_line.split(":", 1)[0].strip("` *-")
    return [candidate] if candidate.isidentifier() else []


def _example_output_display(value):
    if isinstance(value, dict) and isinstance(value.get("columns"), list) and isinstance(value.get("rows"), list):
        from learn_runtime.display_values import sql_result_display

        columns = [str(column) for column in value.get("columns")]
        rows = value.get("rows")
        return sql_result_display(columns, rows, row_count=len(rows), truncated=False)
    return display_value(value)


def _question_public_datasets(question, runtime_context, dataset_artifact):
    datasets = dataset_artifact.get("datasets") if isinstance(dataset_artifact.get("datasets"), list) else []
    if not datasets:
        return []
    refs = _question_dataset_refs(question, runtime_context)
    if not refs:
        return []
    result = []
    seen = set()
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        visibility = str(dataset.get("visibility") or "public").strip().lower()
        if visibility != "public":
            continue
        dataset_id = str(dataset.get("dataset_id") or dataset.get("id") or dataset.get("dataset_ref") or "").strip()
        if refs and dataset_id and dataset_id not in refs:
            continue
        key = dataset_id or str(dataset.get("logical_name") or dataset.get("name") or "")
        if key in seen:
            continue
        seen.add(key)
        result.append(dataset)
    return result


def _question_dataset_refs(question, runtime_context):
    refs = []
    for item in question.get("dataset_refs") if isinstance(question.get("dataset_refs"), list) else []:
        text = str(item or "").strip()
        if text and text not in refs:
            refs.append(text)
    if question.get("dataset_ref"):
        text = str(question.get("dataset_ref") or "").strip()
        if text and text not in refs:
            refs.append(text)
    question_id = str(question.get("id") or "")
    parameter_artifact = runtime_context.get("parameter_artifact") if isinstance(runtime_context.get("parameter_artifact"), dict) else {}
    for case in _parameter_artifact_cases_for_question(parameter_artifact, question_id):
        for ref in _dataset_refs_from_bindings(case.get("parameters") if isinstance(case.get("parameters"), (dict, list)) else case.get("bindings")):
            if ref not in refs:
                refs.append(ref)
    parameter_spec = runtime_context.get("parameter_spec") if isinstance(runtime_context.get("parameter_spec"), dict) else {}
    for entry in parameter_spec.get("questions") if isinstance(parameter_spec.get("questions"), list) else []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("question_id") or entry.get("id") or "") != question_id:
            continue
        for parameter in entry.get("parameters") if isinstance(entry.get("parameters"), list) else []:
            if not isinstance(parameter, dict):
                continue
            ref = str(parameter.get("dataset_ref") or parameter.get("dataset_view_ref") or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def _parameter_artifact_cases_for_question(parameter_artifact, question_id):
    cases = []
    for entry in parameter_artifact.get("questions") if isinstance(parameter_artifact.get("questions"), list) else []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("question_id") or entry.get("id") or "") != question_id:
            continue
        for case in entry.get("cases") if isinstance(entry.get("cases"), list) else []:
            if isinstance(case, dict):
                cases.append(case)
    for case in parameter_artifact.get("cases") if isinstance(parameter_artifact.get("cases"), list) else []:
        if isinstance(case, dict) and str(case.get("question_id") or "") == question_id:
            cases.append(case)
    return cases


def _dataset_refs_from_bindings(value):
    refs = []
    if isinstance(value, list):
        for item in value:
            refs.extend(_dataset_refs_from_bindings(item))
    elif isinstance(value, dict):
        if value.get("dataset_ref"):
            refs.append(str(value.get("dataset_ref")))
        for item in value.values():
            if isinstance(item, (dict, list)):
                refs.extend(_dataset_refs_from_bindings(item))
    return refs


def _safe_dataset_table(dataset):
    logical_name = str(dataset.get("logical_name") or dataset.get("name") or dataset.get("dataset_id") or "").strip()
    if not logical_name:
        return None
    columns = []
    for column in dataset.get("columns") if isinstance(dataset.get("columns"), list) else []:
        safe_column = _safe_dataset_column(column)
        if safe_column:
            columns.append(safe_column)
    if not columns:
        return None
    preview = _safe_dataset_preview(dataset, [column["name"] for column in columns])
    return {
        "name": logical_name,
        "display_name": str(dataset.get("display_name") or dataset.get("description") or logical_name)[:MAX_DISPLAY_CELL_CHARS],
        "kind": str(dataset.get("kind") or "table"),
        "columns": columns,
        "preview": preview,
    }


def _safe_dataset_column(column):
    if not isinstance(column, dict):
        return None
    name = str(column.get("name") or "").strip()
    if not name:
        return None
    result = {
        "name": name,
        "type": str(column.get("dtype") or column.get("type") or column.get("mysql_type") or "unknown")[:MAX_DISPLAY_CELL_CHARS],
        "nullable": bool(column.get("nullable", False)),
    }
    description = str(column.get("description") or column.get("comment") or "").strip()
    if description:
        result["description"] = description[:MAX_DISPLAY_CELL_CHARS]
    return result


def _safe_dataset_preview(dataset, column_names):
    rows = dataset.get("public_preview") or dataset.get("preview_rows") or dataset.get("rows") or []
    if isinstance(rows, dict) and isinstance(rows.get("rows"), list):
        rows = rows.get("rows")
    if not isinstance(rows, list):
        rows = []
    visible_columns = column_names[:MAX_PUBLIC_PREVIEW_COLUMNS]
    visible_rows = rows[:MAX_PUBLIC_PREVIEW_ROWS]
    return {
        "columns": visible_columns,
        "rows": [_safe_preview_row(row, visible_columns) for row in visible_rows],
        "row_limit": MAX_PUBLIC_PREVIEW_ROWS,
        "truncated": len(rows) > MAX_PUBLIC_PREVIEW_ROWS or len(column_names) > MAX_PUBLIC_PREVIEW_COLUMNS,
    }


def _safe_preview_row(row, columns):
    if isinstance(row, dict):
        return [_safe_preview_cell(row.get(column)) for column in columns]
    if isinstance(row, (list, tuple)):
        return [_safe_preview_cell(value) for value in list(row)[: len(columns)]]
    return [_safe_preview_cell(row)]


def _safe_preview_cell(value):
    if value is None or isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    return text if len(text) <= MAX_DISPLAY_CELL_CHARS else text[:MAX_DISPLAY_CELL_CHARS] + "…"


def _safe_dataset_relationships(question, runtime_context, table_names):
    raw_relationships = []
    for source in (question, runtime_context.get("dataset_artifact") if isinstance(runtime_context.get("dataset_artifact"), dict) else {}):
        if isinstance(source, dict):
            value = source.get("relationships") or source.get("table_relationships")
            if isinstance(value, list):
                raw_relationships.extend(value)
    result = []
    for relationship in raw_relationships:
        safe = _safe_dataset_relationship(relationship, table_names)
        if safe:
            result.append(safe)
    return result


def _safe_dataset_relationship(relationship, table_names):
    if not isinstance(relationship, dict):
        return None
    left_table = str(relationship.get("left_table") or relationship.get("from_table") or relationship.get("source_table") or "").strip()
    right_table = str(relationship.get("right_table") or relationship.get("to_table") or relationship.get("target_table") or "").strip()
    left_key = str(relationship.get("left_key") or relationship.get("from_key") or relationship.get("source_key") or "").strip()
    right_key = str(relationship.get("right_key") or relationship.get("to_key") or relationship.get("target_key") or "").strip()
    if (left_table and left_table not in table_names) or (right_table and right_table not in table_names):
        return None
    if not (left_table and right_table and left_key and right_key):
        return None
    result = {
        "kind": str(relationship.get("kind") or "join"),
        "left_table": left_table,
        "left_key": left_key,
        "right_table": right_table,
        "right_key": right_key,
    }
    description = str(relationship.get("description") or "").strip()
    if description:
        result["description"] = description[:MAX_DISPLAY_CELL_CHARS]
    return result


def find_question_by_id(question_id):
    for item in load_questions_data().get("questions") or []:
        if isinstance(item, dict) and item.get("id") == question_id:
            return item
    return None


def load_runtime_context():
    data = load_questions_data()
    context = data.get("runtime_context") if isinstance(data, dict) else None
    return context if isinstance(context, dict) else {}


def runtime_question_cases(question, visibility):
    from learn_runtime.mysql_runtime import question_cases

    return question_cases(question, load_runtime_context(), visibility=visibility)


def display_value(value):
    from learn_runtime.display_values import to_display_value

    return to_display_value(value)


def normalize_selected_indices(selected):
    values = []
    for item in selected or []:
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            continue
    return values


def normalize_question_type(value):
    qtype = str(value or "").strip().lower()
    return {"single": "single_choice", "multi": "multiple_choice", "judge": "true_false"}.get(qtype, qtype)


def grade_concept_answer(question, selected):
    qtype = normalize_question_type(question.get("type"))
    if qtype == "true_false":
        answer = question.get("answer")
        if isinstance(answer, bool):
            correct_idx = 0 if answer else 1
        else:
            correct_idx = 0 if answer == 0 or str(answer).strip().lower() == "true" else 1
        return len(selected) == 1 and selected[0] == correct_idx
    if qtype == "single_choice":
        try:
            correct_idx = int(question.get("answer"))
        except (TypeError, ValueError):
            return False
        return len(selected) == 1 and selected[0] == correct_idx
    if qtype == "multiple_choice":
        expected = []
        raw_answer = question.get("answers", question.get("answer"))
        if isinstance(raw_answer, list):
            for item in raw_answer:
                try:
                    expected.append(int(item))
                except (TypeError, ValueError):
                    continue
        return sorted(set(selected)) == sorted(set(expected))
    return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if args and str(args[1]) not in ("200", "204"):
            super().log_message(format, *args)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_cors(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def serve_file(self, path):
        abs_path = os.path.join(BASE_DIR, path.lstrip("/"))
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            self.send_response(404)
            self.end_headers()
            return
        ext = os.path.splitext(abs_path)[1]
        mime = {
            ".html": "text/html; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".map": "application/json; charset=utf-8",
            ".ttf": "font/ttf",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".svg": "image/svg+xml",
        }.get(ext, "application/octet-stream")
        with open(abs_path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def read_payload(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        return json.loads(body.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_cors()

    def do_GET(self):
        mark_alive()
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            self.serve_file("题集.html")
        elif path == "/questions.json":
            try:
                self.send_json(build_display_safe_questions_payload(load_questions_data()))
            except Exception as e:
                self.send_json({"error": f"questions.json load failed: {e}"}, 500)
        elif path == "/progress":
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json(data)
            else:
                self.send_json({"error": "progress.json not found"}, 404)
        elif path == "/heartbeat":
            self.send_json({"ok": True, "ts": time.time()})
        elif path == "/server-info":
            self.send_json(
                {
                    "base_dir": BASE_DIR,
                    "files": {
                        "html": HTML_FILE,
                        "questions": QUESTIONS_FILE,
                        "progress": PROGRESS_FILE,
                        "server": os.path.join(BASE_DIR, "server.py"),
                    },
                    "start_command": "conda run -n base python server.py",
                    "stop_command": f"pkill -f '{os.path.join(BASE_DIR, 'server.py')}'",
                    "url": f"http://localhost:{PORT}",
                }
            )
        elif path == "/lesson" or path == "/lesson.html":
            self.serve_file("lesson.html")
        elif path == "/heatmap":
            self.send_json(build_heatmap_data())
        else:
            self.serve_file(path)

    def do_POST(self):
        global shutdown_requested
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = self.read_payload()
        except Exception as e:
            self.send_json({"error": f"invalid json: {e}"}, 400)
            return

        mark_alive()

        if path == "/progress":
            try:
                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 400)

        elif path == "/heartbeat":
            self.send_json({"ok": True, "ts": time.time()})

        elif path == "/shutdown":
            shutdown_requested = True
            self.send_json({"ok": True, "message": "server shutting down"})
            self.close_connection = True
            threading.Thread(target=shutdown_server_soon, daemon=True).start()

        elif path == "/finish":
            try:
                result = finish_session(payload)
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)}, 400)

        elif path == "/run":
            try:
                mode = payload.get("mode", "script")
                if mode == "query":
                    result = self._run_sql_query(payload)
                elif mode == "function" and payload.get("function_name"):
                    result = self._run_function_preview(payload, timeout=10)
                else:
                    code = payload.get("code", "")
                    stdin_data = payload.get("stdin", "")
                    result = self._run_python_script(code, stdin_data, timeout=10)
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)}, 400)

        elif path == "/submit":
            try:
                mode = payload.get("mode", "script")
                if mode == "query":
                    result = self._submit_sql_query(payload)
                elif mode == "function" and payload.get("function_name"):
                    result = self._submit_function(payload, timeout=10)
                elif mode == "written":
                    result = self._submit_written(payload)
                elif mode == "answer":
                    question = find_question_by_id(payload.get("question_id"))
                    if not question:
                        raise ValueError("question not found")
                    selected = normalize_selected_indices(payload.get("selected"))
                    unsure = payload.get("unsure") or []
                    result = {
                        "ok": True,
                        "is_correct": grade_concept_answer(question, selected),
                        "unsure": unsure,
                        "submitted_at": payload.get("submitted_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                elif mode == "skip":
                    result = {"ok": True, "skipped": True}
                else:
                    result = self._submit_script(payload, timeout=10)
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)}, 400)

        else:
            self.send_json({"error": "not found"}, 404)

    def _run_sql_query(self, payload):
        question = find_question_by_id(payload.get("question_id"))
        if not isinstance(question, dict):
            raise ValueError("question not found")
        if str(question.get("type") or "").strip() != "sql":
            raise ValueError("question is not a SQL question")
        from learn_runtime.mysql_runtime import run_sql_preview

        sql = payload.get("sql") or payload.get("code") or ""
        return run_sql_preview(question, sql, load_runtime_context())

    def _submit_sql_query(self, payload):
        question = find_question_by_id(payload.get("question_id"))
        if not isinstance(question, dict):
            raise ValueError("question not found")
        if str(question.get("type") or "").strip() != "sql":
            raise ValueError("question is not a SQL question")
        from learn_runtime.mysql_runtime import submit_sql

        sql = payload.get("sql") or payload.get("code") or ""
        return submit_sql(question, sql, load_runtime_context())

    def _run_python_script(self, code, stdin_data="", timeout=10):
        try:
            proc = subprocess.run(
                ["conda", "run", "-n", CONDA_ENV, "python", "-c", code],
                input=stdin_data.encode("utf-8"),
                capture_output=True,
                timeout=timeout,
            )
            return {
                "stdout": proc.stdout.decode("utf-8", errors="replace"),
                "stderr": proc.stderr.decode("utf-8", errors="replace"),
                "returncode": proc.returncode,
                "error": proc.stderr.decode("utf-8", errors="replace") if proc.returncode != 0 else "",
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "", "returncode": -1, "error": "执行超时（超过 10 秒）"}
        except Exception as e:
            return {"stdout": "", "stderr": "", "returncode": -1, "error": str(e)}

    def _submit_script(self, payload, timeout=10):
        code = payload.get("code", "")
        test_cases = payload.get("test_cases", [])
        results = []
        all_passed = True
        for i, tc in enumerate(test_cases):
            result = self._run_python_script(code, tc.get("input", ""), timeout=timeout)
            expected = str(tc.get("output", "")).strip()
            actual = result.get("stdout", "").strip()
            passed = actual == expected and not result.get("error")
            if not passed:
                all_passed = False
            results.append(
                {
                    "case": i + 1,
                    "passed": passed,
                    "expected": expected,
                    "actual": actual,
                    "error": result.get("error", ""),
                }
            )
        return {
            "all_passed": all_passed,
            "passed_count": sum(1 for item in results if item["passed"]),
            "total_count": len(results),
            "results": results,
        }

    def _submit_written(self, payload):
        answer_text = str(payload.get("answer_text") or "")
        submitted_at = str(payload.get("submitted_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        if not answer_text.strip():
            return {
                "ok": False,
                "saved": False,
                "requires_manual_review": True,
                "review_status": "pending",
                "answer_length": 0,
                "submitted_at": submitted_at,
                "error": "答案不能为空",
            }
        return {
            "ok": True,
            "saved": True,
            "requires_manual_review": True,
            "review_status": "pending",
            "answer_length": len(answer_text),
            "submitted_at": submitted_at,
        }

    def _run_function_preview(self, payload, timeout=10):
        cases = payload.get("sample_cases") or payload.get("test_cases") or []
        question = find_question_by_id(payload.get("question_id")) if payload.get("question_id") else None
        if not cases and isinstance(question, dict):
            cases = runtime_question_cases(question, "public")
            if not cases:
                cases = []
                for case in question.get("public_tests") or question.get("test_cases") or []:
                    if isinstance(case, dict):
                        normalized_case = dict(case)
                        normalized_case.setdefault("category", "public")
                        cases.append(normalized_case)
        user_args = payload.get("args")
        user_kwargs = payload.get("kwargs")
        if not cases:
            if user_args is not None or user_kwargs is not None:
                # 用户指定了输入参数：用用户的参数执行并返回实际输出
                case = {}
                if user_args is not None:
                    case["args"] = user_args if isinstance(user_args, list) else [user_args]
                if user_kwargs is not None:
                    case["kwargs"] = user_kwargs
                runner = self._run_function_case(
                    code=payload.get("code", ""),
                    function_name=payload.get("function_name", ""),
                    case=case,
                    timeout=timeout,
                )
                return {
                    "returncode": 0 if not runner.get("error") else -1,
                    "stdout": runner.get("stdout", ""),
                    "stderr": runner.get("stderr", ""),
                    "result_repr": runner.get("actual_repr", ""),
                    "error": runner.get("error", ""),
                }
            return {
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "result_repr": "未提供示例输入。运行模式：语法检查已通过。如需传参调试，请在输入框中填写参数。",
                "error": "",
            }
        run_cases = []
        has_error = False
        for index, case in enumerate(cases[:5]):
            runner = self._run_function_case(
                code=payload.get("code", ""),
                function_name=payload.get("function_name", ""),
                case=case,
                timeout=timeout,
            )
            error = runner.get("error", "")
            has_error = has_error or bool(error)
            input_value = case.get("input", case.get("args", case.get("kwargs"))) if isinstance(case, dict) else None
            expected_value = case.get("expected") if isinstance(case, dict) else None
            run_cases.append(
                {
                    "case": index + 1,
                    "category": "public",
                    "passed": bool(runner.get("passed")) and not error,
                    "input": input_value,
                    "inputDisplay": display_value(input_value),
                    "input_repr": repr(input_value),
                    "expected": expected_value,
                    "expectedDisplay": runner.get("expectedDisplay") or display_value(expected_value),
                    "expected_repr": runner.get("expected_repr", ""),
                    "actualDisplay": runner.get("actualDisplay"),
                    "actual_repr": runner.get("actual_repr", ""),
                    "stdout": runner.get("stdout", ""),
                    "stderr": runner.get("stderr", ""),
                    "traceback": runner.get("traceback", ""),
                    "error": error,
                }
            )
        first = run_cases[0] if run_cases else {}
        return {
            "returncode": -1 if has_error else 0,
            "stdout": "\n".join(str(item.get("stdout") or "") for item in run_cases if item.get("stdout")),
            "stderr": "\n".join(str(item.get("stderr") or item.get("error") or "") for item in run_cases if item.get("stderr") or item.get("error")),
            "result_repr": first.get("actual_repr", ""),
            "run_cases": run_cases,
            "error": "；".join(str(item.get("error") or "") for item in run_cases if item.get("error")),
        }

    def _submit_function(self, payload, timeout=10):
        code = payload.get("code", "")
        question = find_question_by_id(payload.get("question_id")) if payload.get("question_id") else None
        function_name = payload.get("function_name", "")
        test_cases = payload.get("test_cases", [])
        if isinstance(question, dict):
            function_name = function_name or question.get("function_name", "")
            test_cases = runtime_question_cases(question, "all")
            if not test_cases:
                test_cases = []
                for key, category in (("public_tests", "public"), ("hidden_tests", "hidden")):
                    for case in question.get(key) or []:
                        if isinstance(case, dict):
                            normalized_case = dict(case)
                            normalized_case.setdefault("category", category)
                            test_cases.append(normalized_case)
            if not test_cases:
                test_cases = question.get("test_cases", [])
        failed_case_summaries = []
        failure_types = []
        passed_count = 0
        passed_public_count = 0
        passed_hidden_count = 0
        total_public_count = 0
        total_hidden_count = 0
        for i, case in enumerate(test_cases):
            category = case.get("category", "public") if isinstance(case, dict) else "public"
            if category == "hidden":
                total_hidden_count += 1
            else:
                total_public_count += 1
            result = self._run_function_case(code, function_name, case, timeout)
            passed = bool(result.get("passed")) and not result.get("error")
            if passed:
                passed_count += 1
                if category == "hidden":
                    passed_hidden_count += 1
                else:
                    passed_public_count += 1
                continue
            error = result.get("error") or "wrong_answer"
            if error not in failure_types:
                failure_types.append(error)
            if len(failed_case_summaries) < MAX_FAILED_CASE_SUMMARIES:
                summary = {
                    "case": i + 1,
                    "category": category,
                    "passed": False,
                    "error": error,
                    "capability_tags": case.get("capability_tags", []) if isinstance(case, dict) else [],
                }
                if category != "hidden":
                    input_value = case.get("input", case.get("args", case.get("kwargs"))) if isinstance(case, dict) else None
                    expected_value = case.get("expected") if isinstance(case, dict) else None
                    summary.update(
                        {
                            "input": input_value,
                            "inputDisplay": display_value(input_value),
                            "expected": expected_value,
                            "expectedDisplay": result.get("expectedDisplay") or display_value(expected_value),
                            "expected_repr": result.get("expected_repr", ""),
                            "actualDisplay": result.get("actualDisplay"),
                            "actual_repr": result.get("actual_repr", ""),
                        }
                    )
                failed_case_summaries.append(summary)
        return {
            "all_passed": passed_count == len(test_cases),
            "passed_count": passed_count,
            "total_count": len(test_cases),
            "passed_public_count": passed_public_count,
            "total_public_count": total_public_count,
            "passed_hidden_count": passed_hidden_count,
            "total_hidden_count": total_hidden_count,
            "failed_case_summaries": failed_case_summaries,
            "failure_types": failure_types,
            "results": failed_case_summaries,
        }

    def _run_function_case(self, code, function_name, case, timeout):
        payload = {
            "function_name": function_name,
            "case": case,
            "runtime_context": load_runtime_context(),
        }
        harness = textwrap.dedent(
            f"""
            import json
            import os
            import sys
            import traceback
            from pathlib import Path

            sys.path.insert(0, {BASE_DIR!r})
            RESULT_PREFIX = {RESULT_PREFIX!r}
            payload = {payload!r}
            code = Path('user_code.py').read_text(encoding='utf-8')
            namespace = {{}}

            def safe_repr(value):
                try:
                    return repr(value)
                except Exception:
                    return '<unreprable>'

            def display_value(value):
                from learn_runtime.display_values import to_display_value
                return to_display_value(value)

            def build_value(data, code_expr, namespace):
                if code_expr is not None:
                    return eval(code_expr, namespace, namespace)
                return data

            def normalize_runtime_case(case):
                if case.get('parameters') is None and case.get('bindings') is None:
                    return case
                from learn_runtime.mysql_runtime import build_python_call_case
                return build_python_call_case(case, payload.get('runtime_context') or {{}})

            def normalize_args(case, namespace):
                if case.get('args_code') is not None:
                    args = eval(case['args_code'], namespace, namespace)
                    if isinstance(args, tuple):
                        return list(args)
                    if isinstance(args, list):
                        return args
                    raise TypeError('args_code must evaluate to list or tuple')
                if 'args' in case:
                    args = case.get('args')
                    if isinstance(args, tuple):
                        return list(args)
                    if isinstance(args, list):
                        return args
                    raise TypeError('args must be list')
                if case.get('input_code') is not None:
                    return [eval(case['input_code'], namespace, namespace)]
                if 'input' in case:
                    return [case.get('input')]
                return []

            def normalize_kwargs(case, namespace):
                if case.get('kwargs_code') is not None:
                    kwargs = eval(case['kwargs_code'], namespace, namespace)
                    if not isinstance(kwargs, dict):
                        raise TypeError('kwargs_code must evaluate to dict')
                    return kwargs
                if 'kwargs' in case:
                    kwargs = case.get('kwargs')
                    if not isinstance(kwargs, dict):
                        raise TypeError('kwargs must be object')
                    return kwargs
                return {{}}

            def compare_values(actual, expected):
                if hasattr(actual, 'equals') and callable(actual.equals):
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
                return safe_repr(actual) == safe_repr(expected)

            def materialize_case_files(case):
                for raw_path, content in (case.get('files') or {{}}).items():
                    path = Path(str(raw_path))
                    if path.is_absolute() or '..' in path.parts:
                        raise ValueError(f'测试文件路径不允许越界: {{raw_path}}')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(str(content), encoding='utf-8')

            try:
                case = normalize_runtime_case(payload['case'])
                materialize_case_files(case)
                exec(code, namespace, namespace)
                func = namespace[payload['function_name']]
                args = normalize_args(case, namespace)
                kwargs = normalize_kwargs(case, namespace)
                expected = build_value(case.get('expected'), case.get('expected_code'), namespace)
                actual = func(*args, **kwargs)
                result = {{
                    'passed': compare_values(actual, expected),
                    'actual_repr': safe_repr(actual),
                    'expected_repr': safe_repr(expected),
                    'actualDisplay': display_value(actual),
                    'expectedDisplay': display_value(expected),
                    'error': '',
                    'traceback': ''
                }}
            except Exception as exc:
                result = {{
                    'passed': False,
                    'actual_repr': '',
                    'expected_repr': '',
                    'error': ''.join(traceback.format_exception_only(type(exc), exc)).strip(),
                    'traceback': traceback.format_exc()
                }}

            print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False))
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            user_code_path = os.path.join(tmpdir, "user_code.py")
            harness_path = os.path.join(tmpdir, "runner.py")
            with open(user_code_path, "w", encoding="utf-8") as f:
                f.write(code)
            with open(harness_path, "w", encoding="utf-8") as f:
                f.write(harness)
            try:
                proc = subprocess.run(
                    ["conda", "run", "-n", CONDA_ENV, "python", "runner.py"],
                    cwd=tmpdir,
                    capture_output=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return {
                    "passed": False,
                    "actual_repr": "",
                    "expected_repr": "",
                    "stdout": "",
                    "stderr": "",
                    "traceback": "",
                    "error": "执行超时（超过 10 秒）",
                }

        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        stdout_lines = stdout.splitlines()
        for line in reversed(stdout_lines):
            if line.startswith(RESULT_PREFIX):
                result = json.loads(line[len(RESULT_PREFIX) :])
                result["stdout"] = "\n".join(item for item in stdout_lines if not item.startswith(RESULT_PREFIX))
                result["stderr"] = stderr
                return result
        return {
            "passed": False,
            "actual_repr": "",
            "expected_repr": "",
            "stdout": stdout,
            "stderr": stderr,
            "traceback": "",
            "error": stderr.strip() or "函数执行失败，未返回结果。",
        }



def _load_diagnostic_resume_context(plan_path):
    if not plan_path:
        return {}
    diagnostic_path = Path(plan_path).expanduser().resolve().parent / ".learn-workflow" / "diagnostic.json"
    try:
        with open(diagnostic_path, "r", encoding="utf-8") as f:
            diagnostic = json.load(f)
    except Exception:
        return {}
    context = diagnostic.get("resume_context") if isinstance(diagnostic.get("resume_context"), dict) else {}
    return context if isinstance(context, dict) else {}



def build_diagnostic_next_route(progress):
    session = progress.get("session") if isinstance(progress.get("session"), dict) else {}
    execution_mode = session.get("plan_execution_mode")
    if execution_mode not in {"diagnostic", "test-diagnostic"}:
        return None
    round_index = session.get("round_index")
    max_rounds = session.get("max_rounds")
    try:
        next_round_index = int(round_index or 0) + 1
    except (TypeError, ValueError):
        next_round_index = None
    try:
        max_rounds_value = int(max_rounds or 0)
    except (TypeError, ValueError):
        max_rounds_value = 0
    follow_up_needed = bool(session.get("follow_up_needed"))
    next_round_required = bool(follow_up_needed and next_round_index and (max_rounds_value <= 0 or next_round_index <= max_rounds_value))
    return {
        "next_diagnostic_round_required": next_round_required,
        "next_round_index": next_round_index,
        "max_rounds": max_rounds,
        "required_artifacts": ["question-scope-json", "question-plan-json", "question-artifact-json", "question-review-json"] if next_round_required else ["semantic-diagnostic-json"],
        "next_action": "prepare_next_diagnostic_round_artifacts" if next_round_required else "run_semantic_diagnostic_update",
    }



def build_resume_command(progress):
    session = progress.get("session") or {}
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    plan_path = session.get("plan_path")
    resume_context = _load_diagnostic_resume_context(plan_path)
    goal_model = context.get("goal_model") if isinstance(context.get("goal_model"), dict) else {}
    diagnostic_profile = context.get("diagnostic_profile") if isinstance(context.get("diagnostic_profile"), dict) else {}
    resume_topic = session.get("resume_topic") or resume_context.get("topic") or progress.get("topic") or goal_model.get("mainline_goal")
    resume_goal = session.get("resume_goal") or resume_context.get("goal") or goal_model.get("mainline_goal") or progress.get("topic")
    resume_level = session.get("resume_level") or resume_context.get("level") or diagnostic_profile.get("recommended_entry_level") or diagnostic_profile.get("baseline_level") or context.get("current_stage") or "diagnostic"
    resume_schedule = session.get("resume_schedule") or resume_context.get("schedule") or "未指定"
    resume_preference = session.get("resume_preference") or resume_context.get("preference") or "混合"
    execution_mode = session.get("plan_execution_mode")
    session_type = session.get("type")
    skill_dir = session.get("skill_dir") or os.path.expanduser("~/.claude/skills/learn-plan")
    learn_test_update = os.path.join(skill_dir, "learn_test_update.py")
    update_command = None
    if plan_path and session_type == "test":
        update_command = " ".join([
            shlex.quote(sys.executable),
            shlex.quote(learn_test_update),
            "--session-dir", shlex.quote(BASE_DIR),
            "--plan-path", shlex.quote(plan_path),
        ])
    if execution_mode not in {"diagnostic", "test-diagnostic"}:
        return update_command
    if not all([plan_path, resume_topic, resume_goal, resume_level]):
        return update_command
    learn_plan = os.path.join(skill_dir, "learn_plan.py")
    resume_plan_command = " ".join([
        shlex.quote(sys.executable),
        shlex.quote(learn_plan),
        "--topic", shlex.quote(str(resume_topic)),
        "--goal", shlex.quote(str(resume_goal)),
        "--level", shlex.quote(str(resume_level)),
        "--schedule", shlex.quote(str(resume_schedule)),
        "--preference", shlex.quote(str(resume_preference)),
        "--plan-path", shlex.quote(plan_path),
        "--mode", "auto",
    ])
    if update_command:
        return " && ".join([update_command, resume_plan_command])
    return resume_plan_command



def auto_resume_session(resume_command):
    if not resume_command:
        return
    time.sleep(0.2)
    shutdown_server_soon(0)
    time.sleep(0.6)
    subprocess.Popen(
        ["/bin/zsh", "-lc", resume_command],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )



def finish_session(payload):
    progress = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)

    session = progress.get("session") or {}
    session["status"] = "finished"
    session["finished_at"] = payload.get("finished_at") or time.strftime("%Y-%m-%dT%H:%M:%S")
    if payload.get("type") is not None:
        session["type"] = payload.get("type")
    if payload.get("test_mode") is not None:
        session["test_mode"] = payload.get("test_mode")
    if payload.get("result_summary") is not None:
        progress["result_summary"] = payload.get("result_summary")
    progress["session"] = session

    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

    resume_command = build_resume_command(progress)
    diagnostic_next_route = build_diagnostic_next_route(progress)
    auto_resume_started = bool(resume_command)
    if auto_resume_started:
        threading.Thread(target=auto_resume_session, args=(resume_command,), daemon=False).start()
    return {
        "ok": True,
        "progress": progress,
        "message": "session finished",
        "resume_command": resume_command,
        "auto_resume_available": auto_resume_started,
        "auto_resume_started": auto_resume_started,
        "diagnostic_next_route": diagnostic_next_route,
    }


def shutdown_server_soon(delay=0.1):
    time.sleep(delay)
    if server_instance is not None:
        server_instance.shutdown()


def port_is_busy(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("localhost", port)) == 0


if __name__ == "__main__":
    if port_is_busy(PORT):
        print(f"learn-plan 服务未启动：端口 {PORT} 已被占用。")
        print("这通常表示本地已有一个 learn-plan 服务正在运行。")
        print(f"访问地址：http://localhost:{PORT}")
        print(f"当前 session 目录：{BASE_DIR}")
        print(f"题集文件：{HTML_FILE}")
        print(f"题目数据：{QUESTIONS_FILE}")
        print(f"进度文件：{PROGRESS_FILE}")
        print(f"启动命令：conda run -n {CONDA_ENV} python server.py")
        print("若需重启，请先停止已运行服务后再执行上述命令。")
        sys.exit(1)

    server_instance = ThreadingHTTPServer(("localhost", PORT), Handler)

    print("learn-plan 服务器已启动")
    print(f"当前 session 目录：{BASE_DIR}")
    print(f"题集文件：{HTML_FILE}")
    print(f"题目数据：{QUESTIONS_FILE}")
    print(f"进度文件：{PROGRESS_FILE}")
    print(f"服务文件：{os.path.join(BASE_DIR, 'server.py')}")
    print(f"启动命令：conda run -n {CONDA_ENV} python server.py")
    print(f"手动停服命令：pkill -f '{os.path.join(BASE_DIR, 'server.py')}'")
    print(f"浏览器访问：http://localhost:{PORT}")
    print("服务器不会因空闲自动关闭；完成学习/测试后可手动关闭页面或执行停服命令")
    print("按 Ctrl+C 可手动停止服务器")
    try:
        server_instance.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        sys.exit(0)
    finally:
        print("服务器已退出")
