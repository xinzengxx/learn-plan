from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_runtime.mysql_materializer import materialize_dataset_artifact, write_materialized_dataset
from session_orchestrator import maybe_materialize_datasets


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql):
        self.connection.executed.append(sql)

    def executemany(self, sql, values):
        self.connection.executed.append(sql)
        self.connection.values.extend(values)


class FakeConnection:
    def __init__(self):
        self.executed: list[str] = []
        self.values: list[list[object]] = []
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class MySQLMaterializerTest(unittest.TestCase):
    def _artifact(self) -> dict[str, object]:
        return {
            "schema_version": "learn-plan.dataset_artifact.v1",
            "datasets": [
                {
                    "dataset_id": "orders-public",
                    "kind": "sql_table",
                    "visibility": "public",
                    "logical_name": "orders",
                    "columns": [
                        {"name": "order_id", "dtype": "int", "mysql_type": "BIGINT"},
                        {"name": "amount", "dtype": "float", "mysql_type": "DOUBLE"},
                    ],
                    "rows": [
                        {"order_id": 1, "amount": 10.5},
                        {"order_id": 2, "amount": 20.0},
                    ],
                }
            ],
        }

    def test_empty_dataset_artifact_does_not_require_mysql(self) -> None:
        result = materialize_dataset_artifact({"schema_version": "learn-plan.dataset_artifact.v1", "datasets": []})

        self.assertEqual(result["datasets"], [])
        self.assertFalse(result["mysql_runtime"]["configured"])

    def test_materialize_dataset_creates_physical_table_and_rows(self) -> None:
        import learn_runtime.mysql_materializer as materializer

        connection = FakeConnection()
        original_connect = materializer._connect_mysql
        materializer._connect_mysql = lambda config: connection
        try:
            result = materialize_dataset_artifact(
                self._artifact(),
                mysql_config={"database": "learn_test", "table_prefix": "learn_ut"},
                session_dir="/tmp/session-a",
            )
        finally:
            materializer._connect_mysql = original_connect

        self.assertTrue(connection.closed)
        self.assertEqual(len(result["datasets"]), 1)
        record = result["datasets"][0]
        self.assertEqual(record["logical_name"], "orders")
        self.assertEqual(record["row_count"], 2)
        self.assertTrue(str(record["physical_table"]).startswith("learn_ut__"))
        self.assertIn("DROP TABLE IF EXISTS", connection.executed[0])
        self.assertIn("CREATE TABLE IF NOT EXISTS", connection.executed[1])
        self.assertIn("INSERT INTO", connection.executed[2])
        self.assertEqual(connection.values, [[0, 1, 10.5], [1, 2, 20.0]])

    def test_orchestrator_writes_materialized_dataset_path(self) -> None:
        import learn_runtime.mysql_materializer as materializer

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "session"
            dataset_path = Path(tmpdir) / "dataset-artifact.json"
            dataset_path.write_text(json.dumps(self._artifact()), encoding="utf-8")
            connection = FakeConnection()
            original_connect = materializer._connect_mysql
            materializer._connect_mysql = lambda config: connection
            try:
                args = argparse.Namespace(
                    skip_materialize=False,
                    materialized_dataset_json=None,
                    dataset_artifact_json=str(dataset_path),
                    mysql_config_json=None,
                )
                maybe_materialize_datasets(args, session_dir)
            finally:
                materializer._connect_mysql = original_connect

            output_path = session_dir / "materialized-dataset.json"
            self.assertEqual(args.materialized_dataset_json, str(output_path))
            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "learn-plan.materialized_dataset.v1")

    def test_write_materialized_dataset_persists_json(self) -> None:
        import learn_runtime.mysql_materializer as materializer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "materialized.json"
            connection = FakeConnection()
            original_connect = materializer._connect_mysql
            materializer._connect_mysql = lambda config: connection
            try:
                write_materialized_dataset(self._artifact(), output_path, mysql_config={"database": "learn_test"}, session_dir=tmpdir)
            finally:
                materializer._connect_mysql = original_connect

            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["datasets"]), 1)


if __name__ == "__main__":
    unittest.main()
