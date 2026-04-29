from __future__ import annotations

from pathlib import Path
from typing import Any

from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_int, normalize_string_list


def build_coverage_ledger_facts(progress: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, Any]]:
    ledger: dict[str, dict[str, Any]] = {}

    def ensure(concept_id: Any) -> dict[str, Any] | None:
        cid = str(concept_id or "").strip()
        if not cid:
            return None
        if cid not in ledger:
            ledger[cid] = {
                "concept_id": cid,
                "introduced": False,
                "practiced": False,
                "tested": False,
                "mastered": False,
                "repeated_count": 0,
                "evidence": [],
            }
        return ledger[cid]

    for concept_id in normalize_string_list(summary.get("lesson_focus_points") or summary.get("covered_scope") or []):
        item = ensure(concept_id)
        if item:
            item["introduced"] = True
            item["evidence"].append("summary.covered_scope")

    solved_ids = {str(item.get("id") or item.get("question_id") or "").strip() for item in summary.get("solved_items") or [] if isinstance(item, dict)}
    wrong_ids = {str(item.get("id") or item.get("question_id") or "").strip() for item in summary.get("wrong_items") or [] if isinstance(item, dict)}
    questions = progress.get("questions") if isinstance(progress.get("questions"), dict) else {}
    for qid, question in questions.items():
        if not isinstance(question, dict):
            continue
        stats = question.get("stats") if isinstance(question.get("stats"), dict) else {}
        coverage = question.get("coverage") if isinstance(question.get("coverage"), dict) else {}
        concept_ids = normalize_string_list(
            coverage.get("concept_ids")
            or coverage.get("concept_id")
            or question.get("capability_tags")
            or question.get("tags")
            or []
        )
        for concept_id in concept_ids:
            item = ensure(concept_id)
            if not item:
                continue
            item["introduced"] = bool(item["introduced"] or coverage.get("introduced"))
            item["practiced"] = bool(item["practiced"] or coverage.get("practiced") or stats.get("attempted") or question.get("attempted"))
            item["tested"] = bool(item["tested"] or coverage.get("tested") or stats.get("attempted") or question.get("attempted"))
            passed = bool(stats.get("is_correct") or stats.get("passed") or str(qid) in solved_ids)
            failed = str(qid) in wrong_ids
            item["mastered"] = bool(item["mastered"] or (passed and not failed))
            item["repeated_count"] = max(normalize_int(item.get("repeated_count")), normalize_int(coverage.get("repeated_count")))
            item["evidence"].append(str(qid))

    existing_ledger = progress.get("coverage_ledger") if isinstance(progress.get("coverage_ledger"), list) else []
    for existing in existing_ledger:
        if not isinstance(existing, dict):
            continue
        item = ensure(existing.get("concept_id") or existing.get("capability_id"))
        if not item:
            continue
        for field in ("introduced", "practiced", "tested", "mastered"):
            item[field] = bool(item[field] or existing.get(field))
        item["repeated_count"] = max(normalize_int(item.get("repeated_count")), normalize_int(existing.get("repeated_count")))
        item["evidence"].extend(normalize_string_list(existing.get("evidence") or []))

    result = []
    for item in ledger.values():
        normalized = dict(item)
        normalized["evidence"] = normalize_string_list(normalized.get("evidence"))[:8]
        result.append(normalized)
    return result


def build_session_facts(
    progress: dict[str, Any],
    summary: dict[str, Any],
    *,
    session_dir: Path,
    update_type: str,
) -> dict[str, Any]:
    session = progress.get("session") if isinstance(progress.get("session"), dict) else {}
    mastery = summary.get("mastery") if isinstance(summary.get("mastery"), dict) else {}
    evidence = build_session_evidence(summary)
    code_failure_facts = build_code_failure_facts(progress, summary)
    submission_behavior_facts = build_submission_behavior_facts(progress)
    coverage_ledger_facts = build_coverage_ledger_facts(progress, summary)
    difficulty_performance_facts = build_difficulty_performance_facts(progress)
    evidence.extend(build_code_failure_evidence(code_failure_facts))
    evidence.extend(build_submission_behavior_evidence(submission_behavior_facts))
    evidence.extend(build_difficulty_performance_evidence(difficulty_performance_facts))
    evidence = normalize_string_list(evidence)[:20]
    facts = {
        "schema": "learn-plan.session-facts.v1",
        "update_type": update_type,
        "topic": summary.get("topic") or progress.get("topic") or "未命名主题",
        "date": summary.get("finished_at") or summary.get("date") or progress.get("date") or "",
        "session_dir": str(session_dir),
        "session": {
            "type": summary.get("session_type") or session.get("type") or update_type,
            "status": session.get("status") or summary.get("status") or "active",
            "intent": session.get("intent"),
            "assessment_kind": session.get("assessment_kind"),
            "test_mode": summary.get("test_mode") or session.get("test_mode"),
        },
        "scores": {
            "total": normalize_int(summary.get("total")),
            "attempted": normalize_int(summary.get("attempted")),
            "correct": normalize_int(summary.get("correct")),
        },
        "outcome": {
            "overall": summary.get("overall"),
            "can_advance": bool(summary.get("can_advance")),
            "should_review": bool(summary.get("should_review")),
            "recommended_entry_level": summary.get("recommended_entry_level"),
        },
        "mastery": {
            "reading_done": bool(mastery.get("reading_done")),
            "session_done": bool(mastery.get("session_done")),
            "project_done": bool(mastery.get("project_done")),
            "reflection_done": bool(mastery.get("reflection_done")),
        },
        "evidence": evidence,
    }
    if code_failure_facts:
        facts["code_failure_facts"] = code_failure_facts
    if submission_behavior_facts:
        facts["submission_behavior_facts"] = submission_behavior_facts
    if coverage_ledger_facts:
        facts["coverage_ledger_facts"] = coverage_ledger_facts
    if difficulty_performance_facts:
        facts["difficulty_performance_facts"] = difficulty_performance_facts
    if update_type == "today":
        facts["today_context"] = {
            "session_theme": summary.get("session_theme"),
            "lesson_path": summary.get("lesson_path"),
            "reviewer_verdict": summary.get("reviewer_verdict") if isinstance(summary.get("reviewer_verdict"), dict) else {},
            "review_gap": normalize_string_list(summary.get("review_gap")),
            "lesson_focus_points": normalize_string_list(summary.get("lesson_focus_points")),
            "project_tasks": normalize_string_list(summary.get("project_tasks")),
            "project_blockers": normalize_string_list(summary.get("project_blockers")),
            "review_targets": normalize_string_list(summary.get("review_targets")),
        }
    material_alignment = summary.get("material_alignment")
    if isinstance(material_alignment, dict):
        facts["material_alignment"] = {
            "status": material_alignment.get("status"),
            "selected_segments": normalize_string_list(material_alignment.get("selected_segments")),
            "covered_segments": normalize_string_list(material_alignment.get("covered_segments")),
            "missing_segments": normalize_string_list(material_alignment.get("missing_segments")),
            "evidence": normalize_string_list(material_alignment.get("evidence")),
        }
    context = progress.get("context") if isinstance(progress.get("context"), dict) else {}
    planned_content = normalize_string_list((context.get("plan_source_snapshot") or {}).get("new_learning") or context.get("new_learning"))
    actual_content = normalize_string_list(summary.get("covered_scope"))
    if planned_content or actual_content:
        facts["planned_vs_actual"] = {
            "planned": planned_content,
            "actual": actual_content,
        }

    traceability: list[dict[str, Any]] = [
        build_traceability_entry(
            kind="session",
            ref=str(session_dir),
            title=facts["topic"],
            detail=facts["session"].get("type") or update_type,
            stage="feedback",
            status=facts["session"].get("status") or "active",
        )
    ]
    for segment_id in normalize_string_list(((facts.get("material_alignment") or {}).get("selected_segments") or []))[:8]:
        traceability.append(
            build_traceability_entry(
                kind="material-segment",
                ref=segment_id,
                title=segment_id,
                detail="selected segment",
                stage="feedback",
                status=(facts.get("material_alignment") or {}).get("status") or "recorded",
            )
        )

    generation_trace = {
        "stage": "feedback",
        "generator": "progress-summary",
        "status": "summarized",
        "update_type": update_type,
    }
    confidence = 0.75 if evidence else 0.35
    if not facts["scores"]["attempted"]:
        confidence = min(confidence, 0.45)
    facts["outcome"]["confidence"] = confidence

    return apply_quality_envelope(
        facts,
        stage="feedback",
        generator="progress-summary",
        evidence=evidence,
        confidence=confidence,
        quality_review={
            "reviewer": "feedback-session-facts-gate",
            "valid": True,
            "issues": [],
            "warnings": [],
            "confidence": confidence,
            "evidence_adequacy": "sufficient" if evidence else "partial",
            "verdict": "ready",
        },
        generation_trace=generation_trace,
        traceability=traceability,
    )


def build_difficulty_performance_facts(progress: dict[str, Any]) -> list[dict[str, Any]]:
    difficulty_summary = progress.get("difficulty_summary") if isinstance(progress.get("difficulty_summary"), dict) else {}
    by_level = difficulty_summary.get("by_level") if isinstance(difficulty_summary.get("by_level"), dict) else {}
    by_category = difficulty_summary.get("by_category") if isinstance(difficulty_summary.get("by_category"), dict) else {}
    facts: list[dict[str, Any]] = []
    for level, stats in by_level.items():
        if not isinstance(stats, dict):
            continue
        total = normalize_int(stats.get("total"))
        if total <= 0:
            continue
        attempted = normalize_int(stats.get("attempted"))
        correct = normalize_int(stats.get("correct"))
        facts.append(
            {
                "scope": "level",
                "level": str(level),
                "total": total,
                "attempted": attempted,
                "correct": correct,
                "attempted_ratio": round(attempted / total, 4) if total else 0,
                "correct_ratio": round(correct / attempted, 4) if attempted else 0,
            }
        )
    for category, levels in by_category.items():
        if not isinstance(levels, dict):
            continue
        for level, stats in levels.items():
            if not isinstance(stats, dict):
                continue
            total = normalize_int(stats.get("total"))
            if total <= 0:
                continue
            attempted = normalize_int(stats.get("attempted"))
            correct = normalize_int(stats.get("correct"))
            facts.append(
                {
                    "scope": "category_level",
                    "category": str(category),
                    "level": str(level),
                    "total": total,
                    "attempted": attempted,
                    "correct": correct,
                    "attempted_ratio": round(attempted / total, 4) if total else 0,
                    "correct_ratio": round(correct / attempted, 4) if attempted else 0,
                }
            )
    return facts


def build_difficulty_performance_evidence(difficulty_performance_facts: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for fact in difficulty_performance_facts:
        if fact.get("scope") != "level":
            continue
        level = str(fact.get("level") or "unknown")
        evidence.append(
            f"难度表现：{level}，attempted={normalize_int(fact.get('attempted'))}/{normalize_int(fact.get('total'))}，correct={normalize_int(fact.get('correct'))}"
        )
    return normalize_string_list(evidence)


def _normalize_submit_record(record: Any, qid: str) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    payload = record.get("result") if isinstance(record.get("result"), dict) else record
    if not isinstance(payload, dict):
        return None
    is_submit = record.get("type") in {None, "submit"} or payload.get("question_type") == "code" or "passed_hidden_count" in payload
    if not is_submit:
        return None
    all_passed = payload.get("all_passed")
    passed = payload.get("passed")
    status = str(payload.get("status") or "").strip()
    success = bool(all_passed) or bool(passed) or status == "passed"
    failure_types = normalize_string_list(payload.get("failure_types"))
    if not failure_types and not success:
        if payload.get("error"):
            failure_types = [str(payload.get("error"))]
        elif payload.get("results"):
            for case in payload.get("results") or []:
                if isinstance(case, dict) and case.get("error"):
                    failure_types.append(str(case.get("error")))
        if not failure_types:
            failure_types = ["wrong_answer"]
    return {
        "question_id": str(payload.get("question_id") or qid),
        "submitted_at": payload.get("submitted_at") or record.get("submitted_at"),
        "passed": success,
        "failure_types": normalize_string_list(failure_types),
        "passed_public_count": normalize_int(payload.get("passed_public_count")),
        "total_public_count": normalize_int(payload.get("total_public_count")),
        "passed_hidden_count": normalize_int(payload.get("passed_hidden_count")),
        "total_hidden_count": normalize_int(payload.get("total_hidden_count")),
        "capability_tags": normalize_string_list(payload.get("capability_tags")),
    }


def _question_submit_records(qid: str, item: dict[str, Any]) -> list[dict[str, Any]]:
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    records: list[dict[str, Any]] = []
    for source in (stats.get("submit_history"), item.get("submit_history")):
        if isinstance(source, list):
            for record in source:
                normalized = _normalize_submit_record(record, qid)
                if normalized:
                    records.append(normalized)
    for history_record in item.get("history") or []:
        normalized = _normalize_submit_record(history_record, qid)
        if normalized:
            records.append(normalized)
    last_submit = stats.get("last_submit_result") if isinstance(stats.get("last_submit_result"), dict) else None
    normalized_last = _normalize_submit_record(last_submit, qid) if last_submit else None
    if normalized_last:
        records.append(normalized_last)
    deduped: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        key = str(record.get("submitted_at") or f"index-{index}")
        deduped[key] = record
    return sorted(deduped.values(), key=lambda record: str(record.get("submitted_at") or ""))


def build_submission_behavior_facts(progress: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    questions = progress.get("questions") if isinstance(progress.get("questions"), dict) else {}
    for qid, item in questions.items():
        if not isinstance(item, dict):
            continue
        records = _question_submit_records(str(qid), item)
        if not records:
            continue
        attempts = len(records)
        passed_indices = [index for index, record in enumerate(records) if record.get("passed")]
        ever_passed = bool(passed_indices)
        first_pass = ever_passed and passed_indices[0] == 0 and attempts == 1
        retry_success = ever_passed and passed_indices[0] > 0
        persistent_failure = not ever_passed
        failure_sequence: list[str] = []
        failure_types: list[str] = []
        for record in records[: passed_indices[0] if ever_passed else len(records)]:
            for failure_type in normalize_string_list(record.get("failure_types")):
                failure_sequence.append(failure_type)
        for record in records:
            for failure_type in normalize_string_list(record.get("failure_types")):
                if failure_type not in failure_types:
                    failure_types.append(failure_type)
        last_failure_types: list[str] = []
        for record in reversed(records):
            if not record.get("passed"):
                last_failure_types = normalize_string_list(record.get("failure_types"))
                break
        facts.append(
            {
                "question_id": str(qid),
                "question_type": "code",
                "attempts": attempts,
                "ever_passed": ever_passed,
                "first_pass": first_pass,
                "retry_success": retry_success,
                "persistent_failure": persistent_failure,
                "failure_sequence": failure_sequence,
                "failure_types": failure_types,
                "last_failure_types": last_failure_types,
                "first_submitted_at": records[0].get("submitted_at"),
                "last_submitted_at": records[-1].get("submitted_at"),
                "capability_tags": normalize_string_list(records[-1].get("capability_tags")),
            }
        )
    return facts


def build_submission_behavior_evidence(submission_behavior_facts: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for fact in submission_behavior_facts:
        qid = str(fact.get("question_id") or "代码题")
        attempts = normalize_int(fact.get("attempts"))
        if fact.get("first_pass"):
            evidence.append(f"首次提交通过：{qid}，attempts={attempts}")
        elif fact.get("retry_success"):
            failures = ",".join(normalize_string_list(fact.get("failure_sequence"))) or "failed"
            evidence.append(f"多次失败后通过：{qid}，attempts={attempts}，failure_sequence={failures}")
        elif fact.get("persistent_failure"):
            failures = ",".join(normalize_string_list(fact.get("last_failure_types"))) or "failed"
            evidence.append(f"持续失败：{qid}，attempts={attempts}，last_failure={failures}")
    return normalize_string_list(evidence)


def build_code_failure_facts(progress: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    progress_questions = progress.get("questions") if isinstance(progress.get("questions"), dict) else {}

    for item in summary.get("wrong_items") or []:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id") or item.get("question_id") or "").strip()
        submit_result = item.get("submit_result") if isinstance(item.get("submit_result"), dict) else None
        if submit_result is None and qid:
            progress_item = progress_questions.get(qid) if isinstance(progress_questions.get(qid), dict) else {}
            stats = progress_item.get("stats") if isinstance(progress_item.get("stats"), dict) else {}
            submit_result = stats.get("last_submit_result") if isinstance(stats.get("last_submit_result"), dict) else None
        if not submit_result:
            continue
        question_type = str(submit_result.get("question_type") or item.get("category") or "").strip()
        if question_type != "code" and item.get("category") != "code":
            continue
        question_id = str(submit_result.get("question_id") or qid).strip()
        if not question_id or question_id in seen:
            continue
        seen.add(question_id)
        capability_tags = normalize_string_list(submit_result.get("capability_tags") or item.get("capability_tags") or item.get("tags"))
        failed_cases = []
        for case in submit_result.get("failed_case_summaries") or []:
            if not isinstance(case, dict):
                continue
            failed_cases.append(
                {
                    "category": case.get("category"),
                    "input": case.get("input"),
                    "expected": case.get("expected"),
                    "actual_repr": case.get("actual_repr") if "actual_repr" in case else repr(case.get("actual")),
                    "error": case.get("error"),
                    "capability_tags": normalize_string_list(case.get("capability_tags") or capability_tags),
                }
            )
        facts.append(
            {
                "question_id": question_id,
                "title": item.get("title") or question_id,
                "question_type": "code",
                "category": item.get("category") or "code",
                "passed_public_count": normalize_int(submit_result.get("passed_public_count")),
                "total_public_count": normalize_int(submit_result.get("total_public_count")),
                "passed_hidden_count": normalize_int(submit_result.get("passed_hidden_count")),
                "total_hidden_count": normalize_int(submit_result.get("total_hidden_count")),
                "failure_types": normalize_string_list(submit_result.get("failure_types")),
                "capability_tags": capability_tags,
                "failed_case_summaries": failed_cases,
                "submitted_at": submit_result.get("submitted_at"),
            }
        )
    return facts


def build_code_failure_evidence(code_failure_facts: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for fact in code_failure_facts:
        title = str(fact.get("title") or fact.get("question_id") or "代码题").strip()
        failure_types = normalize_string_list(fact.get("failure_types"))
        public = f"public {normalize_int(fact.get('passed_public_count'))}/{normalize_int(fact.get('total_public_count'))}"
        hidden = f"hidden {normalize_int(fact.get('passed_hidden_count'))}/{normalize_int(fact.get('total_hidden_count'))}"
        failure_label = ", ".join(failure_types) if failure_types else "failed"
        evidence.append(f"代码题失败：{title}，{public}，{hidden}，failure={failure_label}")
        for case in fact.get("failed_case_summaries") or []:
            if not isinstance(case, dict):
                continue
            category = str(case.get("category") or "unknown").strip()
            error = str(case.get("error") or failure_label).strip()
            evidence.append(f"代码失败用例：{title}，category={category}，error={error}")
    return normalize_string_list(evidence)


def build_session_evidence(summary: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    attempted = normalize_int(summary.get("attempted"))
    correct = normalize_int(summary.get("correct"))
    if attempted:
        evidence.append(f"已尝试 {attempted} 题，正确/通过 {correct} 题")
    session_theme = str(summary.get("session_theme") or "").strip()
    if session_theme:
        evidence.append(f"今日主题：{session_theme}")
    reviewer_verdict = summary.get("reviewer_verdict") if isinstance(summary.get("reviewer_verdict"), dict) else {}
    if reviewer_verdict.get("lesson") or reviewer_verdict.get("question"):
        parts = []
        if reviewer_verdict.get("lesson"):
            parts.append(f"lesson={reviewer_verdict.get('lesson')}")
        if reviewer_verdict.get("question"):
            parts.append(f"question={reviewer_verdict.get('question')}")
        evidence.append(f"reviewer 结论：{' / '.join(parts)}")
    for value in normalize_string_list(summary.get("project_tasks"))[:3]:
        evidence.append(f"今日任务：{value}")
    for value in normalize_string_list(summary.get("review_gap"))[:3]:
        evidence.append(f"coverage 缺口：{value}")
    for item in summary.get("solved_items") or []:
        if isinstance(item, dict) and item.get("title"):
            evidence.append(f"已解决：{item['title']}")
    for item in summary.get("wrong_items") or []:
        if isinstance(item, dict) and item.get("title"):
            evidence.append(f"暴露薄弱点：{item['title']}")
    for value in normalize_string_list(summary.get("high_freq_errors") or summary.get("weaknesses")):
        evidence.append(f"需复习：{value}")
    mastery = summary.get("mastery") if isinstance(summary.get("mastery"), dict) else {}
    if mastery.get("reflection_text"):
        evidence.append("已有复盘文本")
    return normalize_string_list(evidence)[:20]


__all__ = [
    "build_session_evidence",
    "build_session_facts",
    "build_submission_behavior_facts",
    "build_coverage_ledger_facts",
    "build_difficulty_performance_facts",
]
