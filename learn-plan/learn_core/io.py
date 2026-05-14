from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JsonReadResult:
    status: str
    data: dict[str, Any]
    error: str | None = None
    recovery_path: str | None = None

    def error_state(self) -> dict[str, Any]:
        if self.status in {"ok", "missing"}:
            return dict(self.data)
        payload: dict[str, Any] = {
            "status": self.status,
            "error": self.error,
        }
        if self.recovery_path:
            payload["recovery_path"] = self.recovery_path
        return {"_json_read_error": payload}


def _broken_json_path(path: Path) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    candidate = path.with_name(f"{path.name}.broken.{timestamp}")
    if not candidate.exists():
        return candidate
    return path.with_name(f"{path.name}.broken.{timestamp}.{time.time_ns()}")


def read_json_result(path: Path) -> JsonReadResult:
    if not path.exists() or not path.is_file():
        return JsonReadResult(status="missing", data={})
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        recovery_path: Path | None = None
        try:
            recovery_path = _broken_json_path(path)
            path.replace(recovery_path)
        except OSError:
            recovery_path = None
        return JsonReadResult(
            status="invalid_json",
            data={},
            error=f"{exc.msg} at line {exc.lineno} column {exc.colno}",
            recovery_path=str(recovery_path) if recovery_path else None,
        )
    if not isinstance(payload, dict):
        return JsonReadResult(
            status="wrong_shape",
            data={},
            error=f"expected JSON object, got {type(payload).__name__}",
        )
    return JsonReadResult(status="ok", data=payload)


def read_json(path: Path) -> dict[str, Any]:
    result = read_json_result(path)
    if result.status == "missing":
        raise FileNotFoundError(path)
    if result.status != "ok":
        return result.error_state()
    return result.data


def read_json_if_exists(path: Path) -> dict[str, Any]:
    result = read_json_result(path)
    return result.data if result.status == "ok" else {}


def read_text_if_exists(path: Path) -> str:
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def write_text(path: Path, content: str) -> None:
    _atomic_write_text(path, content)
