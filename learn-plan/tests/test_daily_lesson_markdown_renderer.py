from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.lesson_builder import render_daily_lesson_plan_markdown


class DailyLessonMarkdownRendererTest(unittest.TestCase):
    def test_python_return_none_case_is_rendered_as_story_courseware(self) -> None:
        markdown = render_daily_lesson_plan_markdown(
            {
                "title": "Day 1：return、print 与 None",
                "materials_used": [
                    {"material_title": "Python 教程", "locator": "函数 / return 语句", "match_reason": "解释函数如何把结果交给测试"}
                ],
                "today_focus": {
                    "focus_points": [
                        {"point": "return", "why_it_matters": "测试只能拿到函数返回值", "mastery_check": "能说明 return 如何影响测试断言"},
                        {"point": "print", "why_it_matters": "print 只是显示信息", "mastery_check": "能区分显示结果和返回结果"},
                        {"point": "None", "why_it_matters": "没有 return 的函数会返回 None", "mastery_check": "能定位隐藏测试拿到 None 的原因"},
                    ]
                },
                "case_courseware": {
                    "knowledge_preview_flashcards": [
                        {"front": "return", "prompt": "函数怎样把结果交给调用者？", "mastery_check": "能写出返回计算结果的函数"},
                        {"front": "print", "prompt": "print 的输出会不会成为测试结果？", "mastery_check": "能解释 print 与 return 的区别"},
                        {"front": "None", "prompt": "为什么测试拿到 None？", "mastery_check": "能修复缺少 return 的函数"},
                    ],
                    "case_background": {
                        "protagonist": "学习者",
                        "situation": "刚做完一道 Python 代码题，屏幕上打印出了正确数字，但平台测试仍然失败。",
                        "problem_to_solve": "代码题返回 None，隐藏测试无法通过。",
                    },
                    "guided_story_practice": [
                        {
                            "scene": "先复现测试失败",
                            "challenge": "函数内部只 print 结果，测试断言拿到 None。",
                            "teaching_move": "引入 return：调用者和测试框架只能接收返回值。",
                            "resolution": "把 print(total) 改成 return total，再用断言验证。",
                            "knowledge_points": ["return", "print", "None", "测试"],
                        }
                    ],
                    "review_sources": [
                        {"material_title": "Python 教程", "locator": "函数 / return 语句", "review_focus": "return、print、None 与测试断言"}
                    ],
                    "exercise_policy": {"embedded_questions": False, "question_module": "练习题由独立题目模块生成"},
                },
            }
        )

        self.assertIn("## 讲解背景", markdown)
        self.assertIn("## 核心问题", markdown)
        self.assertIn("## 本期知识点讲解", markdown)
        for token in ("return", "print", "None", "测试"):
            self.assertIn(token, markdown)
        self.assertIn("代码题返回 None", markdown)
        self.assertIn("练习题由独立题目模块生成", markdown)


if __name__ == "__main__":
    unittest.main()
