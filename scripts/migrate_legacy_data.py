"""旧版 Windows 客户端数据迁移脚本。

把 %LOCALAPPDATA%\\Social Auto Upload Web UI\\ 的数据迁移到项目 data/ 目录：
  - cookies/、cookiesFile/、db/  三个目录直接覆盖
  - videoFile/ 中的素材调用后端 /api/materials/upload 上传

使用方法：先执行 start.bat / start.sh 启动后端，再运行本脚本。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析 CLI 参数。"""
    parser = argparse.ArgumentParser(
        description="旧版 Windows 客户端数据迁移到新版 data/ 目录",
    )
    parser.add_argument(
        "--source", type=Path, default=None,
        help="旧版数据目录，默认 %%LOCALAPPDATA%%\\Social Auto Upload Web UI",
    )
    parser.add_argument(
        "--target", type=Path, default=None,
        help="新版 data 目录，默认 {项目根}/data",
    )
    parser.add_argument(
        "--api-base", type=str, default="http://127.0.0.1:5409",
        help="后端 API 根地址，默认 http://127.0.0.1:5409",
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="只列出将要执行的操作，不真正修改文件",
    )
    parser.add_argument(
        "--skip-backup", dest="skip_backup", action="store_true",
        help="跳过备份（仅当你已手动备份时使用）",
    )
    parser.add_argument(
        "--yes", dest="yes", action="store_true",
        help="跳过交互式确认",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    print(f"DEBUG parse_args: {args}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
