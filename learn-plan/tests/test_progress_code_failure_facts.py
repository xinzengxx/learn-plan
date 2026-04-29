from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_feedback.progress_summary import build_session_facts
from learn_core.io import read_json
from learn_test_update import summarize_test_progress, write_feedback_artifacts


class ProgressCodeFailureFactsTest(unittest.TestCase):
    def _progress(self) -> dict[str, object]:
        return {
            "topic": "Python 基础",
            "date": "2026-04-25",
            "session": {"type": "test", "status": "completed", "test_mode": "stage"},
            "summary": {"total": 1, "attempted": 1, "correct": 0},
            "difficulty_summary": {
                "by_level": {
                    "basic": {"total": 0, "attempted": 0, "correct": 0},
                    "medium": {"total": 1, "attempted": 1, "correct": 0},
                    "upper_medium": {"total": 0, "attempted": 0, "correct": 0},
                    "hard": {"total": 0, "attempted": 0, "correct": 0},
                },
                "by_category": {
                    "code": {
                        "basic": {"total": 0, "attempted": 0, "correct": 0},
                        "medium": {"total": 1, "attempted": 1, "correct": 0},
                        "upper_medium": {"total": 0, "attempted": 0, "correct": 0},
                        "hard": {"total": 0, "attempted": 0, "correct": 0},
                    }
                },
            },
            "questions": {
                "code-two-sum": {
                    "difficulty_level": "medium",
                    "difficulty_label": "中等题",
                    "difficulty_score": 2,
                    "stats": {
                        "attempts": 1,
                        "pass_count": 0,
                        "last_status": "failed",
                        "last_submit_result": {
                            "question_id": "code-two-sum",
                            "question_type": "code",
                            "status": "failed",
                            "passed_public_count": 1,
                            "total_public_count": 1,
                            "passed_hidden_count": 0,
                            "total_hidden_count": 2,
                            "failed_case_summaries": [
                                {
                                    "category": "hidden",
                                    "input": {"nums": [3, 2, 4], "target": 6},
                                    "expected": [1, 2],
                                    "actual_repr": "None",
                                    "error": "wrong_answer",
                                    "capability_tags": ["array", "hash-map"],
                                }
                            ],
                            "failure_types": ["wrong_answer"],
                            "capability_tags": ["array", "hash-map"],
                            "submitted_at": "2026-04-25T03:00:00Z",
                        },
                    }
                }
            },
        }

    def test_session_facts_preserve_code_failure_signals(self) -> None:
        progress = self._progress()
        summary = {
            "topic": "Python 基础",
            "date": "2026-04-25",
            "session_type": "test",
            "test_mode": "stage",
            "total": 1,
            "attempted": 1,
            "correct": 0,
            "wrong_items": [
                {
                    "id": "code-two-sum",
                    "title": "两数之和",
                    "category": "code",
                    "tags": ["array"],
                    "capability_tags": ["array", "hash-map"],
                    "submit_result": progress["questions"]["code-two-sum"]["stats"]["last_submit_result"],
                }
            ],
            "solved_items": [],
            "weaknesses": ["边界用例处理"],
            "mastery": {},
        }

        facts = build_session_facts(progress, summary, session_dir=Path("/tmp/session"), update_type="test")

        code_failures = facts.get("code_failure_facts")
        self.assertEqual(len(code_failures), 1)
        failure = code_failures[0]
        self.assertEqual(failure["question_id"], "code-two-sum")
        self.assertEqual(failure["title"], "两数之和")
        self.assertEqual(failure["passed_public_count"], 1)
        self.assertEqual(failure["total_public_count"], 1)
        self.assertEqual(failure["passed_hidden_count"], 0)
        self.assertEqual(failure["total_hidden_count"], 2)
        self.assertEqual(failure["failure_types"], ["wrong_answer"])
        self.assertEqual(failure["capability_tags"], ["array", "hash-map"])
        self.assertEqual(failure["failed_case_summaries"][0]["category"], "hidden")
        self.assertEqual(failure["failed_case_summaries"][0]["error"], "wrong_answer")
        self.assertIn("expected", failure["failed_case_summaries"][0])
        self.assertIn("actual_repr", failure["failed_case_summaries"][0])
        self.assertTrue(any("hidden" in item and "wrong_answer" in item for item in facts.get("evidence", [])))

    def test_session_facts_include_difficulty_performance_facts(self) -> None:
        progress = self._progress()
        summary = {
            "topic": "Python 基础",
            "date": "2026-04-25",
            "session_type": "test",
            "test_mode": "stage",
            "total": 1,
            "attempted": 1,
            "correct": 0,
            "wrong_items": [],
            "solved_items": [],
            "mastery": {},
        }

        facts = build_session_facts(progress, summary, session_dir=Path("/tmp/session"), update_type="test")

        difficulty_facts = facts.get("difficulty_performance_facts")
        self.assertTrue(any(item.get("scope") == "level" and item.get("level") == "medium" and item.get("attempted") == 1 for item in difficulty_facts))
        self.assertTrue(any("难度表现：medium" in item for item in facts.get("evidence", [])))

    def test_test_progress_summary_preserves_submit_result_for_update_facts(self) -> None:
        progress = self._progress()
        questions_data = {
            "questions": [
                {
                    "id": "code-two-sum",
                    "type": "code",
                    "category": "code",
                    "title": "两数之和",
                    "tags": ["array"],
                    "capability_tags": ["array", "hash-map"],
                }
            ]
        }

        summary = summarize_test_progress(progress, questions_data, semantic_review=None)

        wrong_item = summary["wrong_items"][0]
        self.assertEqual(wrong_item["id"], "code-two-sum")
        self.assertEqual(wrong_item["capability_tags"], ["array", "hash-map"])
        submit_result = wrong_item.get("submit_result")
        self.assertIsInstance(submit_result, dict)
        self.assertEqual(submit_result["passed_hidden_count"], 0)
        self.assertEqual(submit_result["total_hidden_count"], 2)
        self.assertEqual(submit_result["failure_types"], ["wrong_answer"])

    def test_write_feedback_artifacts_persists_session_facts(self) -> None:
        progress = self._progress()
        summary = summarize_test_progress(
            progress,
            {
                "questions": [
                    {
                        "id": "code-two-sum",
                        "type": "code",
                        "category": "code",
                        "title": "两数之和",
                        "capability_tags": ["array", "hash-map"],
                    }
                ]
            },
            semantic_review=None,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# plan\n", encoding="utf-8")
            write_feedback_artifacts(plan_path, summary, progress, root / "session")
            persisted = read_json(root / ".learn-workflow" / "session_facts.json")

        code_failures = persisted.get("code_failure_facts")
        self.assertEqual(len(code_failures), 1)
        self.assertEqual(code_failures[0]["question_id"], "code-two-sum")
        self.assertEqual(code_failures[0]["failed_case_summaries"][0]["category"], "hidden")


if __name__ == "__main__":
    unittest.main()
