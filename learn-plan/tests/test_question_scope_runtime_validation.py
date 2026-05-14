from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.question_validation import validate_questions_payload


class QuestionScopeRuntimeValidationTest(unittest.TestCase):
    def _scope(self) -> dict[str, object]:
        return {
            "schema_version": "learn-plan.question_scope.v1",
            "scope_id": "scope-stage",
            "source_profile": "history-stage-test",
            "session_type": "test",
            "session_intent": "assessment",
            "assessment_kind": "stage-test",
            "test_mode": "general",
            "topic": "Python 基础",
            "language_policy": {"user_facing_language": "zh-CN"},
            "scope_basis": [{"kind": "progress", "summary": "history progress learner_model"}],
            "target_capability_ids": ["python-assignment"],
            "target_concepts": [],
            "target_knowledge_point_ids": ["kp-assignment"],
            "diagnostic_strategy": {"selection_strategy": "history_review", "early_stop_allowed": False},
            "review_targets": ["赋值与比较"],
            "lesson_focus_points": [],
            "project_tasks": [],
            "project_blockers": [],
            "source_material_refs": [],
            "difficulty_target": {},
            "minimum_pass_shape": {"required_open_question_count": 0},
            "exclusions": [],
            "evidence": ["progress.json"],
            "generation_trace": {"status": "ok"},
        }

    def _plan(self) -> dict[str, object]:
        return {
            "schema_version": "learn-plan.question_plan.v1",
            "plan_id": "plan-stage",
            "scope_id": "scope-stage",
            "source_profile": "history-stage-test",
            "session_type": "test",
            "session_intent": "assessment",
            "assessment_kind": "stage-test",
            "test_mode": "general",
            "topic": "Python 基础",
            "question_count": 1,
            "question_mix": {"single_choice": 1},
            "difficulty_distribution": {"basic": 1},
            "diagnostic_value": {},
            "early_stop_policy": {},
            "planned_items": [],
            "coverage_matrix": [],
            "minimum_pass_shape": {"required_open_question_count": 0},
            "forbidden_question_types": ["open", "written", "short_answer", "free_text"],
            "generation_guidance": [],
            "review_checklist": [],
            "evidence": ["scope-stage"],
            "generation_trace": {"status": "ok"},
        }

    def _question(self) -> dict[str, object]:
        return {
            "id": "q1",
            "category": "concept",
            "type": "single_choice",
            "title": "Python 赋值符号判断",
            "prompt": "下面哪一个符号用于 **变量赋值**？\n\n- 请选择一个最准确的答案。",
            "question": "下面哪一个符号用于 **变量赋值**？\n\n- 请选择一个最准确的答案。",
            "options": ["=", "==", "!=", ":="],
            "answer": 0,
            "option_diagnostics": [
                {
                    "index": 0,
                    "claim": "`=` 是 Python 的赋值符号。",
                    "diagnostic_role": "correct_concept",
                    "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.9}],
                    "prerequisite_ids": [],
                    "misconception_ids": [],
                    "evidence_span": "选项 `=` 对应变量赋值语法。",
                    "diagnostic_question": "你如何判断这里需要赋值而不是比较？",
                },
                {
                    "index": 1,
                    "claim": "`==` 用于相等比较，不用于赋值。",
                    "diagnostic_role": "distractor",
                    "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.9}],
                    "prerequisite_ids": [],
                    "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
                    "evidence_span": "选项 `==` 是常见干扰项。",
                    "diagnostic_question": "`=` 和 `==` 分别出现在什么语境中？",
                },
                {
                    "index": 2,
                    "claim": "`!=` 用于不相等比较，不用于赋值。",
                    "diagnostic_role": "distractor",
                    "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.85}],
                    "prerequisite_ids": [],
                    "misconception_ids": [{"id": "mc-assignment-vs-comparison", "confidence": 0.7}],
                    "evidence_span": "选项 `!=` 检查是否混淆比较运算。",
                    "diagnostic_question": "`!=` 的返回值是什么类型？",
                },
                {
                    "index": 3,
                    "claim": "`:=` 是赋值表达式，不是普通变量赋值语句的基本符号。",
                    "diagnostic_role": "edge_case",
                    "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.8}],
                    "prerequisite_ids": [],
                    "misconception_ids": [{"id": "mc-assignment-expression", "confidence": 0.6}],
                    "evidence_span": "选项 `:=` 检查是否把赋值表达式和普通赋值混为一谈。",
                    "diagnostic_question": "`:=` 和普通 `=` 有什么区别？",
                },
            ],
            "explanation": "`=` 用于赋值，`==` 用于比较相等。",
            "scoring_rubric": ["识别赋值符号", "区分赋值与比较"],
            "capability_tags": ["python-assignment"],
            "source_trace": {"question_source": "agent-injected", "target_capability_ids": ["python-assignment"]},
            "difficulty_level": "basic",
            "difficulty_label": "基础题",
            "difficulty_score": 1,
            "difficulty_reason": "只要求识别赋值符号。",
            "expected_failure_mode": "把赋值和相等比较混淆。",
            "planned_item_id": "plan-q1",
            "assessment_intent": "检查学习者能否区分普通赋值、比较运算和赋值表达式。",
            "knowledge_scope": {
                "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.9}],
                "prerequisite_ids": [],
                "misconception_ids": [
                    {"id": "mc-assignment-vs-equality", "confidence": 0.8},
                    {"id": "mc-assignment-expression", "confidence": 0.6},
                ],
                "source_trace": {"question_source": "agent-injected"},
            },
            "question_type_rationale": {
                "type": "single_choice",
                "reason": "单选题适合在相似符号中识别唯一基础概念。",
                "assessment_fit": "干扰项分别暴露比较符号和赋值表达式混淆。",
            },
            "coverage_units": [
                {
                    "unit_type": "option",
                    "option_index": 0,
                    "claim": "`=` 是普通变量赋值语句的符号。",
                    "diagnostic_role": "correct_concept",
                    "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.9}],
                    "difficulty_level": "basic",
                    "diagnostic_value": "验证正向概念识别。",
                },
                {
                    "unit_type": "option",
                    "option_index": 1,
                    "claim": "`==` 是相等比较符号。",
                    "diagnostic_role": "distractor",
                    "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.9}],
                    "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
                    "difficulty_level": "basic",
                    "distractor_rationale": "常见误区是把赋值符号和相等比较符号混淆。",
                    "diagnostic_value": "错选可触发赋值/比较区分追问。",
                },
                {
                    "unit_type": "option",
                    "option_index": 2,
                    "claim": "`!=` 是不相等比较符号。",
                    "diagnostic_role": "distractor",
                    "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.85}],
                    "misconception_ids": [{"id": "mc-assignment-vs-comparison", "confidence": 0.7}],
                    "difficulty_level": "basic",
                    "distractor_rationale": "常见误区是只看到比较运算符就把它当成赋值候选。",
                    "diagnostic_value": "错选可暴露比较运算符族混淆。",
                },
                {
                    "unit_type": "option",
                    "option_index": 3,
                    "claim": "`:=` 是赋值表达式符号。",
                    "diagnostic_role": "edge_case",
                    "knowledge_point_ids": [{"id": "kp-assignment", "relevance": "primary", "confidence": 0.8}],
                    "misconception_ids": [{"id": "mc-assignment-expression", "confidence": 0.6}],
                    "difficulty_level": "basic",
                    "diagnostic_value": "检查是否混淆赋值表达式和普通赋值语句。",
                },
            ],
            "difficulty_profile": {
                "target_difficulty_level": "basic",
                "difficulty_level": "basic",
                "difficulty_reason": "只要求识别赋值符号。",
                "expected_failure_mode": "把赋值和相等比较混淆。",
                "coverage_units": [
                    {"option_index": 0, "difficulty_level": "basic"},
                    {"option_index": 1, "difficulty_level": "basic"},
                    {"option_index": 2, "difficulty_level": "basic"},
                    {"option_index": 3, "difficulty_level": "basic"},
                ],
            },
        }

    def _payload(self) -> dict[str, object]:
        scope = self._scope()
        plan = self._plan()
        return {
            "date": "2026-04-29",
            "topic": "Python 基础",
            "mode": "test-general",
            "session_type": "test",
            "session_intent": "assessment",
            "assessment_kind": "stage-test",
            "test_mode": "general",
            "language_policy": {"user_facing_language": "zh-CN"},
            "plan_source": {
                "language_policy": {"user_facing_language": "zh-CN"},
                "question_scope": scope,
                "question_plan": plan,
                "lesson_grounding_context": {
                    "semantic_profile": "stage-test",
                    "session_intent": "assessment",
                    "assessment_kind": "stage-test",
                    "target_capability_ids": ["python-assignment"],
                    "question_scope": scope,
                    "question_plan": plan,
                    "minimum_pass_shape": {},
                },
                "question_generation_mode": "harness-injected",
                "strict_question_review": {"valid": True, "verdict": "ready", "issues": []},
                "deterministic_question_review": {"valid": True, "verdict": "ready", "issues": []},
            },
            "selection_context": {
                "language_policy": {"user_facing_language": "zh-CN"},
                "question_scope": scope,
                "question_plan": plan,
                "daily_lesson_plan": {
                    "semantic_profile": "stage-test",
                    "session_intent": "assessment",
                    "assessment_kind": "stage-test",
                    "target_capability_ids": ["python-assignment"],
                    "question_scope": scope,
                    "question_plan": plan,
                },
            },
            "materials": [],
            "questions": [self._question()],
        }

    def test_scope_plan_aligned_payload_passes(self) -> None:
        result = validate_questions_payload(self._payload())

        self.assertTrue(result.get("valid"), result.get("issues"))

    def test_scope_session_mismatch_fails(self) -> None:
        payload = self._payload()
        payload["plan_source"]["question_scope"]["session_type"] = "today"

        result = validate_questions_payload(payload)

        self.assertIn("question_scope.session_type_mismatch", result.get("issues", []))

    def test_question_mix_mismatch_fails(self) -> None:
        payload = self._payload()
        payload["plan_source"]["question_plan"]["question_mix"] = {"code": 1}
        payload["selection_context"]["question_plan"] = payload["plan_source"]["question_plan"]

        result = validate_questions_payload(payload)

        self.assertTrue(any("question_plan.question_mix_mismatch:code" in issue for issue in result.get("issues", [])))

    def test_difficulty_distribution_mismatch_fails(self) -> None:
        payload = self._payload()
        payload["plan_source"]["question_plan"]["difficulty_distribution"] = {"medium": 1}
        payload["selection_context"]["question_plan"] = payload["plan_source"]["question_plan"]

        result = validate_questions_payload(payload)

        self.assertIn("question_plan.difficulty_distribution_mismatch:medium:0/1", result.get("issues", []))

    def test_target_capability_uncovered_fails(self) -> None:
        payload = self._payload()
        payload["questions"][0]["capability_tags"] = ["other-capability"]
        payload["questions"][0]["source_trace"] = {"question_source": "agent-injected", "target_capability_ids": ["other-capability"]}

        result = validate_questions_payload(payload)

        self.assertIn("question_scope.target_capability_ids_uncovered:python-assignment", result.get("issues", []))

    def test_test_coverage_slice_requires_knowledge_bindings(self) -> None:
        payload = self._payload()
        payload["selection_context"]["test_coverage_slice"] = {"selected_points": ["kp-assignment"]}

        result = validate_questions_payload(payload)

        issues = "\n".join(result.get("issues", []))
        self.assertIn("q1: test 题缺少 knowledge_point_ids", issues)
        self.assertIn("q1: test 题缺少 evidence_types", issues)
        self.assertIn("q1: test 题缺少 rubric_by_knowledge_point", issues)

        payload["questions"][0]["knowledge_point_ids"] = ["kp-assignment"]
        payload["questions"][0]["evidence_types"] = ["explanation"]
        payload["questions"][0]["rubric_by_knowledge_point"] = {"kp-assignment": ["能区分赋值与比较"]}
        fixed = validate_questions_payload(payload)

        self.assertTrue(fixed.get("valid"), fixed.get("issues"))

    def test_planned_item_target_difficulty_underestimated_fails(self) -> None:
        payload = self._payload()
        plan = payload["plan_source"]["question_plan"]
        plan["planned_items"] = [
            {
                "item_id": "p1",
                "target_difficulty_level": "basic",
                "knowledge_point_ids": ["kp-assignment", "kp-comparison"],
                "combination_requirement": "combine",
            }
        ]
        payload["selection_context"]["question_plan"] = plan

        result = validate_questions_payload(payload)

        self.assertTrue(any("target_difficulty_underestimated:basic/medium" in issue for issue in result.get("issues", [])))

    def test_question_above_planned_target_requests_rewrite(self) -> None:
        payload = self._payload()
        plan = payload["plan_source"]["question_plan"]
        plan["planned_items"] = [{"question_id": "q1", "target_difficulty_level": "basic"}]
        payload["selection_context"]["question_plan"] = plan
        payload["questions"][0]["difficulty_level"] = "medium"
        payload["questions"][0]["difficulty"] = "medium"
        payload["questions"][0]["difficulty_label"] = "中等题"
        payload["questions"][0]["difficulty_score"] = 2
        payload["questions"][0]["difficulty_dimensions"] = {"knowledge_point_count": 2, "reasoning_steps": 2}
        plan["difficulty_distribution"] = {"medium": 1}

        result = validate_questions_payload(payload)

        self.assertTrue(any("rewrite question" in issue for issue in result.get("issues", [])))

    def test_question_target_uses_planned_item_position_when_ids_differ(self) -> None:
        payload = self._payload()
        plan = payload["plan_source"]["question_plan"]
        plan["planned_items"] = [{"item_id": "plan-item-1", "target_difficulty_level": "basic"}]
        payload["selection_context"]["question_plan"] = plan
        payload["questions"][0]["difficulty_level"] = "medium"
        payload["questions"][0]["difficulty"] = "medium"
        payload["questions"][0]["difficulty_label"] = "中等题"
        payload["questions"][0]["difficulty_score"] = 2
        payload["questions"][0]["difficulty_dimensions"] = {"knowledge_point_count": 2, "reasoning_steps": 2}
        plan["difficulty_distribution"] = {"medium": 1}

        result = validate_questions_payload(payload)

        self.assertTrue(any("高于计划目标 basic" in issue for issue in result.get("issues", [])))


if __name__ == "__main__":
    unittest.main()
