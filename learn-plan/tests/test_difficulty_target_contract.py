from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from session_bootstrap import parse_difficulty_target


class DifficultyTargetContractTest(unittest.TestCase):
    def test_legacy_string_target_normalizes_aliases(self) -> None:
        target = parse_difficulty_target("concept easy/medium，code medium/hard")

        self.assertEqual(target["concept"], ["basic", "medium"])
        self.assertEqual(target["code"], ["medium", "hard"])
        self.assertEqual(target["allowed_levels"], ["basic", "medium", "upper_medium", "hard"])

    def test_structured_target_preserves_distribution_and_range(self) -> None:
        target = parse_difficulty_target(
            {
                "concept": ["基础", "进阶"],
                "code": ["upper-medium", "hard"],
                "allowed_levels": ["easy", "medium", "upper_medium"],
                "allowed_range": {"concept": ["easy"], "code": ["medium", "hard"]},
                "recommended_distribution": {
                    "concept": {"easy": 1, "medium": "2"},
                    "code": {"upper-medium": 1},
                },
            }
        )

        self.assertEqual(target["concept"], ["basic", "medium"])
        self.assertEqual(target["code"], ["upper_medium", "hard"])
        self.assertEqual(target["allowed_levels"], ["basic", "medium", "upper_medium"])
        self.assertEqual(target["allowed_range"], {"concept": ["basic"], "code": ["medium", "hard"]})
        self.assertEqual(target["recommended_distribution"], {"concept": {"basic": 1, "medium": 2}, "code": {"upper_medium": 1}})


if __name__ == "__main__":
    unittest.main()
