#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a learn-plan test session and update learn-plan.md")
    parser.add_argument("--session-dir", required=True, help="session 目录，需包含 progress.json")
    parser.add_argument("--plan-path", default="learn-plan.md", help="学习计划文件路径")
    parser.add_argument("--project-path", help="可选 PROJECT.md 路径；仅在需要兼容旧项目记录时使用")
    parser.add_argument("--stdout-json", action="store_true", help="额外输出 JSON 摘要")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_text_if_exists(path: Path) -> str:
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def normalize_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def normalize_string_list(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def summarize_mastery(progress: dict[str, Any], questions_data: dict[str, Any]) -> dict[str, Any]:
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    plan_source = questions_data.get("plan_source") if isinstance(questions_data.get("plan_source"), dict) else {}
    mastery_targets = context.get("mastery_targets") if isinstance(context.get("mastery_targets"), dict) else {}
    if not mastery_targets:
        mastery_targets = plan_source.get("mastery_targets") if isinstance(plan_source.get("mastery_targets"), dict) else {}
    mastery_checks = progress.get("mastery_checks") if isinstance(progress.get("mastery_checks"), dict) else {}
    reading_progress = progress.get("reading_progress") if isinstance(progress.get("reading_progress"), dict) else {}
    artifacts = progress.get("artifacts") if isinstance(progress.get("artifacts"), list) else []
    reflection = str(progress.get("reflection") or "").strip()

    target_reading = normalize_string_list(mastery_targets.get("reading_checklist"))
    recorded_reading = normalize_string_list(mastery_checks.get("reading_checklist"))
    if reading_progress and not recorded_reading:
        recorded_reading = normalize_string_list(reading_progress.keys())
    reading_done = bool(target_reading) and len(recorded_reading) >= max(1, min(len(target_reading), 2))

    target_session = normalize_string_list(mastery_targets.get("session_exercises"))
    recorded_session = normalize_string_list(mastery_checks.get("session_exercises"))
    session_done = bool(target_session or recorded_session)

    target_project = normalize_string_list(mastery_targets.get("applied_project"))
    recorded_project = normalize_string_list(mastery_checks.get("applied_project"))
    project_done = bool(recorded_project or artifacts)

    target_reflection = normalize_string_list(mastery_targets.get("reflection"))
    recorded_reflection = normalize_string_list(mastery_checks.get("reflection"))
    reflection_done = bool(recorded_reflection or reflection)

    return {
        "target_reading": target_reading,
        "recorded_reading": recorded_reading,
        "reading_done": reading_done,
        "target_session": target_session,
        "recorded_session": recorded_session,
        "session_done": session_done,
        "target_project": target_project,
        "recorded_project": recorded_project,
        "project_done": project_done,
        "target_reflection": target_reflection,
        "recorded_reflection": recorded_reflection,
        "reflection_done": reflection_done,
        "reflection_text": reflection,
        "artifacts": artifacts,
    }



def update_progress_state(progress: dict[str, Any], summary: dict[str, Any], *, questions_data: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(progress))
    context = updated.get("context") if isinstance(updated.get("context"), dict) else {}
    learning_state = updated.get("learning_state") if isinstance(updated.get("learning_state"), dict) else {}
    progression = updated.get("progression") if isinstance(updated.get("progression"), dict) else {}
    update_history = updated.get("update_history") if isinstance(updated.get("update_history"), list) else []
    session = updated.get("session") if isinstance(updated.get("session"), dict) else {}
    plan_source = questions_data.get("plan_source") if isinstance(questions_data.get("plan_source"), dict) else {}
    mastery = summary.get("mastery") or {}

    weaknesses = normalize_string_list(summary.get("weaknesses"))
    next_actions = normalize_string_list(summary.get("next_actions"))
    covered_scope = normalize_string_list(summary.get("covered_scope"))
    attempted = normalize_int(summary.get("attempted"))
    finished_at = summary.get("finished_at") or summary.get("date")
    active_cluster = str(context.get("topic_cluster") or plan_source.get("today_topic") or context.get("current_day") or context.get("current_stage") or summary.get("topic") or "").strip()

    should_review = bool(summary.get("should_review") or not mastery.get("reading_done") or not mastery.get("reflection_done"))
    can_advance = bool(summary.get("can_advance") and mastery.get("reading_done") and mastery.get("reflection_done"))

    learning_state.update(
        {
            "overall": summary.get("overall") or "未开始",
            "review_focus": weaknesses,
            "next_learning": next_actions if can_advance else [],
            "weaknesses": weaknesses,
            "strengths": normalize_string_list(item.get("title") for item in summary.get("solved_items") or []),
            "should_review": should_review,
            "can_advance": can_advance,
            "advancement_target": next_actions[0] if can_advance and next_actions else None,
            "next_actions": next_actions,
        }
    )

    progression.update(
        {
            "stage_status": "blocked_by_review" if should_review else ("ready_to_advance" if can_advance else "in_progress"),
            "day_status": "completed_with_gaps" if should_review else ("completed" if attempted > 0 else "planned"),
            "review_debt": weaknesses,
            "mastered_clusters": normalize_string_list(list(progression.get("mastered_clusters") or []) + list(summary.get("covered_scope") or [] if can_advance else [])),
            "active_clusters": normalize_string_list(([active_cluster] if active_cluster else []) + list(progression.get("active_clusters") or [])),
            "deferred_clusters": normalize_string_list(list(progression.get("deferred_clusters") or []) + (weaknesses if should_review else [])),
            "updated_at": summary.get("finished_at") or summary.get("date"),
        }
    )

    updated["mastery_checks"] = {
        "reading_checklist": mastery.get("recorded_reading") or [],
        "session_exercises": mastery.get("recorded_session") or [],
        "applied_project": mastery.get("recorded_project") or [],
        "reflection": mastery.get("recorded_reflection") or ([mastery.get("reflection_text")] if mastery.get("reflection_text") else []),
    }
    updated["artifacts"] = mastery.get("artifacts") or []
    updated["reflection"] = mastery.get("reflection_text") or updated.get("reflection")

    update_history.append(
        {
            "update_type": "test",
            "updated_at": summary.get("finished_at") or summary.get("date"),
            "summary": {
                "overall": summary.get("overall"),
                "covered_scope": covered_scope,
                "weaknesses": weaknesses,
                "should_review": should_review,
                "can_advance": can_advance,
                "next_actions": next_actions,
                "blocking_weaknesses": summary.get("blocking_weaknesses") or [],
                "deferred_enhancement": summary.get("deferred_enhancement") or [],
                "mastery": {
                    "reading_done": mastery.get("reading_done"),
                    "session_done": mastery.get("session_done"),
                    "project_done": mastery.get("project_done"),
                    "reflection_done": mastery.get("reflection_done"),
                },
            },
        }
    )

    session["status"] = "finished"
    session["finished_at"] = finished_at
    updated["session"] = session
    updated["learning_state"] = learning_state
    updated["progression"] = progression
    updated["update_history"] = update_history[-20:]
    return updated


def load_questions_data(session_dir: Path) -> dict[str, Any]:
    questions_path = session_dir / "questions.json"
    if not questions_path.exists():
        raise FileNotFoundError(f"未找到 questions.json: {questions_path}")
    return read_json(questions_path)


def load_questions_map(questions_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = questions_data.get("questions") or []
    return {item.get("id"): item for item in items if item.get("id")}


def summarize_test_progress(progress: dict[str, Any], questions_data: dict[str, Any]) -> dict[str, Any]:
    topic = progress.get("topic") or "未命名主题"
    session = progress.get("session") or {}
    summary = progress.get("summary") or {}
    result_summary = progress.get("result_summary") or {}
    question_progress = progress.get("questions") or {}
    questions_map = load_questions_map(questions_data)
    plan_source = questions_data.get("plan_source") or {}
    mastery = summarize_mastery(progress, questions_data)

    total = normalize_int(result_summary.get("total") if result_summary else None) or normalize_int(summary.get("total"))
    attempted = normalize_int(result_summary.get("attempted") if result_summary else None) or normalize_int(summary.get("attempted"))
    correct = normalize_int(result_summary.get("correct") if result_summary else None) or normalize_int(summary.get("correct"))

    wrong_items: list[dict[str, Any]] = []
    solved_items: list[dict[str, Any]] = []

    for qid, item in question_progress.items():
        stats = item.get("stats") or {}
        question = questions_map.get(qid) or {}
        title = question.get("title") or question.get("question") or qid
        attempts = normalize_int(stats.get("attempts"))
        if attempts <= 0:
            continue

        correct_count = normalize_int(stats.get("correct_count"))
        pass_count = normalize_int(stats.get("pass_count"))
        success_count = pass_count if question.get("category") == "code" else correct_count
        tags = question.get("tags") or []

        record = {
            "id": qid,
            "title": title,
            "attempts": attempts,
            "success_count": success_count,
            "category": question.get("category") or "unknown",
            "tags": tags,
        }
        if success_count > 0:
            solved_items.append(record)
        else:
            wrong_items.append(record)

    wrong_items.sort(key=lambda item: (-item["attempts"], item["title"]))
    solved_items.sort(key=lambda item: (-item["success_count"], -item["attempts"], item["title"]))

    weakness_titles = [item["title"] for item in wrong_items[:3]]
    weakness_tags: list[str] = []
    for item in wrong_items:
        for tag in item.get("tags") or []:
            if tag not in weakness_tags:
                weakness_tags.append(tag)
            if len(weakness_tags) >= 3:
                break
        if len(weakness_tags) >= 3:
            break

    covered_scope = []
    for key in ("covered", "weakness_focus", "review", "new_learning"):
        values = plan_source.get(key) or []
        for value in values:
            if value and value not in covered_scope:
                covered_scope.append(value)
    if not covered_scope:
        covered_scope = [f"{topic} 已学核心内容", f"{topic} 最近练习重点"]

    overall = "未开始"
    should_review = False
    can_advance = False
    if attempted > 0:
        accuracy = correct / attempted if attempted else 0
        if accuracy >= 0.85:
            overall = "测试表现较稳"
            can_advance = True
        elif accuracy >= 0.6:
            overall = "测试表现中等"
            should_review = bool(wrong_items)
            can_advance = not wrong_items
        else:
            overall = "测试结果显示需要回炉复习"
            should_review = True

    if not mastery.get("reading_done"):
        should_review = True
        can_advance = False
        overall = "测试题表现可参考，但阅读理解未稳固"
    if not mastery.get("reflection_done"):
        should_review = True
        can_advance = False
        overall = "测试完成，但复盘不足，暂不建议推进"
    if can_advance and not mastery.get("project_done"):
        overall = "测试表现较稳，但应用验证不足"

    review_decision = "建议先回退复习" if should_review else "暂不需要回退复习"
    advance_decision = "可以进入下一阶段" if can_advance else "暂不建议进入下一阶段"

    next_actions: list[str] = []
    if attempted == 0:
        next_actions = [f"先完成 {topic} 的本次测试", f"至少完成 3 道概念题和 2 道代码题后再判断阶段"]
    elif should_review:
        focus = weakness_titles[0] if weakness_titles else (weakness_tags[0] if weakness_tags else topic)
        next_actions = [f"先回退复习 {focus}", f"补做 1 组同类型题后再重新测试"]
    elif can_advance:
        next_actions = [f"进入 {topic} 的下一阶段内容", f"下一轮测试增加速度与稳定性要求"]
    else:
        next_actions = [f"补强 {topic} 当前薄弱点后再做一次测试", f"重点检查概念理解与代码稳定性"]
    if not mastery.get("project_done"):
        next_actions.append("补 1 个小项目/实作，验证知识能否迁移应用")

    return {
        "topic": topic,
        "date": progress.get("date") or "",
        "session_type": session.get("type") or "test",
        "test_mode": session.get("test_mode"),
        "status": session.get("status") or "active",
        "started_at": session.get("started_at"),
        "finished_at": session.get("finished_at"),
        "total": total,
        "attempted": attempted,
        "correct": correct,
        "overall": overall,
        "covered_scope": covered_scope[:4],
        "weaknesses": weakness_titles or weakness_tags or ["暂无明显薄弱项"],
        "should_review": should_review,
        "can_advance": can_advance,
        "review_decision": review_decision,
        "advance_decision": advance_decision,
        "next_actions": normalize_string_list(next_actions),
        "wrong_items": wrong_items,
        "solved_items": solved_items[:3],
        "mastery": mastery,
        "blocking_weaknesses": weakness_titles[:2] or weakness_tags[:2],
        "deferred_enhancement": [] if can_advance else normalize_string_list((plan_source.get("enhancement_modules") or [])[:1]),
    }


def render_log_entry(summary: dict[str, Any], session_dir: Path) -> str:
    covered_text = "；".join(summary["covered_scope"])
    weakness_text = "；".join(summary["weaknesses"])
    next_text = "；".join(summary["next_actions"])
    test_mode = summary.get("test_mode") or "general"
    mastery = summary.get("mastery") or {}
    return "\n".join(
        [
            f"### {summary['date']} / {summary['topic']} / 测试更新",
            f"- session 目录：`{session_dir}`",
            f"- 测试模式：{test_mode}",
            f"- 本次测试覆盖范围：{covered_text}",
            f"- 总题数：{summary['total']}",
            f"- 已练习题数：{summary['attempted']}",
            f"- 正确/通过题数：{summary['correct']}",
            f"- 总体表现：{summary['overall']}",
            f"- 阅读掌握清单：{'已达标' if mastery.get('reading_done') else '未达标'}",
            f"- session 练习/测试：{'已完成' if mastery.get('session_done') else '未完成'}",
            f"- 小项目/实作：{'已完成' if mastery.get('project_done') else '未完成'}",
            f"- 口头/书面复盘：{'已完成' if mastery.get('reflection_done') else '未完成'}",
            f"- 薄弱项：{weakness_text}",
            f"- 是否应回退复习：{summary['review_decision']}",
            f"- 是否可以进入下一阶段：{summary['advance_decision']}",
            f"- 后续建议：{next_text}",
        ]
    )


def upsert_section(text: str, heading: str, block: str) -> str:
    if not text.strip():
        return f"# Learn Plan\n\n## {heading}\n\n{block}\n"

    lines = text.splitlines()
    start = None
    heading_pattern = re.compile(r"^##\s+(?:\d+\.\s*)?(?P<title>.+?)\s*$")
    for idx, line in enumerate(lines):
        match = heading_pattern.match(line.strip())
        if match and match.group("title").strip() == heading:
            start = idx
            break

    if start is None:
        suffix = "" if text.endswith("\n") else "\n"
        return f"{text}{suffix}\n## {heading}\n\n{block}\n"

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break

    section_lines = lines[start:end]
    existing = "\n".join(section_lines).rstrip()
    updated = f"{existing}\n\n{block}".strip()
    new_lines = lines[:start] + updated.splitlines() + lines[end:]
    return "\n".join(new_lines).rstrip() + "\n"


def update_learn_plan(plan_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(plan_path)
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "测试记录", block)
    write_text(plan_path, updated)


def update_project_log(project_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(project_path)
    if not original and not project_path.exists():
        return
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "Learning Progress Log", block)
    write_text(project_path, updated)


def print_summary(summary: dict[str, Any], plan_path: Path, project_path: Path | None, *, stdout_json: bool) -> None:
    print(f"主题：{summary['topic']}")
    print(f"测试模式：{summary.get('test_mode') or 'general'}")
    print(f"覆盖范围：{'；'.join(summary['covered_scope'])}")
    print(f"总体表现：{summary['overall']}")
    print(f"薄弱项：{'；'.join(summary['weaknesses'])}")
    print(f"是否应回退复习：{summary['review_decision']}")
    print(f"是否进入下一阶段：{summary['advance_decision']}")
    print(f"学习计划：{plan_path}")
    if project_path is not None:
        print(f"PROJECT：{project_path}")
    if stdout_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    session_dir = Path(args.session_dir).expanduser().resolve()
    progress_path = session_dir / "progress.json"
    if not progress_path.exists():
        raise FileNotFoundError(f"未找到 progress.json: {progress_path}")

    plan_path = Path(args.plan_path).expanduser().resolve()
    project_path = Path(args.project_path).expanduser().resolve() if args.project_path else None

    progress = read_json(progress_path)
    questions_data = load_questions_data(session_dir)
    summary = summarize_test_progress(progress, questions_data)
    updated_progress = update_progress_state(progress, summary, questions_data=questions_data)
    write_json(progress_path, updated_progress)
    update_learn_plan(plan_path, summary, session_dir)
    if project_path is not None:
        update_project_log(project_path, summary, session_dir)
    print_summary(summary, plan_path, project_path, stdout_json=args.stdout_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
