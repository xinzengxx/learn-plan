from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.material_selection import select_material_segments


class MaterialSelectionGroundingTest(unittest.TestCase):
    def _material(self, local_path: str | None) -> dict:
        return {
            "id": "python-main",
            "title": "Python Main",
            "local_path": local_path,
            "cache_status": "cached" if local_path else "metadata-only",
            "selection_status": "confirmed",
            "role_in_plan": "mainline",
            "capability_alignment": ["pathlib"],
            "reading_segments": [
                {
                    "segment_id": "seg-pathlib",
                    "label": "pathlib read_text",
                    "purpose": "学习 pathlib read_text",
                    "locator": {"sections": ["pathlib read_text"]},
                    "checkpoints": ["解释 read_text 如何读取文本"],
                    "recommended_for": {"days": ["Day 1"]},
                }
            ],
        }

    def test_normal_mode_keeps_extracted_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "lesson.md"
            source.write_text("pathlib read_text 可以读取文本文件内容。", encoding="utf-8")
            plan_source = {
                "topic": "Python",
                "domain": "general-cs",
                "day": "Day 1",
                "new_learning": ["pathlib read_text"],
                "plan_execution_mode": "normal",
            }

            selected, _ = select_material_segments([self._material(str(source))], plan_source)

        self.assertTrue(selected)
        self.assertEqual(selected[0]["source_status"], "extracted")
        self.assertEqual(plan_source["plan_execution_mode"], "normal")
        self.assertEqual(plan_source["material_alignment"]["status"], "aligned")

    def test_normal_mode_degrades_when_only_metadata_fallback_exists(self) -> None:
        plan_source = {
            "topic": "Python",
            "domain": "general-cs",
            "day": "Day 1",
            "new_learning": ["pathlib read_text"],
            "plan_execution_mode": "normal",
        }

        selected, _ = select_material_segments([self._material(None)], plan_source)

        self.assertEqual(selected, [])
        self.assertEqual(plan_source["plan_execution_mode"], "prestudy")
        self.assertTrue(any("缺少已提取的材料片段" in blocker for blocker in plan_source["plan_blockers"]))
        self.assertEqual(plan_source["material_alignment"]["status"], "degraded")
        self.assertIn("fallback-metadata", plan_source["material_alignment"]["source_statuses"])


if __name__ == "__main__":
    unittest.main()
