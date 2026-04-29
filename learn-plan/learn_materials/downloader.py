from __future__ import annotations

import json
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from learn_core.io import read_json, write_json
from learn_core.text_utils import sanitize_filename

from .index_schema import get_index_entries, normalize_materials_index


def resolve_download_url(material: dict[str, Any]) -> str | None:
    direct_url = str(material.get("direct_url") or "").strip()
    if direct_url:
        return direct_url
    url = str(material.get("url") or "").strip()
    return url or None


def is_downloadable_url(url: str | None) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    excluded_domains = [
        "leetcode.com",
        "khanacademy.org",
        "coursera.org",
        "udemy.com",
        "github.com/login",
    ]
    for domain in excluded_domains:
        if domain in url_lower:
            return False
    downloadable_extensions = [
        ".pdf", ".md", ".txt", ".json", ".csv",
        ".html", ".htm", ".xml", ".zip", ".tar.gz",
    ]
    return any(url_lower.endswith(ext) for ext in downloadable_extensions)


def guess_extension(url: str, content_type: str | None) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if path:
        ext = os.path.splitext(path)[1]
        if ext:
            return ext
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
        if ext:
            return ext
    return ".html"


def looks_like_login_or_error_page(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower())[:20000]
    patterns = [
        "login", "log in", "sign in", "signin", "captcha", "access denied",
        "403 forbidden", "404 not found", "enable javascript", "cloudflare",
        "unauthorized", "forbidden", "not found", "请登录", "登录后", "访问被拒绝",
    ]
    return any(pattern in normalized for pattern in patterns)


def validate_downloaded_content(content: bytes, *, url: str, content_type: str | None, expected_ext: str) -> tuple[bool, str, dict[str, Any]]:
    size_bytes = len(content)
    metadata: dict[str, Any] = {
        "status": "invalid",
        "content_type": content_type or "",
        "size_bytes": size_bytes,
        "validator": "learn-materials-downloader.v2",
    }
    if size_bytes == 0:
        metadata["reason"] = "empty-content"
        return False, "下载内容为空", metadata
    if not content.strip():
        metadata["reason"] = "blank-content"
        return False, "下载内容只有空白字符", metadata

    ext = expected_ext.lower()
    if size_bytes < 128 and ext not in {".txt", ".md", ".json", ".csv"}:
        metadata["reason"] = "too-small-content"
        return False, f"下载内容过小：{size_bytes} bytes", metadata

    head = content[:1024]
    if ext == ".pdf":
        if b"%PDF" not in head:
            metadata["reason"] = "invalid-pdf-signature"
            return False, "PDF 签名无效，可能下载到网页或错误内容", metadata
    elif ext in {".zip", ".tar.gz"}:
        if ext == ".zip" and not content.startswith(b"PK"):
            metadata["reason"] = "invalid-zip-signature"
            return False, "ZIP 签名无效", metadata
    elif ext == ".json":
        try:
            json.loads(content.decode("utf-8"))
        except Exception:
            metadata["reason"] = "invalid-json"
            return False, "JSON 内容无法解析", metadata

    text = ""
    if ext in {".html", ".htm", ".txt", ".md", ".csv", ".xml", ".json"} or (content_type and "html" in content_type.lower()):
        text = content[:20000].decode("utf-8", errors="ignore")
        if not text.strip():
            metadata["reason"] = "undecodable-text"
            return False, "文本内容无法解码", metadata
        if looks_like_login_or_error_page(text):
            metadata["reason"] = "login-or-error-page"
            return False, "下载结果疑似登录页、错误页或反爬页面", metadata

    metadata["status"] = "valid"
    metadata.pop("reason", None)
    return True, "内容验证通过", metadata


def download_file(url: str, dest_path: Path, *, timeout: int = 30) -> tuple[bool, str, Path, dict[str, Any]]:
    validation: dict[str, Any] = {"status": "invalid", "validator": "learn-materials-downloader.v2"}
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type")
            final_url = response.geturl() or url
            content_length = response.headers.get("Content-Length")
            final_dest_path = dest_path
            if not final_dest_path.suffix:
                ext = guess_extension(final_url, content_type)
                final_dest_path = final_dest_path.with_suffix(ext)
            content = response.read()
            valid, validation_message, validation = validate_downloaded_content(
                content,
                url=final_url,
                content_type=content_type,
                expected_ext=final_dest_path.suffix or guess_extension(final_url, content_type),
            )
            validation["final_url"] = final_url
            validation["content_length"] = content_length
            if not valid:
                return False, validation_message, final_dest_path, validation
            final_dest_path.parent.mkdir(parents=True, exist_ok=True)
            final_dest_path.write_bytes(content)
            size_kb = len(content) / 1024
            return True, f"下载成功：{final_dest_path.name} ({size_kb:.1f} KB)", final_dest_path, validation
    except HTTPError as e:
        validation.update({"status": "invalid", "reason": "http-error", "http_status": e.code})
        return False, f"HTTP 错误 {e.code}：{e.reason}", dest_path, validation
    except URLError as e:
        validation.update({"status": "invalid", "reason": "url-error"})
        return False, f"URL 错误：{e.reason}", dest_path, validation
    except Exception as e:
        validation.update({"status": "invalid", "reason": "download-error"})
        return False, f"下载失败：{str(e)}", dest_path, validation


def generate_local_path(material: dict[str, Any], materials_dir: Path) -> Path:
    material_id = material.get("id") or "unknown"
    title = material.get("title") or material_id
    domain = material.get("domain") or "general"
    kind = material.get("kind") or "reference"
    subdir = materials_dir / domain / kind
    safe_title = sanitize_filename(title)
    filename = f"{material_id}_{safe_title}"
    return subdir / filename


def should_download(material: dict[str, Any], *, force: bool) -> tuple[bool, str]:
    url = resolve_download_url(material)
    if not url:
        return False, "无 URL"

    downloadable_flag = material.get("downloadable") is True
    direct_file_url = is_downloadable_url(url)
    if not downloadable_flag and not direct_file_url:
        return False, "未标记 downloadable，且 URL 也不是直链下载"

    if downloadable_flag and not direct_file_url:
        url_lower = url.lower()
        excluded_domains = [
            "leetcode.com",
            "khanacademy.org",
            "coursera.org",
            "udemy.com",
            "github.com/login",
        ]
        for domain in excluded_domains:
            if domain in url_lower:
                return False, "URL 不可直接下载（需认证或动态内容）"

    cache_status = material.get("cache_status") or "metadata-only"
    local_path = material.get("local_path")
    if cache_status == "cached" and local_path and not force:
        if Path(local_path).exists():
            return False, "已缓存"

    if downloadable_flag:
        return True, "材料已显式标记为 downloadable"
    return True, "URL 为直链下载"


def update_material_cache_status(material: dict[str, Any], local_path: Path, success: bool, message: str, validation: dict[str, Any] | None = None) -> dict[str, Any]:
    updated = material.copy()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    validation_payload = dict(validation or {})
    validation_payload.setdefault("message", message)
    if success:
        updated["cache_status"] = "cached"
        updated["availability"] = "cached"
        updated["local_path"] = str(local_path)
        updated["cached_at"] = timestamp
        updated["last_attempt"] = timestamp
        validation_payload["status"] = "valid"
    else:
        reason = str(validation_payload.get("reason") or "download-failed")
        updated["cache_status"] = "validation-failed" if validation_payload else "download-failed"
        updated["last_attempt"] = timestamp
        validation_payload.setdefault("status", "invalid")
        validation_payload.setdefault("reason", reason)
    updated["download_validation"] = validation_payload
    return updated


def process_materials(materials_dir: Path, material_id: str | None, *, force: bool, dry_run: bool, timeout: int) -> dict[str, Any]:
    index_path = materials_dir / "index.json"
    if not index_path.exists():
        return {
            "success": False,
            "message": f"材料索引不存在：{index_path}",
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
        }

    index_data = normalize_materials_index(read_json(index_path))
    entries = get_index_entries(index_data)
    if not isinstance(entries, list):
        return {
            "success": False,
            "message": "index.json 格式错误：entries/items 不是列表",
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
        }

    target_materials = []
    if material_id:
        for entry in entries:
            if entry.get("id") == material_id:
                target_materials.append(entry)
                break
        if not target_materials:
            return {
                "success": False,
                "message": f"未找到材料 ID：{material_id}",
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
            }
    else:
        target_materials = entries

    downloaded = 0
    skipped = 0
    failed = 0
    updated_entries = []
    updated_by_id: dict[str, dict[str, Any]] = {}

    for material in target_materials:
        material_id_current = material.get("id") or "unknown"
        title = material.get("title") or material_id_current
        should_dl, reason = should_download(material, force=force)
        if not should_dl:
            print(f"[跳过] {material_id_current}: {title} - {reason}")
            skipped += 1
            updated_material = material
            updated_entries.append(updated_material)
            updated_by_id[material_id_current] = updated_material
            continue

        resolved_url = resolve_download_url(material)
        if dry_run:
            print(f"[模拟] {material_id_current}: {title} - 将下载 {resolved_url}")
            updated_material = material
            updated_entries.append(updated_material)
            updated_by_id[material_id_current] = updated_material
            continue

        local_path = generate_local_path(material, materials_dir)
        url = resolved_url
        print(f"[下载] {material_id_current}: {title}")
        print(f"  URL: {url}")
        print(f"  目标: {local_path}")
        success, message, final_path, validation = download_file(url, local_path, timeout=timeout)
        if success:
            print(f"  ✓ {message}")
            downloaded += 1
        else:
            print(f"  ✗ {message}")
            failed += 1
        updated_material = update_material_cache_status(material, final_path, success, message, validation)
        updated_entries.append(updated_material)
        updated_by_id[material_id_current] = updated_material

    if material_id:
        updated_entries = [updated_by_id.get((entry.get("id") or "unknown"), entry) for entry in entries]

    if not dry_run:
        index_data = normalize_materials_index(index_data, entries=updated_entries)
        index_data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        write_json(index_path, index_data)

    return {
        "success": True,
        "message": "处理完成",
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "index_path": str(index_path),
    }

