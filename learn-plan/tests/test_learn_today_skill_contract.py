from __future__ import annotations

import unittest
from pathlib import Path


class LearnTodaySkillContractTest(unittest.TestCase):
    def test_skill_contract_describes_case_courseware_markdown(self) -> None:
        skill_path = Path.home() / ".claude/skills/learn-today/SKILL.md"
        text = skill_path.read_text(encoding="utf-8")

        for token in (
            "lesson.html",
            "lesson-html.json",
            "/long-output-html 兼容 JSON",
            "Part 1：往期复习",
            "Part 2：本期知识点讲解",
            "Part 3：本期内容回看",
            "原文短摘录",
            "key_quote 或 review_focus",
        ):
            self.assertIn(token, text)
        self.assertIn("生成练习题（三步流程）", text)
        self.assertIn("出题规划（子 Agent A）", text)
        self.assertIn("生成题目（子 Agent B）", text)
        self.assertIn("审题（子 Agent C）", text)
        self.assertIn("lesson-artifact.json", text)
        self.assertIn("source_trace", text)
        self.assertNotIn("learn-today-YYYY-MM-DD.ipynb", text)
        self.assertNotIn("learn-today-YYYY-MM-DD.md", text)


if __name__ == "__main__":
    unittest.main()
