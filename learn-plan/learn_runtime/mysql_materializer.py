from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

MATERIALIZED_DATASET_SCHEMA_VERSION = "learn-plan.materialized_dataset.v1"
LEARN_DATASET_ARTIFACT_SCHEMA_VERSION = "learn-plan.dataset_artifact.v1"
DEFAULT_TABLE_PREFIX = "learn_s"


class MySQLMaterializerError(RuntimeError):
    pass


def materialize_dataset_artifact(
    dataset_artifact: dict[str, Any],
    *,
    mysql_config: dict[str, Any] | None = None,
    session_dir: Path | str | None = None,
) -> dict[str, Any]:
    datasets = dataset_artifact.get("datasets") if isinstance(dataset_artifact, dict) else None
    if not isinstance(datasets, list):
        raise MySQLMaterializerError("dataset-artifact.json 缺少 datasets 列表")
    if not datasets:
        return {"schema_version": MATERIALIZED_DATASET_SCHEMA_VERSION, "datasets": [], "mysql_runtime": {"configured": False}}

    connection = _connect_mysql(mysql_config)
    config = _resolve_mysql_config(mysql_config)
    try:
        materialized: list[dict[str, Any]] = []
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            table_name = _physical_table_name(dataset, session_dir=session_dir, table_prefix=str(config.get("table_prefix") or DEFAULT_TABLE_PREFIX))
            _create_dataset_table(connection, table_name, dataset)
            _insert_dataset_rows(connection, table_name, dataset)
            materialized.append(_materialized_dataset_record(dataset, table_name, config))
    finally:
        connection.close()

    return {
        "schema_version": MATERIALIZED_DATASET_SCHEMA_VERSION,
        "datasets": materialized,
        "mysql_runtime": {
            "configured": True,
            "host": config.get("host"),
            "port": config.get("port"),
            "database": config.get("database"),
        },
    }


def write_materialized_dataset(
    dataset_artifact: dict[str, Any],
    output_path: Path | str,
    *,
    mysql_config: dict[str, Any] | None = None,
    session_dir: Path | str | None = None,
) -> dict[str, Any]:
    payload = materialize_dataset_artifact(dataset_artifact, mysql_config=mysql_config, session_dir=session_dir)
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _resolve_mysql_config(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = config or {}
    password_env = str(raw.get("password_env") or "LEARN_MYSQL_PASSWORD")
    return {
        "host": raw.get("host") or os.environ.get("LEARN_MYSQL_HOST") or "127.0.0.1",
        "port": int(raw.get("port") or os.environ.get("LEARN_MYSQL_PORT") or 3306),
        "user": raw.get("user") or os.environ.get("LEARN_MYSQL_USER") or "root",
        "password": os.environ.get(password_env) or os.environ.get("LEARN_MYSQL_PASSWORD") or "",
        "database": raw.get("database") or os.environ.get("LEARN_MYSQL_DATABASE"),
        "table_prefix": _canonical_identifier(str(raw.get("table_prefix") or DEFAULT_TABLE_PREFIX), fallback=DEFAULT_TABLE_PREFIX),
        "connect_timeout": int(raw.get("connect_timeout") or 5),
        "read_timeout": int(raw.get("read_timeout") or 10),
        "write_timeout": int(raw.get("write_timeout") or 10),
    }


def _connect_mysql(config: dict[str, Any] | None):
    try:
        import pymysql
    except ImportError as exc:
        raise MySQLMaterializerError("MySQL materializer requires PyMySQL，请先安装 pymysql。") from exc
    resolved = _resolve_mysql_config(config)
    if not resolved.get("database"):
        raise MySQLMaterializerError("MySQL materializer 需要 database：请设置 LEARN_MYSQL_DATABASE 或 mysql-config-json.database")
    return pymysql.connect(
        host=resolved["host"],
        port=resolved["port"],
        user=resolved["user"],
        password=resolved["password"],
        database=resolved["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=resolved["connect_timeout"],
        read_timeout=resolved["read_timeout"],
        write_timeout=resolved["write_timeout"],
    )


def _physical_table_name(dataset: dict[str, Any], *, session_dir: Path | str | None, table_prefix: str) -> str:
    session_seed = str(Path(session_dir).expanduser().resolve()) if session_dir else "session"
    dataset_id = str(dataset.get("dataset_id") or dataset.get("id") or "dataset")
    visibility = str(dataset.get("visibility") or "public")
    digest = hashlib.sha256(f"{session_seed}\n{dataset_id}\n{visibility}".encode("utf-8")).hexdigest()[:16]
    return f"{table_prefix}__{digest}"


def _create_dataset_table(connection: Any, table_name: str, dataset: dict[str, Any]) -> None:
    columns = _dataset_columns(dataset)
    column_sql = ["`__row_order` BIGINT NOT NULL"]
    for column in columns:
        column_sql.append(f"{_quote_identifier(column['name'])} {column['mysql_type']}")
    sql = f"CREATE TABLE IF NOT EXISTS {_quote_identifier(table_name)} ({', '.join(column_sql)}, PRIMARY KEY (`__row_order`))"
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {_quote_identifier(table_name)}")
        cursor.execute(sql)


def _insert_dataset_rows(connection: Any, table_name: str, dataset: dict[str, Any]) -> None:
    rows = dataset.get("rows") if isinstance(dataset.get("rows"), list) else []
    columns = _dataset_columns(dataset)
    if not rows:
        return
    names = [column["name"] for column in columns]
    placeholders = ", ".join(["%s"] * (len(names) + 1))
    insert_sql = f"INSERT INTO {_quote_identifier(table_name)} (`__row_order`, {', '.join(_quote_identifier(name) for name in names)}) VALUES ({placeholders})"
    values = []
    for index, row in enumerate(rows):
        values.append([index, *_row_values(row, names)])
    with connection.cursor() as cursor:
        cursor.executemany(insert_sql, values)


def _dataset_columns(dataset: dict[str, Any]) -> list[dict[str, str]]:
    raw_columns = dataset.get("columns") if isinstance(dataset.get("columns"), list) else []
    rows = dataset.get("rows") if isinstance(dataset.get("rows"), list) else []
    columns: list[dict[str, str]] = []
    if raw_columns:
        for column in raw_columns:
            if not isinstance(column, dict):
                continue
            name = _canonical_identifier(str(column.get("name") or ""), fallback="col")
            mysql_type = str(column.get("mysql_type") or _infer_mysql_type(str(column.get("dtype") or ""), rows, name)).strip().upper()
            columns.append({"name": name, "mysql_type": mysql_type})
    elif rows and isinstance(rows[0], dict):
        for name in rows[0].keys():
            safe_name = _canonical_identifier(str(name), fallback="col")
            columns.append({"name": safe_name, "mysql_type": _infer_mysql_type("", rows, str(name))})
    if not columns:
        raise MySQLMaterializerError("dataset 必须声明 columns 或提供 dict rows 以推断列")
    return columns


def _row_values(row: Any, names: list[str]) -> list[Any]:
    if isinstance(row, dict):
        return [row.get(name) for name in names]
    if isinstance(row, (list, tuple)):
        return list(row[: len(names)]) + [None] * max(0, len(names) - len(row))
    return [row] + [None] * max(0, len(names) - 1)


def _infer_mysql_type(dtype: str, rows: list[Any], name: str) -> str:
    key = dtype.lower()
    if any(token in key for token in ("int", "integer")):
        return "BIGINT"
    if any(token in key for token in ("float", "double", "decimal")):
        return "DOUBLE"
    if any(token in key for token in ("bool", "boolean")):
        return "BOOLEAN"
    if "date" in key or "time" in key:
        return "DATETIME"
    for row in rows:
        value = row.get(name) if isinstance(row, dict) else None
        if isinstance(value, bool):
            return "BOOLEAN"
        if isinstance(value, int) and not isinstance(value, bool):
            return "BIGINT"
        if isinstance(value, float):
            return "DOUBLE"
    return "TEXT"


def _materialized_dataset_record(dataset: dict[str, Any], table_name: str, config: dict[str, Any]) -> dict[str, Any]:
    record = {
        "dataset_id": str(dataset.get("dataset_id") or dataset.get("id") or ""),
        "kind": str(dataset.get("kind") or ""),
        "visibility": str(dataset.get("visibility") or "public"),
        "logical_name": str(dataset.get("logical_name") or dataset.get("table_name") or ""),
        "physical_table": table_name,
        "database": config.get("database"),
        "columns": dataset.get("columns") or [],
        "row_count": len(dataset.get("rows") or []),
        "views": dataset.get("views") or [],
        "reconstruction": dataset.get("reconstruction") or dataset.get("reconstruction_metadata") or dataset.get("pandas_metadata") or {},
    }
    return record


def _canonical_identifier(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized or normalized[0].isdigit():
        normalized = f"{fallback}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:8]}"
    return normalized[:48]


def _quote_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise MySQLMaterializerError(f"非法 MySQL identifier: {value}")
    return f"`{value}`"
