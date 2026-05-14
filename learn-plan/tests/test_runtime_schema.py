from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.payload_builder import ensure_question_shape
from learn_runtime.question_validation import validate_questions_payload
from learn_runtime.schemas import (
    validate_dataset_artifact_basic,
    validate_parameter_artifact_basic,
    validate_parameter_spec_basic,
    validate_progress_basic,
    validate_question_plan_basic,
    validate_question_scope_basic,
    validate_questions_basic,
)
from session_bootstrap import normalize_progress_data
from session_bootstrap import progress_shape_is_valid as bootstrap_progress_shape_is_valid
from session_bootstrap import validate_questions_data
from session_orchestrator import progress_shape_is_valid as orchestrator_progress_shape_is_valid


class RuntimeSchemaTest(unittest.TestCase):
    def _today_question_scope(self) -> dict[str, object]:
        return {
            "schema_version": "learn-plan.question_scope.v1",
            "scope_id": "scope-today",
            "source_profile": "today-lesson",
            "session_type": "today",
            "session_intent": "learning",
            "assessment_kind": None,
            "test_mode": None,
            "topic": "Python 基础",
            "language_policy": {"user_facing_language": "zh-CN"},
            "scope_basis": [{"kind": "lesson", "summary": "变量赋值"}],
            "target_capability_ids": ["python-assignment"],
            "target_concepts": ["变量赋值"],
            "target_knowledge_point_ids": ["kp-python-assignment"],
            "diagnostic_strategy": {"selection_strategy": "lesson_aligned", "early_stop_allowed": False},
            "review_targets": [],
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

    def _today_question_plan(self) -> dict[str, object]:
        return {
            "schema_version": "learn-plan.question_plan.v1",
            "plan_id": "plan-today",
            "scope_id": "scope-today",
            "source_profile": "today-lesson",
            "session_type": "today",
            "session_intent": "learning",
            "assessment_kind": None,
            "test_mode": None,
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
            "evidence": ["scope-today"],
            "generation_trace": {"status": "ok"},
        }

    def _questions_payload(self) -> dict[str, object]:
        scope = self._today_question_scope()
        plan = self._today_question_plan()
        return {
            "date": "2026-04-24",
            "topic": "Python 基础",
            "mode": "today",
            "session_type": "today",
            "session_intent": "learning",
            "assessment_kind": None,
            "test_mode": None,
            "language_policy": {"user_facing_language": "zh-CN"},
            "plan_source": {
                "language_policy": {"user_facing_language": "zh-CN"},
                "question_scope": scope,
                "question_plan": plan,
                "lesson_grounding_context": {"semantic_profile": "today", "question_scope": scope, "question_plan": plan},
                "question_generation_mode": "agent-injected",
                "strict_question_review": {"valid": True, "verdict": "ready", "issues": []},
                "deterministic_question_review": {"valid": True, "verdict": "ready", "issues": []},
            },
            "selection_context": {
                "language_policy": {"user_facing_language": "zh-CN"},
                "question_scope": scope,
                "question_plan": plan,
                "daily_lesson_plan": {"semantic_profile": "today", "question_scope": scope, "question_plan": plan},
            },
            "materials": [],
            "questions": [
                {
                    "id": "q1",
                    "category": "concept",
                    "type": "single_choice",
                    "question": "Python 中哪个符号用于 **变量赋值**？\n\n- 请选择一个最准确的答案。",
                    "options": ["=", "=="],
                    "answer": 0,
                    "option_diagnostics": [
                        {
                            "index": 0,
                            "claim": "`=` 是 Python 的赋值符号。",
                            "diagnostic_role": "correct_concept",
                            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
                            "prerequisite_ids": [],
                            "misconception_ids": [],
                            "evidence_span": "选项 `=` 对应变量赋值语法。",
                            "diagnostic_question": "你如何区分赋值符号和比较符号？",
                        },
                        {
                            "index": 1,
                            "claim": "`==` 是 Python 的相等比较符号。",
                            "diagnostic_role": "distractor",
                            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
                            "prerequisite_ids": [],
                            "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
                            "evidence_span": "选项 `==` 容易暴露赋值与相等比较混淆。",
                            "diagnostic_question": "什么时候应该使用 `==` 而不是 `=`？",
                        },
                    ],
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

    def test_sql_question_with_runtime_context_passes_payload_validation(self) -> None:
        payload = self._questions_payload()
        scope = payload["plan_source"]["question_scope"]
        plan = payload["plan_source"]["question_plan"]
        plan["question_mix"] = {"sql": 1}
        payload["questions"] = [
            {
                "id": "sql-1",
                "category": "code",
                "type": "sql",
                "title": "筛选订单",
                "problem_statement": "请基于 `orders` 表，**筛选** 金额大于 100 的订单。\n\n- 只返回订单编号。",
                "input_spec": "输入是一张 MySQL 表 `orders`，包含 `order_id` 与 `amount` 两列。",
                "output_spec": "输出查询结果包含一列 `order_id`，按订单编号升序排列。",
                "constraints": ["只能写单条 SELECT 或 WITH 查询。", "不能修改数据库中的任何表。"],
                "examples": [{"input": "orders public sample", "output": "order_id=2", "explanation": "金额 120 大于 100。"}],
                "scoring_rubric": [{"metric": "SQL 正确性", "threshold": "筛选条件和列选择正确"}],
                "capability_tags": ["mysql-select"],
                "supported_runtimes": ["mysql"],
                "default_runtime": "mysql",
                "starter_sql": "SELECT order_id FROM orders WHERE amount > 100 ORDER BY order_id;",
                "parameter_spec_ref": "sql-1",
                "dataset_refs": ["orders-public", "orders-hidden"],
                "result_contract": {"columns": ["order_id"], "order_sensitive": True},
                "source_trace": {"question_source": "agent-injected"},
                "difficulty_level": "basic",
                "difficulty_label": "基础题",
                "difficulty_score": 1,
                "difficulty_reason": "只考察 SELECT + WHERE。",
                "expected_failure_mode": "漏写过滤条件或列名。",
                "planned_item_id": "plan-sql-1",
                "assessment_intent": "检查学习者能否用 SELECT + WHERE 筛选表并返回指定列。",
                "knowledge_scope": {
                    "knowledge_point_ids": [{"id": "kp-mysql-select-where", "relevance": "primary", "confidence": 0.9}],
                    "prerequisite_ids": [],
                    "misconception_ids": [{"id": "mc-sql-filter-vs-projection", "confidence": 0.75}],
                    "source_trace": {"question_source": "agent-injected"},
                },
                "question_type_rationale": {
                    "type": "sql",
                    "reason": "SQL 题能直接验证查询语句是否满足筛选和列选择要求。",
                    "assessment_fit": "public/hidden 表数据可暴露漏写 WHERE 或列选择错误。",
                },
                "coverage_units": [
                    {
                        "unit_type": "public_test",
                        "claim": "public 样例验证 amount > 100 的筛选条件和 order_id 输出。",
                        "knowledge_point_ids": [{"id": "kp-mysql-select-where", "relevance": "primary", "confidence": 0.9}],
                        "difficulty_level": "basic",
                        "diagnostic_value": "检查 SELECT + WHERE 的基本组合。",
                    },
                    {
                        "unit_type": "rubric",
                        "claim": "评分标准覆盖筛选条件和列选择。",
                        "knowledge_point_ids": [{"id": "kp-mysql-select-where", "relevance": "primary", "confidence": 0.9}],
                        "difficulty_level": "basic",
                        "diagnostic_value": "区分筛选错误和投影列错误。",
                    },
                ],
                "difficulty_profile": {
                    "target_difficulty_level": "basic",
                    "difficulty_level": "basic",
                    "difficulty_reason": "只考察 SELECT + WHERE。",
                    "expected_failure_mode": "漏写过滤条件或列名。",
                    "coverage_units": [
                        {"unit_type": "public_test", "difficulty_level": "basic"},
                        {"unit_type": "rubric", "difficulty_level": "basic"},
                    ],
                },
            }
        ]
        payload["runtime_context"] = {
            "parameter_spec": {
                "schema_version": "learn-plan.parameter_spec.v1",
                "questions": [
                    {
                        "question_id": "sql-1",
                        "supported_runtimes": ["mysql"],
                        "default_runtime": "mysql",
                        "parameters": [{"name": "orders", "type": "sql_table", "dataset_ref": "orders-public"}],
                    }
                ],
            },
            "parameter_artifact": {
                "schema_version": "learn-plan.parameter_artifact.v1",
                "questions": [
                    {
                        "question_id": "sql-1",
                        "cases": [{"case_id": "public-1", "visibility": "public", "parameters": {"orders": {"dataset_ref": "orders-public"}}}],
                    }
                ],
            },
            "dataset_artifact": {
                "schema_version": "learn-plan.dataset_artifact.v1",
                "datasets": [
                    {
                        "dataset_id": "orders-public",
                        "kind": "sql_table",
                        "visibility": "public",
                        "logical_name": "orders",
                        "columns": [
                            {"name": "order_id", "dtype": "int64", "mysql_type": "BIGINT"},
                            {"name": "amount", "dtype": "int64", "mysql_type": "BIGINT"},
                        ],
                        "rows": [{"order_id": 1, "amount": 90}, {"order_id": 2, "amount": 120}],
                    }
                ],
            },
            "materialized_datasets": None,
            "mysql_runtime": {"configured": False, "skip_materialize": True},
        }
        payload["plan_source"]["question_plan"] = plan
        payload["selection_context"]["question_plan"] = plan
        payload["plan_source"]["lesson_grounding_context"]["question_plan"] = plan
        payload["selection_context"]["daily_lesson_plan"]["question_plan"] = plan
        payload["plan_source"]["question_scope"] = scope

        result = validate_questions_payload(payload)

        self.assertTrue(result["valid"], result.get("issues"))

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

    def _question_scope(self) -> dict[str, object]:
        return {
            "schema_version": "learn-plan.question_scope.v1",
            "scope_id": "scope-1",
            "source_profile": "initial-diagnostic",
            "session_type": "test",
            "session_intent": "assessment",
            "assessment_kind": "initial-test",
            "test_mode": "general",
            "topic": "Python 基础",
            "language_policy": {"user_facing_language": "zh-CN"},
            "scope_basis": [{"kind": "purpose-analysis", "summary": "诊断 Python 入门能力"}],
            "target_capability_ids": ["python-basics"],
            "target_concepts": [],
            "target_knowledge_point_ids": ["kp-python-assignment"],
            "diagnostic_strategy": {"selection_strategy": "information_gain_hub_prerequisite_first", "early_stop_allowed": True},
            "review_targets": [],
            "lesson_focus_points": [],
            "project_tasks": [],
            "project_blockers": [],
            "source_material_refs": [],
            "difficulty_target": {},
            "minimum_pass_shape": {"required_open_question_count": 0},
            "exclusions": [],
            "evidence": ["purpose-analysis.html"],
            "generation_trace": {"status": "ok"},
        }

    def _question_plan(self) -> dict[str, object]:
        return {
            "schema_version": "learn-plan.question_plan.v1",
            "plan_id": "plan-1",
            "scope_id": "scope-1",
            "source_profile": "initial-diagnostic",
            "session_type": "test",
            "session_intent": "assessment",
            "assessment_kind": "initial-test",
            "test_mode": "general",
            "topic": "Python 基础",
            "question_count": 2,
            "question_mix": {"single_choice": 1, "code": 1},
            "difficulty_distribution": {"basic": 1, "medium": 1},
            "diagnostic_value": {
                "target_knowledge_point_ids": ["kp-python-assignment"],
                "prerequisite_probe_chain": ["kp-python-name-binding"],
                "expected_information_gain": ["确认变量赋值是否是后续语法学习的薄弱前置点"],
            },
            "early_stop_policy": {
                "enabled": True,
                "stop_when": ["推荐起点稳定", "主要薄弱链稳定", "继续出题边际收益低"],
            },
            "planned_items": [],
            "coverage_matrix": [],
            "minimum_pass_shape": {"required_open_question_count": 0},
            "forbidden_question_types": ["open", "written", "short_answer", "free_text"],
            "generation_guidance": [],
            "review_checklist": [],
            "evidence": ["scope-1"],
            "generation_trace": {"status": "ok"},
        }

    def test_question_scope_schema_accepts_initial_diagnostic(self) -> None:
        self.assertEqual(validate_question_scope_basic(self._question_scope()), [])

    def test_question_scope_rejects_open_required_count(self) -> None:
        scope = self._question_scope()
        scope["minimum_pass_shape"] = {"required_open_question_count": 1}

        self.assertIn(
            "question_scope.minimum_pass_shape.open_not_allowed_by_test_grade",
            validate_question_scope_basic(scope),
        )

    def test_question_plan_schema_accepts_test_grade_plan(self) -> None:
        self.assertEqual(validate_question_plan_basic(self._question_plan()), [])

    def test_question_plan_schema_accepts_sql_mix(self) -> None:
        plan = self._question_plan()
        plan["question_count"] = 2
        plan["question_mix"] = {"single_choice": 1, "sql": 1}
        plan["difficulty_distribution"] = {"basic": 1, "medium": 1}

        self.assertEqual(validate_question_plan_basic(plan), [])

    def test_question_plan_rejects_forbidden_type(self) -> None:
        plan = self._question_plan()
        plan["question_mix"] = {"single_choice": 1, "open": 1}

        self.assertIn("question_plan.question_mix.forbidden_type", validate_question_plan_basic(plan))

    def test_parameter_spec_schema_accepts_basic_contract(self) -> None:
        artifact = {
            "schema_version": "learn-plan.parameter_spec.v1",
            "questions": [
                {
                    "question_id": "sql-1",
                    "supported_runtimes": ["mysql"],
                    "default_runtime": "mysql",
                    "parameters": [
                        {"name": "orders", "type": "sql_table", "dataset_ref": "orders-public"},
                    ],
                }
            ],
        }

        self.assertEqual(validate_parameter_spec_basic(artifact), [])

    def test_parameter_spec_accepts_nested_parameter_schema(self) -> None:
        artifact = {
            "schema_version": "learn-plan.parameter_spec.v1",
            "questions": [
                {
                    "question_id": "code-1",
                    "supported_runtimes": ["python"],
                    "default_runtime": "python",
                    "parameters": [
                        {
                            "name": "records",
                            "type": "json",
                            "schema": {
                                "kind": "list",
                                "element": {
                                    "kind": "object",
                                    "fields": {
                                        "y_true": {"kind": "union", "any_of": [{"kind": "int"}, {"kind": "bool"}, {"kind": "str"}, {"kind": "none"}]},
                                        "score": {"kind": "number", "min": 0, "max": 1},
                                    },
                                },
                                "min_length": 1,
                            },
                        }
                    ],
                }
            ],
        }

        self.assertEqual(validate_parameter_spec_basic(artifact), [])

    def test_parameter_spec_accepts_output_schema(self) -> None:
        artifact = {
            "schema_version": "learn-plan.parameter_spec.v1",
            "questions": [
                {
                    "question_id": "code-1",
                    "supported_runtimes": ["python"],
                    "default_runtime": "python",
                    "parameters": [{"name": "payload", "type": "json", "schema": {"kind": "object", "fields": {"raw": {"kind": "str"}}}}],
                    "output_schema": {
                        "kind": "object",
                        "fields": {
                            "error_code": {"kind": "int", "allowed_values": [0, 1, 2], "description": "0 表示成功，1 表示输入为空，2 表示格式非法。"},
                            "message": {"kind": "str", "max_length": 200, "description": "面向用户的错误说明。"},
                        },
                    },
                }
            ],
        }

        self.assertEqual(validate_parameter_spec_basic(artifact), [])

    def test_parameter_spec_rejects_invalid_output_schema(self) -> None:
        artifact = {
            "schema_version": "learn-plan.parameter_spec.v1",
            "questions": [
                {
                    "question_id": "code-1",
                    "supported_runtimes": ["python"],
                    "parameters": [],
                    "output_schema": {"kind": "list"},
                }
            ],
        }

        self.assertIn("parameter_spec.questions.0.output_schema.element_missing", validate_parameter_spec_basic(artifact))

    def test_parameter_spec_rejects_invalid_nested_parameter_schema(self) -> None:
        artifact = {
            "schema_version": "learn-plan.parameter_spec.v1",
            "questions": [
                {
                    "question_id": "code-1",
                    "supported_runtimes": ["python"],
                    "parameters": [
                        {"name": "records", "type": "json", "schema": {"kind": "list"}},
                        {"name": "threshold", "type": "json", "schema": {"kind": "union", "any_of": [{"kind": "number"}]}},
                    ],
                }
            ],
        }

        issues = validate_parameter_spec_basic(artifact)
        self.assertIn("parameter_spec.questions.0.parameters.0.schema.element_missing", issues)
        self.assertIn("parameter_spec.questions.0.parameters.1.schema.any_of_invalid", issues)

    def test_parameter_spec_schema_rejects_unknown_runtime(self) -> None:
        artifact = {
            "schema_version": "learn-plan.parameter_spec.v1",
            "questions": [{"question_id": "sql-1", "supported_runtimes": ["sqlite"], "parameters": []}],
        }

        self.assertIn("parameter_spec.questions.0.supported_runtimes_invalid:sqlite", validate_parameter_spec_basic(artifact))

    def test_parameter_artifact_schema_accepts_case_bindings(self) -> None:
        artifact = {
            "schema_version": "learn-plan.parameter_artifact.v1",
            "questions": [
                {
                    "question_id": "sql-1",
                    "cases": [
                        {
                            "case_id": "public-1",
                            "visibility": "public",
                            "parameters": {"orders": {"dataset_ref": "orders-public"}},
                        }
                    ],
                }
            ],
        }

        self.assertEqual(validate_parameter_artifact_basic(artifact), [])

    def test_dataset_artifact_schema_accepts_empty_dataset_list(self) -> None:
        artifact = {"schema_version": "learn-plan.dataset_artifact.v1", "datasets": []}

        self.assertEqual(validate_dataset_artifact_basic(artifact), [])

    def test_dataset_artifact_schema_requires_reconstruction_for_dataframe(self) -> None:
        artifact = {
            "schema_version": "learn-plan.dataset_artifact.v1",
            "datasets": [
                {
                    "dataset_id": "df-public",
                    "kind": "dataframe",
                    "visibility": "public",
                    "logical_name": "df",
                    "columns": [{"name": "value", "dtype": "int64", "mysql_type": "BIGINT"}],
                    "rows": [{"value": 1}],
                }
            ],
        }

        self.assertIn("dataset_artifact.datasets.0.reconstruction_metadata_missing", validate_dataset_artifact_basic(artifact))

    def test_progress_template_passes_shared_progress_schema(self) -> None:
        template_path = SKILL_DIR / "templates" / "progress_template.json"
        progress = json.loads(template_path.read_text(encoding="utf-8"))

        self.assertEqual(validate_progress_basic(progress), [])
        self.assertTrue(bootstrap_progress_shape_is_valid(progress))
        self.assertTrue(orchestrator_progress_shape_is_valid(progress))

    def test_bootstrap_fills_agent_evidence_defaults_for_old_progress(self) -> None:
        template_path = SKILL_DIR / "templates" / "progress_template.json"
        template = json.loads(template_path.read_text(encoding="utf-8"))
        old_progress = {
            "date": "2026-04-24",
            "topic": "Python 基础",
            "session": {"type": "today", "status": "active", "started_at": "2026-04-24T08:00:00"},
            "summary": {"total": 1, "attempted": 0, "correct": 0},
            "context": {},
            "questions": {},
        }
        questions_data = {
            "date": "2026-04-24",
            "topic": "Python 基础",
            "session_type": "today",
            "session_intent": "learning",
            "assessment_kind": None,
            "test_mode": None,
            "questions": [
                {
                    "id": "q1",
                    "category": "concept",
                    "type": "single_choice",
                    "question": "Python 中哪个符号用于变量赋值？",
                    "options": ["=", "=="],
                    "answer": 0,
                    "option_diagnostics": [
                        {
                            "index": 0,
                            "claim": "`=` 是 Python 的赋值符号。",
                            "diagnostic_role": "correct_concept",
                            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
                            "prerequisite_ids": [],
                            "misconception_ids": [],
                            "evidence_span": "选项 `=` 对应变量赋值语法。",
                            "diagnostic_question": "你如何区分赋值符号和比较符号？",
                        },
                        {
                            "index": 1,
                            "claim": "`==` 是 Python 的相等比较符号。",
                            "diagnostic_role": "distractor",
                            "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
                            "prerequisite_ids": [],
                            "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
                            "evidence_span": "选项 `==` 容易暴露赋值与相等比较混淆。",
                            "diagnostic_question": "什么时候应该使用 `==` 而不是 `=`？",
                        },
                    ],
                    "difficulty_level": "basic",
                }
            ],
        }
        args = argparse.Namespace(
            session_type=None,
            test_mode=None,
            plan_path="learn-plan.md",
            resume_topic=None,
            resume_goal=None,
            resume_level=None,
            resume_schedule=None,
            resume_preference=None,
        )

        normalized, changed = normalize_progress_data(old_progress, template, questions_data, args)

        self.assertTrue(changed)
        self.assertEqual(normalized["pre_session_review"]["status"], "not_started")
        self.assertEqual(normalized["interaction_evidence"], [])
        self.assertEqual(normalized["user_feedback"]["scope"], "session")
        self.assertEqual(normalized["mastery_judgement"]["status"], "unknown")
        self.assertEqual(normalized["completion_signal"]["status"], "not_received")
        self.assertEqual(validate_progress_basic(normalized), [])
        self.assertTrue(bootstrap_progress_shape_is_valid(normalized))


if __name__ == "__main__":
    unittest.main()
