from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.lesson_builder import (
    build_daily_lesson_plan,
    build_daily_lesson_prompt,
    build_lesson_quality_artifact,
    build_lesson_review,
    render_daily_lesson_plan_markdown,
)


class DailyLessonCoursewareContractTest(unittest.TestCase):
    def _plan_source(self) -> dict[str, object]:
        return {
            "current_stage": "Python 基础",
            "day": "Day 1",
            "today_topic": "函数抽象",
            "mainline_goal": "用 Python 完成数据处理脚本",
            "new_learning": ["函数参数", "返回值"],
            "review": ["变量与列表"],
            "exercise_focus": ["函数改写题"],
            "preference_state": {"teaching_pattern": "adaptive"},
        }

    def _segments(self) -> list[dict[str, object]]:
        return [
            {
                "segment_id": "seg-func",
                "label": "函数抽象",
                "material_title": "Python 教程",
                "material_source_name": "Python 教程",
                "material_kind": "tutorial",
                "source_status": "extracted",
                "source_summary": "函数用于封装重复逻辑",
                "source_key_points": ["函数参数", "返回值"],
                "source_examples": ["老板要求小林把三段重复清洗逻辑改成一个函数"],
                "source_pitfalls": ["只打印结果而不返回值"],
                "locator": {"chapter": "函数", "sections": ["定义函数"]},
            }
        ]

    def test_daily_lesson_builds_metadata_fields(self) -> None:
        plan = build_daily_lesson_plan(
            "Python",
            self._plan_source(),
            self._segments(),
            {"reading_checklist": ["解释函数参数和返回值"]},
        )
        self.assertIn("title", plan)
        self.assertIn("today_focus", plan)
        self.assertIn("review_suggestions", plan)

    def test_lesson_quality_review_requires_extracted_source_in_normal_mode(self) -> None:
        artifact = build_lesson_quality_artifact(
            {
                "title": "test",
                "materials_used": [{"material_title": "Python 教程", "locator": "函数", "source_status": "fallback-metadata"}],
                "today_focus": {"summary": "s", "focus_points": [{"point": "函数参数", "why_it_matters": "w", "mastery_check": "能解释参数"}]},
                "review_suggestions": {"summary": "s", "today_review": ["复述函数参数"], "progress_review": ["变量与列表"]},
                "review_targets": ["函数参数"],
                "plan_execution_mode": "normal",
                "why_today": "test",
            }
        )
        issues = artifact.get("quality_review", {}).get("issues", [])
        self.assertIn("today-lesson.material-source-not-extracted", issues)
        self.assertNotIn("today-lesson.case-courseware-missing", issues)
        self.assertNotIn("today-lesson.project-driven-explanation-missing", issues)

    def test_lesson_review_rejects_placeholder_locator(self) -> None:
        review = build_lesson_review(
            {
                "title": "test",
                "materials_used": [
                    {
                        "material_title": "Python 教程",
                        "locator": "待补充定位",
                        "source_status": "extracted",
                        "source_excerpt": "函数用于封装重复逻辑，并通过参数接收输入。",
                    }
                ],
                "today_focus": {"summary": "s", "focus_points": [{"point": "函数参数", "why_it_matters": "w", "mastery_check": "能解释参数"}]},
                "review_suggestions": {"summary": "s", "today_review": ["复述函数参数"], "progress_review": ["变量与列表"]},
                "review_targets": ["函数参数"],
                "plan_execution_mode": "normal",
                "why_today": "test",
            }
        )
        self.assertIn("today-lesson.material-locator-placeholder", review["issues"])

    def test_default_lesson_does_not_generate_story_case_courseware(self) -> None:
        plan = build_daily_lesson_plan(
            "Python",
            self._plan_source(),
            self._segments(),
            {"reading_checklist": ["解释函数参数和返回值"]},
        )

        self.assertNotIn("case_courseware", plan)

    def test_markdown_renders_metadata_as_public_courseware(self) -> None:
        plan = build_daily_lesson_plan(
            "Python",
            self._plan_source(),
            self._segments(),
            {"reading_checklist": ["解释函数参数和返回值"]},
        )
        markdown = render_daily_lesson_plan_markdown(plan)
        self.assertIn("## 今日定位", markdown)
        self.assertIn("## 本期知识点讲解", markdown)
        self.assertNotIn("## 跟着案例学", markdown)

    def test_lesson_review_validates_hollow_case_when_present(self) -> None:
        review = build_lesson_review(
            {
                "title": "test",
                "materials_used": [{"material_title": "Python 教程", "locator": "函数"}],
                "today_focus": {"summary": "s", "focus_points": [{"point": "return", "why_it_matters": "w", "mastery_check": "能解释 return"}]},
                "review_suggestions": {"summary": "s", "today_review": ["复述 return"], "progress_review": ["函数基础"]},
                "review_targets": ["return"],
                "plan_execution_mode": "normal",
                "why_today": "test",
                "case_courseware": {
                    "knowledge_preview_flashcards": [{"front": "return", "prompt": "今天学什么"}],
                    "case_background": {"situation": "", "problem_to_solve": ""},
                    "review_sources": [{"material_title": "Python 教程"}],
                    "exercise_policy": {"embedded_questions": False},
                },
            }
        )
        self.assertIn("today-lesson.case-background-hollow", review["issues"])
        warnings = review.get("warnings", [])
        self.assertIn("today-lesson.flashcard-mastery-check-missing", warnings)

    def test_prompt_focuses_on_metadata(self) -> None:
        prompt = build_daily_lesson_prompt(
            {"topic": "Python", "today_topic": "函数", "plan_execution_mode": "normal", "teaching_pattern": "adaptive"},
            {"title": "Day 1", "today_focus": {}, "materials_used": [], "review_suggestions": {}, "current_stage": "1", "study_mode": "复习+推进", "why_today": "test"},
        )
        self.assertIn("today_focus", prompt)
        self.assertIn("review_suggestions", prompt)
        self.assertIn("练习题由独立题目模块生成", prompt)


if __name__ == "__main__":
    unittest.main()
