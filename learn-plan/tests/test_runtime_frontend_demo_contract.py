from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = SKILL_DIR / "frontend"
SRC_DIR = FRONTEND_DIR / "src"


class RuntimeFrontendDemoContractTest(unittest.TestCase):
    def test_demo_project_is_vite_vue_typescript(self) -> None:
        package_data = json.loads((FRONTEND_DIR / "package.json").read_text(encoding="utf-8"))
        dependencies = package_data.get("dependencies", {}) | package_data.get("devDependencies", {})

        self.assertEqual(package_data["type"], "module")
        self.assertIn("build", package_data["scripts"])
        self.assertIn("typecheck", package_data["scripts"])
        for dependency in ("@vitejs/plugin-vue", "vite", "vue", "typescript", "vue-tsc"):
            self.assertIn(dependency, dependencies)
        self.assertTrue((FRONTEND_DIR / "index.html").exists())
        self.assertTrue((FRONTEND_DIR / "tsconfig.json").exists())
        self.assertTrue((FRONTEND_DIR / "vite.config.ts").exists())

    def test_demo_build_output_drives_production_templates(self) -> None:
        vite_config = (FRONTEND_DIR / "vite.config.ts").read_text(encoding="utf-8")

        self.assertIn("../templates/runtime-dist", vite_config)
        self.assertNotIn("dist-demo", vite_config)

        bootstrap_source = (SKILL_DIR / "session_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("RUNTIME_FRONTEND_DIST_HTML = RUNTIME_FRONTEND_DIST_DIR / \"index.html\"", bootstrap_source)
        self.assertIn("copy_file(RUNTIME_FRONTEND_DIST_HTML, session_dir / \"题集.html\"", bootstrap_source)
        self.assertIn("copy_tree(RUNTIME_FRONTEND_ASSETS_DIR, session_dir / \"assets\"", bootstrap_source)

    def test_demo_source_declares_three_zone_components(self) -> None:
        expected = [
            SRC_DIR / "main.ts",
            SRC_DIR / "App.vue",
            SRC_DIR / "style.css",
            SRC_DIR / "types.ts",
            SRC_DIR / "mockData.ts",
            SRC_DIR / "store" / "demoStore.ts",
            SRC_DIR / "components" / "Sidebar.vue",
            SRC_DIR / "components" / "ProblemInfoTabs.vue",
            SRC_DIR / "components" / "AnswerWorkspace.vue",
            SRC_DIR / "components" / "StatusPanel.vue",
            SRC_DIR / "components" / "SubmitHistory.vue",
            SRC_DIR / "renderers" / "richText.ts",
        ]
        for path in expected:
            self.assertTrue(path.exists(), path)

        app_source = (SRC_DIR / "App.vue").read_text(encoding="utf-8")
        for marker in ("<Sidebar", "<ProblemInfoTabs", "<AnswerWorkspace"):
            self.assertIn(marker, app_source)

    def test_demo_mock_data_covers_canonical_question_types(self) -> None:
        mock_source = (SRC_DIR / "mockData.ts").read_text(encoding="utf-8")
        for question_type in ("code", "single_choice", "multiple_choice", "true_false"):
            self.assertIn(f"type: '{question_type}'", mock_source)

    def test_answer_workspace_is_answer_only_without_test_results(self) -> None:
        workspace_source = (SRC_DIR / "components" / "AnswerWorkspace.vue").read_text(encoding="utf-8")

        for forbidden in ("控制台摘要", "运行 / 提交结果", "codeResultPanel", "workspace-bottom-panel", "test-result-panel", "测试情况", "未通过测试"):
            self.assertNotIn(forbidden, workspace_source)
        for required in ("运行", "提交", "作答", "editor-monaco", "choice-card"):
            self.assertIn(required, workspace_source)
        self.assertIn("v-if=\"['code', 'sql'].includes(props.question.type)\"", workspace_source)
        self.assertIn("v-else", workspace_source)

    def test_middle_tabs_and_rich_text_contract_are_explicit(self) -> None:
        tabs_source = (SRC_DIR / "components" / "ProblemInfoTabs.vue").read_text(encoding="utf-8")
        status_source = (SRC_DIR / "components" / "StatusPanel.vue").read_text(encoding="utf-8")
        for label in ("题目描述", "提交记录", "答题状态"):
            self.assertIn(label, tabs_source)
        self.assertNotIn("测试情况", tabs_source)
        self.assertNotIn("props.mode === 'tests'", tabs_source)
        for component in ("SubmitHistory", "StatusPanel"):
            self.assertIn(component, tabs_source)
        for marker in ("result-header", "case-detail", "case-tabs"):
            self.assertIn(marker, status_source)

        rich_text_source = (SRC_DIR / "renderers" / "richText.ts").read_text(encoding="utf-8")
        for marker in ("rich-text-code-block", "rich-text-inline-code", "rich-text-list", "rich-text-formula"):
            self.assertIn(marker, rich_text_source)
        self.assertIn("escapeHtml", rich_text_source)

    def test_demo_declares_two_equal_density_long_output_inspired_themes(self) -> None:
        app_source = (SRC_DIR / "App.vue").read_text(encoding="utf-8")
        sidebar_source = (SRC_DIR / "components" / "Sidebar.vue").read_text(encoding="utf-8")
        workspace_source = (SRC_DIR / "components" / "AnswerWorkspace.vue").read_text(encoding="utf-8")
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn("themeMode", app_source)
        self.assertIn("data-theme", app_source)
        self.assertIn(":theme-mode=\"themeMode\"", app_source)
        self.assertIn("@toggle-theme=\"toggleThemeMode\"", app_source)
        self.assertNotIn("theme-toggle", sidebar_source)
        for marker in ("theme-toggle", "浅色模式", "深色模式", "svg", "sun-orbit", "sun-core", "sun-ray"):
            self.assertIn(marker, workspace_source)
        for marker in ("--bg: #1a1a1a", "--bg: #fafafa", "--accent: #1a9af7", "--accent: #1677ff"):
            self.assertIn(marker, style_source)

    def test_demo_layout_supports_resizable_columns(self) -> None:
        app_source = (SRC_DIR / "App.vue").read_text(encoding="utf-8")
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")

        for marker in ("layoutSizes", "shellStyle", "startColumnResize", "pointermove", "column-resizer"):
            self.assertIn(marker, app_source)
        for marker in ("调整题目列表宽度", "调整题目描述和作答区宽度"):
            self.assertIn(marker, app_source)
        for marker in ("--sidebar-width", "--problem-width", "grid-template-columns: var(--sidebar-width) 6px minmax(440px, var(--problem-width)) 6px minmax(420px, 1fr)", "cursor: col-resize"):
            self.assertIn(marker, style_source)

    def test_demo_mock_records_include_failed_test_cases(self) -> None:
        types_source = (SRC_DIR / "types.ts").read_text(encoding="utf-8")
        mock_source = (SRC_DIR / "mockData.ts").read_text(encoding="utf-8")

        self.assertIn("TestCaseRecord", types_source)
        for marker in ("testCases", "expected", "actual", "passed: false"):
            self.assertIn(marker, mock_source)

    def test_left_sidebar_owns_status_and_test_tags(self) -> None:
        app_source = (SRC_DIR / "App.vue").read_text(encoding="utf-8")
        sidebar_source = (SRC_DIR / "components" / "Sidebar.vue").read_text(encoding="utf-8")

        self.assertIn(":latest-records=\"store.latestRecordsByQuestion.value\"", app_source)
        self.assertIn(":records=\"store.activeHistory.value\"", app_source)
        for marker in ("test-tag", "测试", "未过", "通过"):
            self.assertIn(marker, sidebar_source)

    def test_typography_overflow_and_line_number_alignment_contract(self) -> None:
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn("JetBrainsMono Nerd Font", style_source)
        self.assertNotIn("JetBrains Nero", style_source)
        for marker in ("--mono-font", "overflow-wrap: anywhere", "min-width: 0", "white-space: pre", "line-height: var(--code-line-height)"):
            self.assertIn(marker, style_source)
        self.assertNotIn("height: 22.1px", style_source)


if __name__ == "__main__":
    unittest.main()
