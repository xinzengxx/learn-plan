#!/usr/bin/env python3
"""Deprecated entrypoint for learn-plan material downloads."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "material_downloader.py 已废弃。请改用：\n"
        "python3 -m learn_materials.download_cli --materials-dir <materials目录路径>",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
