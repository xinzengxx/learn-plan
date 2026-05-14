from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.schemas import validate_code_question_contract


class CodeArgumentContractTest(unittest.TestCase):
    def _question(self, tests: list[dict[str, object]], *, signature: str = "combine(a: int, b: int, c: int) -> int", single_object_input: bool = False) -> dict[str, object]:
        question = {
            "id": "code-combine",
            "type": "code",
            "category": "code",
            "title": "多参数求和",
            "problem_statement": "实现 combine(a, b, c)，返回三个整数之和。",
            "input_spec": "`a: int`、`b: int`、`c: int`，三个参数均为整数。",
            "output_spec": "返回 `int`，表示三个整数之和。",
            "calculation_spec": "计算规则为 `a + b + c`，不做类型转换或舍入。",
            "constraints": ["参数均为整数"],
            "examples": [{"input": {"a": 1, "b": 2, "c": 3}, "output": 6, "explanation": "1 + 2 + 3 = 6。"}],
            "public_tests": tests,
            "hidden_tests": [{"kwargs": {"a": 2, "b": 3, "c": 4}, "expected": 9, "category": "hidden"}],
            "starter_code": "def combine(a, b, c):\n    pass\n",
            "function_signature": signature,
            "function_name": "combine",
            "scoring_rubric": ["正确处理多个形参"],
            "capability_tags": ["function-arguments"],
        }
        if single_object_input:
            question["single_object_input"] = True
        return question

    def test_multi_parameter_question_accepts_kwargs_cases(self) -> None:
        issues = validate_code_question_contract(
            self._question([{"kwargs": {"a": 1, "b": 2, "c": 3}, "expected": 6, "category": "public"}])
        )

        self.assertNotIn("question.code.public_tests.argument_contract_invalid", issues)

    def test_multi_parameter_question_accepts_args_cases(self) -> None:
        issues = validate_code_question_contract(
            self._question([{"args": [1, 2, 3], "expected": 6, "category": "public"}])
        )

        self.assertNotIn("question.code.public_tests.argument_contract_invalid", issues)

    def test_multi_parameter_question_rejects_ambiguous_dict_input(self) -> None:
        issues = validate_code_question_contract(
            self._question([{"input": {"a": 1, "b": 2, "c": 3}, "expected": 6, "category": "public"}])
        )

        self.assertIn("question.code.public_tests.argument_contract_invalid", issues)

    def test_single_object_question_allows_dict_input(self) -> None:
        issues = validate_code_question_contract(
            self._question(
                [{"input": {"values": [1, 2, 3]}, "expected": 6, "category": "public"}],
                signature="combine(payload: dict) -> int",
                single_object_input=True,
            )
        )

        self.assertNotIn("question.code.public_tests.argument_contract_invalid", issues)

    def test_args_length_must_match_multi_parameter_signature(self) -> None:
        issues = validate_code_question_contract(
            self._question([{"args": [1, 2], "expected": 3, "category": "public"}])
        )

        self.assertIn("question.code.public_tests.argument_contract_invalid", issues)

    def test_starter_code_signature_must_match_function_signature(self) -> None:
        question = self._question([{"kwargs": {"a": 1, "b": 2, "c": 3}, "expected": 6, "category": "public"}])
        question["starter_code"] = "def combine(x, y):\n    pass\n"

        issues = validate_code_question_contract(question)

        self.assertIn("question.code.starter_code_signature_mismatch", issues)


if __name__ == "__main__":
    unittest.main()
