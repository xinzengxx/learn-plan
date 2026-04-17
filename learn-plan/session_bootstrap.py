#!/usr/bin/env python3
"""
learn-plan session bootstrap

用途：
- 将已生成的 questions.json 落成完整 session 目录
- 初始化/重建 progress.json
- 复制题集模板与 server.py
- 按需启动本地服务并打开浏览器

题目生成仍由 skill/Claude 负责，本脚本只负责 session 运行时落地。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

PORT = 8080
URL = f"http://localhost:{PORT}"
SKILL_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SKILL_DIR / "templates"
SERVER_TEMPLATE = TEMPLATES_DIR / "server.py"
HTML_TEMPLATE = TEMPLATES_DIR / "题集模板.html"
PROGRESS_TEMPLATE = TEMPLATES_DIR / "progress_template.json"
SERVER_LOG = "server.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap a learn-plan session directory")
    parser.add_argument("--session-dir", required=True, help="目标 session 目录")
    parser.add_argument("--questions", help="源 questions.json 路径；默认使用 <session-dir>/questions.json")
    parser.add_argument("--plan-path", default="learn-plan.md", help="写入 progress.session.plan_path")
    parser.add_argument("--session-type", choices=["today", "test"], help="覆盖 session 类型")
    parser.add_argument(
        "--test-mode",
        choices=["general", "weakness-focused", "mixed"],
        help="覆盖测试模式，仅 test session 使用",
    )
    parser.add_argument("--force", action="store_true", help="强制覆盖模板文件与 progress.json")
    parser.add_argument("--no-start", action="store_true", help="只落文件，不启动服务")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def copy_file(src: Path, dst: Path, *, overwrite: bool) -> bool:
    should_copy = overwrite or not dst.exists()
    if not should_copy and src.exists() and dst.exists():
        should_copy = src.stat().st_mtime > dst.stat().st_mtime
    if not should_copy:
        return False
    shutil.copy2(src, dst)
    return True


def copy_tree(src: Path, dst: Path, *, overwrite: bool) -> bool:
    if not src.exists() or not src.is_dir():
        return False
    if dst.exists() and overwrite:
        shutil.rmtree(dst)
    if dst.exists() and not overwrite:
        return False
    shutil.copytree(src, dst)
    return True


def find_monaco_assets(session_dir: Path) -> Path | None:
    bundled = SKILL_DIR / "node_modules" / "monaco-editor"
    candidates = [
        bundled,
        session_dir / "node_modules" / "monaco-editor",
        session_dir.parent / "2026-04-07" / "node_modules" / "monaco-editor",
        session_dir.parent / "2026-04-06" / "node_modules" / "monaco-editor",
        session_dir.parent.parent / "1-编程基础" / "sessions" / "2026-03-28" / "node_modules" / "monaco-editor",
    ]
    for candidate in candidates:
        loader = candidate / "min" / "vs" / "loader.js"
        if loader.exists():
            return candidate
    return None


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def normalize_test_mode(value: Any) -> Any:
    if value in ("general", "weakness-focused", "mixed"):
        return value
    return None


def normalize_session_type(value: Any) -> str:
    if value == "test":
        return "test"
    return "today"


def normalize_int(value: Any) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return 0
    return result if result >= 0 else 0


def validate_questions_data(questions_data: dict[str, Any]) -> None:
    required_top_level = ["date", "topic", "mode", "session_type", "test_mode", "plan_source", "materials", "questions"]
    for key in required_top_level:
        if key not in questions_data:
            raise ValueError(f"questions.json 缺少字段: {key}")
    questions = questions_data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("questions 必须是非空列表")
    ids: set[str] = set()
    for item in questions:
        qid = item.get("id") if isinstance(item, dict) else None
        if not qid:
            raise ValueError("存在题目缺少 id")
        if qid in ids:
            raise ValueError(f"存在重复题目 id: {qid}")
        ids.add(qid)


def parse_difficulty_target(raw: Any) -> dict[str, Any]:
    text = str(raw or "").strip()
    result = {"raw": text or None, "concept": [], "code": []}
    if not text:
        return result
    for chunk in text.replace("，", ",").split(","):
        part = chunk.strip()
        if not part or " " not in part:
            continue
        label, levels_blob = part.split(" ", 1)
        label = label.strip().lower()
        levels = [item.strip() for item in levels_blob.split("/") if item.strip()]
        if label in {"concept", "code"}:
            result[label] = levels
    return result



def build_context_snapshot(questions_data: dict[str, Any]) -> dict[str, Any]:
    plan_source = questions_data.get("plan_source") if isinstance(questions_data.get("plan_source"), dict) else {}
    topic = questions_data.get("topic") or ""
    today_topic = str(plan_source.get("today_topic") or "").strip()
    topic_cluster = today_topic or topic or None
    diagnostic_profile = dict(plan_source.get("diagnostic_profile") or {})
    planning_state = dict(plan_source.get("planning_state") or {})
    assessment_depth = plan_source.get("assessment_depth") or planning_state.get("assessment_depth") or diagnostic_profile.get("assessment_depth")
    round_index = plan_source.get("round_index") or planning_state.get("diagnostic_round_index") or diagnostic_profile.get("round_index")
    max_rounds = plan_source.get("max_rounds") or planning_state.get("diagnostic_max_rounds") or diagnostic_profile.get("max_rounds")
    follow_up_needed = plan_source.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = planning_state.get("diagnostic_follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = diagnostic_profile.get("follow_up_needed")
    stop_reason = plan_source.get("stop_reason") or diagnostic_profile.get("stop_reason")
    return {
        "domain": questions_data.get("domain"),
        "source_kind": plan_source.get("source_kind") or plan_source.get("basis") or "plan-markdown-fallback",
        "lesson_generation_mode": plan_source.get("lesson_generation_mode"),
        "question_generation_mode": plan_source.get("question_generation_mode"),
        "daily_plan_artifact_path": plan_source.get("daily_plan_artifact_path"),
        "current_stage": plan_source.get("current_stage"),
        "current_day": plan_source.get("day"),
        "topic_cluster": topic_cluster,
        "review_focus": list(plan_source.get("review") or []),
        "new_learning_focus": list(plan_source.get("new_learning") or []),
        "exercise_focus": list(plan_source.get("exercise_focus") or []),
        "difficulty_target": parse_difficulty_target(plan_source.get("difficulty_target")),
        "recommended_materials": list(plan_source.get("recommended_materials") or []),
        "selected_segments": list(plan_source.get("selected_segments") or []),
        "material_alignment": dict(plan_source.get("material_alignment") or {}),
        "mastery_targets": dict(plan_source.get("mastery_targets") or {}),
        "session_objectives": list(plan_source.get("session_objectives") or []),
        "checkin": dict(plan_source.get("today_progress_checkin") or {}),
        "user_model": dict(plan_source.get("user_model") or {}),
        "goal_model": dict(plan_source.get("goal_model") or {}),
        "planning_state": planning_state,
        "preference_state": dict(plan_source.get("preference_state") or {}),
        "plan_execution_mode": plan_source.get("plan_execution_mode"),
        "session_intent": questions_data.get("session_intent"),
        "assessment_kind": questions_data.get("assessment_kind"),
        "diagnostic_profile": diagnostic_profile,
        "assessment_depth": assessment_depth,
        "round_index": round_index,
        "max_rounds": max_rounds,
        "follow_up_needed": follow_up_needed,
        "stop_reason": stop_reason,
        "goal_focus": {
            "mainline": plan_source.get("mainline_goal"),
            "supporting": list(plan_source.get("supporting_capabilities") or []),
            "enhancement": list(plan_source.get("enhancement_modules") or []),
        },
        "lesson_path": plan_source.get("lesson_path"),
        "plan_source_snapshot": json.loads(json.dumps(plan_source)),
    }



def deep_fill_defaults(target: dict[str, Any], template: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    changed = False
    for key, value in template.items():
        if key not in target:
            target[key] = json.loads(json.dumps(value))
            changed = True
            continue
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _, child_changed = deep_fill_defaults(target[key], value)
            changed = changed or child_changed
    return target, changed



def normalize_progress_questions(progress_questions: Any, questions_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    expected_items = [
        item for item in (questions_data.get("questions") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    expected_ids = [str(item.get("id") or "").strip() for item in expected_items]
    expected_by_id = {str(item.get("id") or "").strip(): item for item in expected_items}
    existing = progress_questions if isinstance(progress_questions, dict) else {}
    normalized: dict[str, Any] = {}
    changed = not isinstance(progress_questions, dict)
    for qid in expected_ids:
        question = expected_by_id.get(qid) or {}
        current = existing.get(qid)
        if not isinstance(current, dict):
            normalized[qid] = {
                "stats": {
                    "attempts": 0,
                    "correct_count": 0,
                    "pass_count": 0,
                    "last_status": None,
                    "last_submitted_at": None,
                },
                "history": [],
            }
            changed = True
            continue
        record = json.loads(json.dumps(current))
        stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
        category = str(question.get("category") or "")
        normalized_stats = json.loads(json.dumps(stats)) if isinstance(stats, dict) else {}
        normalized_stats["attempts"] = normalize_int(stats.get("attempts"))
        normalized_stats["correct_count"] = normalize_int(stats.get("correct_count"))
        normalized_stats["pass_count"] = normalize_int(stats.get("pass_count"))
        normalized_stats["last_status"] = stats.get("last_status")
        normalized_stats["last_submitted_at"] = stats.get("last_submitted_at")
        if category == "open":
            normalized_stats["review_status"] = stats.get("review_status")
        record["stats"] = normalized_stats
        if not isinstance(record.get("history"), list):
            record["history"] = []
            changed = True
        if record != current:
            changed = True
        normalized[qid] = record
    if set(existing.keys()) != set(normalized.keys()):
        changed = True
    return normalized, changed


def normalize_progress_data(progress: dict[str, Any], template: dict[str, Any], questions_data: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    normalized = json.loads(json.dumps(progress if isinstance(progress, dict) else template))
    changed = not isinstance(progress, dict)
    normalized, filled = deep_fill_defaults(normalized, template)
    changed = changed or filled
    questions = questions_data.get("questions") or []
    session_type = normalize_session_type(args.session_type or questions_data.get("session_type"))
    test_mode = normalize_test_mode(args.test_mode if args.test_mode is not None else questions_data.get("test_mode"))
    context_snapshot = build_context_snapshot(questions_data)
    plan_source = questions_data.get("plan_source") or {}

    if normalized.get("date") != questions_data.get("date"):
        normalized["date"] = questions_data.get("date") or template.get("date")
        changed = True
    if normalized.get("topic") != questions_data.get("topic"):
        normalized["topic"] = questions_data.get("topic") or template.get("topic")
        changed = True

    if not isinstance(normalized.get("session"), dict):
        normalized["session"] = json.loads(json.dumps(template.get("session") or {}))
        changed = True
    session = normalized["session"]
    expected_session = {
        "type": session_type,
        "intent": questions_data.get("session_intent") or session.get("intent"),
        "assessment_kind": questions_data.get("assessment_kind") or session.get("assessment_kind"),
        "plan_execution_mode": context_snapshot.get("plan_execution_mode"),
        "test_mode": test_mode,
        "status": session.get("status") if session.get("status") in {"active", "finished"} else "active",
        "started_at": session.get("started_at") or now_iso(),
        "finished_at": session.get("finished_at") if session.get("status") == "finished" else session.get("finished_at"),
        "plan_path": args.plan_path,
        "materials": questions_data.get("materials") or [],
        "source_kind": context_snapshot.get("source_kind") or "plan-markdown-fallback",
    }
    for key, value in expected_session.items():
        if session.get(key) != value:
            session[key] = value
            changed = True

    if not isinstance(normalized.get("summary"), dict):
        normalized["summary"] = json.loads(json.dumps(template.get("summary") or {}))
        changed = True
    summary = normalized["summary"]
    expected_total = len(questions)
    if summary.get("total") != expected_total:
        summary["total"] = expected_total
        changed = True
    for key in ("attempted", "correct"):
        value = summary.get(key)
        if not isinstance(value, int) or value < 0:
            summary[key] = 0
            changed = True

    if not isinstance(normalized.get("context"), dict):
        normalized["context"] = json.loads(json.dumps(template.get("context") or {}))
        changed = True
    context = normalized["context"]
    context, context_filled = deep_fill_defaults(context, template.get("context") or {})
    changed = changed or context_filled
    for key, value in context_snapshot.items():
        if context.get(key) != value:
            context[key] = value
            changed = True

    for key in ("assessment_depth", "round_index", "max_rounds", "follow_up_needed", "stop_reason"):
        expected_value = context_snapshot.get(key)
        if normalized.get(key) != expected_value:
            normalized[key] = expected_value
            changed = True

    expected_material_alignment = plan_source.get("material_alignment") or template.get("material_alignment") or {}
    if normalized.get("material_alignment") != expected_material_alignment:
        normalized["material_alignment"] = json.loads(json.dumps(expected_material_alignment))
        changed = True

    if not isinstance(normalized.get("learning_state"), dict):
        normalized["learning_state"] = json.loads(json.dumps(template.get("learning_state") or {}))
        changed = True
    if not isinstance(normalized.get("progression"), dict):
        normalized["progression"] = json.loads(json.dumps(template.get("progression") or {}))
        changed = True
    if not isinstance(normalized.get("update_history"), list):
        normalized["update_history"] = []
        changed = True

    normalized_questions, questions_changed = normalize_progress_questions(normalized.get("questions"), questions_data)
    if normalized.get("questions") != normalized_questions:
        normalized["questions"] = normalized_questions
    changed = changed or questions_changed

    if "result_summary" not in normalized:
        normalized["result_summary"] = None
        changed = True

    return normalized, changed


def progress_shape_is_valid(progress: dict[str, Any]) -> bool:
    if not isinstance(progress, dict):
        return False
    if not isinstance(progress.get("session"), dict):
        return False
    if not isinstance(progress.get("summary"), dict):
        return False
    if not isinstance(progress.get("questions"), dict):
        return False
    for key in ("date", "topic", "result_summary"):
        if key not in progress:
            return False
    return True


def determine_session_state(session_dir: Path, *, session_complete_before: bool, progress_repaired: bool, runtime_overwritten: bool) -> str:
    required = [session_dir / "题集.html", session_dir / "questions.json", session_dir / "progress.json", session_dir / "server.py"]
    had_all_files_before = all(path.exists() for path in required)
    if session_complete_before and not progress_repaired and not runtime_overwritten:
        return "continued"
    if had_all_files_before or progress_repaired or runtime_overwritten:
        return "repaired"
    return "created"


def make_progress_data(template: dict[str, Any], questions_data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    progress = json.loads(json.dumps(template))
    questions = questions_data.get("questions") or []
    session_type = normalize_session_type(args.session_type or questions_data.get("session_type"))
    test_mode = normalize_test_mode(args.test_mode if args.test_mode is not None else questions_data.get("test_mode"))
    context_snapshot = build_context_snapshot(questions_data)
    plan_source = questions_data.get("plan_source") or {}

    progress["date"] = questions_data.get("date") or progress.get("date")
    progress["topic"] = questions_data.get("topic") or progress.get("topic")
    progress.setdefault("session", {})
    progress["session"]["type"] = session_type
    progress["session"]["intent"] = questions_data.get("session_intent")
    progress["session"]["assessment_kind"] = questions_data.get("assessment_kind")
    progress["session"]["plan_execution_mode"] = context_snapshot.get("plan_execution_mode")
    progress["session"]["test_mode"] = test_mode
    progress["session"]["status"] = "active"
    progress["session"]["started_at"] = now_iso()
    progress["session"]["finished_at"] = None
    progress["session"]["plan_path"] = args.plan_path
    progress["session"]["materials"] = questions_data.get("materials") or []
    progress["session"]["source_kind"] = context_snapshot.get("source_kind") or "plan-markdown-fallback"
    progress.setdefault("summary", {})
    progress["summary"]["total"] = len(questions)
    progress["summary"]["attempted"] = 0
    progress["summary"]["correct"] = 0
    progress["context"] = context_snapshot
    progress["assessment_depth"] = context_snapshot.get("assessment_depth")
    progress["round_index"] = context_snapshot.get("round_index")
    progress["max_rounds"] = context_snapshot.get("max_rounds")
    progress["follow_up_needed"] = context_snapshot.get("follow_up_needed")
    progress["stop_reason"] = context_snapshot.get("stop_reason")
    progress["material_alignment"] = json.loads(json.dumps(plan_source.get("material_alignment") or template.get("material_alignment") or {}))
    progress.setdefault("learning_state", json.loads(json.dumps(template.get("learning_state") or {})))
    progress.setdefault("progression", json.loads(json.dumps(template.get("progression") or {})))
    progress.setdefault("update_history", [])
    progress_questions: dict[str, Any] = {}
    for item in questions:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        qid = str(item.get("id"))
        stats = {
            "attempts": 0,
            "correct_count": 0,
            "pass_count": 0,
            "last_status": None,
            "last_submitted_at": None,
        }
        if item.get("category") == "open":
            stats["review_status"] = None
        progress_questions[qid] = {"stats": stats, "history": []}
    progress["questions"] = progress_questions
    progress["result_summary"] = None
    return progress


def port_is_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("localhost", port)) == 0


def fetch_server_info() -> dict[str, Any] | None:
    try:
        with urlopen(f"{URL}/server-info", timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, TimeoutError, json.JSONDecodeError):
        return None


def inspect_listening_process(port: int) -> dict[str, str] | None:
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return None

    parts = lines[1].split()
    if len(parts) < 2:
        return None

    pid = parts[1]
    command = parts[0]
    command_line = command
    ps_result = subprocess.run(["ps", "-p", pid, "-o", "command="], capture_output=True, text=True, check=False)
    if ps_result.returncode == 0 and ps_result.stdout.strip():
        command_line = ps_result.stdout.strip()

    return {
        "pid": pid,
        "command": command,
        "command_line": command_line,
        "raw": lines[1],
    }


def ensure_questions_file(session_dir: Path, source_questions: Path) -> Path:
    target = session_dir / "questions.json"
    source_resolved = source_questions.resolve()
    target_resolved = target.resolve() if target.exists() else target
    if source_resolved != target_resolved:
        shutil.copy2(source_questions, target)
    elif not target.exists():
        shutil.copy2(source_questions, target)
    return target


def ensure_runtime_files(session_dir: Path, *, overwrite: bool) -> bool:
    changed_server = copy_file(SERVER_TEMPLATE, session_dir / "server.py", overwrite=overwrite)
    changed_html = copy_file(HTML_TEMPLATE, session_dir / "题集.html", overwrite=overwrite)
    monaco_src = find_monaco_assets(session_dir)
    changed_monaco = False
    if monaco_src is not None:
        changed_monaco = copy_tree(monaco_src, session_dir / "node_modules" / "monaco-editor", overwrite=overwrite)
    return changed_server or changed_html or changed_monaco


def ensure_progress_file(session_dir: Path, questions_data: dict[str, Any], args: argparse.Namespace) -> tuple[Path, bool]:
    progress_path = session_dir / "progress.json"
    template = load_json(PROGRESS_TEMPLATE)
    if progress_path.exists() and not args.force:
        progress = load_json(progress_path)
        normalized, changed = normalize_progress_data(progress, template, questions_data, args)
        if changed or not progress_shape_is_valid(progress):
            save_json(progress_path, normalized)
            return progress_path, True
        return progress_path, False
    progress = make_progress_data(template, questions_data, args)
    save_json(progress_path, progress)
    return progress_path, True


def is_complete_session(session_dir: Path) -> bool:
    required = [session_dir / "题集.html", session_dir / "questions.json", session_dir / "progress.json", session_dir / "server.py"]
    if not all(path.exists() for path in required):
        return False
    try:
        validate_questions_data(load_json(session_dir / "questions.json"))
        progress = load_json(session_dir / "progress.json")
    except Exception:
        return False
    return progress_shape_is_valid(progress)


def start_server(session_dir: Path) -> tuple[bool, str]:
    info = fetch_server_info() if port_is_busy(PORT) else None
    if info:
        base_dir = info.get("base_dir")
        if base_dir and Path(base_dir).resolve() == session_dir.resolve():
            return True, "already_running"
        return False, f"端口 {PORT} 已被其他进程占用：{base_dir or 'unknown'}"
    if port_is_busy(PORT):
        process = inspect_listening_process(PORT)
        if process:
            return False, f"端口 {PORT} 已被占用，当前监听进程 PID={process['pid']}，命令={process['command_line']}"
        return False, f"端口 {PORT} 已被占用，无法启动 session 服务"

    log_path = session_dir / SERVER_LOG
    with log_path.open("ab") as log_file:
        subprocess.Popen(
            ["conda", "run", "-n", "base", "python", "server.py"],
            cwd=session_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    deadline = time.time() + 12
    while time.time() < deadline:
        info = fetch_server_info()
        if info and Path(info.get("base_dir", "")).resolve() == session_dir.resolve():
            return True, "started"
        time.sleep(0.2)
    return False, f"服务未在预期时间内启动，可查看日志：{log_path}"


def open_browser(url: str) -> None:
    subprocess.run(["open", url], check=False)


def print_summary(
    session_dir: Path,
    questions_path: Path,
    progress_path: Path,
    started: bool,
    start_status: str,
    *,
    should_start: bool,
    session_state: str,
) -> None:
    server_path = session_dir / "server.py"
    html_path = session_dir / "题集.html"
    log_path = session_dir / SERVER_LOG
    stop_command = f"pkill -f '{server_path}'"
    print(f"session 目录：{session_dir}")
    print(f"题集文件：{html_path}")
    print(f"题目数据：{questions_path}")
    print(f"进度文件：{progress_path}")
    print(f"服务文件：{server_path}")
    print(f"日志文件：{log_path}")
    print(f"session 状态：{session_state}")
    print("启动命令：conda run -n base python server.py")
    print(f"手动停服命令：{stop_command}")
    if should_start:
        print(f"浏览器访问：{URL}")
        print(f"服务状态：{start_status if started else 'failed'}")
        if not started and "端口 8080" in start_status:
            process = inspect_listening_process(PORT)
            print(f"目标 session：{session_dir}")
            if process:
                print(f"端口占用进程：PID={process['pid']} | {process['command_line']}")
            print("切换建议：当前仅支持单端口单 session；我应先告诉用户当前是什么进程占用 8080，并在用户确认后再协助停掉它，然后启动学习服务")
    else:
        print("服务状态：skipped")


def main() -> int:
    args = parse_args()
    session_dir = Path(args.session_dir).expanduser().resolve()
    session_dir.mkdir(parents=True, exist_ok=True)

    source_questions = Path(args.questions).expanduser().resolve() if args.questions else session_dir / "questions.json"
    if not source_questions.exists():
        print(f"questions.json 不存在：{source_questions}", file=sys.stderr)
        return 1

    questions_path = ensure_questions_file(session_dir, source_questions)
    questions_data = load_json(questions_path)
    validate_questions_data(questions_data)

    session_complete_before = is_complete_session(session_dir)
    runtime_changed = ensure_runtime_files(session_dir, overwrite=args.force)
    progress_path, progress_repaired = ensure_progress_file(session_dir, questions_data, args)
    session_state = determine_session_state(
        session_dir,
        session_complete_before=session_complete_before,
        progress_repaired=progress_repaired,
        runtime_overwritten=runtime_changed,
    )

    started = False
    start_status = "not_started"
    if not args.no_start:
        started, start_status = start_server(session_dir)
        if started and not args.no_open:
            open_browser(URL)

    print_summary(
        session_dir,
        questions_path,
        progress_path,
        started,
        start_status,
        should_start=not args.no_start,
        session_state=session_state,
    )

    if not args.no_start and not started:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
