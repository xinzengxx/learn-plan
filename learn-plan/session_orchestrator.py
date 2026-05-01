#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists as core_read_json_if_exists, read_text_if_exists as core_read_text_if_exists, write_json as core_write_json
from learn_core.markdown_sections import extract_markdown_section
from learn_core.plan_parser import extract_numbered_subsection as core_extract_numbered_subsection, extract_plain_bullets as core_extract_plain_bullets, extract_recent_bullet_values as core_extract_recent_bullet_values, split_semicolon_values as core_split_semicolon_values, summarize_plan_bullets as core_summarize_plan_bullets
from learn_core.text_utils import normalize_string_list as core_normalize_string_list
from learn_core.topic_family import detect_topic_family as core_detect_topic_family, infer_domain as core_infer_domain
from learn_runtime.material_selection import (
    choose_material_local_path,
    load_materials,
    material_matches_recommendation,
    material_text_blob,
    normalize_material_item,
    prefer_precise_segments,
    segment_matches_day,
    select_material_segments,
    text_has_any,
)
from learn_runtime.plan_source import (
    apply_cli_overrides,
    apply_plan_gates,
    day_matches,
    extract_nested_bullet_block,
    extract_prefixed_values,
    extract_today_checkin,
    make_plan_source,
    make_plan_source_from_markdown_fallback,
    make_plan_source_from_progress_state,
    normalize_day_key,
    normalize_python_day_material_anchor,
    normalize_status_token,
    parse_learning_profile_section,
    plan_status_is_executable,
    resolve_plan_execution_mode,
)
from learn_runtime.payload_builder import (
    build_questions_payload as runtime_build_questions_payload,
    ensure_question_shape,
)
from learn_runtime.mysql_materializer import write_materialized_dataset
from learn_runtime.schemas import ensure_dataset_artifact_basic, validate_progress_basic
from learn_runtime.lesson_builder import render_daily_lesson_plan_markdown
from learn_runtime.notebook_renderer import render_daily_lesson_notebook
from learn_runtime.question_generation import is_valid_runtime_question
from learn_runtime.session_history import load_latest_structured_state
from learn_runtime.source_grounding import (
    build_content_aware_explanation,
    build_content_aware_pitfall,
    build_segment_source_brief,
    clean_source_teaching_terms,
    collect_segment_pdf_search_terms,
    combine_source_terms,
    compact_source_text,
    derive_git_teaching_terms,
    derive_material_text_candidates,
    ensure_segment_source_cache,
    extract_pdf_pages_to_text,
    extract_pdfkit_pages_to_text,
    extract_segment_source_context,
    load_cached_segment_text,
    load_material_source_text,
    normalize_source_text,
    parse_pages_spec,
    resolve_segment_cache_path,
    search_pdfkit_pages_for_terms,
    segment_specificity,
    source_brief_has_substance,
    split_source_paragraphs,
    summarize_segment_teaching_points,
)

SKILL_DIR = Path(__file__).resolve().parent
BOOTSTRAP = SKILL_DIR / "session_bootstrap.py"
VALID_TEST_MODES = {"general", "weakness-focused", "mixed"}

TOPIC_FAMILIES = {
    "english": ["英语", "词汇", "语法", "阅读", "写作", "英文", "English", "english"],
    "math": ["数学", "线代", "高数", "概率", "离散", "微积分"],
    "algorithm": ["算法", "数据结构", "刷题", "LeetCode", "leetcode", "双指针", "二分", "DFS", "BFS", "动态规划"],
    "linux": ["Linux", "linux", "GNU/Linux", "shell", "Shell", "bash", "zsh", "命令行", "终端", "操作系统", "系统管理", "系统运维", "服务器"],
    "llm-app": ["LangChain", "langchain", "LangGraph", "langgraph", "RAG", "rag", "Agent", "agent", "提示工程", "大模型", "LLM", "llm", "向量数据库", "embedding", "embeddings", "prompt", "Claude API", "Anthropic API", "模型应用"],
    "backend": ["后端", "backend", "API", "api", "Flask", "Django", "FastAPI", "Spring", "Node.js", "服务端", "微服务"],
    "frontend": ["前端", "frontend", "React", "react", "Vue", "vue", "Next.js", "next.js", "HTML", "CSS", "JavaScript", "TypeScript", "浏览器"],
    "database": ["数据库", "database", "SQL", "sql", "MySQL", "PostgreSQL", "postgres", "Redis", "索引", "事务"],
    "git": ["Git", "git", "版本控制", "仓库", "暂存区", "提交", "commit", "branch", "分支", "merge", "remote", "HEAD"],
    "python": ["Python", "python", "pandas", "Pandas", "numpy", "NumPy", "pythonic", "Jupyter", "jupyter", "数据分析"],
}

EXECUTABLE_PLAN_STATUSES = {
    "approved",
    "plan-confirmed",
    "confirmed",
    "accepted",
    "complete",
    "completed",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a minimal learn-plan session and bootstrap it")
    parser.add_argument("--session-dir", required=True, help="目标 session 目录")
    parser.add_argument("--topic", help="学习主题；未提供时尝试从 plan 中提取")
    parser.add_argument("--plan-path", default="learn-plan.md", help="学习计划文件路径")
    parser.add_argument("--session-type", choices=["today", "test"], default="today")
    parser.add_argument("--test-mode", choices=["general", "weakness-focused", "mixed"], help="test session 的模式")
    parser.add_argument("--date", default=time.strftime("%Y-%m-%d"), help="写入 questions.json 的日期")
    parser.add_argument("--force-generate", action="store_true", help="即使 questions.json 已存在也重生成")
    parser.add_argument("--force-bootstrap", action="store_true", help="透传给 bootstrap 的 --force")
    parser.add_argument("--no-start", action="store_true", help="透传给 bootstrap 的 --no-start")
    parser.add_argument("--no-open", action="store_true", help="透传给 bootstrap 的 --no-open")
    parser.add_argument("--current-stage", help="显式指定当前阶段，优先级高于自动推断")
    parser.add_argument("--current-day", help="显式指定当前 Day，优先级高于自动推断")
    parser.add_argument("--today-topic", help="显式指定今日主题，优先级高于自动推断")
    parser.add_argument("--review", action="append", help="显式指定复习点，可重复传入")
    parser.add_argument("--new-learning", action="append", help="显式指定新学习点，可重复传入")
    parser.add_argument("--exercise-focus", action="append", help="显式指定练习重点，可重复传入")
    parser.add_argument("--lesson-focus-point", action="append", help="显式指定 lesson focus point，可重复传入")
    parser.add_argument("--project-task", action="append", help="显式指定 project task，可重复传入")
    parser.add_argument("--project-blocker", action="append", help="显式指定 project blocker，可重复传入")
    parser.add_argument("--review-target", action="append", help="显式指定 review target，可重复传入")
    parser.add_argument("--time-budget", help="显式指定今日时间预算")
    parser.add_argument("--assessment-depth", choices=["simple", "deep"], help="已废弃的兼容参数；新链路请使用 --max-rounds 与 --questions-per-round")
    parser.add_argument("--round-index", type=int, help="显式指定当前诊断轮次")
    parser.add_argument("--max-rounds", type=int, help="显式指定诊断总轮次")
    parser.add_argument("--questions-per-round", type=int, help="显式指定每轮总题数")
    parser.add_argument("--follow-up-needed", action="store_true", default=None, help="显式标记需要后续追问轮次")
    parser.add_argument("--stop-reason", help="显式指定当前诊断结束原因或状态")
    parser.add_argument("--locked-plan-execution-mode", choices=["diagnostic", "test-diagnostic"], help="锁定运行时 plan_execution_mode，避免显式诊断 session 被通用 gate 覆盖")
    parser.add_argument("--resume-topic", help="自动回流到 /learn-plan 时使用的 topic")
    parser.add_argument("--resume-goal", help="自动回流到 /learn-plan 时使用的 goal")
    parser.add_argument("--resume-level", help="自动回流到 /learn-plan 时使用的 level")
    parser.add_argument("--resume-schedule", help="自动回流到 /learn-plan 时使用的 schedule")
    parser.add_argument("--resume-preference", help="自动回流到 /learn-plan 时使用的 preference")
    parser.add_argument("--lesson-artifact-json", help="外部注入的 lesson artifact JSON 路径")
    parser.add_argument("--lesson-html-json", help="外部注入的课件 HTML JSON 路径（long-output-html 格式）")
    parser.add_argument("--question-scope-json", help="外部注入的 question scope JSON 路径")
    parser.add_argument("--question-plan-json", help="外部注入的 question plan JSON 路径")
    parser.add_argument("--question-artifact-json", help="外部注入的 questions artifact JSON 路径")
    parser.add_argument("--question-review-json", help="外部注入的 strict question review JSON 路径")
    parser.add_argument("--parameter-spec-json", help="外部注入的 parameter-spec JSON 路径")
    parser.add_argument("--parameter-artifact-json", help="外部注入的 parameter-artifact JSON 路径")
    parser.add_argument("--dataset-artifact-json", help="外部注入的 dataset-artifact JSON 路径")
    parser.add_argument("--materialized-dataset-json", help="外部注入或 materializer 生成的 materialized-dataset JSON 路径")
    parser.add_argument("--mysql-config-json", help="MySQL runtime 配置 JSON 路径；密码只允许通过环境变量引用")
    parser.add_argument("--skip-materialize", action="store_true", help="跳过 dataset-artifact 到 MySQL 的物化步骤")
    return parser.parse_args()


def read_text_if_exists(path: Path) -> str:
    return core_read_text_if_exists(path)


def read_json_if_exists(path: Path) -> dict[str, Any]:
    return core_read_json_if_exists(path)


def load_runtime_json(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    payload = read_json_if_exists(path)
    return payload if isinstance(payload, dict) and payload else None


def maybe_materialize_datasets(args: argparse.Namespace, session_dir: Path) -> None:
    if args.skip_materialize or args.materialized_dataset_json or not args.dataset_artifact_json:
        return
    dataset_artifact = load_runtime_json(args.dataset_artifact_json)
    if not dataset_artifact:
        return
    ensure_dataset_artifact_basic(dataset_artifact)
    if not dataset_artifact.get("datasets"):
        return
    mysql_config = load_runtime_json(args.mysql_config_json)
    output_path = session_dir / "materialized-dataset.json"
    write_materialized_dataset(dataset_artifact, output_path, mysql_config=mysql_config, session_dir=session_dir)
    args.materialized_dataset_json = str(output_path)


def extract_topic_from_plan(plan_text: str) -> str | None:
    for line in plan_text.splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if not stripped:
            continue
        if stripped.startswith("学习主题"):
            parts = stripped.split(":", 1) if ":" in stripped else stripped.split("：", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            value = stripped.lstrip("#").strip()
            if value and value.lower() != "learn plan":
                return value
    return None


def detect_topic_family(topic: str, plan_text: str) -> str:
    return core_detect_topic_family(topic, TOPIC_FAMILIES, fallback_text=plan_text)


def infer_domain(topic: str, plan_text: str) -> str:
    return core_infer_domain(topic, TOPIC_FAMILIES, fallback_text=plan_text)


def extract_section(plan_text: str, heading: str) -> str:
    return extract_markdown_section(plan_text, heading)


def extract_recent_bullet_values(section_text: str, prefixes: list[str], *, limit: int = 3) -> list[str]:
    return core_extract_recent_bullet_values(section_text, prefixes, limit=limit)


def extract_plain_bullets(section_text: str, *, limit: int = 4) -> list[str]:
    return core_extract_plain_bullets(section_text, limit=limit)


def extract_numbered_subsection(section_text: str, heading: str) -> str:
    return core_extract_numbered_subsection(section_text, heading)


def summarize_plan_bullets(plan_text: str, *, limit: int = 6) -> list[str]:
    return core_summarize_plan_bullets(plan_text, limit=limit)


def split_semicolon_values(value: Any) -> list[str]:
    return core_split_semicolon_values(value)



def normalize_string_list(values: Any) -> list[str]:
    return core_normalize_string_list(values)



def write_json(path: Path, data: dict[str, Any]) -> None:
    core_write_json(path, data)


def progress_shape_is_valid(progress: dict[str, Any]) -> bool:
    if not isinstance(progress, dict):
        return False
    if not isinstance(progress.get("summary"), dict):
        return False
    if not isinstance(progress.get("questions"), dict):
        return False
    for key in ("total", "attempted", "correct"):
        if key not in progress["summary"]:
            return False
    return not validate_progress_basic(progress)


def is_complete_session(session_dir: Path) -> bool:
    required = [session_dir / "题集.html", session_dir / "questions.json", session_dir / "progress.json", session_dir / "server.py"]
    if not all(path.exists() for path in required):
        return False
    try:
        ensure_question_shape(json.loads((session_dir / "questions.json").read_text(encoding="utf-8")))
        progress = json.loads((session_dir / "progress.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    return progress_shape_is_valid(progress)


def run_bootstrap(args: argparse.Namespace, session_dir: Path, questions_path: Path | None) -> int:
    command = [sys.executable, str(BOOTSTRAP), "--session-dir", str(session_dir), "--plan-path", args.plan_path]
    if questions_path is not None:
        command.extend(["--questions", str(questions_path)])
    if args.session_type == "test":
        command.extend(["--session-type", "test"])
        if args.test_mode:
            command.extend(["--test-mode", args.test_mode])
    if args.resume_topic:
        command.extend(["--resume-topic", args.resume_topic])
    if args.resume_goal:
        command.extend(["--resume-goal", args.resume_goal])
    if args.resume_level:
        command.extend(["--resume-level", args.resume_level])
    if args.resume_schedule:
        command.extend(["--resume-schedule", args.resume_schedule])
    if args.resume_preference:
        command.extend(["--resume-preference", args.resume_preference])
    if args.force_bootstrap:
        command.append("--force")
    if args.no_start:
        command.append("--no-start")
    if args.no_open:
        command.append("--no-open")
    return subprocess.run(command, check=False).returncode


def write_daily_lesson_plan(plan_path: Path, payload: dict[str, Any], session_dir: Path, *, lesson_html_json: str | None = None) -> Path:
    plan_source = payload.get("plan_source") if isinstance(payload.get("plan_source"), dict) else {}
    daily_plan = plan_source.get("daily_lesson_plan") if isinstance(plan_source.get("daily_lesson_plan"), dict) else {}
    date_text = payload.get("date") or time.strftime("%Y-%m-%d")
    root_html_path = session_dir / "lesson.html"

    if lesson_html_json and Path(lesson_html_json).exists():
        # 新管线：先校验 lesson-html.json 内容质量，再渲染
        from learn_runtime.lesson_html_validation import validate_lesson_html_json

        json_text = Path(lesson_html_json).read_text(encoding="utf-8")
        try:
            lesson_data = json.loads(json_text)
            quality = validate_lesson_html_json(lesson_data)
            if not quality.get("valid"):
                issues_text = "；".join(quality["issues"][:6])
                raise ValueError(f"lesson-html.json 内容质量不合格：{issues_text}")
        except json.JSONDecodeError as e:
            raise ValueError(f"lesson-html.json JSON 解析失败：{e}") from e

        # 渲染
        render_script = Path("/Users/xinyuan/.claude/scripts/render_long_output_html.py")
        if render_script.exists():
            import subprocess
            html_result = subprocess.run(
                ["python3", str(render_script)],
                input=json_text, capture_output=True, text=True,
            )
            if html_result.returncode == 0:
                rendered_path = html_result.stdout.strip().splitlines()[-1] if html_result.stdout.strip() else ""
                if rendered_path and Path(rendered_path).exists():
                    import shutil
                    shutil.copy2(rendered_path, root_html_path)
            else:
                print(f"警告：long-output-html 渲染失败，回退到旧管线。stderr: {html_result.stderr[:300]}")
        else:
            print(f"警告：渲染脚本不存在 {render_script}，回退到旧管线。")
    else:
        raise ValueError(
            "未提供 --lesson-html-json。请 Agent 按 learn-today/SKILL.md §4.1 生成 /long-output-html 兼容 JSON。"
            " 要求覆盖三段教学框架：Part 1 往期复习、Part 2 本期知识点讲解、Part 3 本期内容回看，"
            " 并在内容回看中提供材料名、章节、页码、段落、section 或 locator 等具体引用信息。"
        )

    if not root_html_path.exists():
        # Fallback 仅在新管线渲染失败时使用
        print("使用已废弃的旧渲染器生成课件。叙事质量受限。")
        content = render_daily_lesson_plan_markdown(daily_plan) if daily_plan else "# 当日学习计划\n\n- 暂无可生成的教学计划内容。\n"
        html_content = f"<!doctype html><meta charset=utf-8><pre>{content}</pre>"
        root_html_path.write_text(html_content, encoding="utf-8")

    # 不再生成 .ipynb 副本
    plan_source["lesson_path"] = str(root_html_path)
    plan_source["daily_plan_artifact_path"] = str(root_html_path)
    plan_source["lesson_notebook_path"] = None
    plan_source["lesson_markdown_path"] = None
    return root_html_path



def print_orchestrator_summary(session_dir: Path, plan_path: Path, materials: list[dict[str, Any]], *, daily_plan_path: Path | None = None) -> None:
    print(f"检测 learn-plan.md：{'yes' if plan_path.exists() else 'no'}")
    print(f"材料条目数：{len(materials)}")
    if daily_plan_path is not None:
        print(f"当日教学计划：{daily_plan_path}")


def main() -> int:
    args = parse_args()
    if args.session_type == "test" and not args.test_mode:
        args.test_mode = "general"
    if args.session_type == "today":
        args.test_mode = None
    if args.test_mode and args.test_mode not in VALID_TEST_MODES:
        raise ValueError(f"无效 test_mode: {args.test_mode}")

    session_dir = Path(args.session_dir).expanduser().resolve()
    maybe_materialize_datasets(args, session_dir)
    plan_path = Path(args.plan_path).expanduser().resolve()
    plan_text = read_text_if_exists(plan_path)
    topic = (args.topic or extract_topic_from_plan(plan_text) or "算法基础").strip()

    lesson_html_json = getattr(args, "lesson_html_json", None)
    is_test_session = args.session_type == "test"

    if is_complete_session(session_dir) and not args.force_generate:
        questions_path = session_dir / "questions.json"
        existing_payload = read_json_if_exists(questions_path)
        daily_plan_path = write_daily_lesson_plan(plan_path, existing_payload, session_dir, lesson_html_json=lesson_html_json) if existing_payload and not is_test_session else None
        if existing_payload:
            write_json(questions_path, existing_payload)
        print_orchestrator_summary(session_dir, plan_path, load_materials(plan_path, topic), daily_plan_path=daily_plan_path)
        return run_bootstrap(args, session_dir, None)

    questions_path = session_dir / "questions.json"
    materials = load_materials(plan_path, topic)
    payload = runtime_build_questions_payload(args, topic, plan_text, materials)
    # test session 不需要 lesson.html，只生成题集
    daily_plan_path = write_daily_lesson_plan(plan_path, payload, session_dir, lesson_html_json=lesson_html_json) if not is_test_session else None
    write_json(questions_path, payload)
    print_orchestrator_summary(session_dir, plan_path, materials, daily_plan_path=daily_plan_path)
    return run_bootstrap(args, session_dir, questions_path)


if __name__ == "__main__":
    sys.exit(main())
