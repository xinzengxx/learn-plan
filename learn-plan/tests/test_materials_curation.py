from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_materials.curation import build_material_curation


class MaterialsCurationTest(unittest.TestCase):
    def test_cached_confirmed_material_becomes_mainline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "lesson.md"
            source.write_text("pathlib lets Python code work with file paths. read_text reads files.")
            curation = build_material_curation(
                {
                    "entries": [
                        {
                            "id": "python-main",
                            "title": "Python Main",
                            "kind": "tutorial",
                            "selection_status": "confirmed",
                            "role_in_plan": "mainline",
                            "availability": "cached",
                            "cache_status": "cached",
                            "local_path": str(source),
                            "capability_alignment": ["syntax"],
                            "reading_segments": [
                                {
                                    "segment_id": "seg-1",
                                    "label": "pathlib",
                                    "purpose": "学习 pathlib",
                                    "locator": {"sections": ["pathlib"]},
                                    "checkpoints": ["解释 read_text"],
                                }
                            ],
                        }
                    ]
                },
                topic="Python",
                goal="通过考试",
                level="入门",
                diagnostic={"diagnostic_result": {"recommended_entry_level": "入门", "capability_assessment": [{"capability_id": "syntax", "current_level": "薄弱"}]}},
            )

            self.assertEqual(curation["status"], "needs-user-confirmation")
            self.assertFalse(curation["user_confirmation"]["confirmed"])
            item = curation["materials"][0]
            self.assertEqual(item["role"], "mainline")
            self.assertEqual(item["fit"]["diagnostic_gap_alignment"], ["syntax"])
            self.assertTrue(item["excerpt_briefs"])

    def test_metadata_only_material_stays_candidate(self) -> None:
        curation = build_material_curation(
            {
                "entries": [
                    {
                        "id": "online",
                        "title": "Online",
                        "selection_status": "candidate",
                        "role_in_plan": "optional",
                        "availability": "metadata-only",
                        "cache_status": "metadata-only",
                    }
                ]
            },
            topic="Python",
            goal="通过考试",
            level="入门",
        )

        item = curation["materials"][0]
        self.assertEqual(item["role"], "optional-candidate")
        self.assertIn("当前仅有在线元数据", item["risks"][0])


if __name__ == "__main__":
    unittest.main()
