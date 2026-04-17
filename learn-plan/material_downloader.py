#!/usr/bin/env python3
"""
learn-plan 材料下载器 CLI facade。

核心下载、缓存状态与 index.json 回写逻辑由 learn_materials.downloader 负责。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from learn_materials.downloader import process_materials


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download materials for learn-plan")
    parser.add_argument("--materials-dir", required=True, help="materials 目录路径")
    parser.add_argument("--material-id", help="指定下载某个材料 ID；不指定则下载所有可下载材料")
    parser.add_argument("--force", action="store_true", help="强制重新下载已缓存的材料")
    parser.add_argument("--dry-run", action="store_true", help="只显示将要下载的材料，不实际下载")
    parser.add_argument("--timeout", type=int, default=30, help="下载超时时间（秒）")
    return parser.parse_args()


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
