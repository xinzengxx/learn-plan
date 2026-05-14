from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_core.io import read_json, read_json_if_exists, read_json_result, write_json


class CoreIoTest(unittest.TestCase):
    def test_invalid_json_is_moved_as_broken_and_compat_read_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            path.write_text('{"broken": ', encoding="utf-8")

            result = read_json_result(path)

            self.assertEqual(result.status, "invalid_json")
            self.assertFalse(path.exists())
            self.assertTrue(result.recovery_path)
            self.assertTrue(Path(result.recovery_path or "").exists())
            self.assertEqual(read_json_if_exists(path), {})

    def test_read_json_returns_error_metadata_for_wrong_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            path.write_text(json.dumps(["not", "object"]), encoding="utf-8")

            data = read_json(path)

            self.assertEqual(data["_json_read_error"]["status"], "wrong_shape")
            self.assertIn("expected JSON object", data["_json_read_error"]["error"])

    def test_write_json_replaces_file_atomically_without_temp_leftovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "state.json"

            write_json(path, {"ok": True})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"ok": True})
            self.assertEqual([item.name for item in root.iterdir() if item.name.startswith(".state.json.tmp-")], [])


if __name__ == "__main__":
    unittest.main()
