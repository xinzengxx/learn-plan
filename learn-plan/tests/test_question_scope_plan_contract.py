from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.schemas import validate_question_plan_basic, validate_question_scope_basic


class QuestionScopePlanContractTest(unittest.TestCase):
    def _scope(self, source_profile: str = "today-lesson") -> dict[str, object]:
        assessment_kind = None if source_profile == "today-lesson" else "initial-test" if source_profile == "initial-diagnostic" else "stage-test"
        return {
            "schema_version": "learn-plan.question_scope.v1",
            "scope_id": f"scope-{source_profile}",
            "source_profile": source_profile,
            "session_type": "today" if source_profile == "today-lesson" else "test",
            "session_intent": "learning" if source_profile == "today-lesson" else "assessment",
            "assessment_kind": assessment_kind,
            "test_mode": None if source_profile == "today-lesson" else "general",
            "topic": "Python 基础",
            "language_policy": {"user_facing_language": "zh-CN"},
            "scope_basis": [{"kind": "learn-plan", "summary": "history progress learner_model"}],
            "target_capability_ids": ["python-basics"],
            "target_concepts": ["变量赋值"],
            "target_knowledge_point_ids": ["akp-python-assignment"],
            "diagnostic_strategy": {
                "selection_strategy": "information_gain_hub_prerequisite_first" if source_profile == "initial-diagnostic" else "lesson_aligned",
                "early_stop_allowed": source_profile == "initial-diagnostic",
            },
            "review_targets": ["变量与比较运算"],
            "lesson_focus_points": ["变量赋值"],
            "project_tasks": [],
            "project_blockers": [],
            "source_material_refs": [],
            "difficulty_target": {},
            "minimum_pass_shape": {"required_open_question_count": 0},
            "exclusions": [],
            "evidence": ["fixture"],
            "generation_trace": {"status": "ok"},
        }

    def _plan(self, source_profile: str = "today-lesson") -> dict[str, object]:
        assessment_kind = None if source_profile == "today-lesson" else "initial-test" if source_profile == "initial-diagnostic" else "stage-test"
        return {
            "schema_version": "learn-plan.question_plan.v1",
            "plan_id": f"plan-{source_profile}",
            "scope_id": f"scope-{source_profile}",
            "source_profile": source_profile,
            "session_type": "today" if source_profile == "today-lesson" else "test",
            "session_intent": "learning" if source_profile == "today-lesson" else "assessment",
            "assessment_kind": assessment_kind,
            "test_mode": None if source_profile == "today-lesson" else "general",
            "topic": "Python 基础",
            "question_count": 2,
            "question_mix": {"single_choice": 1, "true_false": 1},
            "difficulty_distribution": {"basic": 1, "medium": 1},
            "diagnostic_value": {
                "target_knowledge_point_ids": ["akp-python-assignment"],
                "prerequisite_probe_chain": ["akp-python-name-binding"],
                "expected_information_gain": ["确认变量赋值与比较混淆是否影响后续语法路线"],
            } if source_profile == "initial-diagnostic" else {},
            "early_stop_policy": {
                "enabled": True,
                "stop_when": ["推荐起点稳定", "主要薄弱链稳定", "继续出题边际收益低"],
            } if source_profile == "initial-diagnostic" else {},
            "planned_items": [],
            "coverage_matrix": [],
            "minimum_pass_shape": {"required_open_question_count": 0},
            "forbidden_question_types": ["open", "written", "short_answer", "free_text"],
            "generation_guidance": [],
            "review_checklist": [],
            "evidence": ["fixture"],
            "generation_trace": {"status": "ok"},
        }

    def test_valid_scope_profiles_pass(self) -> None:
        for profile in ("today-lesson", "initial-diagnostic", "history-stage-test"):
            with self.subTest(profile=profile):
                self.assertEqual(validate_question_scope_basic(self._scope(profile)), [])

    def test_valid_question_plan_passes(self) -> None:
        self.assertEqual(validate_question_plan_basic(self._plan("initial-diagnostic")), [])

    def test_unknown_source_profile_fails(self) -> None:
        scope = self._scope()
        scope["source_profile"] = "unknown"

        self.assertIn("question_scope.source_profile_invalid", validate_question_scope_basic(scope))

    def test_test_scope_requires_capabilities(self) -> None:
        scope = self._scope("initial-diagnostic")
        scope["target_capability_ids"] = []

        self.assertIn("question_scope.initial.target_capability_ids_missing", validate_question_scope_basic(scope))

    def test_initial_scope_requires_atomic_point_strategy(self) -> None:
        scope = self._scope("initial-diagnostic")
        scope["target_knowledge_point_ids"] = []
        scope.pop("diagnostic_strategy")

        issues = validate_question_scope_basic(scope)
        self.assertIn("question_scope.initial.target_knowledge_point_ids_missing", issues)
        self.assertIn("question_scope.initial.diagnostic_strategy_missing", issues)

    def test_open_question_count_is_forbidden(self) -> None:
        plan = self._plan()
        plan["minimum_pass_shape"] = {"required_open_question_count": 1}

        self.assertIn("question_plan.minimum_pass_shape.open_not_allowed_by_test_grade", validate_question_plan_basic(plan))

    def test_initial_plan_requires_diagnostic_value_and_early_stop(self) -> None:
        plan = self._plan("initial-diagnostic")
        plan["diagnostic_value"] = {}
        plan["early_stop_policy"] = {}

        issues = validate_question_plan_basic(plan)
        self.assertIn("question_plan.initial.diagnostic_value_missing", issues)
        self.assertIn("question_plan.initial.early_stop_policy_missing", issues)

    def test_forbidden_question_type_in_mix_fails(self) -> None:
        plan = self._plan()
        plan["question_mix"] = {"single_choice": 1, "open": 1}

        self.assertIn("question_plan.question_mix.forbidden_type", validate_question_plan_basic(plan))

    def test_question_count_and_mix_mismatch_fails(self) -> None:
        plan = self._plan()
        plan["question_count"] = 3

        self.assertIn("question_plan.question_mix.count_mismatch", validate_question_plan_basic(plan))

    def test_planned_item_difficulty_dimension_shape_is_validated(self) -> None:
        plan = self._plan()
        plan["planned_items"] = [
            {
                "item_id": "p1",
                "target_difficulty_level": "basic",
                "difficulty_dimensions": {"knowledge_point_count": "many"},
            }
        ]

        self.assertIn("question_plan.planned_items.0.difficulty_dimensions.knowledge_point_count_invalid", validate_question_plan_basic(plan))

    def test_planned_item_target_difficulty_level_is_validated(self) -> None:
        plan = self._plan()
        plan["planned_items"] = [{"item_id": "p1", "target_difficulty_level": "impossible"}]

        self.assertIn("question_plan.planned_items.0.target_difficulty_level_invalid", validate_question_plan_basic(plan))

    def test_planned_item_target_difficulty_underestimation_is_validated(self) -> None:
        plan = self._plan()
        plan["planned_items"] = [
            {
                "item_id": "p1",
                "target_difficulty_level": "basic",
                "knowledge_point_ids": ["kp-assignment", "kp-comparison"],
                "combination_requirement": "combine",
            }
        ]

        self.assertIn("question_plan.planned_items.0.target_difficulty_underestimated:basic/medium", validate_question_plan_basic(plan))


if __name__ == "__main__":
    unittest.main()
