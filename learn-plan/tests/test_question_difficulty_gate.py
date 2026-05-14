from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.question_generation import build_difficulty_review
from learn_runtime.question_validation import validate_questions_payload
from learn_runtime.schemas import (
    infer_min_difficulty_from_dimensions,
    validate_objective_question_contract,
    validate_question_authoring_metadata,
    validate_question_difficulty_fields,
)


def option_diagnostics() -> list[dict[str, object]]:
    return [
        {
            "index": 0,
            "claim": "`=` 是 Python 的赋值符号。",
            "diagnostic_role": "correct_concept",
            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
            "prerequisite_ids": [],
            "misconception_ids": [],
            "evidence_span": "选项 `=` 对应变量赋值语法。",
            "diagnostic_question": "你如何区分赋值和相等比较？",
        },
        {
            "index": 1,
            "claim": "`==` 是 Python 的相等比较符号。",
            "diagnostic_role": "distractor",
            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
            "prerequisite_ids": [],
            "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
            "evidence_span": "选项 `==` 暴露赋值与比较混淆。",
            "diagnostic_question": "什么时候应该使用 `==` 而不是 `=`？",
        },
    ]


def base_question(level: str = "basic") -> dict[str, object]:
    labels = {"basic": "基础题", "medium": "中等题", "upper_medium": "中难题", "hard": "难题"}
    scores = {"basic": 1, "medium": 2, "upper_medium": 3, "hard": 4}
    return {
        "id": f"q-{level}",
        "category": "concept",
        "type": "single_choice",
        "title": "赋值符号",
        "prompt": "**问题**：Python 中哪个符号用于赋值？\n\n请选择最合适的一项。",
        "options": ["=", "=="],
        "answer": 0,
        "option_diagnostics": option_diagnostics(),
        "explanation": "= 用于赋值。",
        "scoring_rubric": [{"metric": "概念理解", "threshold": "识别赋值符号"}],
        "capability_tags": ["python-assignment"],
        "source_trace": {"question_source": "agent-injected"},
        "difficulty": level,
        "difficulty_level": level,
        "difficulty_label": labels[level],
        "difficulty_score": scores[level],
        "difficulty_reason": "只考察一个基础概念。",
        "expected_failure_mode": "混淆赋值和相等比较。",
    }


def add_scope_plan(payload: dict[str, object]) -> dict[str, object]:
    questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
    question_mix: dict[str, int] = {}
    difficulty_distribution: dict[str, int] = {}
    for question in questions:
        if not isinstance(question, dict):
            continue
        qtype = "code" if question.get("category") == "code" or question.get("type") == "code" else str(question.get("type") or "single_choice")
        question_mix[qtype] = question_mix.get(qtype, 0) + 1
        level = str(question.get("difficulty_level") or question.get("difficulty") or "medium")
        difficulty_distribution[level] = difficulty_distribution.get(level, 0) + 1
    scope = {
        "schema_version": "learn-plan.question_scope.v1",
        "scope_id": "scope-difficulty-fixture",
        "source_profile": "today-lesson",
        "session_type": "today",
        "session_intent": "learning",
        "assessment_kind": None,
        "test_mode": None,
        "topic": payload.get("topic") or "Python 基础",
        "language_policy": payload.get("language_policy") or {"user_facing_language": "zh-CN"},
        "scope_basis": [{"kind": "lesson", "summary": "difficulty fixture"}],
        "target_capability_ids": ["python-assignment"],
        "target_concepts": ["赋值符号"],
        "target_knowledge_point_ids": ["kp-python-assignment"],
        "diagnostic_strategy": {"selection_strategy": "lesson_aligned", "early_stop_allowed": False},
        "review_targets": [],
        "lesson_focus_points": ["赋值符号"],
        "project_tasks": [],
        "project_blockers": [],
        "source_material_refs": [],
        "difficulty_target": {},
        "minimum_pass_shape": {"required_open_question_count": 0},
        "exclusions": [],
        "evidence": ["fixture"],
        "generation_trace": {"status": "ok"},
    }
    plan = {
        "schema_version": "learn-plan.question_plan.v1",
        "plan_id": "plan-difficulty-fixture",
        "scope_id": "scope-difficulty-fixture",
        "source_profile": "today-lesson",
        "session_type": "today",
        "session_intent": "learning",
        "assessment_kind": None,
        "test_mode": None,
        "topic": payload.get("topic") or "Python 基础",
        "question_count": len(questions),
        "question_mix": question_mix,
        "difficulty_distribution": difficulty_distribution,
        "diagnostic_value": {},
        "early_stop_policy": {},
        "planned_items": [],
        "coverage_matrix": [],
        "minimum_pass_shape": {"required_open_question_count": 0},
        "forbidden_question_types": ["open", "written", "short_answer", "free_text"],
        "generation_guidance": [],
        "review_checklist": [],
        "evidence": ["scope-difficulty-fixture"],
        "generation_trace": {"status": "ok"},
    }
    plan_source = payload.setdefault("plan_source", {})
    if isinstance(plan_source, dict):
        plan_source["question_scope"] = scope
        plan_source["question_plan"] = plan
        plan_source.setdefault("language_policy", payload.get("language_policy") or {"user_facing_language": "zh-CN"})
        grounding_context = plan_source.setdefault("lesson_grounding_context", {})
        if isinstance(grounding_context, dict):
            grounding_context["semantic_profile"] = "today"
            grounding_context["question_scope"] = scope
            grounding_context["question_plan"] = plan
    payload["selection_context"] = {
        "language_policy": payload.get("language_policy") or {"user_facing_language": "zh-CN"},
        "question_scope": scope,
        "question_plan": plan,
        "daily_lesson_plan": {"semantic_profile": "today", "question_scope": scope, "question_plan": plan},
    }
    return payload


def base_payload() -> dict[str, object]:
    return add_scope_plan({
        "date": "2026-04-29",
        "topic": "Python 基础",
        "mode": "today-generated",
        "session_type": "today",
        "session_intent": "learning",
        "assessment_kind": None,
        "test_mode": None,
        "language_policy": {"user_facing_language": "zh-CN", "localization_required": True},
        "plan_source": {
            "difficulty_target": {
                "concept": ["basic", "medium"],
                "recommended_distribution": {"concept": {"basic": 1, "medium": 1}},
            }
        },
        "materials": [],
        "questions": [add_authoring_metadata(base_question("basic")), add_authoring_metadata(base_question("medium"))],
    })


def add_authoring_metadata(question: dict[str, object], *, target_level: str | None = None) -> dict[str, object]:
    level = str(question.get("difficulty_level") or question.get("difficulty") or "basic")
    target = target_level or level
    question["planned_item_id"] = "plan-item-assignment"
    question["assessment_intent"] = "检查学习者是否能区分 Python 赋值与相等比较，并通过错选诊断符号语义混淆。"
    question["knowledge_scope"] = {
        "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
        "prerequisite_ids": [],
        "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
        "source_trace": {"question_source": "agent-injected"},
    }
    question["question_type_rationale"] = {
        "type": question.get("type"),
        "reason": "单选题适合在相似符号中识别唯一正确概念。",
        "assessment_fit": "干扰项能暴露赋值与相等比较混淆。",
    }
    question["coverage_units"] = [
        {
            "unit_type": "option",
            "option_index": 0,
            "claim": "`=` 是 Python 的赋值符号。",
            "diagnostic_role": "correct_concept",
            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
            "difficulty_level": level,
            "diagnostic_value": "验证正向概念识别。",
        },
        {
            "unit_type": "option",
            "option_index": 1,
            "claim": "`==` 是 Python 的相等比较符号。",
            "diagnostic_role": "distractor",
            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
            "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
            "difficulty_level": level,
            "distractor_rationale": "常见误区是把赋值和比较符号混淆。",
            "diagnostic_value": "错选可触发赋值/比较区分追问。",
        },
    ]
    question["difficulty_profile"] = {
        "target_difficulty_level": target,
        "difficulty_level": level,
        "difficulty_reason": question.get("difficulty_reason"),
        "expected_failure_mode": question.get("expected_failure_mode"),
        "coverage_units": [
            {"option_index": 0, "difficulty_level": level},
            {"option_index": 1, "difficulty_level": level},
        ],
    }
    return question


class QuestionDifficultyGateTest(unittest.TestCase):
    def test_complete_difficulty_fields_pass(self) -> None:
        self.assertEqual(validate_question_difficulty_fields(base_question()), [])

    def test_missing_reason_and_failure_mode_block(self) -> None:
        question = base_question()
        question.pop("difficulty_reason")
        question.pop("expected_failure_mode")

        issues = validate_question_difficulty_fields(question)

        self.assertIn("question.difficulty.difficulty_reason_missing", issues)
        self.assertIn("question.difficulty.expected_failure_mode_missing", issues)

    def test_score_mismatch_blocks(self) -> None:
        question = base_question("hard")
        question["difficulty_score"] = 2

        self.assertIn("question.difficulty.score_mismatch", validate_question_difficulty_fields(question))

    def test_payload_distribution_passes(self) -> None:
        result = validate_questions_payload(base_payload())

        self.assertEqual(result.get("issues"), [])
        self.assertEqual(result.get("difficulty_counts"), {"basic": 1, "medium": 1})

    def test_payload_distribution_mismatch_blocks(self) -> None:
        payload = base_payload()
        payload["questions"] = [base_question("basic"), copy.deepcopy(base_question("basic"))]
        payload["questions"][1]["id"] = "q-basic-2"

        result = validate_questions_payload(payload)

        self.assertTrue(any("难度分布不符合目标" in issue for issue in result.get("issues", [])))

    def test_allowed_range_blocks_out_of_scope_level(self) -> None:
        payload = base_payload()
        payload["plan_source"] = {"difficulty_target": {"concept": ["basic"]}}

        result = validate_questions_payload(payload)

        self.assertTrue(any("超出 concept 允许范围" in issue for issue in result.get("issues", [])))

    def test_difficulty_dimensions_infer_minimum_level(self) -> None:
        self.assertEqual(
            infer_min_difficulty_from_dimensions({"knowledge_point_count": 1, "reasoning_steps": 1}),
            "basic",
        )
        self.assertEqual(
            infer_min_difficulty_from_dimensions({"knowledge_point_count": 2, "requires_concept_combination": True}),
            "medium",
        )
        self.assertEqual(
            infer_min_difficulty_from_dimensions({"knowledge_point_count": 3, "requires_concept_combination": True, "reasoning_steps": 3}),
            "upper_medium",
        )

    def test_question_dimensions_underestimated_level_blocks(self) -> None:
        payload = base_payload()
        payload["questions"] = [base_question("basic")]
        payload["questions"][0]["difficulty_dimensions"] = {
            "knowledge_point_count": 2,
            "requires_concept_combination": True,
            "reasoning_steps": 2,
        }
        payload["plan_source"]["question_plan"]["question_count"] = 1
        payload["plan_source"]["question_plan"]["question_mix"] = {"single_choice": 1}
        payload["plan_source"]["question_plan"]["difficulty_distribution"] = {"basic": 1}
        payload["selection_context"]["question_plan"] = payload["plan_source"]["question_plan"]

        result = validate_questions_payload(payload)

        self.assertTrue(any("低于启发式最低难度 medium" in issue for issue in result.get("issues", [])))

    def test_legacy_question_without_dimensions_still_passes(self) -> None:
        result = validate_questions_payload(base_payload())

        self.assertEqual(result.get("issues"), [])

    def test_difficulty_review_uses_planned_item_position_when_ids_differ(self) -> None:
        question = base_question("medium")
        question["difficulty_dimensions"] = {"knowledge_point_count": 2, "reasoning_steps": 2}
        review = build_difficulty_review(
            [question],
            {"planned_items": [{"item_id": "plan-item-1", "target_difficulty_level": "basic"}]},
        )

        self.assertFalse(review.get("valid"))
        self.assertTrue(any("高于计划目标 basic" in issue for issue in review.get("issues", [])))
        self.assertEqual(review.get("items", [])[0].get("target_difficulty_level"), "basic")

    def test_complete_authoring_metadata_passes(self) -> None:
        question = add_authoring_metadata(base_question("basic"))

        self.assertEqual(validate_question_authoring_metadata(question), [])

    def test_partial_authoring_metadata_blocks(self) -> None:
        question = base_question("basic")
        question["assessment_intent"] = "检查赋值符号。"

        issues = validate_question_authoring_metadata(question)

        self.assertIn("question.authoring.knowledge_scope_missing", issues)
        self.assertIn("question.authoring.coverage_units_missing", issues)

    def test_coverage_unit_above_target_blocks_difficulty_review(self) -> None:
        question = add_authoring_metadata(base_question("medium"), target_level="basic")
        question["difficulty_dimensions"] = {"knowledge_point_count": 1, "reasoning_steps": 1}
        review = build_difficulty_review(
            [question],
            {"planned_items": [{"item_id": "plan-item-assignment", "target_difficulty_level": "basic"}]},
        )

        self.assertFalse(review.get("valid"))
        self.assertTrue(any("coverage unit" in issue and "高于计划目标 basic" in issue for issue in review.get("issues", [])))

    def test_payload_authoring_metadata_quality_gate_blocks_new_incomplete_artifact(self) -> None:
        payload = base_payload()
        payload["questions"] = [base_question("basic")]
        payload["questions"][0]["assessment_intent"] = "检查赋值符号。"
        payload["plan_source"]["question_plan"]["question_count"] = 1
        payload["plan_source"]["question_plan"]["question_mix"] = {"single_choice": 1}
        payload["plan_source"]["question_plan"]["difficulty_distribution"] = {"basic": 1}
        payload["selection_context"]["question_plan"] = payload["plan_source"]["question_plan"]

        result = validate_questions_payload(payload)

        self.assertTrue(any("question.authoring.knowledge_scope_missing" in issue for issue in result.get("issues", [])))

    def test_new_agent_question_without_authoring_metadata_blocks(self) -> None:
        question = base_question("basic")

        issues = validate_question_authoring_metadata(question)

        self.assertIn("question.authoring.assessment_intent_missing", issues)
        self.assertIn("question.authoring.knowledge_scope_missing", issues)
        self.assertIn("question.authoring.coverage_units_missing", issues)
        self.assertIn("question.authoring.difficulty_profile_missing", issues)

    def test_low_information_choice_option_blocks(self) -> None:
        question = add_authoring_metadata(base_question("basic"))
        question["options"] = ["=", "==", "以上都不对"]
        diagnostics = list(question["option_diagnostics"])
        diagnostics.append({
            "index": 2,
            "claim": "兜底选项：以上都不对。",
            "diagnostic_role": "distractor",
            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
            "misconception_ids": [{"id": "mc-low-information-option", "confidence": 0.8}],
            "evidence_span": "选项 `以上都不对` 没有提供具体误区命题。",
            "diagnostic_question": "这个兜底选项对应哪一种具体误区？",
            "confidence": 0.8,
        })
        question["option_diagnostics"] = diagnostics
        question["coverage_units"].append({
            "unit_type": "option",
            "option_index": 2,
            "claim": "兜底选项：以上都不对。",
            "diagnostic_role": "distractor",
            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
            "misconception_ids": [{"id": "mc-low-information-option", "confidence": 0.8}],
            "difficulty_level": "basic",
            "distractor_rationale": "兜底选项没有诊断价值。",
            "diagnostic_value": "低信息选项应被阻断。",
        })

        issues = validate_objective_question_contract(question)

        self.assertIn("question.objective.options.low_information_option", issues)

    def test_distractor_without_real_misconception_blocks(self) -> None:
        question = add_authoring_metadata(base_question("basic"))
        diagnostics = list(question["option_diagnostics"])
        diagnostics[1] = {
            "index": 1,
            "claim": "选项表达的命题：==",
            "diagnostic_role": "distractor",
            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
            "prerequisite_ids": [],
            "misconception_ids": [],
            "evidence_span": "选项文本：==",
            "diagnostic_question": "你为什么认为这个选项成立或不成立？",
            "confidence": 0.6,
        }
        question["option_diagnostics"] = diagnostics
        question["coverage_units"][1].pop("misconception_ids", None)
        question["coverage_units"][1].pop("distractor_rationale", None)

        issues = validate_objective_question_contract(question) + validate_question_authoring_metadata(question)

        self.assertIn("question.objective.option_diagnostics.1.distractor_misconception_missing", issues)
        self.assertIn("question.objective.option_diagnostics.1.synthetic_or_template_evidence", issues)
        self.assertIn("question.objective.option_diagnostics.1.synthetic_or_template_question", issues)
        self.assertIn("question.authoring.coverage_units.1.distractor_rationale_missing", issues)

    def test_true_false_authoring_metadata_requires_boundary_unit(self) -> None:
        question = add_authoring_metadata(base_question("medium"))
        question["type"] = "true_false"
        question["options"] = []
        question["answer"] = True
        question["question_type_rationale"] = {
            "type": "true_false",
            "reason": "判断题用于检验限定条件是否成立。",
            "assessment_fit": "边界反例能暴露只背术语的误区。",
        }
        question["coverage_units"] = [
            {
                "unit_type": "statement",
                "claim": "赋值语句会把名字绑定到对象。",
                "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
                "difficulty_level": "medium",
                "diagnostic_value": "检查判断命题本身。",
            },
            {
                "unit_type": "truth_rationale",
                "claim": "变量名绑定的是对象引用而不是复制对象。",
                "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
                "difficulty_level": "medium",
                "diagnostic_value": "检查解释理由。",
            },
        ]

        issues = validate_question_authoring_metadata(question)

        self.assertTrue(any("true_false_units_missing:boundary_or_counterexample" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
