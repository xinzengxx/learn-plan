from __future__ import annotations

from collections.abc import Iterable
from typing import Any

MAX_REPR_LENGTH = 2000
MAX_DISPLAY_ROWS = 20
MAX_DISPLAY_COLUMNS = 20


def safe_repr(value: Any, *, max_length: int = MAX_REPR_LENGTH) -> str:
    try:
        text = repr(value)
    except Exception:
        text = "<unreprable>"
    if len(text) > max_length:
        return f"{text[:max_length]}…"
    return text


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    try:
        import datetime

        if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
            return value.isoformat()
    except Exception:
        pass
    return safe_repr(value)


def _preview_rows(rows: Iterable[Any], *, max_rows: int = MAX_DISPLAY_ROWS) -> tuple[list[Any], bool]:
    preview: list[Any] = []
    truncated = False
    for index, row in enumerate(rows):
        if index >= max_rows:
            truncated = True
            break
        preview.append(_json_safe(row))
    return preview, truncated


def sql_result_display(columns: list[str], rows: list[Any], *, row_count: int | None = None, truncated: bool = False) -> dict[str, Any]:
    safe_rows, preview_truncated = _preview_rows(rows)
    return {
        "kind": "sql_result",
        "columns": [str(column) for column in columns[:MAX_DISPLAY_COLUMNS]],
        "rows": safe_rows,
        "row_count": row_count if row_count is not None else len(rows),
        "truncated": bool(truncated or preview_truncated or len(columns) > MAX_DISPLAY_COLUMNS),
        "repr": safe_repr({"columns": columns, "rows": rows}),
    }


def error_display(message: str) -> dict[str, Any]:
    return {"kind": "error", "message": str(message), "repr": str(message)}


def dataframe_display(value: Any) -> dict[str, Any]:
    columns = [str(column) for column in list(getattr(value, "columns", []))]
    head = value.head(MAX_DISPLAY_ROWS) if hasattr(value, "head") else value
    rows = head.to_dict(orient="records") if hasattr(head, "to_dict") else []
    return {
        "kind": "dataframe",
        "columns": columns[:MAX_DISPLAY_COLUMNS],
        "rows": _json_safe(rows),
        "shape": list(getattr(value, "shape", [])),
        "dtypes": {str(key): str(item) for key, item in getattr(value, "dtypes", {}).items()} if hasattr(getattr(value, "dtypes", None), "items") else {},
        "truncated": bool(getattr(value, "shape", [0, 0])[0] > MAX_DISPLAY_ROWS or len(columns) > MAX_DISPLAY_COLUMNS),
        "repr": safe_repr(value),
    }


def series_display(value: Any) -> dict[str, Any]:
    head = value.head(MAX_DISPLAY_ROWS) if hasattr(value, "head") else value
    rows = head.to_list() if hasattr(head, "to_list") else list(head)[:MAX_DISPLAY_ROWS]
    return {
        "kind": "series",
        "name": str(getattr(value, "name", "") or ""),
        "values": _json_safe(rows),
        "shape": list(getattr(value, "shape", [])),
        "dtype": str(getattr(value, "dtype", "")),
        "truncated": bool(len(value) > MAX_DISPLAY_ROWS) if hasattr(value, "__len__") else False,
        "repr": safe_repr(value),
    }


def ndarray_display(value: Any) -> dict[str, Any]:
    values = value.tolist() if hasattr(value, "tolist") else safe_repr(value)
    return {
        "kind": "ndarray",
        "shape": list(getattr(value, "shape", [])),
        "dtype": str(getattr(value, "dtype", "")),
        "values": _json_safe(values),
        "repr": safe_repr(value),
    }


def tensor_display(value: Any) -> dict[str, Any]:
    shape = list(value.shape) if hasattr(value, "shape") else []
    dtype = str(getattr(value, "dtype", ""))
    device = str(getattr(value, "device", ""))
    detached = value.detach().cpu() if hasattr(value, "detach") and hasattr(value, "cpu") else value
    values = detached.tolist() if hasattr(detached, "tolist") else safe_repr(value)
    return {
        "kind": "tensor",
        "shape": shape,
        "dtype": dtype,
        "device": device,
        "values": _json_safe(values),
        "repr": safe_repr(value),
    }


def to_display_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("kind"), str):
        return _json_safe(value)
    if hasattr(value, "columns") and hasattr(value, "to_dict"):
        return dataframe_display(value)
    if hasattr(value, "dtype") and hasattr(value, "to_list") and not hasattr(value, "columns"):
        return series_display(value)
    module_name = type(value).__module__
    if module_name.startswith("torch"):
        return tensor_display(value)
    if hasattr(value, "shape") and hasattr(value, "tolist"):
        return ndarray_display(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return {"kind": "scalar", "value": value, "repr": safe_repr(value)}
    if isinstance(value, (list, tuple, dict)):
        return {"kind": "json", "value": _json_safe(value), "repr": safe_repr(value)}
    return {"kind": "repr", "repr": safe_repr(value)}
