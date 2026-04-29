from __future__ import annotations

from typing import Any

from learn_core.quality_review import collect_quality_issues, normalize_confidence
from learn_core.text_utils import normalize_string_list

from .contracts import (
    CONTRACT_VERSION,
    DEFAULT_CONSULTATION_TOPICS,
    DEFAULT_LANGUAGE_POLICY,
    NEXT_ACTION_ENTER_TODAY,
    STAGE_EXIT_CONTRACTS,
    WORKFLOW_STATE_QUALITY_PREFIXES,
    next_action_for_mode,
)


RESEARCH_KEYWORDS = (
    "工作",
    "就业",
    "转岗",
    "面试",
    "岗位",
    "求职",
    "职业",
    "大模型",
    "llm",
    "agent",
    "rag",
    "langchain",
    "langgraph",
    "模型应用",
    "应用开发",
)
LEVEL_UNCERTAIN_KEYWORDS = (
    "不确定",
    "说不清",
    "不清楚",
    "不会判断",
    "不知道自己什么水平",
)
QUALITY_CONFIDENCE_THRESHOLD = {
    "clarification": 0.35,
    "research": 0.45,
    "diagnostic": 0.5,
    "approval": 0.4,
    "planning": 0.45,
}
LEGACY_SEMANTIC_REVIEWER = "legacy-semantic-gate"
LEGACY_DIAGNOSTIC_ASSESSMENT_KIND = "plan-diagnostic"
INITIAL_TEST_ASSESSMENT_KIND = "initial-test"
LEGACY_DIAGNOSTIC_SESSION_INTENT = "plan-diagnostic"
INITIAL_TEST_SESSION_INTENT = "assessment"


def _normalize_positive_int(value: Any) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 1 else None


def _extract_question_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("question", "prompt", "text", "title", "detail", "label", "raw", "id", "key"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return str(value or "").strip()


def _question_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    text = _extract_question_text(value).lower()
    if text:
        keys.add(text)
    if isinstance(value, dict):
        for field in ("id", "key", "slug", "question_id"):
            field_value = str(value.get(field) or "").strip().lower()
            if field_value:
                keys.add(field_value)
    return keys


def _matches_known_item(value: Any, known_items: set[str]) -> bool:
    if not known_items:
        return False
    for key in _question_keys(value):
        if key in known_items:
            return True
        if len(key) >= 6 and any(key in item or item in key for item in known_items):
            return True
    return False


def _question_mentions_budget(value: Any) -> bool:
    text = _extract_question_text(value).lower()
    if not text:
        return False
    return any(
        token in text
        for token in (
            "测评预算",
            "assessment budget",
            "最多几轮",
            "几轮测试",
            "每轮几题",
            "多少题",
            "题数",
            "max rounds",
            "questions per round",
            "max_assessment_rounds_preference",
            "questions_per_round_preference",
        )
    )


def _question_deferred_to_diagnostic(value: Any) -> bool:
    if isinstance(value, dict):
        if bool(value.get("deferred_to_diagnostic")):
            return True
        deferred_to = str(value.get("deferred_to") or value.get("stage") or value.get("owner_stage") or "").strip().lower()
        if deferred_to in {"diagnostic", "assessment", "initial-test", "test"}:
            return True
        status = str(value.get("status") or "").strip().lower()
        if status in {"deferred", "deferred_to_diagnostic", "diagnostic"}:
            return True
    text = _extract_question_text(value).lower()
    return any(
        token in text
        for token in (
            "通过 diagnostic",
            "通过测评",
            "起始测评",
            "诊断阶段",
            "测评校准",
            "能力边界",
            "校准",
        )
    )


def _question_is_blocking(value: Any, resolved_items: set[str], budget_confirmed: bool) -> bool:
    if _matches_known_item(value, resolved_items):
        return False
    if budget_confirmed and _question_mentions_budget(value):
        return False
    if _question_deferred_to_diagnostic(value):
        return False
    tags = _question_semantic_tags(value)
    if tags & {"current_level_boundary", "role_priority", "weekly_capacity", "success_criteria"}:
        return False
    if isinstance(value, dict):
        blocking = _parse_optional_bool(value.get("blocking"))
        if blocking is not None:
            return blocking
        status = str(value.get("status") or "").strip().lower()
        if status in {"resolved", "answered", "confirmed", "done"}:
            return False
    return False


def _question_semantic_tags(value: Any) -> set[str]:
    text = _extract_question_text(value).lower()
    tags: set[str] = set()
    if any(token in text for token in ("最多几轮", "几轮测试", "max_assessment_rounds", "max rounds", "rounds_preference", "max_assessment_rounds_preference")):
        tags.add("assessment_rounds")
    if any(token in text for token in ("每轮最多接受多少题", "每轮几题", "questions_per_round", "questions per round", "题数", "questions_per_round_preference")):
        tags.add("assessment_questions")
    if any(token in text for token in ("岗位", "role_priority", "primary_role", "优先岗位线", "主攻哪个方向", "更优先哪一侧", "均衡推进")):
        tags.add("role_priority")
    if any(token in text for token in ("每周", "weekly_capacity", "时间窗口", "投入多少", "deadline", "投递", "面试时间点")):
        tags.add("weekly_capacity")
    if any(token in text for token in ("能力边界", "真实熟练度", "函数封装", "异常处理", "pandas", "numpy", "算法题", "ai 应用脚本", "llm 应用脚本")):
        tags.add("current_level_boundary")
    if any(token in text for token in ("成功标准", "较从容面试", "筛选题", "项目讲解", "抗追问", "success_criteria")):
        tags.add("success_criteria")
    if any(token in text for token in ("题驱动", "项目驱动", "数据任务驱动", "知识点驱动", "learning_organizer", "先测后讲", "先讲后练", "刷题反馈", "实战小任务", "结构化知识梳理", "结构化梳理")):
        tags.add("learning_organizer")
    if any(token in text for token in ("手写速度", "数据处理熟练度", "算法题感", "ai 应用脚本能力", "面试表达", "learning_focus", "focus_preference")):
        tags.add("focus_preference")
    return tags


def _pending_item_is_blocking(
    value: Any,
    *,
    resolved_items: set[str],
    budget_confirmed: bool,
    blocking_question_tags: set[str],
    confirmed_preferences: list[str],
) -> bool:
    if isinstance(value, dict) and value.get("required") is False:
        return False
    if _matches_known_item(value, resolved_items):
        return False
    if budget_confirmed and _question_mentions_budget(value):
        return False
    tags = _question_semantic_tags(value)
    if tags & blocking_question_tags:
        return False
    if tags & {"current_level_boundary", "role_priority", "weekly_capacity", "success_criteria"}:
        return False
    if confirmed_preferences and tags & {"learning_organizer", "focus_preference"}:
        return False
    return bool(_extract_question_text(value))


def _normalized_question_list(values: Any) -> list[Any]:
    items = values if isinstance(values, list) else []
    normalized: list[Any] = []
    seen: set[str] = set()
    for item in items:
        text = _extract_question_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item if isinstance(item, dict) else text)
    return normalized


def _collect_success_criteria(questionnaire: dict[str, Any], clarification_state: dict[str, Any], goal_model: dict[str, Any]) -> list[str]:
    success_criteria_state = clarification_state.get("success_criteria")
    state_confirmed = []
    if isinstance(success_criteria_state, dict):
        state_confirmed = normalize_string_list(success_criteria_state.get("confirmed") or success_criteria_state.get("items") or [])
    elif isinstance(success_criteria_state, list):
        state_confirmed = normalize_string_list(success_criteria_state)
    return normalize_string_list(
        questionnaire.get("success_criteria")
        or state_confirmed
        or goal_model.get("supporting_capabilities")
        or ([goal_model.get("mainline_goal")] if goal_model.get("mainline_goal") else [])
    )


def _collect_time_constraint_signals(
    questionnaire: dict[str, Any],
    clarification_state: dict[str, Any],
    user_model: dict[str, Any],
    schedule: dict[str, Any],
) -> list[str]:
    time_constraints = questionnaire.get("time_constraints") if isinstance(questionnaire.get("time_constraints"), dict) else {}
    return normalize_string_list(
        list(time_constraints.get("routine_constraints") or [])
        or questionnaire.get("constraints")
        or schedule.get("time_constraints_confirmed")
        or user_model.get("constraints")
        or clarification_state.get("constraints_confirmed")
    )


def _topic_by_id(topics: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in topics if isinstance(topics, list) else []:
        if not isinstance(item, dict):
            continue
        topic_id = str(item.get("id") or "").strip()
        if topic_id:
            result[topic_id] = dict(item)
    return result


def _normalize_consultation_state(value: Any) -> dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, dict) else {}
    default_topics = [dict(item) for item in DEFAULT_CONSULTATION_TOPICS]
    incoming_topics = _topic_by_id(raw.get("topics"))
    topics: list[dict[str, Any]] = []
    for default in default_topics:
        topic_id = str(default.get("id") or "").strip()
        merged = {**default, **incoming_topics.get(topic_id, {})}
        merged["id"] = topic_id
        merged["label"] = str(merged.get("label") or default.get("label") or topic_id)
        merged["required"] = bool(merged.get("required"))
        merged["status"] = str(merged.get("status") or "not-started").strip() or "not-started"
        merged["exit_criteria"] = normalize_string_list(merged.get("exit_criteria") or default.get("exit_criteria") or [])
        merged["confirmed_values"] = dict(merged.get("confirmed_values") or {}) if isinstance(merged.get("confirmed_values"), dict) else {}
        merged["open_questions"] = _normalized_question_list(merged.get("open_questions") or [])
        merged["assumptions"] = _normalized_question_list(merged.get("assumptions") or [])
        merged["ambiguities"] = _normalized_question_list(merged.get("ambiguities") or [])
        merged["evidence"] = normalize_string_list(merged.get("evidence") or [])
        topics.append(merged)
    known_ids = {str(item.get("id") or "") for item in topics}
    for topic_id, item in incoming_topics.items():
        if topic_id not in known_ids:
            item["open_questions"] = _normalized_question_list(item.get("open_questions") or [])
            item["assumptions"] = _normalized_question_list(item.get("assumptions") or [])
            item["ambiguities"] = _normalized_question_list(item.get("ambiguities") or [])
            item["evidence"] = normalize_string_list(item.get("evidence") or [])
            topics.append(item)
    topic_order = normalize_string_list(raw.get("topic_order") or [item.get("id") for item in default_topics])
    if not topic_order:
        topic_order = [str(item.get("id") or "") for item in topics if str(item.get("id") or "").strip()]
    current_topic_id = str(raw.get("current_topic_id") or "").strip()
    if not current_topic_id:
        for item in topics:
            if str(item.get("status") or "").strip().lower() not in {"resolved", "deferred"}:
                current_topic_id = str(item.get("id") or "").strip()
                break
    thread = [dict(item) for item in raw.get("thread") if isinstance(item, dict)] if isinstance(raw.get("thread"), list) else []
    all_open_questions: list[Any] = []
    all_assumptions: list[Any] = []
    for item in topics:
        all_open_questions.extend(item.get("open_questions") or [])
        all_assumptions.extend(item.get("assumptions") or [])
    if isinstance(raw.get("open_questions"), list):
        all_open_questions.extend(raw.get("open_questions") or [])
    if isinstance(raw.get("assumptions"), list):
        all_assumptions.extend(raw.get("assumptions") or [])
    return {
        "status": str(raw.get("status") or "needs-more").strip() or "needs-more",
        "current_topic_id": current_topic_id,
        "topic_order": topic_order,
        "topics": topics,
        "thread": thread,
        "open_questions": _normalized_question_list(all_open_questions),
        "assumptions": _normalized_question_list(all_assumptions),
    }


def _consultation_topic_status(consultation_state: dict[str, Any], topic_id: str) -> str:
    for item in consultation_state.get("topics") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == topic_id:
            return str(item.get("status") or "").strip().lower()
    return ""


def normalize_language_policy(value: Any = None) -> dict[str, Any]:
    policy = dict(DEFAULT_LANGUAGE_POLICY)
    if isinstance(value, dict):
        for key in policy:
            if value.get(key) not in (None, ""):
                policy[key] = value.get(key)
    return policy


def normalize_clarification_artifact(
    clarification: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clarification = clarification if isinstance(clarification, dict) else {}
    normalized = dict(clarification)
    questionnaire = dict(clarification.get("questionnaire") or {}) if isinstance(clarification.get("questionnaire"), dict) else {}
    clarification_state = dict(clarification.get("clarification_state") or {}) if isinstance(clarification.get("clarification_state"), dict) else {}
    preference_state = dict(clarification.get("preference_state") or {}) if isinstance(clarification.get("preference_state"), dict) else {}
    user_model = dict(clarification.get("user_model") or {}) if isinstance(clarification.get("user_model"), dict) else {}
    goal_model = dict(clarification.get("goal_model") or {}) if isinstance(clarification.get("goal_model"), dict) else {}
    schedule = dict(clarification.get("schedule") or {}) if isinstance(clarification.get("schedule"), dict) else {}
    questionnaire_schedule = dict(questionnaire.get("schedule") or {}) if isinstance(questionnaire.get("schedule"), dict) else {}
    if not schedule and questionnaire_schedule:
        schedule = questionnaire_schedule
    consultation_model_enabled = bool(clarification.get("consultation_model_enabled")) or isinstance(clarification.get("consultation_state"), dict)
    consultation_state = _normalize_consultation_state(clarification.get("consultation_state"))
    topic_map = _topic_by_id(consultation_state.get("topics"))
    language_policy = normalize_language_policy(clarification.get("language_policy"))

    learning_purpose = topic_map.get("learning_purpose", {}).get("confirmed_values") or {}
    exam_or_job_target = topic_map.get("exam_or_job_target", {}).get("confirmed_values") or {}
    success_topic = topic_map.get("success_criteria", {}).get("confirmed_values") or {}
    current_level_topic = topic_map.get("current_level", {}).get("confirmed_values") or {}
    constraints_topic = topic_map.get("constraints", {}).get("confirmed_values") or {}
    teaching_topic = topic_map.get("teaching_preference", {}).get("confirmed_values") or {}
    practice_topic = topic_map.get("practice_preference", {}).get("confirmed_values") or {}
    materials_topic = topic_map.get("materials", {}).get("confirmed_values") or {}
    assessment_topic = topic_map.get("assessment_scope", {}).get("confirmed_values") or {}
    non_goals_topic = topic_map.get("non_goals", {}).get("confirmed_values") or {}

    if not str(questionnaire.get("goal") or "").strip():
        questionnaire["goal"] = learning_purpose.get("goal") or learning_purpose.get("purpose") or exam_or_job_target.get("target") or ""
    if not questionnaire.get("success_criteria"):
        questionnaire["success_criteria"] = normalize_string_list(success_topic.get("success_criteria") or success_topic.get("criteria") or [])
    if not str(questionnaire.get("current_level_self_report") or "").strip():
        questionnaire["current_level_self_report"] = str(current_level_topic.get("current_level_self_report") or current_level_topic.get("current_level") or current_level_topic.get("self_report") or "").strip()
    if not questionnaire.get("existing_materials"):
        questionnaire["existing_materials"] = normalize_string_list(materials_topic.get("existing_materials") or materials_topic.get("materials") or [])
    if not questionnaire.get("non_goals"):
        questionnaire["non_goals"] = normalize_string_list(non_goals_topic.get("non_goals") or non_goals_topic.get("items") or [])

    success_criteria = _collect_success_criteria(questionnaire, clarification_state, goal_model)
    if success_criteria:
        questionnaire["success_criteria"] = success_criteria

    time_constraints = dict(questionnaire.get("time_constraints") or {}) if isinstance(questionnaire.get("time_constraints"), dict) else {}
    if not time_constraints and constraints_topic:
        time_constraints = {
            "frequency": constraints_topic.get("frequency") or "",
            "session_length": constraints_topic.get("session_length") or "",
            "deadline": constraints_topic.get("deadline") or "",
            "routine_constraints": normalize_string_list(constraints_topic.get("routine_constraints") or constraints_topic.get("constraints") or []),
        }
    learning_preferences = dict(questionnaire.get("learning_preferences") or {}) if isinstance(questionnaire.get("learning_preferences"), dict) else {}
    if teaching_topic or practice_topic:
        learning_preferences.setdefault("style", normalize_string_list(teaching_topic.get("style") or teaching_topic.get("preferences") or []))
        learning_preferences.setdefault("exercise_types", normalize_string_list(practice_topic.get("exercise_types") or practice_topic.get("practice_types") or []))
        if practice_topic.get("feedback_style") and not learning_preferences.get("feedback_style"):
            learning_preferences["feedback_style"] = practice_topic.get("feedback_style")
    if learning_preferences:
        questionnaire["learning_preferences"] = learning_preferences
    constraint_signals = _collect_time_constraint_signals(questionnaire, clarification_state, user_model, schedule)
    if constraint_signals:
        questionnaire["constraints"] = normalize_string_list(list(questionnaire.get("constraints") or []) or constraint_signals)
        if not time_constraints:
            time_constraints = {"routine_constraints": constraint_signals}
        elif not normalize_string_list(time_constraints.get("routine_constraints") or []):
            time_constraints["routine_constraints"] = constraint_signals
    if time_constraints:
        questionnaire["time_constraints"] = time_constraints

    assessment_budget = resolve_assessment_budget_preference(clarification, diagnostic)
    mastery_preferences = dict(questionnaire.get("mastery_preferences") or {}) if isinstance(questionnaire.get("mastery_preferences"), dict) else {}
    if assessment_topic:
        max_round_aliases = (
            "max_assessment_rounds_preference",
            "max_rounds",
            "diagnostic_max_rounds",
            "assessment_max_rounds",
            "max_assessment_rounds",
        )
        questions_per_round_aliases = (
            "questions_per_round_preference",
            "questions_per_round",
            "diagnostic_questions_per_round",
            "assessment_questions_per_round",
            "per_round_questions",
        )
        for source_key in max_round_aliases:
            if mastery_preferences.get("max_assessment_rounds_preference") in (None, "") and assessment_topic.get(source_key) not in (None, ""):
                mastery_preferences["max_assessment_rounds_preference"] = assessment_topic.get(source_key)
                break
        for source_key in questions_per_round_aliases:
            if mastery_preferences.get("questions_per_round_preference") in (None, "") and assessment_topic.get(source_key) not in (None, ""):
                mastery_preferences["questions_per_round_preference"] = assessment_topic.get(source_key)
                break
        if not mastery_preferences.get("question_mix_preference"):
            mastery_preferences["question_mix_preference"] = normalize_string_list(assessment_topic.get("question_mix_preference") or [])
    if assessment_budget.get("max_assessment_rounds_preference") is not None:
        mastery_preferences["max_assessment_rounds_preference"] = assessment_budget.get("max_assessment_rounds_preference")
    if assessment_budget.get("questions_per_round_preference") is not None:
        mastery_preferences["questions_per_round_preference"] = assessment_budget.get("questions_per_round_preference")
    if mastery_preferences:
        questionnaire["mastery_preferences"] = mastery_preferences
    budget_confirmed = (
        assessment_budget.get("max_assessment_rounds_preference") is not None
        and assessment_budget.get("questions_per_round_preference") is not None
    )
    resolved_items = {
        key
        for item in _normalized_question_list(clarification_state.get("resolved_items") or [])
        for key in _question_keys(item)
    }
    clarification_state["resolved_items"] = _normalized_question_list(clarification_state.get("resolved_items") or [])
    raw_open_questions = _normalized_question_list(clarification_state.get("open_questions") or [])
    raw_open_questions.extend(consultation_state.get("open_questions") or [])
    clarification_state["open_questions"] = [
        item
        for item in _normalized_question_list(raw_open_questions)
        if _question_is_blocking(item, resolved_items, budget_confirmed)
    ]
    raw_assumptions = _normalized_question_list(clarification_state.get("assumptions") or [])
    raw_assumptions.extend(consultation_state.get("assumptions") or [])
    clarification_state["assumptions"] = _normalized_question_list(raw_assumptions)
    blocking_question_keys = {
        key
        for item in clarification_state["open_questions"]
        for key in _question_keys(item)
    }
    blocking_question_tags = {
        tag
        for item in clarification_state["open_questions"]
        for tag in _question_semantic_tags(item)
    }
    confirmed_preferences = normalize_string_list(
        preference_state.get("confirmed_preferences") or preference_state.get("confirmed") or []
    )

    pending_items = _normalized_question_list(preference_state.get("pending_items") or [])
    if str(preference_state.get("status") or "").strip().lower() in {"confirmed", "partial", "partially_confirmed", "pending", "pending-confirmation", "needs-confirmation", "needs_user_input"}:
        pending_items = [
            item
            for item in pending_items
            if not _matches_known_item(item, blocking_question_keys)
            and _pending_item_is_blocking(
                item,
                resolved_items=resolved_items,
                budget_confirmed=budget_confirmed,
                blocking_question_tags=blocking_question_tags,
                confirmed_preferences=confirmed_preferences,
            )
        ]
    else:
        pending_items = [
            item
            for item in pending_items
            if not _matches_known_item(item, resolved_items)
            and not (budget_confirmed and _question_mentions_budget(item))
            and not _matches_known_item(item, blocking_question_keys)
        ]
    preference_state["pending_items"] = pending_items

    normalized["questionnaire"] = questionnaire
    normalized["clarification_state"] = clarification_state
    normalized["preference_state"] = preference_state
    normalized["consultation_state"] = consultation_state
    normalized["consultation_model_enabled"] = consultation_model_enabled
    normalized["language_policy"] = language_policy
    return normalized


def resolve_assessment_budget_preference(
    clarification: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, int | None]:
    clarification = clarification if isinstance(clarification, dict) else {}
    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    mastery_preferences = questionnaire.get("mastery_preferences") if isinstance(questionnaire.get("mastery_preferences"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    user_model = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    max_rounds = None
    questions_per_round = None
    for value in (
        mastery_preferences.get("max_assessment_rounds_preference"),
        questionnaire.get("max_assessment_rounds_preference"),
        preference_state.get("max_assessment_rounds_preference"),
        user_model.get("max_assessment_rounds_preference"),
        diagnostic_plan.get("max_rounds"),
        diagnostic_profile.get("max_rounds"),
    ):
        max_rounds = _normalize_positive_int(value)
        if max_rounds is not None:
            break
    for value in (
        mastery_preferences.get("questions_per_round_preference"),
        questionnaire.get("questions_per_round_preference"),
        preference_state.get("questions_per_round_preference"),
        user_model.get("questions_per_round_preference"),
        diagnostic_plan.get("questions_per_round"),
        diagnostic_profile.get("questions_per_round"),
    ):
        questions_per_round = _normalize_positive_int(value)
        if questions_per_round is not None:
            break
    return {
        "max_assessment_rounds_preference": max_rounds,
        "questions_per_round_preference": questions_per_round,
    }


def diagnostic_metadata_is_valid(assessment_kind: Any, session_intent: Any, plan_execution_mode: Any | None = None) -> bool:
    normalized_kind = str(assessment_kind or "").strip()
    normalized_intent = str(session_intent or "").strip()
    if normalized_kind == LEGACY_DIAGNOSTIC_ASSESSMENT_KIND and normalized_intent == LEGACY_DIAGNOSTIC_SESSION_INTENT:
        return True
    return normalized_kind == INITIAL_TEST_ASSESSMENT_KIND and normalized_intent == INITIAL_TEST_SESSION_INTENT


def diagnostic_blueprint_missing_fields(
    target_capability_ids: Any,
    scoring_rubric: Any,
    diagnostic_items: Any,
) -> list[str]:
    normalized_targets = normalize_string_list(target_capability_ids or [])
    normalized_rubric = scoring_rubric if isinstance(scoring_rubric, list) else []
    normalized_items = diagnostic_items if isinstance(diagnostic_items, list) else []
    missing_fields: list[str] = []
    if not normalized_targets:
        missing_fields.append("target_capability_ids")
    if not normalized_rubric:
        missing_fields.append("scoring_rubric")
    if not normalized_items:
        missing_fields.append("diagnostic_items")
    elif not any(
        isinstance(item, dict)
        and str(item.get("capability_id") or item.get("capability") or item.get("id") or "").strip()
        and normalize_string_list(item.get("expected_signals") or [])
        for item in normalized_items
    ):
        missing_fields.append("diagnostic_items_blueprint")
    return missing_fields


def diagnostic_blueprint_is_valid(
    target_capability_ids: Any,
    scoring_rubric: Any,
    diagnostic_items: Any,
) -> bool:
    return not diagnostic_blueprint_missing_fields(target_capability_ids, scoring_rubric, diagnostic_items)


def _normalized_goal_text(topic: str, goal: str) -> str:
    return f"{topic} {goal}".lower()


def needs_research(topic: str, goal: str) -> bool:
    normalized_goal = _normalized_goal_text(topic, goal)
    return any(keyword in normalized_goal for keyword in RESEARCH_KEYWORDS)


def _has_uncertainty_signal(*values: Any) -> bool:
    normalized = " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())
    return any(keyword in normalized for keyword in LEVEL_UNCERTAIN_KEYWORDS)


def _parse_optional_bool(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y", "是", "需要"}:
        return True
    if text in {"false", "0", "no", "n", "否", "不需要"}:
        return False
    return None


def _diagnostic_follow_up_needed(diagnostic: dict[str, Any] | None = None) -> bool:
    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
    diagnostic_result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
    for value in (
        diagnostic_result.get("follow_up_needed"),
        diagnostic_profile.get("follow_up_needed"),
        diagnostic_plan.get("follow_up_needed"),
    ):
        normalized = _parse_optional_bool(value)
        if normalized is not None:
            return normalized
    return False


def _diagnostic_has_reliable_level_signal(diagnostic: dict[str, Any] | None = None) -> bool:
    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
    diagnostic_result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    result_status = str(diagnostic_result.get("status") or "").strip().lower()
    profile_status = str(diagnostic_profile.get("status") or "").strip().lower()
    if _diagnostic_follow_up_needed(diagnostic):
        return False
    if result_status != "evaluated" and profile_status != "validated":
        return False
    return bool(
        str(diagnostic_result.get("recommended_entry_level") or diagnostic_profile.get("recommended_entry_level") or "").strip()
        or list(diagnostic_result.get("capability_assessment") or [])
    )


def level_uncertain(
    topic: str,
    goal: str,
    diagnostic: dict[str, Any] | None = None,
    clarification: dict[str, Any] | None = None,
) -> bool:
    normalized_goal = _normalized_goal_text(topic, goal)
    if _has_uncertainty_signal(normalized_goal):
        return True
    clarification = clarification if isinstance(clarification, dict) else {}
    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    user_model = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    current_level_self_report = str(
        questionnaire.get("current_level_self_report")
        or user_model.get("profile")
        or ""
    ).strip()
    if _has_uncertainty_signal(current_level_self_report):
        return True
    if _diagnostic_follow_up_needed(diagnostic):
        return True
    if _diagnostic_has_reliable_level_signal(diagnostic):
        return False
    if current_level_self_report:
        return False
    return True


def diagnostic_required(diagnostic: dict[str, Any] | None = None) -> bool:
    return not _diagnostic_has_reliable_level_signal(diagnostic)


def research_scope_required(
    clarification: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> bool:
    assessment_budget = resolve_assessment_budget_preference(clarification, diagnostic)
    return (
        assessment_budget.get("max_assessment_rounds_preference") is not None
        and assessment_budget.get("questions_per_round_preference") is not None
        and diagnostic_required(diagnostic)
    )


def infer_workflow_type(
    topic: str,
    goal: str,
    diagnostic: dict[str, Any] | None = None,
    clarification: dict[str, Any] | None = None,
) -> str:
    research_needed = needs_research(topic, goal)
    clarification = clarification if isinstance(clarification, dict) else {}
    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    user_model = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    current_level_self_report = str(
        questionnaire.get("current_level_self_report")
        or user_model.get("profile")
        or ""
    ).strip()
    diagnostic_needed_at_entry = _has_uncertainty_signal(topic, goal, current_level_self_report) or not current_level_self_report
    if research_needed and diagnostic_needed_at_entry:
        return "mixed"
    if research_needed:
        return "research-first"
    if diagnostic_needed_at_entry:
        return "diagnostic-first"
    return "light"


def _artifact_has_quality_signal(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "quality_review",
            "generation_trace",
            "traceability",
            "evidence",
            "confidence",
            "candidate_version",
            "stage",
        )
    )


def _legacy_stage_semantic_issues(stage: str, artifact: dict[str, Any]) -> list[str]:
    normalized_stage = str(stage or "").strip().lower()
    issues: list[str] = []
    if normalized_stage == "clarification":
        normalized_artifact = normalize_clarification_artifact(artifact)
        questionnaire = normalized_artifact.get("questionnaire") if isinstance(normalized_artifact.get("questionnaire"), dict) else {}
        clarification_state = normalized_artifact.get("clarification_state") if isinstance(normalized_artifact.get("clarification_state"), dict) else {}
        preference_state = normalized_artifact.get("preference_state") if isinstance(normalized_artifact.get("preference_state"), dict) else {}
        assessment_budget = resolve_assessment_budget_preference(normalized_artifact, None)
        if not normalize_string_list(questionnaire.get("success_criteria")):
            issues.append("clarification.success_criteria_missing")
        if not str(questionnaire.get("current_level_self_report") or "").strip():
            issues.append("clarification.current_level_self_report_missing")
        if list(clarification_state.get("open_questions") or []):
            issues.append("clarification.open_questions")
        if list(preference_state.get("pending_items") or []):
            issues.append("clarification.preference_state")
        if assessment_budget.get("max_assessment_rounds_preference") is None:
            issues.append("clarification.max_assessment_rounds_preference")
        if assessment_budget.get("questions_per_round_preference") is None:
            issues.append("clarification.questions_per_round_preference")
    elif normalized_stage == "research":
        research_plan = artifact.get("research_plan") if isinstance(artifact.get("research_plan"), dict) else {}
        report = artifact.get("research_report") if isinstance(artifact.get("research_report"), dict) else {}
        plan_status = str(research_plan.get("status") or ("completed" if report else "")).strip().lower()
        if research_plan and plan_status not in {"approved", "completed"}:
            issues.append("research.plan_status")
        if str(report.get("report_status") or "").strip().lower() != "completed":
            issues.append("research.report_status")
        if not str(report.get("research_brief") or "").strip():
            issues.append("research.research_brief")
        if not str(report.get("goal_target_band") or "").strip():
            issues.append("research.goal_target_band")
        if not normalize_string_list(report.get("must_master_core")):
            issues.append("research.must_master_core")
        if not normalize_string_list(report.get("evidence_expectations")):
            issues.append("research.evidence_expectations")
        if not list(report.get("capability_metrics") or []) and not normalize_string_list(report.get("mainline_capabilities") or []):
            issues.append("research.capability_metrics")
        if not normalize_string_list(report.get("evidence_summary") or report.get("source_evidence")):
            issues.append("research.evidence")
    elif normalized_stage == "diagnostic":
        diagnostic_plan = artifact.get("diagnostic_plan") if isinstance(artifact.get("diagnostic_plan"), dict) else {}
        diagnostic_result = artifact.get("diagnostic_result") if isinstance(artifact.get("diagnostic_result"), dict) else {}
        diagnostic_profile = artifact.get("diagnostic_profile") if isinstance(artifact.get("diagnostic_profile"), dict) else {}
        delivery = str(diagnostic_plan.get("delivery") or diagnostic_plan.get("diagnostic_delivery") or "").strip()
        assessment_kind = str(diagnostic_plan.get("assessment_kind") or diagnostic_profile.get("assessment_kind") or "").strip()
        session_intent = str(diagnostic_plan.get("session_intent") or diagnostic_profile.get("session_intent") or "").strip()
        plan_execution_mode = str(diagnostic_plan.get("plan_execution_mode") or diagnostic_profile.get("plan_execution_mode") or "").strip()
        if delivery != "web-session":
            issues.append("diagnostic.delivery")
        if not diagnostic_metadata_is_valid(assessment_kind, session_intent, plan_execution_mode):
            issues.append("diagnostic.assessment_kind")
            issues.append("diagnostic.session_intent")
        round_index = _normalize_positive_int(diagnostic_plan.get("round_index") if "round_index" in diagnostic_plan else diagnostic_profile.get("round_index"))
        max_rounds = _normalize_positive_int(diagnostic_plan.get("max_rounds") if "max_rounds" in diagnostic_plan else diagnostic_profile.get("max_rounds"))
        questions_per_round = _normalize_positive_int(diagnostic_plan.get("questions_per_round") if "questions_per_round" in diagnostic_plan else diagnostic_profile.get("questions_per_round"))
        if round_index is None:
            issues.append("diagnostic.round_index")
        if max_rounds is None or (round_index is not None and max_rounds < round_index):
            issues.append("diagnostic.max_rounds")
        if questions_per_round is None:
            issues.append("diagnostic.questions_per_round")
        evaluated = str(diagnostic_result.get("status") or "").strip().lower() == "evaluated" or str(diagnostic_profile.get("status") or "").strip().lower() == "validated"
        if evaluated and not list(diagnostic_result.get("capability_assessment") or []):
            issues.append("diagnostic.capability_assessment")
        if "follow_up_needed" not in diagnostic_result and "follow_up_needed" not in diagnostic_profile and "follow_up_needed" not in diagnostic_plan:
            issues.append("diagnostic.follow_up_needed")
        if _diagnostic_follow_up_needed(artifact):
            issues.append("diagnostic.follow_up_pending")
        if not str(diagnostic_result.get("recommended_entry_level") or diagnostic_profile.get("recommended_entry_level") or "").strip():
            issues.append("diagnostic.recommended_entry_level")
        if not str(diagnostic_result.get("confidence") or diagnostic_profile.get("confidence") or "").strip():
            issues.append("diagnostic.confidence")
        if not str(diagnostic_result.get("stop_reason") or diagnostic_profile.get("stop_reason") or diagnostic_plan.get("stop_reason") or "").strip():
            issues.append("diagnostic.stop_reason")
    elif normalized_stage == "approval":
        approval_state = artifact.get("approval_state") if isinstance(artifact.get("approval_state"), dict) else {}
        if not approval_state:
            issues.append("approval.approval_state")
        elif not str(approval_state.get("approval_status") or "").strip():
            issues.append("approval.approval_status")
    elif normalized_stage == "planning":
        plan_candidate = artifact.get("plan_candidate") if isinstance(artifact.get("plan_candidate"), dict) else {}
        if not plan_candidate:
            issues.append("planning.plan_candidate")
        if not normalize_string_list(plan_candidate.get("stage_goals")):
            issues.append("planning.stage_goals")
        if not normalize_string_list(plan_candidate.get("mastery_checks")):
            issues.append("planning.mastery_checks")
    return issues


def _collect_stage_quality(
    *,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    planning: dict[str, Any] | None = None,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    artifacts = {
        "clarification": clarification or {},
        "research": research or {},
        "diagnostic": diagnostic or {},
        "approval": approval or {},
        "planning": planning or {},
    }
    issues_by_stage: dict[str, list[str]] = {}
    quality_summary: dict[str, dict[str, Any]] = {}
    for stage, payload in artifacts.items():
        artifact = payload if isinstance(payload, dict) else {}
        review = artifact.get("quality_review") if isinstance(artifact.get("quality_review"), dict) else {}
        if not artifact:
            issues_by_stage[stage] = []
            quality_summary[stage] = {
                "present": False,
                "valid": False,
                "verdict": "missing",
                "confidence": 0.0,
                "reviewer": "",
                "issues": [],
            }
            continue
        if not _artifact_has_quality_signal(artifact):
            legacy_issues = normalize_string_list(_legacy_stage_semantic_issues(stage, artifact))
            issues_by_stage[stage] = legacy_issues
            quality_summary[stage] = {
                "present": True,
                "evaluated": True,
                "valid": not legacy_issues,
                "verdict": "ready" if not legacy_issues else "needs-revision",
                "confidence": normalize_confidence(artifact.get("confidence"), default=0.0),
                "reviewer": LEGACY_SEMANTIC_REVIEWER,
                "issues": legacy_issues,
            }
            continue
        issues = normalize_string_list(
            collect_quality_issues(
                artifact,
                prefix=WORKFLOW_STATE_QUALITY_PREFIXES.get(stage, stage),
                require_evidence=True,
                require_traceability=True,
                require_generation_trace=True,
                require_review=True,
                require_valid_review=True,
                min_confidence=QUALITY_CONFIDENCE_THRESHOLD.get(stage),
            )
        )
        issues_by_stage[stage] = issues
        quality_summary[stage] = {
            "present": True,
            "evaluated": True,
            "valid": (not issues) and (bool(review.get("valid")) if review else True),
            "verdict": str(review.get("verdict") or ("ready" if not issues else "needs-revision")).strip() or ("ready" if not issues else "needs-revision"),
            "confidence": normalize_confidence(artifact.get("confidence"), default=0.0),
            "reviewer": str(review.get("reviewer") or "").strip(),
            "issues": issues,
        }
    return issues_by_stage, quality_summary


def collect_missing_requirements(
    *,
    topic: str,
    goal: str,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    curriculum_patch_queue: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    raw_clarification = clarification if isinstance(clarification, dict) else {}
    has_explicit_consultation_state = bool(raw_clarification.get("consultation_model_enabled")) if "consultation_model_enabled" in raw_clarification else isinstance(raw_clarification.get("consultation_state"), dict)
    clarification = normalize_clarification_artifact(raw_clarification, diagnostic)
    research = research or {}
    diagnostic = diagnostic or {}
    approval = approval or {}

    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    clarification_state = clarification.get("clarification_state") if isinstance(clarification.get("clarification_state"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    consultation_state = clarification.get("consultation_state") if isinstance(clarification.get("consultation_state"), dict) else {}
    topic_map = _topic_by_id(consultation_state.get("topics"))
    user_model = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    goal_model = clarification.get("goal_model") if isinstance(clarification.get("goal_model"), dict) else {}
    schedule = clarification.get("schedule") if isinstance(clarification.get("schedule"), dict) else {}

    success_criteria = _collect_success_criteria(questionnaire, clarification_state, goal_model)
    current_level_self_report = str(
        questionnaire.get("current_level_self_report")
        or user_model.get("profile")
        or ""
    ).strip()
    time_constraints = questionnaire.get("time_constraints") if isinstance(questionnaire.get("time_constraints"), dict) else {}
    legacy_constraints = _collect_time_constraint_signals(questionnaire, clarification_state, user_model, schedule)
    assessment_budget = resolve_assessment_budget_preference(clarification, diagnostic)
    max_rounds_preference = assessment_budget.get("max_assessment_rounds_preference")
    questions_per_round_preference = assessment_budget.get("questions_per_round_preference")
    budget_confirmed = max_rounds_preference is not None and questions_per_round_preference is not None

    clarification_missing: list[str] = []
    if not (str(topic or "").strip() or str(questionnaire.get("topic") or "").strip()):
        clarification_missing.append("clarification.topic")
    if not (str(goal or "").strip() or str(questionnaire.get("goal") or "").strip()):
        clarification_missing.append("clarification.goal")
    if not success_criteria:
        clarification_missing.append("clarification.success_criteria")
    current_level_deferred = _consultation_topic_status(consultation_state, "current_level") == "deferred"
    if not current_level_self_report and not current_level_deferred:
        clarification_missing.append("clarification.current_level_self_report")
    if not str(time_constraints.get("frequency") or "").strip() and not str(time_constraints.get("session_length") or "").strip() and not legacy_constraints:
        clarification_missing.append("clarification.time_constraints")
    if list(clarification_state.get("open_questions") or []):
        clarification_missing.append("clarification.open_questions")
    if list(preference_state.get("pending_items") or []):
        clarification_missing.append("clarification.preference_state")
    if max_rounds_preference is None:
        clarification_missing.append("clarification.max_assessment_rounds_preference")
    if questions_per_round_preference is None:
        clarification_missing.append("clarification.questions_per_round_preference")
    topics = consultation_state.get("topics") if isinstance(consultation_state.get("topics"), list) else []
    if has_explicit_consultation_state:
        if not consultation_state.get("current_topic_id") or not topics:
            clarification_missing.append("clarification.consultation_state")
        else:
            for item in topics:
                if not isinstance(item, dict) or not item.get("required"):
                    continue
                topic_id = str(item.get("id") or "unknown").strip()
                status = str(item.get("status") or "").strip().lower()
                if status == "resolved":
                    continue
                if status == "deferred" and topic_id == "current_level" and budget_confirmed:
                    continue
                clarification_missing.append(f"clarification.consultation_topic.{topic_id}")
            current_topic = topic_map.get(str(consultation_state.get("current_topic_id") or ""))
            if current_topic and str(current_topic.get("status") or "").strip().lower() not in {"resolved", "deferred"}:
                if not current_topic.get("open_questions") and not current_topic.get("ambiguities"):
                    clarification_missing.append("clarification.consultation_current_topic.follow_up")

    research_missing: list[str] = []
    if needs_research(topic, goal):
        research_plan = research.get("research_plan") if isinstance(research.get("research_plan"), dict) else {}
        research_report = research.get("research_report") if isinstance(research.get("research_report"), dict) else {}
        report_status = str(research_report.get("report_status") or ("completed" if research_report else "missing"))
        capability_metrics = list(research_report.get("capability_metrics") or [])
        visible_capabilities = list(research_report.get("must_master_capabilities") or research_report.get("must_master") or research_report.get("mainline_capabilities") or [])
        evidence_summary = list(research_report.get("evidence_summary") or research_report.get("source_evidence") or [])
        research_brief = str(research_report.get("research_brief") or "").strip()
        goal_target_band = str(research_report.get("goal_target_band") or "").strip()
        must_master_core = list(research_report.get("must_master_core") or [])
        evidence_expectations = list(research_report.get("evidence_expectations") or [])
        diagnostic_scope = research_report.get("diagnostic_scope") if isinstance(research_report.get("diagnostic_scope"), dict) else {}
        required_level_definition = str(research_report.get("required_level_definition") or "").strip()
        user_facing_report = research_report.get("user_facing_report") if isinstance(research_report.get("user_facing_report"), dict) else {}
        user_facing_format = str(user_facing_report.get("format") or "").strip().lower()
        user_facing_html = str(user_facing_report.get("html") or user_facing_report.get("path") or "").strip()
        user_facing_summary = normalize_string_list(user_facing_report.get("summary") or [])
        if not research:
            research_missing.append("research.report")
        plan_status = str(research_plan.get("status") or ("completed" if research_report else "")).strip().lower()
        if research_plan and plan_status not in {"approved", "completed"}:
            research_missing.append("research.plan_status")
        if report_status == "completed" and plan_status not in {"approved", "completed"}:
            research_missing.append("research.plan_confirmation_required")
        research_review = research.get("research_review") if isinstance(research.get("research_review"), dict) else {}
        review_status = str(research_review.get("status") or "").strip().lower()
        if report_status != "completed":
            research_missing.append("research.report_status")
        elif review_status not in {"confirmed", "approved", "accepted", "reviewed"}:
            research_missing.append("research.user_review_confirmation")
        if not research_brief:
            research_missing.append("research.research_brief")
        if not goal_target_band:
            research_missing.append("research.goal_target_band")
        if not required_level_definition:
            research_missing.append("research.required_level_definition")
        if user_facing_format != "html":
            research_missing.append("research.user_facing_report.format")
        if not user_facing_html:
            research_missing.append("research.user_facing_report.html")
        if not user_facing_summary:
            research_missing.append("research.user_facing_report.summary")
        if not must_master_core:
            research_missing.append("research.must_master_core")
        if not evidence_expectations:
            research_missing.append("research.evidence_expectations")
        if not capability_metrics and not visible_capabilities:
            research_missing.append("research.capability_metrics")
        for index, metric in enumerate(capability_metrics):
            if not isinstance(metric, dict):
                continue
            for field in ("observable_behaviors", "quantitative_indicators", "diagnostic_methods", "learning_evidence", "source_evidence"):
                if not normalize_string_list(metric.get(field) or []):
                    research_missing.append(f"research.capability_metrics.{index}.{field}")
        if not evidence_summary:
            research_missing.append("research.evidence")
        if research_scope_required(clarification, diagnostic):
            if not diagnostic_scope:
                research_missing.append("research.diagnostic_scope")
            else:
                if not normalize_string_list(diagnostic_scope.get("target_capability_ids") or []):
                    research_missing.append("research.diagnostic_scope.target_capability_ids")
                if not normalize_string_list(diagnostic_scope.get("scoring_dimensions") or []):
                    research_missing.append("research.diagnostic_scope.scoring_dimensions")
                if not normalize_string_list(diagnostic_scope.get("gap_judgement_basis") or []):
                    research_missing.append("research.diagnostic_scope.gap_judgement_basis")

    diagnostic_missing: list[str] = []
    if diagnostic_required(diagnostic):
        diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
        diagnostic_result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}
        diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
        result_status = str(diagnostic_result.get("status") or "")
        profile_status = str(diagnostic_profile.get("status") or "")
        diagnostic_delivery = str(diagnostic_plan.get("delivery") or diagnostic_plan.get("diagnostic_delivery") or "").strip()
        diagnostic_assessment_kind = str(diagnostic_plan.get("assessment_kind") or diagnostic_profile.get("assessment_kind") or "").strip()
        diagnostic_session_intent = str(diagnostic_plan.get("session_intent") or diagnostic_profile.get("session_intent") or "").strip()
        diagnostic_execution_mode = str(diagnostic_plan.get("plan_execution_mode") or diagnostic_profile.get("plan_execution_mode") or "").strip()
        round_index = diagnostic_plan.get("round_index") if "round_index" in diagnostic_plan else diagnostic_profile.get("round_index")
        max_rounds = diagnostic_plan.get("max_rounds") if "max_rounds" in diagnostic_plan else diagnostic_profile.get("max_rounds")
        questions_per_round = diagnostic_plan.get("questions_per_round") if "questions_per_round" in diagnostic_plan else diagnostic_profile.get("questions_per_round")
        if not diagnostic:
            diagnostic_missing.append("diagnostic.result")
        evaluated = result_status.strip().lower() == "evaluated" or profile_status.strip().lower() == "validated"
        if evaluated and not list(diagnostic_result.get("capability_assessment") or []):
            diagnostic_missing.append("diagnostic.capability_assessment")
        if diagnostic_delivery != "web-session":
            diagnostic_missing.append("diagnostic.delivery")
        if not diagnostic_metadata_is_valid(
            diagnostic_assessment_kind,
            diagnostic_session_intent,
            diagnostic_execution_mode,
        ):
            diagnostic_missing.append("diagnostic.assessment_kind")
            diagnostic_missing.append("diagnostic.session_intent")
        target_capability_ids = normalize_string_list(diagnostic_plan.get("target_capability_ids") or [])
        scoring_rubric = diagnostic_plan.get("scoring_rubric") if isinstance(diagnostic_plan.get("scoring_rubric"), list) else []
        diagnostic_items = diagnostic.get("diagnostic_items") if isinstance(diagnostic.get("diagnostic_items"), list) else []
        for field in diagnostic_blueprint_missing_fields(target_capability_ids, scoring_rubric, diagnostic_items):
            diagnostic_missing.append(f"diagnostic.{field}")
        research_report = research.get("research_report") if isinstance(research.get("research_report"), dict) else {}
        diagnostic_scope = research_report.get("diagnostic_scope") if isinstance(research_report.get("diagnostic_scope"), dict) else {}
        if research_scope_required(clarification, diagnostic):
            scope_capability_ids = normalize_string_list(diagnostic_scope.get("target_capability_ids") or [])
            if not diagnostic_scope:
                diagnostic_missing.append("diagnostic.research_scope")
            elif scope_capability_ids and not set(scope_capability_ids).issubset(set(target_capability_ids)):
                diagnostic_missing.append("diagnostic.scope_alignment")
        try:
            round_index_value = int(round_index)
        except (TypeError, ValueError):
            round_index_value = 0
        try:
            max_rounds_value = int(max_rounds)
        except (TypeError, ValueError):
            max_rounds_value = 0
        try:
            questions_per_round_value = int(questions_per_round)
        except (TypeError, ValueError):
            questions_per_round_value = 0
        if round_index_value < 1:
            diagnostic_missing.append("diagnostic.round_index")
        if max_rounds_value < max(1, round_index_value):
            diagnostic_missing.append("diagnostic.max_rounds")
        if questions_per_round_value < 1:
            diagnostic_missing.append("diagnostic.questions_per_round")
        if evaluated:
            if not str(diagnostic_result.get("recommended_entry_level") or diagnostic_profile.get("recommended_entry_level") or "").strip():
                diagnostic_missing.append("diagnostic.recommended_entry_level")
            if not str(diagnostic_result.get("confidence") or diagnostic_profile.get("confidence") or "").strip():
                diagnostic_missing.append("diagnostic.confidence")
        follow_up_needed = _diagnostic_follow_up_needed(diagnostic)
        if "follow_up_needed" not in diagnostic_result and "follow_up_needed" not in diagnostic_profile and "follow_up_needed" not in diagnostic_plan:
            diagnostic_missing.append("diagnostic.follow_up_needed")
        if follow_up_needed:
            diagnostic_missing.append("diagnostic.follow_up_pending")
        if not str(diagnostic_result.get("stop_reason") or diagnostic_profile.get("stop_reason") or diagnostic_plan.get("stop_reason") or "").strip():
            diagnostic_missing.append("diagnostic.stop_reason")

    approval_missing: list[str] = []
    approval_state = approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {}
    curriculum_patch_queue = curriculum_patch_queue if isinstance(curriculum_patch_queue, dict) else {}
    patch_items = [item for item in (curriculum_patch_queue.get("patches") or []) if isinstance(item, dict)]
    effective_pending_decisions = list(approval_state.get("pending_decisions") or [])
    effective_pending_decisions.extend(
        f"patch[{item.get('patch_type') or 'unknown'}] {item.get('topic') or topic}"
        for item in patch_items
        if str(item.get("status") or "").strip() in {"proposed", "pending", "pending-evidence"}
    )
    approval_status = str(approval_state.get("approval_status") or "").strip().lower()
    if approval_status not in {"approved", "accepted", "confirmed"}:
        approval_missing.append("approval.approval_status")
    if not bool(approval_state.get("ready_for_execution")):
        approval_missing.append("approval.ready_for_execution")
    if effective_pending_decisions:
        approval_missing.append("approval.pending_decisions")
    for field in (
        "confirmed_material_strategy",
        "confirmed_daily_execution_style",
        "confirmed_mastery_checks",
    ):
        if not approval_state.get(field):
            approval_missing.append(f"approval.{field}")
    material_curation = approval.get("material_curation") if isinstance(approval.get("material_curation"), dict) else {}
    if not material_curation:
        approval_missing.append("approval.material_curation")
    else:
        if str(material_curation.get("status") or "").strip().lower() != "confirmed":
            approval_missing.append("approval.material_curation.status")
        user_confirmation = material_curation.get("user_confirmation") if isinstance(material_curation.get("user_confirmation"), dict) else {}
        if not bool(user_confirmation.get("confirmed")):
            approval_missing.append("approval.material_curation.pending_user_confirmation")
        mainline_items = [
            item for item in (material_curation.get("materials") or [])
            if isinstance(item, dict) and item.get("role") == "mainline" and item.get("selection_status") == "confirmed"
        ]
        mainline_unavailable_reason = str(material_curation.get("mainline_unavailable_reason") or "").strip()
        open_risks = [str(item).strip() for item in (material_curation.get("open_risks") or []) if str(item).strip()]
        if not mainline_items and not mainline_unavailable_reason:
            approval_missing.append("approval.material_curation.mainline")
        invalid_mainline = [
            item for item in mainline_items
            if str(item.get("cache_status") or "") in {"download-failed", "validation-failed"}
        ]
        if mainline_items and len(invalid_mainline) == len(mainline_items) and not open_risks:
            approval_missing.append("approval.material_curation.mainline_cache_validation")

    return {
        "clarification": clarification_missing,
        "research": research_missing,
        "diagnostic": diagnostic_missing,
        "approval": approval_missing,
    }


def _split_stage_requirements(
    missing_by_stage: dict[str, list[str]],
    planning_missing: list[str],
    blocking_stage: str,
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    by_stage = {
        "clarification": list(missing_by_stage.get("clarification") or []),
        "research": list(missing_by_stage.get("research") or []),
        "diagnostic": list(missing_by_stage.get("diagnostic") or []),
        "approval": list(missing_by_stage.get("approval") or []),
        "planning": list(planning_missing or []),
    }
    stage_order = ["clarification", "research", "diagnostic", "approval", "planning"]
    if blocking_stage not in stage_order:
        return by_stage, [], []
    stage_index = stage_order.index(blocking_stage)
    actionable_stage = stage_order[stage_index]
    actionable = list(by_stage.get(actionable_stage) or [])
    reference: list[str] = []
    for stage in stage_order[stage_index + 1:]:
        reference.extend(by_stage.get(stage) or [])
    return by_stage, actionable, reference


def _build_workflow_instruction(blocking_stage: str, next_action: str) -> str:
    instructions = {
        "clarification": "当前只处理 clarification 阶段缺口；继续顾问式澄清，并先确认起始测评预算。不要提前进入 research、diagnostic 或手动补中间态 JSON。",
        "research": "当前只处理 research 阶段缺口；先完成 research plan / report 与用户确认，再继续下一阶段。不要手动补 research.json、diagnostic.json 或 diagnostic blueprint。",
        "diagnostic": "当前只处理 diagnostic 阶段缺口；应按 diagnostic workflow 或网页 session 重新产出诊断内容。不要手动补 diagnostic.json 或 blueprint 试图绕过 gate。",
        "approval": "当前只处理 approval 阶段缺口；先完成草案确认与 patch 审批，再决定是否 finalize。不要手动改 approval JSON 跳过确认。",
        "planning": "当前只处理 planning 阶段缺口；先生成或补齐 plan_candidate，再进入 finalize。不要把中间态直接当正式计划。",
        "ready": "前序 workflow gate 已满足；按 next_action 进入 finalize 或 /learn-today。",
    }
    base = instructions.get(blocking_stage, "请按 next_action 指向的阶段继续 workflow。")
    return f"{base} next_action={next_action}"


def _build_manual_patch_warning(blocking_stage: str) -> str:
    if blocking_stage == "ready":
        return ""
    if blocking_stage == "approval":
        return "当 should_continue_workflow=true 时，不要手动编辑 .learn-workflow/approval.json 来跳过确认。"
    return "当 should_continue_workflow=true 时，不要手动编辑 .learn-workflow/*.json 或手填 diagnostic blueprint；请回到 next_action 指向的阶段重新产出。"


def build_workflow_state(
    *,
    topic: str,
    goal: str,
    requested_mode: str,
    current_mode: str,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    planning: dict[str, Any] | None = None,
    learner_model: dict[str, Any] | None = None,
    curriculum_patch_queue: dict[str, Any] | None = None,
    quality_issues: list[str] | None = None,
    artifacts: dict[str, str] | None = None,
    workflow_type: str | None = None,
) -> dict[str, Any]:
    missing_by_stage = collect_missing_requirements(
        topic=topic,
        goal=goal,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        curriculum_patch_queue=curriculum_patch_queue,
    )
    stage_quality_issues, stage_quality = _collect_stage_quality(
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning=planning,
    )
    planning = planning or {}
    planning_candidate = planning.get("plan_candidate") if isinstance(planning.get("plan_candidate"), dict) else {}
    planning_missing: list[str] = []
    if str(current_mode or "").strip() == "finalize" and not planning_candidate:
        planning_missing.append("planning.plan_candidate")

    routing_reasons: list[str] = []
    blocking_stage = "ready"
    recommended_mode = "finalize"

    if missing_by_stage["clarification"]:
        blocking_stage = "clarification"
        recommended_mode = "draft"
        if (
            "clarification.max_assessment_rounds_preference" in missing_by_stage["clarification"]
            or "clarification.questions_per_round_preference" in missing_by_stage["clarification"]
        ):
            routing_reasons.append("起始测评预算尚未确认，应先确认最多几轮测试与每轮几题，再进入网页诊断 session")
        else:
            routing_reasons.append("仍存在待澄清问题，应优先补齐顾问式澄清")
    elif stage_quality_issues["clarification"]:
        blocking_stage = "clarification"
        recommended_mode = "draft"
        routing_reasons.append("clarification candidate 尚未通过质量评审，应先补齐证据、追踪信息与未决项")
    elif missing_by_stage["research"]:
        blocking_stage = "research"
        recommended_mode = "research-report"
        routing_reasons.append("目标需要 research 支撑，应优先补齐能力要求与材料取舍依据")
    elif stage_quality_issues["research"]:
        blocking_stage = "research"
        recommended_mode = "research-report"
        routing_reasons.append("research candidate 尚未通过质量评审，应先补齐 evidence/source grounding 与取舍理由")
    elif missing_by_stage["diagnostic"]:
        blocking_stage = "diagnostic"
        recommended_mode = "diagnostic"
        routing_reasons.append("当前水平仍不可靠，应优先完成最小水平诊断")
    elif stage_quality_issues["diagnostic"]:
        blocking_stage = "diagnostic"
        recommended_mode = "diagnostic"
        routing_reasons.append("diagnostic candidate 尚未通过质量评审，应先补齐 confidence、推荐起点与能力覆盖")
    elif missing_by_stage["approval"]:
        blocking_stage = "approval"
        recommended_mode = "draft"
        routing_reasons.append("计划尚未通过 approval gate，应先完成确认与关键决策")
    elif stage_quality_issues["approval"]:
        blocking_stage = "approval"
        recommended_mode = "draft"
        routing_reasons.append("approval candidate 尚未通过质量评审，应先明确 ready 状态与待决策项")
    elif planning_missing:
        blocking_stage = "planning"
        recommended_mode = "finalize"
        routing_reasons.append("finalize 前仍缺少结构化 plan candidate，应先生成规划候选态")
    elif stage_quality_issues["planning"]:
        blocking_stage = "planning"
        recommended_mode = "finalize"
        routing_reasons.append("planning candidate 尚未通过质量评审，应先补齐阶段目标、掌握标准与执行逻辑")
    else:
        routing_reasons.append("主要 workflow gate 已满足，可进入 finalize / 执行阶段")

    missing_requirements_by_stage, actionable_missing_requirements, reference_missing_requirements = _split_stage_requirements(
        missing_by_stage,
        planning_missing,
        blocking_stage,
    )
    external_quality_issues = normalize_string_list(quality_issues or [])
    combined_quality_issues = normalize_string_list(
        [
            *stage_quality_issues["clarification"],
            *stage_quality_issues["research"],
            *stage_quality_issues["diagnostic"],
            *stage_quality_issues["approval"],
            *stage_quality_issues["planning"],
            *external_quality_issues,
        ]
    )
    actionable_quality_issues = list(stage_quality_issues.get(blocking_stage) or []) if blocking_stage != "ready" else []
    reference_quality_issues: list[str] = []
    if blocking_stage in {"clarification", "research", "diagnostic", "approval", "planning"}:
        stage_order = ["clarification", "research", "diagnostic", "approval", "planning"]
        for stage in stage_order[stage_order.index(blocking_stage) + 1:]:
            reference_quality_issues.extend(stage_quality_issues.get(stage) or [])
    ready_for_entry = blocking_stage == "ready" and current_mode == "finalize" and not combined_quality_issues
    next_action = NEXT_ACTION_ENTER_TODAY if ready_for_entry else next_action_for_mode(recommended_mode)
    workflow_instruction = _build_workflow_instruction(blocking_stage, next_action)
    manual_patch_warning = _build_manual_patch_warning(blocking_stage)
    stage_exit_contract = dict(STAGE_EXIT_CONTRACTS.get(blocking_stage) or {})
    stage_entry_contract = dict(STAGE_EXIT_CONTRACTS.get(blocking_stage) or {})
    stage_exit_missing_values = list(actionable_missing_requirements)
    stage_exit_required_artifacts = list(stage_exit_contract.get("required_artifacts") or [])
    stage_exit_user_visible_next_step = str(stage_exit_contract.get("user_visible_next_step") or "").strip()

    research_plan = research.get("research_plan") if isinstance(research, dict) and isinstance(research.get("research_plan"), dict) else {}
    research_report = research.get("research_report") if isinstance(research, dict) and isinstance(research.get("research_report"), dict) else {}
    research_review = research.get("research_review") if isinstance(research, dict) and isinstance(research.get("research_review"), dict) else {}
    research_artifact_ready = bool(research_plan or research_report)
    research_artifact_displayable = research_artifact_ready and not stage_quality_issues["research"]
    research_artifact_valid = research_artifact_ready and not missing_by_stage["research"] and not stage_quality_issues["research"]
    resolved_workflow_type = str(workflow_type or "").strip()
    if resolved_workflow_type not in {"light", "diagnostic-first", "research-first", "mixed"}:
        resolved_workflow_type = infer_workflow_type(topic, goal, diagnostic, clarification)
    effective_current_mode = current_mode
    mode_demoted = False
    demotion_reason = ""
    if current_mode == "finalize" and blocking_stage != "ready":
        effective_current_mode = recommended_mode
        mode_demoted = True
        demotion_reason = f"blocking_stage={blocking_stage} incompatible with finalize"
    all_missing_requirements = [
        *missing_by_stage["clarification"],
        *missing_by_stage["research"],
        *missing_by_stage["diagnostic"],
        *missing_by_stage["approval"],
        *planning_missing,
    ]
    return {
        "contract_version": CONTRACT_VERSION,
        "workflow_type": resolved_workflow_type,
        "topic": topic,
        "goal": goal,
        "requested_mode": requested_mode,
        "current_mode": effective_current_mode,
        "recommended_mode": recommended_mode,
        "blocking_stage": blocking_stage,
        "mode_demoted": mode_demoted,
        "demotion_reason": demotion_reason,
        "should_continue_workflow": not ready_for_entry,
        "is_intermediate_product": not ready_for_entry,
        "next_action": next_action,
        "missing_requirements": all_missing_requirements,
        "all_missing_requirements": all_missing_requirements,
        "missing_requirements_by_stage": missing_requirements_by_stage,
        "actionable_stage": blocking_stage,
        "actionable_missing_requirements": actionable_missing_requirements,
        "reference_missing_requirements": reference_missing_requirements,
        "routing_reasons": routing_reasons,
        "quality_issues": combined_quality_issues,
        "actionable_quality_issues": actionable_quality_issues,
        "reference_quality_issues": reference_quality_issues,
        "workflow_instruction": workflow_instruction,
        "manual_patch_warning": manual_patch_warning,
        "stage_entry_contract": stage_entry_contract,
        "stage_exit_contract": stage_exit_contract,
        "stage_exit_missing_values": stage_exit_missing_values,
        "stage_exit_required_artifacts": stage_exit_required_artifacts,
        "stage_exit_user_visible_next_step": stage_exit_user_visible_next_step,
        "stage_quality": stage_quality,
        "research_plan": research_plan,
        "research_report": research_report,
        "research_review": research_review,
        "research_artifact_ready": research_artifact_ready,
        "research_artifact_valid": research_artifact_valid,
        "should_show_research_report": research_artifact_displayable,
        "artifacts": dict(artifacts or {}),
    }
