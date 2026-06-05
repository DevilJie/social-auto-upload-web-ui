"""旧版 Windows 客户端数据迁移脚本。

把 %LOCALAPPDATA%\\Social Auto Upload Web UI\\ 的数据迁移到项目 data/ 目录：
  - cookies/、cookiesFile/、db/  三个目录直接覆盖
  - videoFile/ 中的素材调用后端 /api/materials/upload 上传

使用方法：先执行 start.bat / start.sh 启动后端，再运行本脚本。
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import requests


def default_source() -> Path:
    """解析旧版数据目录。Windows 下用 %LOCALAPPDATA%，其他平台回退到 fixture。"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / "Social Auto Upload Web UI"
    return Path(__file__).resolve().parent / "legacy_fixture"


def default_target() -> Path:
    """解析新版 data 目录。优先 SAU_DATA_DIR，否则 {项目根}/data。"""
    env = os.environ.get("SAU_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data"


UUID_PREFIX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_",
    re.IGNORECASE,
)

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v", ".wmv", ".mpeg", ".mpg"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
ALLOWED_EXTS = VIDEO_EXTS | IMAGE_EXTS


def strip_uuid_prefix(name: str) -> str:
    """剥掉 {uuid}_ 前缀，仅剥一次。"""
    return UUID_PREFIX.sub("", name, count=1)


def is_allowed_ext(filename: str) -> bool:
    """判断文件扩展名是否在新版素材库白名单内。"""
    return Path(filename).suffix.lower() in ALLOWED_EXTS


def check_backend(api_base: str, timeout: float = 2.0) -> bool:
    """探测后端健康状态。返回 True 表示可访问。

    使用 /api/materials/list 端点做轻量级 ping。
    """
    try:
        resp = requests.get(
            f"{api_base}/api/materials/list",
            params={"page": 1, "page_size": 1},
            timeout=timeout,
        )
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _timestamp() -> str:
    """返回 YYYYMMDD_HHMMSS 格式时间戳。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_data(
    data_dir: Path,
    dry_run: bool = False,
    skip: bool = False,
) -> Path | None:
    """把 data 目录整个复制到 data.bak.YYYYMMDD_HHMMSS/data/ 下。返回备份路径。

    备份采用 data/ 子目录包装布局（例如 <backup>/data/cookies/foo.json），
    方便直接 `cp -r <backup>/data/* <target>/` 整体恢复。

    - skip=True  时返回 None（不创建任何目录）
    - dry_run=True 时返回预期的备份路径但不实际复制
    """
    if skip:
        return None
    backup_path = data_dir.parent / f"data.bak.{_timestamp()}"
    if dry_run:
        return backup_path
    shutil.copytree(data_dir, backup_path / "data")
    return backup_path


def copy_directory(
    src: Path,
    dst: Path,
    dry_run: bool = False,
) -> tuple[int, int]:
    """递归把 src 下的所有文件覆盖到 dst 下。

    返回 (copied, failed) 计数。已存在于 dst 的文件被覆盖，但 dst 中
    不在 src 下的文件不会被删除（覆盖语义，非镜像语义）。
    """
    if not src.exists():
        return 0, 0
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    failed = 0
    for src_file in src.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(src)
        dst_file = dst / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        if dry_run:
            copied += 1
            continue
        try:
            shutil.copy2(src_file, dst_file)
            copied += 1
        except OSError as e:
            print(f"ERROR: copy {src_file} -> {dst_file}: {e}", file=sys.stderr)
            failed += 1
    return copied, failed


def upload_material(
    src: Path,
    api_base: str,
    dry_run: bool = False,
    timeout: float = 300.0,
) -> bool:
    """把 src 调后端 /api/materials/upload 上传。返回 True/False。

    - 文件名 uuid 前缀被剥离后作为 multipart.filename 传递
    - mime 用 mimetypes.guess_type 推断
    - dry_run=True 时不实际发送请求
    """
    original_name = strip_uuid_prefix(src.name)
    if dry_run:
        return True
    mime_type, _ = mimetypes.guess_type(original_name)
    mime_type = mime_type or "application/octet-stream"
    try:
        with open(src, "rb") as f:
            resp = requests.post(
                f"{api_base}/api/materials/upload",
                files={"file": (original_name, f, mime_type)},
                timeout=timeout,
            )
        resp.raise_for_status()
        return True
    except (requests.exceptions.RequestException, OSError) as e:
        print(f"ERROR: 上传 {src.name} 失败: {e}", file=sys.stderr)
        return False


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
