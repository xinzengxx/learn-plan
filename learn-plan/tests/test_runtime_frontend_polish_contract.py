from __future__ import annotations

import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = SKILL_DIR / "frontend" / "src"


class RuntimeFrontendPolishContractTest(unittest.TestCase):
    def test_status_panel_has_result_header_above_case_tabs(self) -> None:
        status_source = (SRC_DIR / "components" / "StatusPanel.vue").read_text(encoding="utf-8")
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")

        result_index = status_source.index("result-header")
        case_tabs_index = status_source.index("case-tabs")
        self.assertLess(result_index, case_tabs_index)
        for marker in ("testCase", "latestRecord", "failure_types", "resultLabel", "activeCases"):
            self.assertIn(marker, status_source)
        for marker in (".result-header", "white-space: pre-wrap", "font-family: var(--mono-font)"):
            self.assertIn(marker, style_source)

    def test_problem_description_uses_structured_longform_sections(self) -> None:
        tabs_source = (SRC_DIR / "components" / "ProblemInfoTabs.vue").read_text(encoding="utf-8")
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")

        for marker in (
            "statement-card hero",
            "io-spec-grid",
            "io-spec-card input-spec",
            "io-spec-card output-spec",
            "ExampleDisplaySection",
            "example-card",
            "constraint-list",
        ):
            self.assertIn(marker, tabs_source + style_source)
        for marker in ("rich-text-code-block", "rich-text-inline-code", "rich-text-formula"):
            self.assertIn(marker, style_source)

    def test_monaco_uses_custom_paper_and_ink_themes(self) -> None:
        workspace_source = (SRC_DIR / "components" / "AnswerWorkspace.vue").read_text(encoding="utf-8")

        for marker in (
            "defineTheme",
            "learn-paper",
            "learn-ink",
            "registerLearnMonacoThemes",
            "theme: props.themeMode === 'paper' ? 'learn-paper' : 'learn-ink'",
            "window.monaco.editor.setTheme(themeMode === 'paper' ? 'learn-paper' : 'learn-ink')",
        ):
            self.assertIn(marker, workspace_source)

    def test_font_and_code_example_blocks_are_distinct(self) -> None:
        tabs_source = (SRC_DIR / "components" / "ProblemInfoTabs.vue").read_text(encoding="utf-8")
        example_source = (SRC_DIR / "components" / "ExampleDisplaySection.vue").read_text(encoding="utf-8")
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")
        types_source = (SRC_DIR / "types.ts").read_text(encoding="utf-8")
        combined_source = tabs_source + example_source + style_source + types_source

        self.assertIn("JetBrainsMono Nerd Font Mono", style_source)
        for marker in (
            "RuntimeExampleDisplay",
            "exampleDisplays",
            "example-io-grid",
            "input-block polished",
            "output-block polished",
            "example-parameter-row",
            "example-table-input-card",
        ):
            self.assertIn(marker, combined_source)
        self.assertIn(".demo-shell", style_source)
        self.assertIn("font-family: var(--ui-font)", style_source)
        self.assertIn("grid-template-columns: 1fr", style_source)
        self.assertNotIn(".example-io-grid {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(0, 1fr));", style_source)
        self.assertNotIn(".public-test-card {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(0, 1fr));", style_source)
        for marker in ("white-space: pre-wrap", "font-family: var(--mono-font)"):
            self.assertIn(marker, style_source)

    def test_type_badge_description_rhythm_and_terminal_output_are_clear(self) -> None:
        tabs_source = (SRC_DIR / "components" / "ProblemInfoTabs.vue").read_text(encoding="utf-8")
        status_source = (SRC_DIR / "components" / "StatusPanel.vue").read_text(encoding="utf-8")
        store_source = (SRC_DIR / "store" / "runtimeStore.ts").read_text(encoding="utf-8")
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")
        server_source = (SKILL_DIR / "templates" / "server.py").read_text(encoding="utf-8")

        for marker in ("questionTypeMeta", "type-badge-label", "type-badge-code", "代码题", "选择题", "判断题"):
            self.assertIn(marker, tabs_source)
        self.assertIn("min-width", style_source)
        self.assertIn("white-space: nowrap", style_source)
        self.assertIn(".type-badge {", style_source)
        self.assertNotIn(".type-badge,\n.draft-chip", style_source)
        for marker in (".rich-text", "line-height: 1.68", "margin-top"):
            self.assertIn(marker, style_source)
        for marker in ("terminalOutput", "latestRecord.terminalOutput", "result-header", "case-detail"):
            self.assertIn(marker, status_source + store_source)
        self.assertNotIn("答案正确。", status_source)
        for marker in ("run_cases", "input_repr", "actual_repr"):
            self.assertIn(marker, server_source)
        self.assertNotIn("testCase.note", status_source)
        self.assertNotIn("note: testCase.note", store_source)
        self.assertNotIn("note: testCase.capability_tags", store_source)


if __name__ == "__main__":
    unittest.main()
