from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.payload_builder import ensure_question_shape
from learn_runtime.question_validation import validate_questions_payload
from learn_runtime.schemas import validate_progress_basic, validate_questions_basic
from session_bootstrap import progress_shape_is_valid as bootstrap_progress_shape_is_valid
from session_bootstrap import validate_questions_data
from session_orchestrator import progress_shape_is_valid as orchestrator_progress_shape_is_valid


class RuntimeSchemaTest(unittest.TestCase):
    def _questions_payload(self) -> dict[str, object]:
        return {
            "date": "2026-04-24",
            "topic": "Python 基础",
            "mode": "today",
            "session_type": "today",
            "session_intent": "learning",
            "assessment_kind": None,
            "test_mode": None,
            "language_policy": {"user_facing_language": "zh-CN"},
            "plan_source": {"language_policy": {"user_facing_language": "zh-CN"}},
            "materials": [],
            "questions": [
                {
                    "id": "q1",
                    "category": "concept",
                    "type": "single",
                    "question": "Python 中哪个符号用于赋值？",
                    "options": ["=", "=="],
                    "answer": 0,
                    "explanation": "= 用于赋值。",
                    "scoring_rubric": [{"metric": "概念理解", "threshold": "识别赋值符号"}],
                    "capability_tags": ["python-assignment"],
                    "source_trace": {"question_source": "agent-injected"},
                    "difficulty_level": "basic",
                    "difficulty_label": "基础题",
                    "difficulty_score": 1,
                    "difficulty_reason": "只考察赋值符号识别。",
                    "expected_failure_mode": "混淆赋值和相等比较。",
                }
            ],
        }

    def test_questions_schema_is_shared_by_runtime_entries(self) -> None:
        payload = self._questions_payload()

        self.assertEqual(validate_questions_basic(payload), [])
        ensure_question_shape(payload)
        validate_questions_data(payload)
        result = validate_questions_payload(payload)
        self.assertNotIn("questions.json 缺少字段", "\n".join(result.get("issues", [])))

    def test_missing_required_question_fields_fail_consistently(self) -> None:
        for field in ("language_policy", "session_intent", "assessment_kind"):
            payload = self._questions_payload()
            payload.pop(field, None)

            self.assertTrue(validate_questions_basic(payload))
            with self.assertRaises(ValueError):
                ensure_question_shape(payload)
            with self.assertRaises(ValueError):
                validate_questions_data(payload)
            result = validate_questions_payload(payload)
            self.assertTrue(result.get("issues"))

    def test_progress_template_passes_shared_progress_schema(self) -> None:
        template_path = SKILL_DIR / "templates" / "progress_template.json"
        progress = json.loads(template_path.read_text(encoding="utf-8"))

        self.assertEqual(validate_progress_basic(progress), [])
        self.assertTrue(bootstrap_progress_shape_is_valid(progress))
        self.assertTrue(orchestrator_progress_shape_is_valid(progress))


if __name__ == "__main__":
    unittest.main()
