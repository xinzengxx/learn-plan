#!/usr/bin/env python3
"""
learn-plan 材料下载器

用途：
- 从 materials/index.json 读取材料元数据
- 根据 URL 和类型自动下载到本地
- 更新 index.json 的缓存状态
- 支持多种材料类型：PDF、HTML、Markdown、JSON 等

使用方式：
python3 material_downloader.py --materials-dir <materials目录> [--material-id <指定ID>] [--force]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download materials for learn-plan")
    parser.add_argument("--materials-dir", required=True, help="materials 目录路径")
    parser.add_argument("--material-id", help="指定下载某个材料 ID；不指定则下载所有可下载材料")
    parser.add_argument("--force", action="store_true", help="强制重新下载已缓存的材料")
    parser.add_argument("--dry-run", action="store_true", help="只显示将要下载的材料，不实际下载")
    parser.add_argument("--timeout", type=int, default=30, help="下载超时时间（秒）")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_downloadable_url(url: str | None) -> bool:
    """判断 URL 是否可直接下载"""
    if not url:
        return False
    url_lower = url.lower()
    # 排除需要认证或动态内容的站点
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
    # 支持直接文件下载
    downloadable_extensions = [
        ".pdf", ".md", ".txt", ".json", ".csv",
        ".html", ".htm", ".xml", ".zip", ".tar.gz"
    ]
    return any(url_lower.endswith(ext) for ext in downloadable_extensions)


def sanitize_filename(name: str) -> str:
    """清理文件名，移除不安全字符"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:200]  # 限制长度


def guess_extension(url: str, content_type: str | None) -> str:
    """根据 URL 和 Content-Type 推测文件扩展名"""
    # 先从 URL 提取
    parsed = urlparse(url)
    path = parsed.path
    if path:
        ext = os.path.splitext(path)[1]
        if ext:
            return ext

    # 从 Content-Type 推测
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
        if ext:
            return ext

    return ".html"  # 默认


def download_file(url: str, dest_path: Path, *, timeout: int = 30) -> tuple[bool, str]:
    """
    下载文件到指定路径
    返回：(成功标志, 消息)
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        req = Request(url, headers=headers)

        with urlopen(req, timeout=timeout) as response:
            content_type = response.headers.get('Content-Type')

            # 如果目标路径没有扩展名，尝试推测
            if not dest_path.suffix:
                ext = guess_extension(url, content_type)
                dest_path = dest_path.with_suffix(ext)

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # 下载内容
            content = response.read()
            dest_path.write_bytes(content)

            size_kb = len(content) / 1024
            return True, f"下载成功：{dest_path.name} ({size_kb:.1f} KB)"

    except HTTPError as e:
        return False, f"HTTP 错误 {e.code}：{e.reason}"
    except URLError as e:
        return False, f"URL 错误：{e.reason}"
    except Exception as e:
        return False, f"下载失败：{str(e)}"


def generate_local_path(material: dict[str, Any], materials_dir: Path) -> Path:
    """为材料生成本地存储路径"""
    material_id = material.get("id") or "unknown"
    title = material.get("title") or material_id
    domain = material.get("domain") or "general"
    kind = material.get("kind") or "reference"

    # 创建子目录结构：materials/{domain}/{kind}/
    subdir = materials_dir / domain / kind

    # 文件名：{id}_{sanitized_title}
    safe_title = sanitize_filename(title)
    filename = f"{material_id}_{safe_title}"

    return subdir / filename


def should_download(material: dict[str, Any], *, force: bool) -> tuple[bool, str]:
    """判断是否应该下载该材料"""
    url = material.get("url")
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


def update_material_cache_status(
    material: dict[str, Any],
    local_path: Path,
    success: bool,
    message: str
) -> dict[str, Any]:
    """更新材料的缓存状态"""
    updated = material.copy()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    if success:
        updated["cache_status"] = "cached"
        updated["availability"] = "cached"
        updated["selection_status"] = "confirmed"
        updated["local_path"] = str(local_path)
        updated["cached_at"] = timestamp
        updated["cache_note"] = message
        updated["exists_locally"] = True
        local_artifact = dict(updated.get("local_artifact") or {})
        local_artifact.update(
            {
                "path": str(local_path),
                "file_type": local_path.suffix.lstrip(".") or None,
                "downloaded_at": timestamp,
            }
        )
        updated["local_artifact"] = local_artifact
    else:
        updated["cache_status"] = "download-failed"
        updated["availability"] = updated.get("availability") or "metadata-only"
        updated["cache_note"] = message
        updated["last_attempt"] = timestamp
        updated["exists_locally"] = bool(updated.get("exists_locally"))

    return updated


def process_materials(
    materials_dir: Path,
    material_id: str | None,
    *,
    force: bool,
    dry_run: bool,
    timeout: int
) -> dict[str, Any]:
    """处理材料下载"""
    index_path = materials_dir / "index.json"

    if not index_path.exists():
        return {
            "success": False,
            "message": f"材料索引不存在：{index_path}",
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
        }

    index_data = read_json(index_path)
    entries = index_data.get("entries") or []

    if not isinstance(entries, list):
        return {
            "success": False,
            "message": "index.json 格式错误：entries 不是列表",
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
        }

    # 筛选要处理的材料
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

    # 处理每个材料
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

        if dry_run:
            print(f"[模拟] {material_id_current}: {title} - 将下载 {material.get('url')}")
            updated_material = material
            updated_entries.append(updated_material)
            updated_by_id[material_id_current] = updated_material
            continue

        # 生成本地路径
        local_path = generate_local_path(material, materials_dir)
        url = material.get("url")

        print(f"[下载] {material_id_current}: {title}")
        print(f"  URL: {url}")
        print(f"  目标: {local_path}")

        success, message = download_file(url, local_path, timeout=timeout)

        if success:
            print(f"  ✓ {message}")
            downloaded += 1
        else:
            print(f"  ✗ {message}")
            failed += 1

        # 更新材料元数据
        updated_material = update_material_cache_status(material, local_path, success, message)
        updated_entries.append(updated_material)
        updated_by_id[material_id_current] = updated_material

    # 保留未处理的材料，同时维持原有顺序
    if material_id:
        updated_entries = [updated_by_id.get((entry.get("id") or "unknown"), entry) for entry in entries]

    # 写回 index.json
    if not dry_run:
        index_data["entries"] = updated_entries
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


def main() -> int:
    args = parse_args()
    materials_dir = Path(args.materials_dir).expanduser().resolve()

    if not materials_dir.exists():
        print(f"材料目录不存在：{materials_dir}", file=sys.stderr)
        return 1

    print(f"材料目录：{materials_dir}")
    print(f"索引文件：{materials_dir / 'index.json'}")
    if args.material_id:
        print(f"指定材料：{args.material_id}")
    if args.force:
        print("模式：强制重新下载")
    if args.dry_run:
        print("模式：模拟运行（不实际下载）")
    print()

    result = process_materials(
        materials_dir,
        args.material_id,
        force=args.force,
        dry_run=args.dry_run,
        timeout=args.timeout,
    )

    if not result["success"]:
        print(f"\n错误：{result['message']}", file=sys.stderr)
        return 1

    print(f"\n下载完成：{result['downloaded']}")
    print(f"跳过：{result['skipped']}")
    print(f"失败：{result['failed']}")
    print(f"索引已更新：{result['index_path']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
