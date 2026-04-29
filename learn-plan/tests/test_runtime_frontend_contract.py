from __future__ import annotations

import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = SKILL_DIR / "frontend" / "src"


class RuntimeFrontendContractTest(unittest.TestCase):
    def test_code_submit_payload_includes_question_id_without_hidden_tests(self) -> None:
        store_source = (SRC_DIR / "store" / "runtimeStore.ts").read_text(encoding="utf-8")

        self.assertIn("fetch('./submit'", store_source)
        self.assertIn("question_id", store_source)
        self.assertIn("function_name", store_source)
        self.assertNotIn("hidden_tests", store_source)
        self.assertNotIn("test_cases: cases", store_source)

    def test_code_page_renders_structured_leetcode_fields(self) -> None:
        store_source = (SRC_DIR / "store" / "runtimeStore.ts").read_text(encoding="utf-8")
        tabs_source = (SRC_DIR / "components" / "ProblemInfoTabs.vue").read_text(encoding="utf-8")

        for field in ("problem_statement", "input_spec", "output_spec", "constraints", "examples", "public_tests"):
            self.assertIn(field, store_source)
        self.assertNotIn("hidden_tests", tabs_source)
        self.assertIn("公开测试", tabs_source)

    def test_problem_layout_has_scroll_resize_and_long_text_guards(self) -> None:
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")
        app_source = (SRC_DIR / "App.vue").read_text(encoding="utf-8")

        for marker in ("overflow-wrap: anywhere", "min-width: 0", "overflow: hidden", "overflow: auto"):
            self.assertIn(marker, style_source)
        for marker in ("column-resizer", "startColumnResize", "--sidebar-width", "--problem-width"):
            self.assertIn(marker, app_source + style_source)

    def test_problem_body_uses_unified_rich_text_renderer(self) -> None:
        rich_text_source = (SRC_DIR / "renderers" / "richText.ts").read_text(encoding="utf-8")
        tabs_source = (SRC_DIR / "components" / "ProblemInfoTabs.vue").read_text(encoding="utf-8")

        for marker in ("renderRichText", "rich-text-paragraph", "rich-text-code-block", "rich-text-inline-code", "rich-text-list", "rich-text-ordered-list", "rich-text-heading", "rich-text-formula"):
            self.assertIn(marker, rich_text_source)
        self.assertIn("renderRichText", tabs_source)
        self.assertNotIn(".replace(/\\n/g, '<br>')", tabs_source)

    def test_status_panel_renders_failure_summary_input_expected_actual_error(self) -> None:
        status_source = (SRC_DIR / "components" / "StatusPanel.vue").read_text(encoding="utf-8")

        for field in ("testCase.input", "testCase.expected", "testCase.actual", "testCase.error"):
            self.assertIn(field, status_source)

    def test_difficulty_badge_uses_four_level_contract(self) -> None:
        types_source = (SRC_DIR / "types.ts").read_text(encoding="utf-8")
        store_source = (SRC_DIR / "store" / "runtimeStore.ts").read_text(encoding="utf-8")
        sidebar_source = (SRC_DIR / "components" / "Sidebar.vue").read_text(encoding="utf-8")
        tabs_source = (SRC_DIR / "components" / "ProblemInfoTabs.vue").read_text(encoding="utf-8")
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")

        for marker in ("basic", "medium", "upper_medium", "hard"):
            self.assertIn(marker, types_source)
            self.assertIn(marker, store_source)
            self.assertIn(f".difficulty-badge.{marker}", style_source)
        self.assertIn("difficultyLevel", types_source)
        self.assertIn("difficulty_summary", store_source)
        self.assertIn("difficulty-badge", sidebar_source)
        self.assertIn("difficulty-badge", tabs_source)


if __name__ == "__main__":
    unittest.main()
