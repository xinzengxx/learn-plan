"""证明 SKILL.md 与 Python runtime 之间存在 schema gap 的复现测试。

Step 1（复现）：所有测试预期 FAIL，证明 gap 存在。
Step 5（验证）：修复 schema 文档后，测试应 PASS。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))


# ---- 模拟"只看过 SKILL.md 的 Agent"的产出物 ----

def make_naive_agent_question_artifact() -> dict:
    """按 SKILL.md 描述生成的题目：Agent 知道要出选择题/编程题，但不知道必填字段。"""
    return {
        "questions": [
            {
                # 概念题：SKILL.md 说"选择题"，但没说要 scoring_rubric、capability_tags
                "id": "q1",
                "type": "single_choice",
                "category": "concept",
                "title": "变量赋值理解",
                "prompt": "Python 中 a = [1,2,3]; b = a; b.append(4); print(a) 输出什么？",
                "options": ["[1,2,3]", "[1,2,3,4]", "[1,2,3,4,4]", "报错"],
                "answer": 1,
                "explanation": "b = a 不会复制列表，b 和 a 指向同一个对象。",
            },
            {
                # 代码题：SKILL.md 说"编程题"，但没说要 8 个必填字段
                "id": "q2",
                "type": "code",
                "category": "code",
                "title": "实现列表过滤",
                "prompt": "写一个函数，过滤列表中的 None 和负数。",
                "function_signature": "def filter_scores(scores):",
                "starter_code": "def filter_scores(scores):\n    pass\n",
                "solution_code": "def filter_scores(scores):\n    return [x for x in scores if x is not None and x >= 0]\n",
            },
        ],
    }


def make_naive_agent_lesson_artifact() -> dict:
    """Agent 按 SKILL.md 生成了完美的 Markdown 课件，但 lesson-artifact-json 只写了标题。"""
    return {
        "lesson": {
            "title": "Python 变量与对象引用",
            "why_today": "理解变量与对象的关系是 Python 编程的基础。",
        }
    }


# ---- GAP 1: 题目缺少必填字段 ----

class QuestionSchemaGapTest(unittest.TestCase):
    def test_naive_concept_question_missing_scoring_rubric(self):
        """复现 GAP 3：Agent 生成的概念题缺少 scoring_rubric、capability_tags。

        预期 FAIL：runtime 拒绝，但 Agent 不知道要填这些字段。
        """
        from learn_runtime.question_validation import validate_questions_payload

        artifact = make_naive_agent_question_artifact()
        result = validate_questions_payload(artifact)

        issues = result.get("issues") or []
        issue_text = " ".join(issues)

        self.assertFalse(
            result.get("valid"),
            f"缺少必填字段应该让 valid=false，issues={issues}",
        )
        self.assertTrue(
            any("scoring_rubric" in i or "capability_tags" in i or "schema 不合法" in i for i in issues),
            f"必须报缺少必填字段，实际 issues={issues}",
        )

    def test_naive_code_question_missing_required_fields(self):
        """复现 GAP 2：Agent 生成的代码题缺少 8 个必填字段 + hidden_tests。

        预期 FAIL：runtime 拒绝代码题。
        """
        from learn_runtime.question_validation import validate_questions_payload

        artifact = make_naive_agent_question_artifact()
        result = validate_questions_payload(artifact)

        issues = result.get("issues") or []
        issue_text = " ".join(issues)

        # 代码题 q2 缺少 problem_statement/input_spec/output_spec/constraints/examples/hidden_tests
        code_issues = [i for i in issues if "q2" in i]
        self.assertTrue(
            len(code_issues) > 0,
            f"代码题 q2 缺少多个必填字段应该被检测到，实际 issues={issues}",
        )

    def test_naive_question_missing_top_level_fields(self):
        """复现 GAP 1：Agent 生成的 questions.json 缺少 11 个顶层必填字段。

        预期 FAIL：顶层字段缺失。
        """
        from learn_runtime.question_validation import validate_questions_payload

        artifact = make_naive_agent_question_artifact()
        result = validate_questions_payload(artifact)

        issues = result.get("issues") or []
        issue_text = " ".join(issues)

        # 缺少 date, topic, mode, session_type 等
        missing_top = [i for i in issues if "缺少字段" in i]
        self.assertTrue(
            len(missing_top) > 0,
            f"顶层缺少 date/topic/mode/session_type 等应被检测到，issues={issues}",
        )


# ---- GAP 2: lesson artifact 缺少 JSON 结构 ----

class LessonSchemaGapTest(unittest.TestCase):
    def test_naive_lesson_missing_json_artifact_causes_build_failure(self):
        """复现 GAP 10：Agent 生成 Markdown 课件，但没有 JSON artifact。

        预期 FAIL：build_runtime_lesson_artifact 抛 ValueError。
        """
        from learn_runtime.payload_builder import build_runtime_lesson_artifact

        artifact = make_naive_agent_lesson_artifact()

        with self.assertRaises(ValueError) as ctx:
            build_runtime_lesson_artifact(
                topic="Python",
                plan_source={},
                selected_segments=[],
                mastery_targets={},
                grounding_context={},
                lesson_artifact={},  # 空 JSON = 缺失
            )
        self.assertIn("lesson artifact", str(ctx.exception))

    def test_valid_lesson_structure_required_keys(self):
        """lesson review 仍检测缺失的 today_focus。case_courseware 现在是可选的。"""
        from learn_runtime.lesson_builder import build_lesson_review

        naive_plan = {
            "title": "测试课件",
            "why_today": "今天学基础概念很有必要。",
            "today_focus": {},
            "review_suggestions": {},
            "review_targets": [],
            "materials_used": [],
            "plan_execution_mode": "normal",
        }
        result = build_lesson_review(naive_plan)

        self.assertFalse(
            result.get("valid"),
            f"缺少 today_focus.focus_points 应失败",
        )
        issues = result.get("issues") or []
        self.assertTrue(
            any("focus" in i.lower() or "review" in i.lower() for i in issues),
            f"lesson review 应报告缺失字段，issues={issues}",
        )


# ---- GAP 3: learn-test 缺少 --lesson-artifact-json ----

class LearnTestCLIGapTest(unittest.TestCase):
    def test_learn_test_command_missing_lesson_flag(self):
        """复现 GAP 38：learn-test/SKILL.md 的命令行缺少 --lesson-artifact-json。

        预期 FAIL：文档中没有 --lesson-artifact-json，但 runtime 强制要求。
        """
        skill_path = SKILL_DIR.parent / "learn-test" / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")

        self.assertIn(
            "--lesson-artifact-json",
            text,
            "learn-test/SKILL.md 的命令行缺少 --lesson-artifact-json，"
            "但 session_orchestrator.py 对所有 session type 都强制要求该参数。"
            "缺少会导致 ValueError('缺少 Agent 生成的 lesson artifact')。",
        )


if __name__ == "__main__":
    unittest.main()


# ---- Step 5（验证）: 符合 schema 的产物应通过校验 ----

def make_valid_question_artifact() -> dict:
    """按 docs/question-schema.md 生成的正确题目 artifact。"""
    return {
        "date": "2026-04-27",
        "topic": "Python 变量与对象引用",
        "mode": "today-generated",
        "session_type": "today",
        "session_intent": "learning",
        "assessment_kind": None,
        "test_mode": None,
        "language_policy": {
            "user_facing_language": "zh-CN",
            "localization_required": True,
        },
        "plan_source": {
            "plan_execution_mode": "normal",
            "language_policy": {"user_facing_language": "zh-CN"},
            "question_generation_mode": "agent-injected",
            "question_source": "agent-injected",
            "daily_lesson_plan": {},
            "lesson_grounding_context": {
                "semantic_profile": "today",
                "session_intent": "learning",
            },
        },
        "materials": [],
        "questions": [
            {
                "id": "q-concept-01",
                "type": "single_choice",
                "category": "concept",
                "title": "变量引用理解",
                "prompt": "Python 中 a = [1,2,3]; b = a; b.append(4); print(a) 输出什么？",
                "question": "执行以下代码后，`print(a)` 输出什么？\n\n```python\na = [1, 2, 3]\nb = a\nb.append(4)\nprint(a)\n```\n\n**提示**：想一想 `b = a` 是复制列表还是创建引用？",
                "options": ["[1,2,3]", "[1,2,3,4]", "报错", "None"],
                "answer": 1,
                "explanation": "b = a 是引用赋值，a 和 b 指向同一列表对象。",
                "scoring_rubric": [
                    {"metric": "概念理解", "threshold": "正确识别变量引用语义"}
                ],
                "capability_tags": ["python-core"],
                "source_trace": {"question_source": "agent-injected"},
                "question_role": "learn",
                "difficulty_level": "medium",
                "difficulty_label": "中等题",
                "difficulty_score": 2,
                "difficulty_reason": "需要理解变量名绑定到同一可变对象，而不是只记忆语法输出。",
                "expected_failure_mode": "误以为 b = a 会复制列表，选择原列表不变。",
            },
            {
                "id": "q-code-01",
                "type": "code",
                "category": "code",
                "title": "过滤列表中的无效值",
                "problem_statement": "实现 `filter_scores` 函数：\n\n接收一个可能含 `None` 和负数的整数列表，返回**只含非负整数**的新列表，保持原顺序。\n\n调用后不得修改原始列表。",
                "input_spec": "scores: list[int | None] — 可能含 None 和负数的整数列表",
                "output_spec": "list[int] — 只含非负整数的新列表，保持原顺序",
                "constraints": ["不修改原列表", "保持元素顺序", "None 和负数被过滤", "0 和正数保留"],
                "function_signature": "def filter_scores(scores: list) -> list:",
                "function_name": "filter_scores",
                "starter_code": "def filter_scores(scores):\n    pass\n",
                "solution_code": "def filter_scores(scores):\n    return [x for x in scores if x is not None and x >= 0]\n",
                "examples": [
                    {
                        "input": {"scores": [100, None, -1, 0, 88]},
                        "output": [100, 0, 88],
                        "explanation": "None 和 -1 被过滤，其他保留。",
                    }
                ],
                "hidden_tests": [
                    {"args": [[100, None, -1, 0, 88]], "expected": [100, 0, 88]},
                    {"args": [[None, None]], "expected": []},
                ],
                "scoring_rubric": [
                    {"metric": "正确性", "threshold": "所有测试通过"}
                ],
                "capability_tags": ["python-core"],
                "source_trace": {"question_source": "agent-injected"},
                "question_role": "project_task",
                "difficulty_level": "medium",
                "difficulty_label": "中等题",
                "difficulty_score": 2,
                "difficulty_reason": "需要实现列表过滤并保证不修改原列表，覆盖基础语法和副作用意识。",
                "expected_failure_mode": "直接原地删除元素或没有正确处理 None，导致副作用或测试失败。",
            },
        ],
    }


def make_valid_lesson_plan_for_review() -> dict:
    """按 docs/lesson-schema.md 生成的最小通过课件。"""
    return {
        "title": "Python 变量与对象引用",
        "why_today": "理解变量引用机制是避免 Python 常见 bug 的基础。",
        "plan_execution_mode": "normal",
        "materials_used": [
            {
                "material_title": "Python编程：从入门到实践（第3版）",
                "locator": "第2章 变量和简单数据类型",
            }
        ],
        "today_focus": {
            "summary": "今天核心学习变量引用语义。",
            "focus_points": [
                {
                    "point": "变量名绑定对象引用",
                    "why_it_matters": "理解 list/dict 可变性、函数传参的前提",
                    "mastery_check": "能解释 a=[1]; b=a; b.append(2) 后 a 的值及原因",
                }
            ],
        },
        "project_driven_explanation": {
            "summary": "通过数据清洗任务展示变量引用副作用。",
            "tasks": [
                {
                    "task_name": "复现变量引用 Bug",
                    "real_context": "修改副本后发现原数据也被改了",
                    "blocker": "不清楚为什么修改副本会影响原数据",
                    "why_now": "Python 新手最常见的困惑之一",
                    "knowledge_points": ["变量引用语义"],
                    "explanation": "Python 赋值不复制对象，而是创建新引用。",
                    "how_to_apply": "使用 .copy() 创建独立副本",
                    "extension": "函数参数传递也遵循同样的引用语义",
                }
            ],
        },
        "review_suggestions": {
            "summary": "今日复习",
            "today_review": ["用自己的话解释变量引用和对象复制之间的区别"],
            "progress_review": ["回顾之前学过的 list 操作"],
            "next_actions": ["下次学习 copy 模块"],
        },
        "case_courseware": {
            "knowledge_preview_flashcards": [
                {
                    "term": "变量引用",
                    "explanation": "变量名指向内存中的对象",
                    "mastery_check": "判断：b = a 总是创建副本？（答案：错误）",
                }
            ],
            "case_background": {
                "situation": "你接手了一个数据清洗脚本，修改筛选后的列表时发现原数据也被污染了...",
                "problem_to_solve": "如何创建数据的独立副本？",
            },
            "guided_story_practice": [
                {
                    "scene": "你打开 colleague 的 Jupyter notebook",
                    "challenge": "为什么修改 filtered_data 影响 raw_data？",
                    "teaching_move": "引入 Python 变量引用模型，展示内存图",
                    "resolution": "使用 .copy() 方法创建浅拷贝",
                }
            ],
            "review_sources": [
                {
                    "material_title": "Python 官方文档",
                    "locator": "Data Model — Objects, values and types",
                    "review_focus": "理解对象标识和值的关系",
                }
            ],
            "exercise_policy": {"embedded_questions": False},
        },
        "review_targets": ["确认变量引用语义掌握"],
    }


class SchemaCompliantPassTest(unittest.TestCase):
    """验证符合 schema 的正确产物能通过 runtime 校验。"""

    def test_valid_question_artifact_passes_validation(self):
        """Step 5（验证）：规范题目应通过 validate_questions_payload。"""
        from learn_runtime.question_validation import validate_questions_payload

        artifact = make_valid_question_artifact()
        result = validate_questions_payload(artifact)

        self.assertTrue(
            result.get("valid"),
            f"规范题目应通过校验，issues={result.get('issues')}",
        )

    def test_valid_lesson_plan_passes_review(self):
        """Step 5（验证）：规范课件应通过 build_lesson_review。"""
        from learn_runtime.lesson_builder import build_lesson_review

        plan = make_valid_lesson_plan_for_review()
        result = build_lesson_review(plan)

        self.assertTrue(
            result.get("valid"),
            f"规范课件应通过校验，issues={result.get('issues')}",
        )

    def test_code_question_preflight_passes_with_correct_solution(self):
        """Step 5（验证）：solution_code 正确时 preflight 应通过。"""
        from learn_runtime.schemas import preflight_code_question_tests

        code_q = {
            "id": "test-code",
            "type": "code",
            "category": "code",
            "solution_code": "def add(a, b):\n    return a + b\n",
            "function_name": "add",
            "function_signature": "def add(a, b):",
            "public_tests": [
                {"args": [1, 2], "expected": 3},
                {"args": [-1, 1], "expected": 0},
            ],
            "hidden_tests": [
                {"args": [10, 20], "expected": 30},
            ],
        }
        issues = preflight_code_question_tests(code_q)
        self.assertEqual(
            len(issues), 0,
            f"正确解答的 preflight 不应有错误，实际 issues={issues}",
        )
