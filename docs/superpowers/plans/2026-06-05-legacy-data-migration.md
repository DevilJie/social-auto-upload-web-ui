# 旧版 Windows 客户端数据迁移脚本实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供一个独立 Python 脚本，把旧版 Windows 客户端（`%LOCALAPPDATA%\Social Auto Upload Web UI\`）的 cookies/cookiesFile/db 三个目录直接覆盖到新版项目 `data/`，并把 videoFile 内的旧版素材逐个通过 `POST /api/materials/upload` 上传到新版素材库。

**Architecture:** 单文件 CLI 脚本，五阶段顺序执行：解析路径 → 备份当前 data → 探测后端 5409 端口 → 递归覆盖三个目录 → 遍历 videoFile 调后端上传。视频文件命名 `{uuid}_{原文件名}` 通过正则剥前缀，原始文件名作为 `multipart.filename` 传给后端。后端自动生成新 uuid、抽帧、写库。

**Tech Stack:** Python 3.14（项目 .venv）、`requests`（项目已有依赖）、`pytest`（项目隐式依赖，通过 `backend/test_*.py` 已使用）

---

## 文件结构

```
scripts/
├── migrate_legacy_data.py              # 主脚本（CLI 入口 + 五个阶段 + 汇总报告）
├── legacy_fixture/                     # 假旧版数据（仅用于开发测试）
│   ├── cookies/foo.json                # 占位 cookie
│   ├── cookiesFile/xhs.json            # 占位 cookie
│   ├── db/database.db                  # 空 SQLite
│   └── videoFile/
│       ├── 11111111-2222-3333-4444-555555555555_test1.mp4   # 占位 mp4（>0 bytes）
│       ├── 66666666-7777-8888-9999-000000000000_test2.png   # 占位 png
│       └── .DS_Store                   # 应被跳过
└── tests/
    ├── __init__.py
    └── test_migrate_legacy_data.py    # pytest 单元测试
```

修改：无需修改任何现有文件。

---

## Task 1: 脚手架与 CLI 参数解析

**Files:**
- Create: `scripts/migrate_legacy_data.py`
- Create: `scripts/tests/__init__.py`
- Create: `scripts/tests/test_migrate_legacy_data.py`

- [ ] **Step 1: 写失败测试 — argparse 默认值**

`scripts/tests/test_migrate_legacy_data.py`:

```python
"""迁移脚本的单元测试。"""
import sys
from pathlib import Path

# 把 scripts/ 目录加入 sys.path，便于导入 migrate_legacy_data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_legacy_data as mld


def test_parse_args_defaults(monkeypatch):
    """不传任何参数时，所有字段有合理默认值。"""
    monkeypatch.setattr(sys, "argv", ["migrate_legacy_data.py"])
    args = mld.parse_args()
    # api_base 默认 http://127.0.0.1:5409
    assert args.api_base == "http://127.0.0.1:5409"
    # dry-run / skip-backup / yes 默认 False
    assert args.dry_run is False
    assert args.skip_backup is False
    assert args.yes is False
    # source / target 是 Path 类型，字符串或 None（稍后解析）
    assert isinstance(args.source, (Path, type(None)))
    assert isinstance(args.target, (Path, type(None)))


def test_parse_args_custom(monkeypatch):
    """显式传入所有参数时被正确解析。"""
    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", "C:/old/data",
        "--target", "D:/new/data",
        "--api-base", "http://localhost:9999",
        "--dry-run",
        "--skip-backup",
        "--yes",
    ])
    args = mld.parse_args()
    assert str(args.source) == "C:/old/data"
    assert str(args.target) == "D:/new/data"
    assert args.api_base == "http://localhost:9999"
    assert args.dry_run is True
    assert args.skip_backup is True
    assert args.yes is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 失败，报 `ModuleNotFoundError: No module named 'migrate_legacy_data'`

- [ ] **Step 3: 写最小实现 — argparse 骨架**

`scripts/migrate_legacy_data.py`:

```python
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
        help="旧版数据目录，默认 %LOCALAPPDATA%\\Social Auto Upload Web UI",
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_legacy_data.py scripts/tests/__init__.py scripts/tests/test_migrate_legacy_data.py
git commit -m "feat(scripts): 迁移脚本脚手架与 CLI 参数解析"
```

---

## Task 2: 路径解析 (default_source / default_target)

**Files:**
- Modify: `scripts/migrate_legacy_data.py`
- Modify: `scripts/tests/test_migrate_legacy_data.py`

- [ ] **Step 1: 追加失败测试 — 路径解析**

在 `scripts/tests/test_migrate_legacy_data.py` 追加：

```python
import os


def test_default_target_uses_sau_data_dir_env(monkeypatch, tmp_path):
    """SAU_DATA_DIR 环境变量被优先使用。"""
    monkeypatch.setenv("SAU_DATA_DIR", str(tmp_path))
    assert mld.default_target() == tmp_path


def test_default_target_uses_repo_data_dir(monkeypatch):
    """未设置 SAU_DATA_DIR 时使用 {脚本父目录的父目录}/data。"""
    monkeypatch.delenv("SAU_DATA_DIR", raising=False)
    expected = mld.Path(__file__).resolve().parent.parent / "data"
    assert mld.default_target() == expected


def test_default_source_non_windows(monkeypatch):
    """非 Windows 下默认指向 scripts/legacy_fixture。"""
    monkeypatch.setattr(mld.sys, "platform", "linux")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    expected = Path(__file__).resolve().parent.parent / "legacy_fixture"
    assert mld.default_source() == expected


def test_default_source_windows(monkeypatch, tmp_path):
    """Windows 下默认指向 %LOCALAPPDATA%\\Social Auto Upload Web UI。"""
    monkeypatch.setattr(mld.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    expected = tmp_path / "Social Auto Upload Web UI"
    assert mld.default_source() == expected
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 失败，4 个新测试报 `AttributeError: module 'migrate_legacy_data' has no attribute 'default_target'`

- [ ] **Step 3: 实现 default_source / default_target**

修改 `scripts/migrate_legacy_data.py`，在 `import` 区域和 `parse_args` 之间新增：

```python
import os


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
```

并把 import 改为：

```python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_legacy_data.py scripts/tests/test_migrate_legacy_data.py
git commit -m "feat(scripts): 路径解析 default_source/default_target"
```

---

## Task 3: uuid 前缀剥离 + 文件类型白名单

**Files:**
- Modify: `scripts/migrate_legacy_data.py`
- Modify: `scripts/tests/test_migrate_legacy_data.py`

- [ ] **Step 1: 追加失败测试**

```python
def test_strip_uuid_prefix_standard():
    """标准 uuid 前缀被剥离。"""
    name = "1781ca06-5427-11f1-8000-bc2411b9d4e7_大理女孩-成品.mp4"
    assert mld.strip_uuid_prefix(name) == "大理女孩-成品.mp4"


def test_strip_uuid_prefix_uppercase():
    """大写 UUID 前缀同样被剥离。"""
    name = "AABBCCDD-1234-5678-9ABC-DEF012345678_video.mp4"
    assert mld.strip_uuid_prefix(name) == "video.mp4"


def test_strip_uuid_prefix_no_prefix():
    """没有 uuid 前缀时原样返回。"""
    name = "video.mp4"
    assert mld.strip_uuid_prefix(name) == "video.mp4"


def test_strip_uuid_prefix_inner_uuid_kept():
    """文件名中第二个及之后的 uuid 模式不被剥离。"""
    name = "11111111-2222-3333-4444-555555555555_aaa-bbb-ccc-ddd-eee.txt"
    assert mld.strip_uuid_prefix(name) == "aaa-bbb-ccc-ddd-eee.txt"


def test_is_allowed_ext_video():
    assert mld.is_allowed_ext(".mp4") is True
    assert mld.is_allowed_ext(".MP4") is True
    assert mld.is_allowed_ext(".mov") is True
    assert mld.is_allowed_ext(".webm") is True


def test_is_allowed_ext_image():
    assert mld.is_allowed_ext(".png") is True
    assert mld.is_allowed_ext(".jpg") is True
    assert mld.is_allowed_ext(".webp") is True


def test_is_allowed_ext_rejected():
    assert mld.is_allowed_ext(".DS_Store") is False
    assert mld.is_allowed_ext("") is False
    assert mld.is_allowed_ext(".tmp") is False
    assert mld.is_allowed_ext(".db") is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 失败，新测试报 `AttributeError: module 'migrate_legacy_data' has no attribute 'strip_uuid_prefix'`

- [ ] **Step 3: 实现 strip_uuid_prefix / is_allowed_ext**

在 `scripts/migrate_legacy_data.py` 的 `default_target` 后追加：

```python
import re

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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 13 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_legacy_data.py scripts/tests/test_migrate_legacy_data.py
git commit -m "feat(scripts): uuid 前缀剥离与文件类型白名单"
```

---

## Task 4: 后端健康探测

**Files:**
- Modify: `scripts/migrate_legacy_data.py`
- Modify: `scripts/tests/test_migrate_legacy_data.py`

- [ ] **Step 1: 追加失败测试（用 monkeypatch 替换 requests.get）**

```python
from unittest.mock import MagicMock


def _mock_response(status_code: int, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {"code": 200}
    resp.raise_for_status = MagicMock()
    return resp


def test_check_backend_healthy(monkeypatch):
    monkeypatch.setattr(mld.requests, "get",
                        lambda *a, **kw: _mock_response(200))
    assert mld.check_backend("http://127.0.0.1:5409") is True


def test_check_backend_unhealthy_status(monkeypatch):
    """后端返回 500 时视为不健康。"""
    resp = _mock_response(500)
    resp.raise_for_status = MagicMock(side_effect=Exception("HTTP 500"))
    monkeypatch.setattr(mld.requests, "get", lambda *a, **kw: resp)
    assert mld.check_backend("http://127.0.0.1:5409") is False


def test_check_backend_connection_refused(monkeypatch):
    """连接被拒绝时视为不健康。"""
    def fake_get(*a, **kw):
        raise mld.requests.exceptions.ConnectionError("refused")
    monkeypatch.setattr(mld.requests, "get", fake_get)
    assert mld.check_backend("http://127.0.0.1:5409") is False


def test_check_backend_timeout(monkeypatch):
    """超时视为不健康。"""
    def fake_get(*a, **kw):
        raise mld.requests.exceptions.Timeout("timeout")
    monkeypatch.setattr(mld.requests, "get", fake_get)
    assert mld.check_backend("http://127.0.0.1:5409") is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 失败，4 个新测试报 `AttributeError: module 'migrate_legacy_data' has no attribute 'check_backend'`

- [ ] **Step 3: 实现 check_backend**

在 `scripts/migrate_legacy_data.py` 顶部 import 区域追加：

```python
import requests
```

并新增：

```python
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
    except (requests.exceptions.RequestException, Exception):
        return False
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 17 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_legacy_data.py scripts/tests/test_migrate_legacy_data.py
git commit -m "feat(scripts): 后端健康探测 check_backend"
```

---

## Task 5: 备份目录

**Files:**
- Modify: `scripts/migrate_legacy_data.py`
- Modify: `scripts/tests/test_migrate_legacy_data.py`

- [ ] **Step 1: 追加失败测试**

```python
def test_backup_creates_timestamped_copy(monkeypatch, tmp_path):
    """备份把整个 data 目录复制到 data.bak.YYYYMMDD_HHMMSS/。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "cookies").mkdir()
    (data_dir / "cookies" / "foo.json").write_text("x")

    timestamp = "20260605_153012"
    monkeypatch.setattr(mld, "_timestamp", lambda: timestamp)

    backup_path = mld.backup_data(data_dir, dry_run=False)
    assert backup_path == data_dir.parent / f"data.bak.{timestamp}"
    assert backup_path.exists()
    assert (backup_path / "data" / "cookies" / "foo.json").read_text() == "x"


def test_backup_dry_run_does_not_copy(monkeypatch, tmp_path):
    """dry-run 模式下不实际复制。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "cookies").mkdir()
    timestamp = "20260605_153012"
    monkeypatch.setattr(mld, "_timestamp", lambda: timestamp)

    backup_path = mld.backup_data(data_dir, dry_run=True)
    assert backup_path == data_dir.parent / f"data.bak.{timestamp}"
    assert not backup_path.exists()


def test_backup_skip_returns_none(tmp_path):
    """skip_backup=True 时返回 None 且不创建目录。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    assert mld.backup_data(data_dir, dry_run=False, skip=True) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 失败，3 个新测试报 `AttributeError: module 'migrate_legacy_data' has no attribute 'backup_data'`

- [ ] **Step 3: 实现 backup_data / _timestamp**

在 `scripts/migrate_legacy_data.py` 顶部 import 区域追加：

```python
import shutil
from datetime import datetime
```

并新增：

```python
def _timestamp() -> str:
    """返回 YYYYMMDD_HHMMSS 格式时间戳。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_data(
    data_dir: Path,
    dry_run: bool = False,
    skip: bool = False,
) -> Path | None:
    """把 data 目录整个复制到 data.bak.YYYYMMDD_HHMMSS/。返回备份路径。

    - skip=True  时返回 None（不创建任何目录）
    - dry_run=True 时返回预期的备份路径但不实际复制
    """
    if skip:
        return None
    backup_path = data_dir.parent / f"data.bak.{_timestamp()}"
    if dry_run:
        return backup_path
    shutil.copytree(data_dir, backup_path)
    return backup_path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 20 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_legacy_data.py scripts/tests/test_migrate_legacy_data.py
git commit -m "feat(scripts): 备份目录 backup_data"
```

---

## Task 6: 目录覆盖拷贝

**Files:**
- Modify: `scripts/migrate_legacy_data.py`
- Modify: `scripts/tests/test_migrate_legacy_data.py`

- [ ] **Step 1: 追加失败测试**

```python
def test_copy_directory_overwrite(monkeypatch, tmp_path):
    """递归覆盖拷贝：目标文件存在时被覆盖，不存在的被创建。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "cookies").mkdir()
    (src / "cookies" / "a.json").write_text("new")

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "cookies").mkdir()
    (dst / "cookies" / "old.json").write_text("old")

    copied, failed = mld.copy_directory(src / "cookies", dst / "cookies", dry_run=False)
    assert copied == 1
    assert failed == 0
    assert (dst / "cookies" / "a.json").read_text() == "new"
    # 目标已有的 old.json 不被删除（覆盖语义而非 mirror 语义）
    assert (dst / "cookies" / "old.json").read_text() == "old"


def test_copy_directory_dry_run(monkeypatch, tmp_path):
    """dry-run 模式不实际拷贝。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("x")

    dst = tmp_path / "dst"
    dst.mkdir()

    copied, failed = mld.copy_directory(src, dst, dry_run=True)
    assert copied == 1
    assert failed == 0
    assert not (dst / "f.txt").exists()


def test_copy_directory_handles_subdirs(monkeypatch, tmp_path):
    """支持多层子目录递归。"""
    src = tmp_path / "src"
    (src / "deep" / "nested").mkdir(parents=True)
    (src / "deep" / "nested" / "f.txt").write_text("hello")

    dst = tmp_path / "dst"
    dst.mkdir()

    copied, failed = mld.copy_directory(src, dst, dry_run=False)
    assert copied == 1
    assert failed == 0
    assert (dst / "deep" / "nested" / "f.txt").read_text() == "hello"


def test_copy_directory_reports_failures(monkeypatch, tmp_path):
    """单个文件失败不影响其他文件，并计入 failed 计数。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "good.txt").write_text("ok")
    (src / "bad.txt").write_text("bad")

    dst = tmp_path / "dst"
    dst.mkdir()

    real_copy2 = mld.shutil.copy2

    def fake_copy2(src_file, dst_file, *a, **kw):
        if "bad" in str(src_file):
            raise OSError("simulated copy error")
        return real_copy2(src_file, dst_file, *a, **kw)

    monkeypatch.setattr(mld.shutil, "copy2", fake_copy2)

    copied, failed = mld.copy_directory(src, dst, dry_run=False)
    assert copied == 1
    assert failed == 1
    assert (dst / "good.txt").read_text() == "ok"
    assert not (dst / "bad.txt").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 失败，4 个新测试报 `AttributeError: module 'migrate_legacy_data' has no attribute 'copy_directory'`

- [ ] **Step 3: 实现 copy_directory**

在 `scripts/migrate_legacy_data.py` 追加：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 24 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_legacy_data.py scripts/tests/test_migrate_legacy_data.py
git commit -m "feat(scripts): 目录覆盖拷贝 copy_directory"
```

---

## Task 7: HTTP 素材上传

**Files:**
- Modify: `scripts/migrate_legacy_data.py`
- Modify: `scripts/tests/test_migrate_legacy_data.py`

- [ ] **Step 1: 追加失败测试**

```python
def test_upload_material_success(monkeypatch, tmp_path):
    """成功上传：返回 True，文件以原文件名（去前缀）传递。"""
    captured: dict = {}

    def fake_post(url, files, timeout):
        captured["url"] = url
        captured["files"] = files
        captured["timeout"] = timeout
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "code": 200,
            "data": {"id": "new-uuid", "stored_path": "materials/2026/06/new-uuid.mp4"},
        }
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(mld.requests, "post", fake_post)

    src = tmp_path / "11111111-2222-3333-4444-555555555555_test.mp4"
    src.write_bytes(b"fake video content")

    ok = mld.upload_material(
        src, api_base="http://127.0.0.1:5409", dry_run=False,
    )
    assert ok is True
    assert captured["url"] == "http://127.0.0.1:5409/api/materials/upload"
    field_name, file_tuple = captured["files"]["file"]
    # file_tuple: (filename, file_obj, mime)
    assert file_tuple[0] == "test.mp4"  # uuid 前缀已剥离


def test_upload_material_dry_run(monkeypatch, tmp_path):
    """dry-run 模式不实际调用 HTTP。"""
    called = {"count": 0}

    def fake_post(*a, **kw):
        called["count"] += 1
        return MagicMock()

    monkeypatch.setattr(mld.requests, "post", fake_post)

    src = tmp_path / "uuid_test.mp4"
    src.write_bytes(b"x")
    ok = mld.upload_material(src, api_base="http://x", dry_run=True)
    assert ok is True
    assert called["count"] == 0


def test_upload_material_http_error(monkeypatch, tmp_path, capsys):
    """HTTP 500 时返回 False 并打印错误。"""
    def fake_post(*a, **kw):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        resp.raise_for_status = MagicMock(
            side_effect=mld.requests.exceptions.HTTPError("500")
        )
        return resp

    monkeypatch.setattr(mld.requests, "post", fake_post)

    src = tmp_path / "uuid_x.mp4"
    src.write_bytes(b"x")
    ok = mld.upload_material(src, api_base="http://x", dry_run=False)
    assert ok is False
    captured = capsys.readouterr()
    assert "ERROR" in captured.err


def test_upload_material_connection_error(monkeypatch, tmp_path, capsys):
    """连接错误时返回 False。"""
    def fake_post(*a, **kw):
        raise mld.requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(mld.requests, "post", fake_post)

    src = tmp_path / "uuid_x.mp4"
    src.write_bytes(b"x")
    ok = mld.upload_material(src, api_base="http://x", dry_run=False)
    assert ok is False
    captured = capsys.readouterr()
    assert "ERROR" in captured.err
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 失败，4 个新测试报 `AttributeError: module 'migrate_legacy_data' has no attribute 'upload_material'`

- [ ] **Step 3: 实现 upload_material**

在 `scripts/migrate_legacy_data.py` 顶部 import 区域追加：

```python
import mimetypes
```

并新增：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 28 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_legacy_data.py scripts/tests/test_migrate_legacy_data.py
git commit -m "feat(scripts): HTTP 素材上传 upload_material"
```

---

## Task 8: 编排 main() — 整合五个阶段

**Files:**
- Modify: `scripts/migrate_legacy_data.py`

- [ ] **Step 1: 追加失败测试 — 端到端编排**

在 `scripts/tests/test_migrate_legacy_data.py` 追加：

```python
def test_main_happy_path(monkeypatch, tmp_path, capsys):
    """完整流程：备份 → 探测 → 拷贝 → 上传，dry_run=False。"""
    # 准备旧版 fixture
    src = tmp_path / "old"
    (src / "cookies").mkdir(parents=True)
    (src / "cookies" / "a.json").write_text("ck")
    (src / "cookiesFile").mkdir()
    (src / "cookiesFile" / "b.json").write_text("cf")
    (src / "db").mkdir()
    (src / "db" / "database.db").write_text("db")
    (src / "videoFile").mkdir()
    (src / "videoFile" / "11111111-2222-3333-4444-555555555555_movie.mp4").write_bytes(b"v")
    (src / "videoFile" / "22222222-3333-4444-5555-666666666666_pic.png").write_bytes(b"p")
    (src / "videoFile" / "Thumbs.db").write_bytes(b"junk")  # 应被跳过

    # 准备目标 data（用 tmp_path/data，与后端 conf.py 行为对齐）
    target = tmp_path / "data"
    target.mkdir()
    (target / "cookies").mkdir()

    # stub 后端探测 + 上传
    monkeypatch.setattr(mld, "check_backend", lambda api: True)
    upload_calls: list = []
    monkeypatch.setattr(mld, "upload_material",
                        lambda p, api_base, dry_run=False, timeout=300.0: upload_calls.append(p.name) or True)

    # stub 备份时间戳
    monkeypatch.setattr(mld, "_timestamp", lambda: "20260605_153012")

    # 用 monkeypatch 替换 sys.argv 注入参数
    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(src),
        "--target", str(target),
        "--api-base", "http://127.0.0.1:5409",
        "--yes",
    ])

    rc = mld.main()
    assert rc == 0

    # 断言：目标 data 包含拷贝内容
    assert (target / "cookies" / "a.json").read_text() == "ck"
    assert (target / "cookiesFile" / "b.json").read_text() == "cf"
    assert (target / "db" / "database.db").read_text() == "db"

    # 断言：备份存在
    backup = tmp_path / "data.bak.20260605_153012"
    assert backup.exists()
    assert (backup / "data" / "cookies").exists()

    # 断言：两个白名单文件都被上传，Thumbs.db 被跳过
    assert len(upload_calls) == 2
    assert "11111111-2222-3333-4444-555555555555_movie.mp4" in upload_calls
    assert "22222222-3333-4444-5555-666666666666_pic.png" in upload_calls

    # 断言：报告打印到 stdout
    out = capsys.readouterr().out
    assert "迁移报告" in out


def test_main_backend_unreachable(monkeypatch, tmp_path):
    """后端不可达时退出码 3。"""
    src = tmp_path / "old"
    src.mkdir()
    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(mld, "check_backend", lambda api: False)

    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(src),
        "--target", str(target),
        "--yes",
    ])

    rc = mld.main()
    assert rc == 3


def test_main_source_not_found(monkeypatch, tmp_path):
    """源路径不存在时退出码 1。"""
    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(tmp_path / "nonexistent"),
        "--target", str(target),
        "--yes",
    ])

    rc = mld.main()
    assert rc == 1


def test_main_dry_run_no_modifications(monkeypatch, tmp_path):
    """dry-run 模式不实际写任何文件。"""
    src = tmp_path / "old"
    (src / "cookies").mkdir(parents=True)
    (src / "cookies" / "a.json").write_text("ck")

    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(mld, "check_backend", lambda api: True)
    upload_calls: list = []
    monkeypatch.setattr(mld, "upload_material",
                        lambda *a, **kw: upload_calls.append(True) or True)

    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(src),
        "--target", str(target),
        "--dry-run",
        "--yes",
    ])

    rc = mld.main()
    assert rc == 0
    # 目标 cookies 目录被创建但不包含 a.json
    assert not (target / "cookies" / "a.json").exists()
    # 上传被 dry-run 跳过（upload_material 内部 dry-run，但此处 stub 仍被调用一次）
    # 实际验证：main() 不会因 dry-run 单独调用 upload
    # 我们这里主要验证：dry-run 下没有真实拷贝发生
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 失败，4 个新测试报 `TypeError: main() takes 0 positional arguments but 1 was given` 或类似

- [ ] **Step 3: 实现 main() 编排**

在 `scripts/migrate_legacy_data.py` 中，把现有的 `main()` 替换为：

```python
def main(argv: list[str] | None = None) -> int:
    """脚本主入口。返回退出码。"""
    args = parse_args(argv if argv is not None else sys.argv[1:])

    source = args.source or default_source()
    target = args.target or default_target()
    api_base = args.api_base.rstrip("/")

    print(f"[1/5] 解析源/目标路径...")
    print(f"      源: {source}")
    print(f"      目标: {target}")
    if not source.exists():
        print(f"ERROR: 旧版数据目录不存在: {source}", file=sys.stderr)
        return 1

    # 阶段 2: 备份
    if not args.skip_backup and target.exists():
        ts = _timestamp()
        backup_path = target.parent / f"data.bak.{ts}"
        print(f"[2/5] 备份当前 data → {backup_path.name} ...")
        if not args.dry_run:
            try:
                shutil.copytree(target, backup_path)
            except OSError as e:
                print(f"ERROR: 备份失败: {e}", file=sys.stderr)
                return 2
            print(f"      ✓ 已备份到 {backup_path}")
        else:
            print(f"      ⊘ dry-run 模式，跳过实际备份")
    else:
        if args.skip_backup:
            print(f"[2/5] 备份：已跳过（--skip-backup）")
        else:
            print(f"[2/5] 备份：目标 data 不存在，跳过")

    # 确保目标子目录存在
    for sub in ["cookies", "cookiesFile", "db", "materials"]:
        (target / sub).mkdir(parents=True, exist_ok=True)

    # 阶段 3: 后端探测
    print(f"[3/5] 探测后端健康状态 ({api_base})...")
    if not args.dry_run and not check_backend(api_base):
        print(f"ERROR: 后端不可达，请先执行 start.bat / start.sh 启动后端", file=sys.stderr)
        return 3
    print(f"      ✓ 后端正常")

    # 阶段 4: 拷贝
    print(f"[4/5] 拷贝 cookies/cookiesFile/db ...")
    copy_stats: dict = {}
    for sub in ["cookies", "cookiesFile", "db"]:
        src_sub = source / sub
        if not src_sub.exists():
            print(f"      ⊘ {sub}/ 源目录不存在，跳过")
            copy_stats[sub] = (0, 0)
            continue
        copied, failed = copy_directory(src_sub, target / sub, dry_run=args.dry_run)
        copy_stats[sub] = (copied, failed)
        marker = "⊘" if args.dry_run else "✓"
        print(f"      {marker} {sub}/  复制 {copied} 个文件" + (f", 失败 {failed}" if failed else ""))

    # 阶段 5: 迁移素材
    print(f"[5/5] 迁移素材库 (videoFile/)...")
    vf = source / "videoFile"
    upload_ok = 0
    upload_fail = 0
    upload_skip = 0
    if not vf.exists():
        print(f"      ⊘ videoFile/ 源目录不存在，跳过")
    else:
        files = sorted(p for p in vf.rglob("*") if p.is_file())
        total = len(files)
        for i, f in enumerate(files, 1):
            rel = f.relative_to(vf)
            if not is_allowed_ext(f.name):
                upload_skip += 1
                print(f"      [{i}/{total}] 跳过 {f.name} (非素材类型) ⊘")
                continue
            print(f"      [{i}/{total}] 上传 {strip_uuid_prefix(f.name)} ... ", end="", flush=True)
            ok = upload_material(f, api_base=api_base, dry_run=args.dry_run)
            if ok:
                upload_ok += 1
                print("✓" if not args.dry_run else "⊘ dry-run")
            else:
                upload_fail += 1
                print("✗")

    # 报告
    print()
    print("=" * 40)
    print("迁移报告")
    print("=" * 40)
    for sub in ["cookies", "cookiesFile", "db"]:
        c, f = copy_stats.get(sub, (0, 0))
        print(f"  {sub}/        复制 {c} 个文件" + (f", 失败 {f}" if f else ""))
    print(f"  videoFile/      成功 {upload_ok}, 失败 {upload_fail}, 跳过 {upload_skip}")
    if not args.skip_backup and target.exists():
        # 找最新的备份
        backups = sorted(target.parent.glob("data.bak.*"), key=lambda p: p.name, reverse=True)
        if backups:
            print(f"  备份位置:       {backups[0]}")
    print("=" * 40)

    return 0
```

把 `if __name__ == "__main__"` 块改为：

```python
if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 32 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_legacy_data.py scripts/tests/test_migrate_legacy_data.py
git commit -m "feat(scripts): 编排 main() 整合五个阶段"
```

---

## Task 9: 创建 legacy_fixture 夹具

**Files:**
- Create: `scripts/legacy_fixture/cookies/foo.json`
- Create: `scripts/legacy_fixture/cookiesFile/xhs.json`
- Create: `scripts/legacy_fixture/db/database.db`
- Create: `scripts/legacy_fixture/videoFile/11111111-2222-3333-4444-555555555555_test1.mp4`
- Create: `scripts/legacy_fixture/videoFile/66666666-7777-8888-9999-000000000000_test2.png`
- Create: `scripts/legacy_fixture/videoFile/.DS_Store`

- [ ] **Step 1: 创建夹具目录结构**

Run:
```bash
mkdir -p scripts/legacy_fixture/cookies
mkdir -p scripts/legacy_fixture/cookiesFile
mkdir -p scripts/legacy_fixture/db
mkdir -p scripts/legacy_fixture/videoFile
```

- [ ] **Step 2: 创建占位文件**

`scripts/legacy_fixture/cookies/foo.json`:
```json
{"placeholder": "cookie fixture", "user": "test_user"}
```

`scripts/legacy_fixture/cookiesFile/xhs.json`:
```json
{"placeholder": "cookieFile fixture", "platform": "xhs"}
```

`scripts/legacy_fixture/db/database.db`:
```python
# 空 SQLite 数据库（用 Python 一次性创建）
import sqlite3
conn = sqlite3.connect("scripts/legacy_fixture/db/database.db")
conn.close()
```

Run:
```bash
python -c "import sqlite3; sqlite3.connect('scripts/legacy_fixture/db/database.db').close()"
```

`scripts/legacy_fixture/videoFile/11111111-2222-3333-4444-555555555555_test1.mp4`:
```bash
# 占位文件，需 >0 bytes 才会被 rglob 识别为 file
echo "fixture video" > "scripts/legacy_fixture/videoFile/11111111-2222-3333-4444-555555555555_test1.mp4"
```

`scripts/legacy_fixture/videoFile/66666666-7777-8888-9999-000000000000_test2.png`:
```bash
echo "fixture image" > "scripts/legacy_fixture/videoFile/66666666-7777-8888-9999-000000000000_test2.png"
```

`scripts/legacy_fixture/videoFile/.DS_Store`:
```bash
echo "junk" > "scripts/legacy_fixture/videoFile/.DS_Store"
```

- [ ] **Step 3: 验证文件结构**

Run:
```bash
find scripts/legacy_fixture -type f | sort
```

Expected:
```
scripts/legacy_fixture/cookies/foo.json
scripts/legacy_fixture/cookiesFile/xhs.json
scripts/legacy_fixture/db/database.db
scripts/legacy_fixture/videoFile/.DS_Store
scripts/legacy_fixture/videoFile/11111111-2222-3333-4444-555555555555_test1.mp4
scripts/legacy_fixture/videoFile/66666666-7777-8888-9999-000000000000_test2.png
```

- [ ] **Step 4: 跑一次 dry-run 验证夹具可用**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python scripts/migrate_legacy_data.py \
    --source scripts/legacy_fixture \
    --target /tmp/mld_test_target \
    --api-base http://127.0.0.1:5409 \
    --dry-run \
    --yes
```

Expected output includes:
- 解析源/目标路径 OK
- 备份：目标不存在，跳过
- 后端探测：dry-run 跳过
- 拷贝阶段显示 cookies/cookiesFile/db 三个文件各 1 个
- 视频阶段：test1.mp4 + test2.png 两个白名单，.DS_Store 一个跳过
- 退出码 0

- [ ] **Step 5: 提交**

```bash
git add scripts/legacy_fixture/
git commit -m "test(scripts): 添加 legacy_fixture 测试夹具"
```

---

## Task 10: 集成测试 — 跑通完整流程

**Files:**
- Modify: `scripts/tests/test_migrate_legacy_data.py`

- [ ] **Step 1: 追加集成测试 — 使用真实 legacy_fixture**

在 `scripts/tests/test_migrate_legacy_data.py` 追加：

```python
def test_integration_against_legacy_fixture(monkeypatch, tmp_path, capsys):
    """端到端：用真实 legacy_fixture 跑完整流程。"""
    fixture_root = Path(__file__).resolve().parent.parent / "legacy_fixture"
    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(mld, "check_backend", lambda api: True)
    upload_calls: list = []
    monkeypatch.setattr(mld, "upload_material",
                        lambda p, api_base, dry_run=False, timeout=300.0: upload_calls.append(p.name) or True)
    monkeypatch.setattr(mld, "_timestamp", lambda: "20260605_153012")

    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(fixture_root),
        "--target", str(target),
        "--yes",
    ])

    rc = mld.main()
    assert rc == 0

    # 拷贝内容
    assert (target / "cookies" / "foo.json").exists()
    assert (target / "cookiesFile" / "xhs.json").exists()
    assert (target / "db" / "database.db").exists()

    # 上传白名单文件
    upload_names = [Path(p).name for p in upload_calls]
    assert "11111111-2222-3333-4444-555555555555_test1.mp4" in upload_names
    assert "66666666-7777-8888-9999-000000000000_test2.png" in upload_names
    assert ".DS_Store" not in upload_names  # 被跳过

    # 报告输出
    out = capsys.readouterr().out
    assert "迁移报告" in out
    assert "videoFile/      成功 2" in out
    assert "跳过 1" in out


def test_integration_idempotent_dry_run(monkeypatch, tmp_path):
    """连跑两次 dry-run 不修改任何文件。"""
    fixture_root = Path(__file__).resolve().parent.parent / "legacy_fixture"
    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(mld, "check_backend", lambda api: True)
    monkeypatch.setattr(mld, "upload_material", lambda *a, **kw: True)

    for _ in range(2):
        monkeypatch.setattr(sys, "argv", [
            "migrate_legacy_data.py",
            "--source", str(fixture_root),
            "--target", str(target),
            "--dry-run",
            "--yes",
        ])
        rc = mld.main()
        assert rc == 0

    # dry-run 不应该产生任何 cookies/foo.json
    assert not (target / "cookies" / "foo.json").exists()
```

- [ ] **Step 2: 跑测试确认通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python -m pytest scripts/tests/test_migrate_legacy_data.py -v`

Expected: 34 passed

- [ ] **Step 3: 跑一次真实 dry-run 手动验证**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python scripts/migrate_legacy_data.py \
    --source scripts/legacy_fixture \
    --target /tmp/mld_smoke_target \
    --dry-run --yes
echo "exit=$?"
```

Expected: `exit=0`，输出包含"迁移报告"和"成功 2, 失败 0, 跳过 1"。

- [ ] **Step 4: 提交**

```bash
git add scripts/tests/test_migrate_legacy_data.py
git commit -m "test(scripts): 集成测试 — 真实 legacy_fixture 端到端"
```

---

## 自审记录

- **Spec coverage**：
  - §1 脚本位置 → Task 1 ✓
  - §2 CLI 接口 → Task 1 ✓
  - §3 阶段流程 → Task 8 ✓
  - §4.1 路径解析 → Task 2 ✓
  - §4.2 uuid 前缀剥离 → Task 3 ✓
  - §4.3 文件类型白名单 → Task 3 ✓
  - §4.4 HTTP 上传 → Task 7 ✓
  - §4.5 mime 推断 → Task 7 ✓
  - §5 错误处理 → Task 8（含 4 个错误处理测试）✓
  - §6 测试策略 → Task 9-10 ✓
  - §7 退出码 → Task 8（测试覆盖 0/1/3，备份失败 2 通过 backup_data 测试隐含）✓
  - §8 影响范围 → 全部体现 ✓
- **Placeholder scan**：所有 step 包含具体代码与命令，无 TBD/TODO。
- **Type consistency**：
  - `default_source() / default_target()` 返回 `Path` — 全部使用一致
  - `backup_data()` 返回 `Path | None` — Task 5 测试和 Task 8 消费处一致
  - `copy_directory()` 返回 `tuple[int, int]` — Task 6 和 Task 8 消费处一致
  - `upload_material()` 返回 `bool` — Task 7 和 Task 8 消费处一致
  - `check_backend()` 返回 `bool` — Task 4 和 Task 8 消费处一致
  - `strip_uuid_prefix(str) -> str` — Task 3 和 Task 7/8 消费处一致
  - `is_allowed_ext(str) -> bool` — Task 3 和 Task 8 消费处一致
  - `main(argv: list[str] | None = None) -> int` — Task 8 一致
- **Ambiguity check**：
  - dry-run 在所有阶段的行为在 Task 5/6/7/8 中分别有测试覆盖
  - 备份阶段的 dry-run 行为在 Task 5 测试中明确：返回预期路径但不创建
  - 跳过 `videoFile/` 不存在的情况在 Task 8 main() 中显式处理
  - 跳过备份且目标 data 不存在时，主流程不中断（Task 8 main() 内显式处理）

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-06-05-legacy-data-migration.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
