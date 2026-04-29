from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from session_orchestrator import write_daily_lesson_plan


class SessionOrchestratorNotebookOutputTest(unittest.TestCase):
    def test_write_daily_lesson_plan_produces_html_only(self) -> None:
        """新管线：write_daily_lesson_plan 只产出 .html，不再生成 .ipynb 和 .md 副本。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Learn Plan\n", encoding="utf-8")
            session_dir = root / "sessions" / "2026-04-25"
            session_dir.mkdir(parents=True)

            # 提供有效的 lesson-html.json
            lesson_json_path = root / "lesson-html.json"
            import json
            lesson_json_path.write_text(json.dumps({
                "title": "test",
                "sections": [
                    {"type": "body", "title": "Part 1 往期复习", "content": "上一期学习 return 和 None，本期继续用函数契约衔接。" * 12},
                    {"type": "body", "title": "Part 2 本期知识点讲解", "content": "通过 `return` 示例讲解函数返回值。\n\n- 先观察 print 误区\n- 再写 return\n- 最后测试结果" * 10},
                    {"type": "body", "title": "Part 3 本期内容回看", "content": "参考资料：Python 教程 第 4 章 P.12 paragraph 2；key_quote 原文摘录：The return statement returns with a value from a function. 回看重点是函数定义和 return 语句。" * 8},
                ]
            }, ensure_ascii=False), encoding="utf-8")

            payload = {
                "date": "2026-04-25",
                "plan_source": {
                    "daily_lesson_plan": {
                        "title": "Day 1：return 与 None",
                        "current_stage": "阶段 1",
                        "today_focus": {"summary": "修复返回 None", "focus_points": [{"point": "return", "mastery_check": "能返回结果"}]},
                        "case_courseware": {
                            "knowledge_preview_flashcards": [{"front": "return", "prompt": "如何返回结果？", "mastery_check": "能写 return"}],
                            "case_background": {"protagonist": "学习者", "situation": "代码题打印正确但测试失败。", "problem_to_solve": "函数返回 None。"},
                            "guided_story_practice": [{"scene": "复现失败", "challenge": "只 print", "teaching_move": "引入 return", "resolution": "return 计算结果", "knowledge_points": ["return", "None"]}],
                            "review_sources": [{"material_title": "Python 教程", "locator": "函数", "review_focus": "return"}],
                            "exercise_policy": {"embedded_questions": False, "question_module": "练习题由独立题目模块生成"},
                        },
                    }
                },
            }

            artifact_path = write_daily_lesson_plan(plan_path, payload, session_dir, lesson_html_json=str(lesson_json_path))

            # lesson.html 产在 session_dir 下
            self.assertEqual(artifact_path.name, "lesson.html")
            self.assertTrue(artifact_path.exists())
            self.assertEqual(payload["plan_source"]["daily_plan_artifact_path"], str(artifact_path))
            self.assertEqual(payload["plan_source"]["lesson_path"], str(artifact_path))
            self.assertIsNone(payload["plan_source"]["lesson_notebook_path"])
            self.assertIsNone(payload["plan_source"]["lesson_markdown_path"])

    def test_write_daily_lesson_plan_raises_without_lesson_html_json(self) -> None:
        """未提供 --lesson-html-json 时，直接 raise ValueError 而不是静默回退。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Learn Plan\n", encoding="utf-8")
            session_dir = root / "sessions" / "2026-04-25"
            session_dir.mkdir(parents=True)
            payload = {"date": "2026-04-25", "plan_source": {}}

            with self.assertRaises(ValueError) as ctx:
                write_daily_lesson_plan(plan_path, payload, session_dir)
            self.assertIn("lesson-html-json", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
