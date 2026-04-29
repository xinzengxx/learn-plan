from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.question_validation import validate_questions_payload
from learn_runtime.schemas import validate_question_difficulty_fields


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


def base_payload() -> dict[str, object]:
    return {
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
        "questions": [base_question("basic"), base_question("medium")],
    }


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


if __name__ == "__main__":
    unittest.main()
