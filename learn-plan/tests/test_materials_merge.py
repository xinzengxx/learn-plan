from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_materials.merge import merge_material_entries


class MaterialsMergeTest(unittest.TestCase):
    def test_preserves_existing_downloaded_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cached = Path(tmpdir) / "book.pdf"
            cached.write_bytes(b"%PDF-1.4 test")
            merged = merge_material_entries(
                [
                    {
                        "id": "book",
                        "local_path": str(cached),
                        "cache_status": "cached",
                        "cached_at": "2026-04-29T00:00:00",
                    }
                ],
                [
                    {
                        "id": "book",
                        "title": "Book",
                        "topic": "Python",
                        "domain": "general-cs",
                        "local_path": str(Path(tmpdir) / "book"),
                        "role_in_plan": "mainline",
                        "selection_status": "confirmed",
                        "availability": "local-downloadable",
                        "reading_segments": [],
                    }
                ],
            )

            self.assertEqual(merged[0]["local_path"], str(cached))
            self.assertEqual(merged[0]["cache_status"], "cached")
            self.assertEqual(merged[0]["role_in_plan"], "mainline")


if __name__ == "__main__":
    unittest.main()
