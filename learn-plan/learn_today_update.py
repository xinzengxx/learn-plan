#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a learn-plan today session and update learn-plan.md")
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


def summarize_mastery(progress: dict[str, Any]) -> dict[str, Any]:
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    mastery_targets = context.get("mastery_targets") if isinstance(context.get("mastery_targets"), dict) else {}
    if not mastery_targets:
        plan_source_snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
        mastery_targets = plan_source_snapshot.get("mastery_targets") if isinstance(plan_source_snapshot.get("mastery_targets"), dict) else {}
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



def update_diagnostic_state(progress: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(progress))
    context = updated.get("context") if isinstance(updated.get("context"), dict) else {}
    user_model = context.get("user_model") if isinstance(context.get("user_model"), dict) else {}
    planning_state = context.get("planning_state") if isinstance(context.get("planning_state"), dict) else {}
    diagnostic_profile = summary.get("diagnostic_profile") or {}
    user_model["strengths"] = normalize_string_list(diagnostic_profile.get("observed_strengths"))
    user_model["weaknesses"] = normalize_string_list(diagnostic_profile.get("observed_weaknesses"))
    planning_state["diagnostic_status"] = diagnostic_profile.get("status") or "validated"
    context["user_model"] = user_model
    context["planning_state"] = planning_state
    context["diagnostic_profile"] = diagnostic_profile
    snapshot = context.get("plan_source_snapshot") if isinstance(context.get("plan_source_snapshot"), dict) else {}
    snapshot["diagnostic_profile"] = diagnostic_profile
    context["plan_source_snapshot"] = snapshot
    updated["context"] = context
    session = updated.get("session") if isinstance(updated.get("session"), dict) else {}
    session["status"] = "finished"
    session["finished_at"] = summary.get("date")
    updated["session"] = session
    updated["result_summary"] = {
        "attempted": summary.get("attempted", 0),
        "overall": summary.get("overall"),
        "recommended_entry_level": summary.get("recommended_entry_level"),
        "diagnostic_profile": diagnostic_profile,
    }
    history = updated.get("update_history") if isinstance(updated.get("update_history"), list) else []
    history.append({
        "update_type": "diagnostic",
        "updated_at": summary.get("date"),
        "summary": {
            "overall": summary.get("overall"),
            "recommended_entry_level": summary.get("recommended_entry_level"),
            "diagnostic_profile": diagnostic_profile,
        },
    })
    updated["update_history"] = history[-20:]
    return updated



def update_progress_state(progress: dict[str, Any], summary: dict[str, Any], *, session_dir: Path) -> dict[str, Any]:
    updated = json.loads(json.dumps(progress))
    context = updated.get("context") if isinstance(updated.get("context"), dict) else {}
    learning_state = updated.get("learning_state") if isinstance(updated.get("learning_state"), dict) else {}
    progression = updated.get("progression") if isinstance(updated.get("progression"), dict) else {}
    update_history = updated.get("update_history") if isinstance(updated.get("update_history"), list) else []
    session = updated.get("session") if isinstance(updated.get("session"), dict) else {}
    mastery = summary.get("mastery") or {}

    review_focus = normalize_string_list(summary.get("review_focus"))
    next_learning = normalize_string_list(summary.get("next_learning"))
    weaknesses = normalize_string_list(summary.get("high_freq_errors"))
    strengths = normalize_string_list(item.get("title") for item in summary.get("solved_items") or [])
    attempted = normalize_int(summary.get("attempted"))
    finished_at = summary.get("finished_at") or summary.get("date")
    active_cluster = str(context.get("topic_cluster") or context.get("current_day") or context.get("current_stage") or summary.get("topic") or "").strip()

    needs_more_review = bool(weaknesses or not mastery.get("reading_done") or not mastery.get("reflection_done"))
    can_advance = bool(attempted > 0 and not weaknesses and mastery.get("reading_done") and mastery.get("reflection_done"))

    learning_state.update(
        {
            "overall": summary.get("overall") or "未开始",
            "review_focus": review_focus,
            "next_learning": next_learning,
            "weaknesses": weaknesses,
            "strengths": strengths,
            "should_review": needs_more_review,
            "can_advance": can_advance,
            "advancement_target": next_learning[0] if next_learning and can_advance else None,
            "next_actions": next_learning or review_focus,
        }
    )

    progression.update(
        {
            "stage_status": "planned" if attempted <= 0 else ("blocked_by_review" if needs_more_review else "ready_to_advance"),
            "day_status": "planned" if attempted <= 0 else ("completed_with_gaps" if needs_more_review else "completed"),
            "review_debt": review_focus,
            "mastered_clusters": normalize_string_list(list(progression.get("mastered_clusters") or []) + strengths),
            "active_clusters": normalize_string_list(([active_cluster] if active_cluster else []) + list(progression.get("active_clusters") or [])),
            "deferred_clusters": normalize_string_list(list(progression.get("deferred_clusters") or []) + weaknesses),
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
            "update_type": "today",
            "updated_at": summary.get("finished_at") or summary.get("date"),
            "summary": {
                "overall": summary.get("overall"),
                "review_focus": review_focus,
                "next_learning": next_learning,
                "high_freq_errors": weaknesses,
                "mainline_progress": summary.get("mainline_progress"),
                "supporting_gap": summary.get("supporting_gap") or [],
                "defer_enhancement": summary.get("defer_enhancement") or [],
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


def load_questions_map(session_dir: Path) -> dict[str, dict[str, Any]]:
    questions_path = session_dir / "questions.json"
    if not questions_path.exists():
        raise FileNotFoundError(f"未找到 questions.json: {questions_path}")
    data = read_json(questions_path)
    items = data.get("questions") or []
    return {item.get("id"): item for item in items if item.get("id")}


def summarize_diagnostic_progress(progress: dict[str, Any], questions_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    topic = progress.get("topic") or "未命名主题"
    question_progress = progress.get("questions") or {}
    session = progress.get("session") or {}
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}

    strengths: list[str] = []
    weaknesses: list[str] = []
    evidence: list[str] = []
    attempted = 0

    for qid, item in question_progress.items():
        stats = item.get("stats") or {}
        history = item.get("history") or []
        question = questions_map.get(qid) or {}
        title = question.get("title") or question.get("question") or qid
        attempts = normalize_int(stats.get("attempts"))
        if attempts <= 0:
            continue
        attempted += 1
        if question.get("category") == "open":
            strengths.append(f"已完成简答：{title}")
            evidence.append(f"简答题《{title}》已提交文本答案")
            continue
        success_count = normalize_int(stats.get("pass_count")) if question.get("category") == "code" else normalize_int(stats.get("correct_count"))
        if success_count > 0:
            strengths.append(title)
            evidence.append(f"题目《{title}》完成良好")
        else:
            weaknesses.append(title)
            evidence.append(f"题目《{title}》暴露当前薄弱点")

    if not attempted:
        overall = "未完成诊断"
        recommended_entry_level = context.get("current_stage") or "待诊断后判断"
    elif weaknesses:
        overall = "已形成起点判断，存在需优先补齐的基础薄弱点"
        recommended_entry_level = "阶段 1"
    else:
        overall = "诊断结果显示可从当前阶段继续推进"
        recommended_entry_level = context.get("current_stage") or "当前阶段"

    return {
        "topic": topic,
        "date": progress.get("date") or "",
        "session_type": session.get("type") or "today",
        "status": session.get("status") or "active",
        "attempted": attempted,
        "overall": overall,
        "recommended_entry_level": recommended_entry_level,
        "diagnostic_profile": {
            "status": "validated" if attempted > 0 else "in-progress",
            "baseline_level": context.get("current_stage") or topic,
            "dimensions": [q.get("title") or q.get("question") or qid for qid, q in questions_map.items()],
            "observed_strengths": normalize_string_list(strengths),
            "observed_weaknesses": normalize_string_list(weaknesses),
            "evidence": normalize_string_list(evidence),
            "recommended_entry_level": recommended_entry_level,
            "confidence": 0.8 if attempted > 0 else 0.3,
        },
    }



def summarize_progress(progress: dict[str, Any], questions_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    topic = progress.get("topic") or "未命名主题"
    session = progress.get("session") or {}
    summary = progress.get("summary") or {}
    result_summary = progress.get("result_summary") or {}
    question_progress = progress.get("questions") or {}
    mastery = summarize_mastery(progress)
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    goal_focus = context.get("goal_focus") if isinstance(context.get("goal_focus"), dict) else {}
    progression = progress.get("progression") if isinstance(progress.get("progression"), dict) else {}

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
        last_status = stats.get("last_status")
        correct_count = normalize_int(stats.get("correct_count"))
        pass_count = normalize_int(stats.get("pass_count"))
        success_count = pass_count if question.get("category") == "code" else correct_count

        if attempts <= 0:
            continue
        if success_count > 0:
            solved_items.append({
                "id": qid,
                "title": title,
                "attempts": attempts,
                "success_count": success_count,
                "last_status": last_status,
            })
        else:
            wrong_items.append({
                "id": qid,
                "title": title,
                "attempts": attempts,
                "last_status": last_status,
                "category": question.get("category") or "unknown",
                "tags": question.get("tags") or [],
            })

    wrong_items.sort(key=lambda item: (-item["attempts"], item["title"]))
    solved_items.sort(key=lambda item: (-item["success_count"], -item["attempts"], item["title"]))

    high_freq_errors = [item["title"] for item in wrong_items[:3]]
    review_focus = high_freq_errors[:] or [f"复习 {topic} 的基础概念", f"回看 {topic} 的易错题型"]
    if not mastery.get("reading_done"):
        review_focus.append("补齐阅读掌握清单对应内容")
    if not mastery.get("reflection_done"):
        review_focus.append("补做书面/口头复盘，确认是否真正理解")

    next_learning: list[str] = []
    if attempted == 0:
        next_learning = [f"先完成 {topic} 的首轮练习", f"补做至少 3 道概念题和 2 道代码题"]
    elif wrong_items:
        next_learning = [f"先针对 {wrong_items[0]['title']} 做定点复习", f"在 {topic} 中加入 1 组同类新题巩固"]
    else:
        next_learning = [f"进入 {topic} 的下一批新题", f"把训练重心从基础正确率转向速度和稳定性"]
    if not mastery.get("project_done"):
        next_learning.append("补 1 个小项目/实作，验证知识能否迁移应用")

    overall = "未开始"
    if attempted > 0:
        accuracy = correct / attempted if attempted else 0
        if accuracy >= 0.85 and mastery.get("reading_done") and mastery.get("reflection_done"):
            overall = "表现较稳"
        elif accuracy >= 0.6:
            overall = "表现中等"
        else:
            overall = "基础仍需巩固"
        if accuracy >= 0.85 and not mastery.get("project_done"):
            overall = "练习表现较稳，但应用验证不足"
        if accuracy >= 0.85 and not mastery.get("reading_done"):
            overall = "练习表现尚可，但阅读理解未稳固"

    return {
        "topic": topic,
        "date": progress.get("date") or "",
        "session_type": session.get("type") or "today",
        "test_mode": session.get("test_mode"),
        "status": session.get("status") or "active",
        "started_at": session.get("started_at"),
        "finished_at": session.get("finished_at"),
        "total": total,
        "attempted": attempted,
        "correct": correct,
        "overall": overall,
        "high_freq_errors": high_freq_errors,
        "review_focus": normalize_string_list(review_focus),
        "next_learning": normalize_string_list(next_learning),
        "wrong_items": wrong_items,
        "solved_items": solved_items[:3],
        "mastery": mastery,
        "mainline_progress": goal_focus.get("mainline") or context.get("topic_cluster") or topic,
        "supporting_gap": normalize_string_list(goal_focus.get("supporting"))[:2] if high_freq_errors else [],
        "defer_enhancement": normalize_string_list(goal_focus.get("enhancement"))[:1] if (high_freq_errors or progression.get("review_debt")) else [],
    }


def render_log_entry(summary: dict[str, Any], session_dir: Path) -> str:
    weak_text = "；".join(summary["high_freq_errors"]) if summary["high_freq_errors"] else "暂无明显高频错误"
    review_text = "；".join(summary["review_focus"])
    next_text = "；".join(summary["next_learning"])
    mastery = summary.get("mastery") or {}
    return "\n".join(
        [
            f"### {summary['date']} / {summary['topic']} / 今日学习更新",
            f"- session 目录：`{session_dir}`",
            f"- 总题数：{summary['total']}",
            f"- 已练习题数：{summary['attempted']}",
            f"- 正确/通过题数：{summary['correct']}",
            f"- 总体表现：{summary['overall']}",
            f"- 高频错误点：{weak_text}",
            f"- 阅读掌握清单：{'已达标' if mastery.get('reading_done') else '未达标'}",
            f"- session 练习/测试：{'已完成' if mastery.get('session_done') else '未完成'}",
            f"- 小项目/实作：{'已完成' if mastery.get('project_done') else '未完成'}",
            f"- 口头/书面复盘：{'已完成' if mastery.get('reflection_done') else '未完成'}",
            f"- 下次复习重点：{review_text}",
            f"- 下次新学习建议：{next_text}",
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


def update_learn_plan_with_diagnostic(plan_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(plan_path)
    diagnostic = summary.get("diagnostic_profile") or {}
    block = "\n".join([
        f"### {summary['date']} / {summary['topic']} / 前置诊断更新",
        f"- session 目录：`{session_dir}`",
        f"- 总体判断：{summary.get('overall')}",
        f"- 推荐起步层级：{summary.get('recommended_entry_level')}",
        *( [f"- 已观察到的优势：{'；'.join(diagnostic.get('observed_strengths', []))}"] if diagnostic.get("observed_strengths") else [] ),
        *( [f"- 已观察到的薄弱点：{'；'.join(diagnostic.get('observed_weaknesses', []))}"] if diagnostic.get("observed_weaknesses") else [] ),
    ])
    updated = upsert_section(original, "学习记录", block)
    write_text(plan_path, updated)



def update_learn_plan(plan_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(plan_path)
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "学习记录", block)
    write_text(plan_path, updated)


def update_project_log(project_path: Path, summary: dict[str, Any], session_dir: Path) -> None:
    original = read_text_if_exists(project_path)
    if not original and not project_path.exists():
        return
    block = render_log_entry(summary, session_dir)
    updated = upsert_section(original, "Learning Progress Log", block)
    write_text(project_path, updated)


def print_diagnostic_summary(summary: dict[str, Any], plan_path: Path, *, stdout_json: bool) -> None:
    diagnostic = summary.get("diagnostic_profile") or {}
    print(f"主题：{summary['topic']}")
    print(f"诊断结论：{summary.get('overall')}")
    print(f"推荐起步层级：{summary.get('recommended_entry_level')}")
    print(f"已观察到的优势：{'；'.join(diagnostic.get('observed_strengths', [])) if diagnostic.get('observed_strengths') else '暂无'}")
    print(f"已观察到的薄弱点：{'；'.join(diagnostic.get('observed_weaknesses', [])) if diagnostic.get('observed_weaknesses') else '暂无明显薄弱点'}")
    print(f"学习计划：{plan_path}")
    if stdout_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))



def print_summary(summary: dict[str, Any], plan_path: Path, project_path: Path | None, *, stdout_json: bool) -> None:
    print(f"主题：{summary['topic']}")
    print(f"总题数：{summary['total']}")
    print(f"已练习：{summary['attempted']}")
    print(f"正确/通过：{summary['correct']}")
    print(f"高频错误点：{'；'.join(summary['high_freq_errors']) if summary['high_freq_errors'] else '暂无明显高频错误'}")
    print(f"下次复习重点：{'；'.join(summary['review_focus'])}")
    print(f"下次新学习建议：{'；'.join(summary['next_learning'])}")
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
    questions_map = load_questions_map(session_dir)
    session = progress.get("session") if isinstance(progress.get("session"), dict) else {}
    if session.get("intent") == "plan-diagnostic" or session.get("assessment_kind") == "plan-diagnostic" or session.get("plan_execution_mode") == "diagnostic":
        summary = summarize_diagnostic_progress(progress, questions_map)
        updated_progress = update_diagnostic_state(progress, summary)
        write_json(progress_path, updated_progress)
        update_learn_plan_with_diagnostic(plan_path, summary, session_dir)
        print_diagnostic_summary(summary, plan_path, stdout_json=args.stdout_json)
        return 0
    summary = summarize_progress(progress, questions_map)
    updated_progress = update_progress_state(progress, summary, session_dir=session_dir)
    write_json(progress_path, updated_progress)
    update_learn_plan(plan_path, summary, session_dir)
    if project_path is not None:
        update_project_log(project_path, summary, session_dir)
    print_summary(summary, plan_path, project_path, stdout_json=args.stdout_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
