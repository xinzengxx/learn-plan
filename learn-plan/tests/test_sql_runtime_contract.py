from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.mysql_runtime import submit_sql, validate_select_query
from session_bootstrap import ensure_runtime_support_modules


class FakeConnection:
    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql):
        self.description = [("value",)]
        self.rows = [(1,)] if "expected_hidden" not in sql else [(2,)]

    def fetchmany(self, size):
        return self.rows

    def close(self):
        pass


class SqlRuntimeContractTest(unittest.TestCase):
    def test_select_only_rejects_writes_and_multi_statement(self) -> None:
        self.assertEqual(validate_select_query("SELECT 1;"), "SELECT 1")
        with self.assertRaisesRegex(Exception, "只允许单条"):
            validate_select_query("SELECT 1; SELECT 2")
        with self.assertRaisesRegex(Exception, "只允许单条"):
            validate_select_query("SELECT 1 FROM users; DROP TABLE users")
        with self.assertRaisesRegex(Exception, "只允许 SELECT"):
            validate_select_query("UPDATE users SET name = 'x'")

    def test_submit_sql_hidden_failure_is_safe(self) -> None:
        import learn_runtime.mysql_runtime as mysql_runtime

        original_connect = mysql_runtime.connect_mysql
        mysql_runtime.connect_mysql = lambda runtime_context: FakeConnection()
        try:
            result = submit_sql(
                {"id": "sql-q", "type": "sql", "reference_sql": "SELECT 1"},
                "SELECT 1",
                {
                    "parameter_artifact": {
                        "schema_version": "learn-plan.parameter_artifact.v1",
                        "questions": [
                            {
                                "question_id": "sql-q",
                                "cases": [
                                    {"case_id": "h1", "visibility": "hidden", "parameters": {}, "expected_sql": "SELECT expected_hidden"}
                                ],
                            }
                        ],
                    }
                },
            )
        finally:
            mysql_runtime.connect_mysql = original_connect

        self.assertFalse(result["all_passed"])
        self.assertEqual(result["total_hidden_count"], 1)
        summary = result["failed_case_summaries"][0]
        self.assertEqual(summary["category"], "hidden")
        self.assertNotIn("input", summary)
        self.assertNotIn("expected_repr", summary)
        self.assertNotIn("actual_repr", summary)
        self.assertNotIn("expected_hidden", repr(result))

    def test_bootstrap_copies_runtime_support_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            changed = ensure_runtime_support_modules(session_dir, overwrite=False)
            self.assertTrue(changed)
            self.assertTrue((session_dir / "learn_runtime" / "__init__.py").exists())
            self.assertTrue((session_dir / "learn_runtime" / "display_values.py").exists())
            self.assertTrue((session_dir / "learn_runtime" / "mysql_runtime.py").exists())
            init_source = (session_dir / "learn_runtime" / "__init__.py").read_text(encoding="utf-8")
            self.assertNotIn("material_selection", init_source)
            spec = importlib.util.spec_from_file_location(
                "session_mysql_runtime",
                session_dir / "learn_runtime" / "mysql_runtime.py",
            )
            self.assertIsNotNone(spec)


if __name__ == "__main__":
    unittest.main()
