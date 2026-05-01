from __future__ import annotations

import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = SKILL_DIR / "frontend" / "src"


class RuntimeFrontendEditorStatusContractTest(unittest.TestCase):
    def test_code_editor_uses_monaco_with_textarea_fallback(self) -> None:
        workspace_source = (SRC_DIR / "components" / "AnswerWorkspace.vue").read_text(encoding="utf-8")

        for marker in (
            "monacoEditor",
            "ensureMonaco",
            "./node_modules/monaco-editor/min/vs/loader.js",
            "language: editorLanguage.value",
            "tabSize: 4",
            "insertSpaces: true",
            "window.monaco.editor.setTheme",
            "monaco-fallback",
        ):
            self.assertIn(marker, workspace_source)

    def test_status_cards_are_forced_to_one_row_and_test_cards_do_not_clip(self) -> None:
        style_source = (SRC_DIR / "style.css").read_text(encoding="utf-8")

        self.assertNotIn("max-height: 220px", style_source)
        for marker in (".result-header", ".case-tabs", ".case-detail", "white-space: pre-wrap"):
            self.assertIn(marker, style_source)


if __name__ == "__main__":
    unittest.main()
