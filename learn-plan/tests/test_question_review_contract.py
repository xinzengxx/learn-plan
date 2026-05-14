from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.payload_builder import strict_review_failure_message
from learn_runtime.question_generation import merge_question_review_results, normalize_generated_runtime_questions, normalize_strict_question_review


DIMENSION_REVIEWS = {
    "description_completeness": {
        "status": "pass",
        "issues": [],
        "evidence": ["题干、选项、答案与解析完整。"],
        "suggestions": [],
        "repair_instruction": "",
    },
    "knowledge_coverage_match": {
        "status": "pass",
        "issues": [],
        "evidence": ["覆盖 planned item 的知识点。"],
        "suggestions": [],
        "repair_instruction": "",
    },
    "difficulty_correctness": {
        "status": "pass",
        "issues": [],
        "evidence": ["难度与 coverage unit 一致。"],
        "suggestions": [],
        "repair_instruction": "",
    },
    "type_fitness": {
        "status": "pass",
        "issues": [],
        "evidence": ["题型服务 assessment intent。"],
        "suggestions": [],
        "repair_instruction": "",
    },
}


def question_reviews(*question_ids: str) -> list[dict[str, object]]:
    return [
        {
            "question_id": question_id,
            "dimension_reviews": DIMENSION_REVIEWS,
            "issues": [],
            "warnings": [],
            "suggestions": [],
        }
        for question_id in question_ids
    ]


class QuestionReviewContractTest(unittest.TestCase):
    def test_complete_dimension_reviews_pass(self) -> None:
        review = normalize_strict_question_review(
            {
                "valid": True,
                "issues": [],
                "warnings": [],
                "suggestions": [],
                "confidence": 0.9,
                "evidence": ["fixture"],
                "verdict": "ready",
                "dimension_reviews": DIMENSION_REVIEWS,
                "question_reviews": question_reviews("q-1"),
                "repair_plan": {"blocking": False},
            }
        )

        self.assertTrue(review.get("valid"))
        self.assertEqual(review.get("issues"), [])
        self.assertEqual(review.get("dimension_reviews", {}).get("type_fitness", {}).get("status"), "pass")

    def test_missing_dimension_reviews_warn(self) -> None:
        review = normalize_strict_question_review(
            {
                "valid": True,
                "issues": [],
                "warnings": [],
                "suggestions": [],
                "confidence": 0.9,
                "evidence": ["legacy fixture"],
                "verdict": "ready",
            }
        )

        self.assertTrue(review.get("valid"))
        self.assertTrue(any("dimension_reviews.description_completeness_missing" in warning for warning in review.get("warnings", [])))

    def test_missing_question_reviews_blocks_when_expected_ids_are_provided(self) -> None:
        review = normalize_strict_question_review(
            {
                "valid": True,
                "issues": [],
                "warnings": [],
                "suggestions": [],
                "confidence": 0.9,
                "evidence": ["fixture"],
                "verdict": "ready",
                "dimension_reviews": DIMENSION_REVIEWS,
                "repair_plan": {"blocking": False},
            },
            {"expected_question_ids": ["q-1"]},
        )

        self.assertFalse(review.get("valid"))
        self.assertIn("question_review.question_reviews_missing", review.get("issues", []))

    def test_question_reviews_must_cover_expected_question_ids(self) -> None:
        review = normalize_strict_question_review(
            {
                "valid": True,
                "issues": [],
                "warnings": [],
                "suggestions": [],
                "confidence": 0.9,
                "evidence": ["fixture"],
                "verdict": "ready",
                "dimension_reviews": DIMENSION_REVIEWS,
                "question_reviews": question_reviews("q-1"),
                "repair_plan": {"blocking": False},
            },
            {"expected_question_ids": ["q-1", "q-2"]},
        )

        self.assertFalse(review.get("valid"))
        self.assertIn("question_review.question_reviews.missing_ids:q-2", review.get("issues", []))

    def test_failed_dimension_blocks_review(self) -> None:
        dimensions = {key: dict(value) for key, value in DIMENSION_REVIEWS.items()}
        dimensions["type_fitness"] = {
            "status": "fail",
            "issues": ["true_false 只考术语真假，缺少边界反例。"],
            "evidence": ["coverage_units 缺 boundary_or_counterexample"],
            "suggestions": ["重写为边界判断题。"],
            "repair_instruction": "补充 boundary_or_counterexample unit。",
        }

        review = normalize_strict_question_review(
            {
                "valid": True,
                "issues": [],
                "warnings": [],
                "suggestions": [],
                "confidence": 0.9,
                "evidence": ["fixture"],
                "verdict": "ready",
                "dimension_reviews": dimensions,
                "question_reviews": question_reviews("q-1"),
                "repair_plan": {"blocking": False},
            }
        )

        self.assertFalse(review.get("valid"))
        self.assertEqual(review.get("verdict"), "needs-revision")
        self.assertTrue(any("type_fitness_failed" in issue for issue in review.get("issues", [])))
        self.assertTrue(review.get("repair_plan", {}).get("blocking"))

    def test_generated_question_normalizer_reports_rejected_questions(self) -> None:
        rejected: list[dict[str, object]] = []

        questions = normalize_generated_runtime_questions(
            {
                "questions": [
                    {"id": "bad", "category": "concept", "type": "single", "question": "只有一个选项", "options": ["A"], "answer": 0},
                    {
                        "id": "good",
                        "category": "concept",
                        "type": "single",
                        "question": "Python 赋值符号是什么？",
                        "options": ["=", "=="],
                        "answer": 0,
                        "explanation": "`=` 用于赋值。",
                        "capability_tags": ["python-assignment"],
                    },
                ]
            },
            "python",
            limit=2,
            default_question_source="agent-injected",
            default_source_status="agent-injected",
            rejected_questions=rejected,
        )

        self.assertEqual([item["id"] for item in questions], ["good"])
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["question_id"], "bad")
        self.assertIn("options", rejected[0]["fields"])
        self.assertEqual(rejected[0]["validator"], "runtime-question-normalizer")

    def test_merge_preserves_dimension_reviews_and_blocks_failures(self) -> None:
        dimensions = {key: dict(value) for key, value in DIMENSION_REVIEWS.items()}
        dimensions["difficulty_correctness"] = {**dimensions["difficulty_correctness"], "status": "fail"}
        strict = normalize_strict_question_review(
            {
                "valid": False,
                "issues": [],
                "warnings": [],
                "suggestions": [],
                "confidence": 0.8,
                "evidence": ["fixture"],
                "verdict": "needs-revision",
                "dimension_reviews": dimensions,
                "question_reviews": question_reviews("q-1"),
                "repair_plan": {"blocking": True},
            }
        )
        deterministic = {"reviewer": "deterministic", "valid": True, "issues": [], "warnings": [], "confidence": 1.0, "repair_plan": {}}

        merged = merge_question_review_results(deterministic, strict)

        self.assertFalse(merged.get("valid"))
        self.assertEqual(merged.get("verdict"), "needs-revision")
        self.assertTrue(merged.get("dimension_reviews", {}).get("difficulty_correctness"))

    def test_strict_review_failure_message_exposes_external_repair_status(self) -> None:
        message = strict_review_failure_message(
            "question generation",
            {
                "valid": False,
                "issues": ["question_review.question_reviews_missing"],
                "repair_plan": {
                    "blocking": True,
                    "failure_codes": ["question_review.question_reviews_missing"],
                    "repair_actions": [{"action": "补齐逐题 question_reviews", "reason": "缺少逐题审查"}],
                },
            },
        )

        self.assertIn("review_loop_status=needs_external_repair", message)
        self.assertIn("question_review.question_reviews_missing", message)
        self.assertIn("补齐逐题 question_reviews", message)


if __name__ == "__main__":
    unittest.main()
