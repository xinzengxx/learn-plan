from __future__ import annotations

import unittest
from pathlib import Path
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.mysql_runtime import build_python_call_case, reconstruct_dataset_value


class FakeCursor:
    description = [("a",), ("b",)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql):
        self.sql = sql

    def fetchall(self):
        return [(1, 10), (2, 20)]


class FakeConnection:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return FakeCursor()

    def close(self):
        self.closed = True


class PythonTabularRuntimeContractTest(unittest.TestCase):
    def _context(self) -> dict[str, object]:
        return {
            "materialized_datasets": {
                "schema_version": "learn-plan.materialized_dataset.v1",
                "datasets": [
                    {
                        "dataset_id": "df-public",
                        "kind": "dataframe",
                        "visibility": "public",
                        "logical_name": "features",
                        "physical_table": "learn_ut__features",
                        "columns": [
                            {"name": "a", "dtype": "int", "mysql_type": "BIGINT"},
                            {"name": "b", "dtype": "int", "mysql_type": "BIGINT"},
                        ],
                        "reconstruction": {"index": {"kind": "range"}},
                    }
                ],
            },
            "mysql_runtime": {"config": {"database": "learn_test"}},
        }

    def test_reconstruct_dataset_value_returns_dataframe(self) -> None:
        import learn_runtime.mysql_runtime as mysql_runtime

        original_connect = mysql_runtime.connect_mysql
        connection = FakeConnection()
        mysql_runtime.connect_mysql = lambda runtime_context: connection
        try:
            frame = reconstruct_dataset_value("df-public", self._context(), "public")
        finally:
            mysql_runtime.connect_mysql = original_connect

        self.assertTrue(connection.closed)
        self.assertEqual(list(frame.columns), ["a", "b"])
        self.assertEqual(frame.to_dict(orient="records"), [{"a": 1, "b": 10}, {"a": 2, "b": 20}])

    def test_build_python_call_case_turns_dataset_binding_into_kwarg(self) -> None:
        import learn_runtime.mysql_runtime as mysql_runtime

        original_connect = mysql_runtime.connect_mysql
        mysql_runtime.connect_mysql = lambda runtime_context: FakeConnection()
        try:
            call_case = build_python_call_case(
                {
                    "case_id": "p1",
                    "visibility": "public",
                    "parameters": {"df": {"dataset_ref": "df-public"}, "threshold": {"value": 10}},
                    "expected": 30,
                },
                self._context(),
            )
        finally:
            mysql_runtime.connect_mysql = original_connect

        self.assertIn("kwargs", call_case)
        self.assertEqual(call_case["kwargs"]["threshold"], 10)
        self.assertEqual(call_case["kwargs"]["df"].shape, (2, 2))
        self.assertEqual(call_case["expected"], 30)


if __name__ == "__main__":
    unittest.main()
