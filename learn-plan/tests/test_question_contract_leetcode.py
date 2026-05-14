from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.question_generation import build_question_reviewer_prompt, build_runtime_question_prompt
from learn_runtime.question_validation import validate_questions_payload
from learn_runtime.schemas import (
    MAX_FAILED_CASE_SUMMARIES,
    validate_code_question_contract,
    validate_objective_question_contract,
    validate_submit_result_contract,
    validate_test_grade_question,
)


class LeetCodeQuestionContractTest(unittest.TestCase):
    def _code_question(self) -> dict[str, object]:
        return {
            "id": "code-two-sum",
            "type": "code",
            "category": "code",
            "title": "两数之和：返回满足目标和的下标",
            "problem_statement": "实现 `two_sum(nums, target)`。\n\n**目标**：返回两个不同元素的下标，使它们的和等于 `target`。\n\n要求：\n- 不能重复使用同一个元素\n- 返回任意一个满足条件的下标组合",
            "input_spec": "`nums: list[int]`，长度 2 到 10^4；`target: int`。",
            "output_spec": "返回 `list[int]`，长度固定为 2；每个元素是 `nums` 中的下标，类型为 `int`，取值范围从 0 到 `len(nums) - 1`；两个下标必须不同，顺序不限。",
            "calculation_spec": "从左到右扫描 `nums`，找到两个不同下标 `i` 和 `j`，满足 `nums[i] + nums[j] == target`；不得重复使用同一个元素。",
            "constraints": ["每个输入恰好存在一个答案", "不能重复使用同一个元素"],
            "examples": [
                {
                    "input": {"nums": [2, 7, 11, 15], "target": 9},
                    "output": [0, 1],
                    "explanation": "nums[0] + nums[1] = 9。",
                }
            ],
            "public_tests": [
                {"kwargs": {"nums": [2, 7, 11, 15], "target": 9}, "expected": [0, 1], "category": "public"}
            ],
            "hidden_tests": [
                {"kwargs": {"nums": [3, 2, 4], "target": 6}, "expected": [1, 2], "category": "hidden"}
            ],
            "starter_code": "def two_sum(nums, target):\n    pass\n",
            "function_signature": "two_sum(nums: list[int], target: int) -> list[int]",
            "function_name": "two_sum",
            "scoring_rubric": ["正确返回两个不同下标", "覆盖重复值和边界输入"],
            "capability_tags": ["array", "hash-map"],
            "source_trace": {"question_source": "test-fixture"},
            "explanation": "可用哈希表记录已访问数字。",
        }

    def _option_diagnostics(self, options: list[str], correct_indices: set[int] | None = None) -> list[dict[str, object]]:
        correct_indices = correct_indices or {0}
        return [
            {
                "index": index,
                "claim": f"`{option}` 对列表对象身份和内容变化的影响是否符合题目要求。",
                "diagnostic_role": "correct_concept" if index in correct_indices else "distractor",
                "knowledge_point_ids": [{"id": "kp-list-mutability", "relevance": "primary", "confidence": 0.9}],
                "prerequisite_ids": [{"id": "kp-python-object-reference", "confidence": 0.7}],
                "misconception_ids": [] if index in correct_indices else [{"id": "mc-copy-vs-mutation", "confidence": 0.8}],
                "evidence_span": f"该选项用于区分 `{option}` 是否会修改原列表对象，而不是只复述选项文本。",
                "diagnostic_question": "你如何区分原地修改和创建新对象？",
                "confidence": 0.85,
            }
            for index, option in enumerate(options)
        ]

    def _objective_question(self) -> dict[str, object]:
        options = ["xs.append(1)", "xs + [1]", "tuple(xs)", "xs.copy()"]
        return {
            "id": "choice-mutability",
            "type": "single_choice",
            "category": "concept",
            "title": "Python 列表可变性判断",
            "prompt": "以下哪个操作会原地修改列表 xs？",
            "options": options,
            "answer": 0,
            "explanation": "append 会原地修改列表，其他选项会创建新对象或转换对象。",
            "scoring_rubric": ["识别列表原地修改 API", "区分新对象创建与原地变更"],
            "capability_tags": ["python-list", "mutability"],
            "option_diagnostics": self._option_diagnostics(options),
            "source_trace": {"question_source": "test-fixture"},
        }

    def _submit_result(self) -> dict[str, object]:
        return {
            "question_id": "code-two-sum",
            "question_type": "code",
            "status": "failed",
            "passed_public_count": 1,
            "total_public_count": 1,
            "passed_hidden_count": 0,
            "total_hidden_count": 1,
            "failed_case_summaries": [
                {
                    "category": "hidden",
                    "input": {"nums": [3, 2, 4], "target": 6},
                    "expected": [1, 2],
                    "actual": [0, 1],
                    "error": "wrong_answer",
                    "capability_tags": ["array", "hash-map"],
                }
            ],
            "failure_types": ["wrong_answer"],
            "capability_tags": ["array", "hash-map"],
            "submitted_at": "2026-04-25T02:00:00Z",
        }

    def test_canonical_code_question_contract_passes(self) -> None:
        self.assertEqual(validate_code_question_contract(self._code_question()), [])
        self.assertEqual(validate_test_grade_question(self._code_question()), [])

    def test_canonical_objective_question_contract_passes(self) -> None:
        self.assertEqual(validate_objective_question_contract(self._objective_question()), [])
        self.assertEqual(validate_test_grade_question(self._objective_question()), [])

    def test_single_and_multiple_choice_require_option_diagnostics(self) -> None:
        question = self._objective_question()
        question.pop("option_diagnostics", None)

        self.assertIn("question.objective.option_diagnostics_missing", validate_objective_question_contract(question))

    def test_option_diagnostics_must_cover_each_option_once(self) -> None:
        question = self._objective_question()
        question["option_diagnostics"] = list(question["option_diagnostics"])[1:]
        count_issues = validate_objective_question_contract(question)
        self.assertIn("question.objective.option_diagnostics_count_mismatch", count_issues)
        self.assertIn("question.objective.option_diagnostics_index_coverage_missing", count_issues)

        question = self._objective_question()
        diagnostics = list(question["option_diagnostics"])
        diagnostics[1] = {**diagnostics[1], "index": 0}
        duplicate_issues = validate_objective_question_contract({**question, "option_diagnostics": diagnostics})
        self.assertIn("question.objective.option_diagnostics.1.index_duplicate", duplicate_issues)
        self.assertIn("question.objective.option_diagnostics_index_coverage_missing", duplicate_issues)

    def test_option_diagnostics_require_claim_role_evidence_and_knowledge_mapping(self) -> None:
        question = self._objective_question()
        diagnostic = dict(question["option_diagnostics"][0])
        for field in ("claim", "diagnostic_role", "evidence_span", "diagnostic_question"):
            diagnostic[field] = ""
        diagnostic["knowledge_point_ids"] = []
        diagnostic["confidence"] = 1.2
        diagnostic["prerequisite_ids"] = [{"id": "kp-python-object-reference", "confidence": -0.1}]
        diagnostic["misconception_ids"] = [""]
        diagnostics = list(question["option_diagnostics"])
        diagnostics[0] = diagnostic

        issues = validate_objective_question_contract({**question, "option_diagnostics": diagnostics})

        for expected in (
            "question.objective.option_diagnostics.0.claim_missing",
            "question.objective.option_diagnostics.0.diagnostic_role_missing",
            "question.objective.option_diagnostics.0.evidence_span_missing",
            "question.objective.option_diagnostics.0.diagnostic_question_missing",
            "question.objective.option_diagnostics.0.knowledge_point_ids_missing",
            "question.objective.option_diagnostics.0.confidence_invalid",
            "question.objective.option_diagnostics.0.prerequisite_ids.0.confidence_invalid",
            "question.objective.option_diagnostics.0.misconception_ids.0.id_missing",
        ):
            self.assertIn(expected, issues)

    def test_option_diagnostics_validate_relevance_and_role(self) -> None:
        question = self._objective_question()
        diagnostic = dict(question["option_diagnostics"][0])
        diagnostic["diagnostic_role"] = "unknown"
        diagnostic["knowledge_point_ids"] = [{"id": "kp-list-mutability", "relevance": "weak", "confidence": 0.7}]
        diagnostics = list(question["option_diagnostics"])
        diagnostics[0] = diagnostic

        issues = validate_objective_question_contract({**question, "option_diagnostics": diagnostics})

        self.assertIn("question.objective.option_diagnostics.0.diagnostic_role_invalid", issues)
        self.assertIn("question.objective.option_diagnostics.0.knowledge_point_ids.0.relevance_invalid", issues)

    def test_true_false_option_diagnostics_remain_optional_for_first_pass(self) -> None:
        question = self._objective_question()
        question["type"] = "true_false"
        question["options"] = ["正确", "错误"]
        question["answer"] = True
        question.pop("option_diagnostics", None)

        self.assertNotIn("question.objective.option_diagnostics_missing", validate_objective_question_contract(question))

    def test_open_written_questions_are_not_test_grade_by_default(self) -> None:
        question = {
            "id": "open-1",
            "type": "written",
            "category": "open",
            "question": "解释 Python GIL。",
            "prompt": "解释 Python GIL。",
            "reference_points": ["线程", "解释器锁"],
        }

        issues = validate_test_grade_question(question)
        self.assertIn("question.open_not_allowed_by_default", issues)

    def test_code_question_missing_required_leetcode_fields_fails(self) -> None:
        required_fields = (
            "problem_statement",
            "input_spec",
            "output_spec",
            "calculation_spec",
            "constraints",
            "examples",
            "public_tests",
            "hidden_tests",
            "scoring_rubric",
            "capability_tags",
        )
        for field in required_fields:
            with self.subTest(field=field):
                question = self._code_question()
                question.pop(field, None)
                issues = validate_code_question_contract(question)
                self.assertIn(f"question.code.{field}_missing", issues)

    def test_submit_result_contract_passes_and_caps_failed_case_summaries(self) -> None:
        self.assertEqual(validate_submit_result_contract(self._submit_result()), [])
        result = self._submit_result()
        result["failed_case_summaries"] = list(result["failed_case_summaries"]) * (MAX_FAILED_CASE_SUMMARIES + 1)

        issues = validate_submit_result_contract(result)
        self.assertIn("submit_result.failed_case_summaries_too_many", issues)

    def _parameter_spec(self, question_id: str = "code-two-sum") -> dict[str, object]:
        return {
            "schema_version": "learn-plan.parameter_spec.v1",
            "questions": [
                {
                    "question_id": question_id,
                    "supported_runtimes": ["python"],
                    "default_runtime": "python",
                    "parameters": [
                        {"name": "nums", "type": "json", "schema": {"kind": "list", "element": {"kind": "int"}, "min_length": 2, "max_length": 10000}},
                        {"name": "target", "type": "json", "schema": {"kind": "int"}},
                    ],
                    "output_schema": {"kind": "list", "element": {"kind": "int", "min": 0}, "min_length": 2, "max_length": 2},
                }
            ],
        }

    def _questions_payload(self, question: dict[str, object], *, include_parameter_spec: bool = True, parameter_spec: dict[str, object] | None = None) -> dict[str, object]:
        qtype = "code" if question.get("category") == "code" or question.get("type") == "code" else str(question.get("type") or "single_choice")
        level = str(question.get("difficulty_level") or "medium")
        capabilities = list(question.get("capability_tags") or []) or ["python"]
        scope = {
            "schema_version": "learn-plan.question_scope.v1",
            "scope_id": "scope-stage-fixture",
            "source_profile": "history-stage-test",
            "session_type": "test",
            "session_intent": "assessment",
            "assessment_kind": "stage-test",
            "test_mode": "general",
            "topic": "Python",
            "language_policy": {"user_facing_language": "zh-CN"},
            "scope_basis": [{"kind": "progress", "summary": "history progress learner_model"}],
            "target_capability_ids": capabilities,
            "target_concepts": [],
            "review_targets": [],
            "lesson_focus_points": [],
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
            "plan_id": "plan-stage-fixture",
            "scope_id": "scope-stage-fixture",
            "source_profile": "history-stage-test",
            "session_type": "test",
            "session_intent": "assessment",
            "assessment_kind": "stage-test",
            "test_mode": "general",
            "topic": "Python",
            "question_count": 1,
            "question_mix": {qtype: 1},
            "difficulty_distribution": {level: 1},
            "planned_items": [],
            "coverage_matrix": [],
            "minimum_pass_shape": {"required_open_question_count": 0},
            "forbidden_question_types": ["open", "written", "short_answer", "free_text"],
            "generation_guidance": [],
            "review_checklist": [],
            "evidence": ["scope-stage-fixture"],
            "generation_trace": {"status": "ok"},
        }
        payload = {
            "date": "2026-04-25",
            "topic": "Python",
            "mode": "test",
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
                    "target_capability_ids": capabilities,
                    "question_scope": scope,
                    "question_plan": plan,
                    "minimum_pass_shape": {},
                },
                "question_generation_mode": "agent-subagent",
                "strict_question_review": {"valid": True, "verdict": "pass", "issues": []},
                "deterministic_question_review": {"valid": True, "verdict": "pass", "issues": []},
            },
            "selection_context": {
                "language_policy": {"user_facing_language": "zh-CN"},
                "question_scope": scope,
                "question_plan": plan,
                "daily_lesson_plan": {"semantic_profile": "stage-test", "question_scope": scope, "question_plan": plan},
            },
            "materials": [],
            "questions": [question],
        }
        if include_parameter_spec and (question.get("category") == "code" or question.get("type") == "code"):
            payload["runtime_context"] = {"parameter_spec": parameter_spec or self._parameter_spec(str(question.get("id") or "code-two-sum"))}
        return payload

    def test_validate_questions_payload_rejects_code_question_missing_test_grade_contract(self) -> None:
        question = self._code_question()
        question.pop("input_spec", None)

        review = validate_questions_payload(self._questions_payload(question))

        self.assertFalse(review.get("valid"))
        self.assertIn("code-two-sum: question.code.input_spec_missing", review.get("issues", []))

    def test_validate_questions_payload_rejects_one_paragraph_code_statement(self) -> None:
        question = self._code_question()
        question["problem_statement"] = "实现 two_sum 函数，接收 nums 和 target，返回两个不同元素下标，使它们的和等于 target，不能重复使用同一个元素，每个输入恰好存在一个答案。"

        review = validate_questions_payload(self._questions_payload(question))

        self.assertFalse(review.get("valid"))
        self.assertTrue(any("problem_statement 为纯文本一段到底" in issue for issue in review.get("issues", [])))

    def test_validate_questions_payload_rejects_semicolon_packed_constraints(self) -> None:
        question = self._code_question()
        question["constraints"] = "每个输入恰好存在一个答案；不能重复使用同一个元素；返回顺序不限"

        review = validate_questions_payload(self._questions_payload(question))

        self.assertFalse(review.get("valid"))
        self.assertTrue(any("constraints 必须用数组" in issue for issue in review.get("issues", [])))

    def test_validate_questions_payload_rejects_code_question_missing_parameter_spec(self) -> None:
        review = validate_questions_payload(self._questions_payload(self._code_question(), include_parameter_spec=False))

        self.assertFalse(review.get("valid"))
        self.assertIn("code-two-sum: runtime_context.parameter_spec_missing", review.get("issues", []))

    def test_validate_questions_payload_rejects_code_question_missing_output_schema(self) -> None:
        parameter_spec = self._parameter_spec()
        parameter_spec["questions"][0].pop("output_schema", None)

        review = validate_questions_payload(self._questions_payload(self._code_question(), parameter_spec=parameter_spec))

        self.assertFalse(review.get("valid"))
        self.assertIn("code-two-sum: question.code.output_schema_missing:code-two-sum", review.get("issues", []))

    def test_validate_questions_payload_rejects_output_values_mismatching_output_schema(self) -> None:
        question = self._code_question()
        question["examples"] = [{"input": {"nums": [2, 7], "target": 9}, "output": [0, "1"], "explanation": "输出元素必须是 int。"}]
        question["public_tests"] = [{"kwargs": {"nums": [2, 7], "target": 9}, "expected": [0, 1, 2], "category": "public"}]
        question["hidden_tests"] = [{"kwargs": {"nums": [3, 2, 4], "target": 6}, "expected": [-1, 2], "category": "hidden"}]

        review = validate_questions_payload(self._questions_payload(question))

        self.assertFalse(review.get("valid"))
        issues = "\n".join(review.get("issues", []))
        self.assertIn("question.code.examples.output_type_mismatch:$[1]", issues)
        self.assertIn("question.code.public_tests.output_type_mismatch:$", issues)
        self.assertIn("question.code.hidden_tests.output_type_mismatch:$[0]", issues)

    def test_validate_questions_payload_rejects_output_spec_schema_coverage_gap(self) -> None:
        question = self._code_question()
        question["output_spec"] = "返回对象，包含 error_code 和 message。"
        parameter_spec = self._parameter_spec()
        parameter_spec["questions"][0]["output_schema"] = {
            "kind": "object",
            "fields": {
                "error_code": {"kind": "int", "allowed_values": [0, 1, 2], "description": "0 表示成功，1 表示未找到答案，2 表示输入非法。"},
                "message": {"kind": "str", "max_length": 200, "description": "结果说明文本。"},
            },
        }
        question["examples"] = [{"input": {"nums": [2, 7], "target": 9}, "output": {"error_code": 0, "message": "ok"}, "explanation": "0 表示成功。"}]
        question["public_tests"] = [{"kwargs": {"nums": [2, 7], "target": 9}, "expected": {"error_code": 0, "message": "ok"}, "category": "public"}]
        question["hidden_tests"] = [{"kwargs": {"nums": [3, 2, 4], "target": 6}, "expected": {"error_code": 0, "message": "ok"}, "category": "hidden"}]

        review = validate_questions_payload(self._questions_payload(question, parameter_spec=parameter_spec))

        self.assertFalse(review.get("valid"))
        issues = "\n".join(review.get("issues", []))
        self.assertIn("question.code.output_spec.schema_coverage_missing:int", issues)
        self.assertIn("question.code.output_spec.schema_coverage_missing:0", issues)
        self.assertIn("question.code.output_spec.schema_coverage_missing:200", issues)

    def test_validate_questions_payload_rejects_output_schema_field_without_definition_or_range(self) -> None:
        question = self._code_question()
        question["output_spec"] = "返回 object/dict 对象，包含 error_code，类型为 int。"
        parameter_spec = self._parameter_spec()
        parameter_spec["questions"][0]["output_schema"] = {"kind": "object", "fields": {"error_code": {"kind": "int"}}}
        question["examples"] = [{"input": {"nums": [2, 7], "target": 9}, "output": {"error_code": 0}, "explanation": "返回状态码。"}]
        question["public_tests"] = [{"kwargs": {"nums": [2, 7], "target": 9}, "expected": {"error_code": 0}, "category": "public"}]
        question["hidden_tests"] = [{"kwargs": {"nums": [3, 2, 4], "target": 6}, "expected": {"error_code": 0}, "category": "hidden"}]

        review = validate_questions_payload(self._questions_payload(question, parameter_spec=parameter_spec))

        self.assertFalse(review.get("valid"))
        issues = "\n".join(review.get("issues", []))
        self.assertIn("question.code.output_schema.description_missing:$.error_code", issues)
        self.assertIn("question.code.output_schema.range_missing:$.error_code", issues)

    def test_validate_questions_payload_rejects_parameter_spec_missing_signature_parameter(self) -> None:
        parameter_spec = self._parameter_spec()
        parameter_spec["questions"][0]["parameters"] = [parameter_spec["questions"][0]["parameters"][0]]

        review = validate_questions_payload(self._questions_payload(self._code_question(), parameter_spec=parameter_spec))

        self.assertFalse(review.get("valid"))
        self.assertIn("code-two-sum: question.code.parameter_spec.parameter_missing:target", review.get("issues", []))

    def test_validate_questions_payload_rejects_example_type_mismatch_against_parameter_spec(self) -> None:
        question = self._code_question()
        question["examples"] = [{"input": {"nums": [True, 7], "target": 8}, "output": [0, 1], "explanation": "bool 不能冒充 int。"}]

        review = validate_questions_payload(self._questions_payload(question))

        self.assertFalse(review.get("valid"))
        self.assertTrue(any("question.code.examples.type_mismatch:nums:$[0]" in issue for issue in review.get("issues", [])))

    def test_validate_questions_payload_rejects_public_and_hidden_type_mismatch_against_parameter_spec(self) -> None:
        question = self._code_question()
        question["public_tests"] = [{"kwargs": {"nums": [2, "7"], "target": 9}, "expected": [0, 1], "category": "public"}]
        question["hidden_tests"] = [{"kwargs": {"nums": [3, 2, 4], "target": "6"}, "expected": [1, 2], "category": "hidden"}]

        review = validate_questions_payload(self._questions_payload(question))

        self.assertFalse(review.get("valid"))
        issues = "\n".join(review.get("issues", []))
        self.assertIn("question.code.public_tests.type_mismatch:nums:$[1]", issues)
        self.assertIn("question.code.hidden_tests.type_mismatch:target:$", issues)

    def test_validate_questions_payload_rejects_input_spec_schema_coverage_gap(self) -> None:
        question = self._code_question()
        question["input_spec"] = "`nums` 与 `target` 两个参数。"

        review = validate_questions_payload(self._questions_payload(question))

        self.assertFalse(review.get("valid"))
        self.assertTrue(any("question.code.input_spec.schema_coverage_missing:nums:list" in issue for issue in review.get("issues", [])))

    def test_validate_questions_payload_rejects_open_question_by_default(self) -> None:
        question = {
            "id": "open-1",
            "type": "written",
            "category": "open",
            "question": "解释 Python GIL。",
            "prompt": "解释 Python GIL。",
            "reference_points": ["线程", "解释器锁"],
            "source_trace": {"question_source": "test-fixture"},
        }

        review = validate_questions_payload(self._questions_payload(question))

        self.assertFalse(review.get("valid"))
        self.assertIn("open-1: question.open_not_allowed_by_default", review.get("issues", []))

    def test_runtime_question_prompt_requires_test_grade_questions(self) -> None:
        prompt = build_runtime_question_prompt(
            "Python",
            {"semantic_profile": "stage-test", "session_intent": "assessment", "assessment_kind": "stage-test"},
            {"plan_execution_mode": "assessment", "language_policy": {"user_facing_language": "zh-CN"}},
            limit=3,
            question_mix={"code": 2, "single_choice": 1, "open": 1},
            seed_constraints={"required_open_question_count": 1, "required_code_question_count": 1},
        )

        self.assertIn("test-grade", prompt)
        self.assertIn("single_choice", prompt)
        self.assertIn("multiple_choice", prompt)
        self.assertIn("true_false", prompt)
        self.assertIn("problem_statement", prompt)
        self.assertIn("input_spec", prompt)
        self.assertIn("output_spec", prompt)
        self.assertIn("output_schema", prompt)
        self.assertIn("字段/元素", prompt)
        self.assertIn("取值范围", prompt)
        self.assertIn("枚举", prompt)
        self.assertIn("expected output", prompt)
        self.assertIn("constraints", prompt)
        self.assertIn("option_diagnostics", prompt)
        self.assertIn("claim", prompt)
        self.assertIn("knowledge_point_ids", prompt)
        self.assertIn("misconception_ids", prompt)
        self.assertIn("prerequisite_ids", prompt)
        self.assertIn("examples", prompt)
        self.assertIn("public_tests", prompt)
        self.assertIn("hidden_tests", prompt)
        self.assertIn("scoring_rubric", prompt)
        self.assertIn("capability_tags", prompt)
        self.assertIn("Markdown 可读文本", prompt)
        self.assertIn("每条独立成行", prompt)
        self.assertIn("禁止用分号堆成一行", prompt)
        self.assertIn("禁止生成 open / written / short_answer / free_text", prompt)
        self.assertNotIn("允许生成 concept / code / open", prompt)
        self.assertNotIn("open 题 type 必须是 written", prompt)
        self.assertNotIn("required_open_question_count", prompt)

    def test_strict_question_reviewer_prompt_blocks_non_test_grade_questions(self) -> None:
        prompt = build_question_reviewer_prompt(
            "Python",
            {"semantic_profile": "stage-test", "session_intent": "assessment", "assessment_kind": "stage-test"},
            {"plan_execution_mode": "assessment", "language_policy": {"user_facing_language": "zh-CN"}},
            [self._code_question()],
            {"valid": False, "issues": ["code-two-sum: question.code.input_spec_missing"], "warnings": []},
        )

        for required in (
            "LeetCode-like",
            "problem_statement",
            "input_spec",
            "output_spec",
            "constraints",
            "示例解释",
            "hidden_tests",
            "output_schema",
            "字段/范围定义",
            "expected output 与 output_schema 不一致",
            "题干和测试用例不一致",
            "禁止 open / written / short_answer / free_text",
            "泄露 hidden tests",
            "Markdown 可读文本",
            "分号堆成一行",
            "option_diagnostics",
            "选项级诊断",
            "knowledge_point_ids",
            "misconception_ids",
        ):
            self.assertIn(required, prompt)
        self.assertNotIn("code/open/concept", prompt)


if __name__ == "__main__":
    unittest.main()
