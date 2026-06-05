# 旧版 Windows 客户端数据迁移脚本

> 提供一个独立 Python 脚本，把旧版 Windows 客户端的用户数据迁移到新版项目 `data/` 目录。

---

## 背景与问题

旧版 Windows 客户端把用户数据存放在：

```
C:\Users\{用户名}\AppData\Local\Social Auto Upload Web UI\
├─ cookies\         # 账号登录 Cookie
├─ cookiesFile\     # 平台上传用的 Cookie 文件
├─ db\              # SQLite 数据库
└─ videoFile\       # 旧版"素材库"目录，文件命名 {uuid}_{原文件名}
```

新版项目已重构，素材通过 `POST /api/materials/upload` 走统一存储（`materials/{YYYY}/{MM}/{uuid}{ext}` + 缩略图自动抽帧 + 写入 `materials` 表），不再使用 `videoFile/` 平铺目录。需要在用户首次升级到新版时，提供一条迁移路径，把旧版数据落到新版的 `data/`。

---

## 方案选型

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A: Python + requests 调后端 HTTP 上传 (选定)** | 脚本独立运行，先拷贝 cookies/cookiesFile/db，再逐个 POST 旧版素材 | 单一职责、与新版上传路径同源、零业务逻辑冗余、storage 未来扩展（S3 等）零代码改动 | 依赖 requests 库 |
| B: Python import 后端 storage 模块直写 | 绕过 HTTP，直接 import `storage.get_storage()` + INSERT materials 表 | 稍快、绕开 HTTP 序列化 | 耦合后端代码路径、抽帧/缩略图/mime 推断需自实现 |
| C: PowerShell + curl | 完全脱离 Python | Windows 零依赖 | multipart 构造、进度打印、断点续传都要手写、风格不一致 |

---

## 1. 脚本位置与形态

```
scripts/
└── migrate_legacy_data.py    # 单一 Python 脚本
```

- 与现有 `scripts/download-cloakbrowser-binary.py` 风格一致
- 可被未来 `start.bat` / `start.sh` 链式调用（暂不接入）

## 2. CLI 接口

```
python scripts/migrate_legacy_data.py
    [--source <path>]                 # 旧版数据目录，默认 %LOCALAPPDATA%\Social Auto Upload Web UI
    [--target <path>]                 # 新版 data 目录，默认 {项目根}/data（与 backend/conf.py 对齐）
    [--api-base http://127.0.0.1:5409]
    [--dry-run]                       # 只列出将执行的操作，不真正修改任何文件
    [--skip-backup]                   # 跳过备份（仅在你已经手动备份过时使用）
    [--yes]                           # 跳过交互式确认
```

示例输出（成功路径）：

```
[1/5] 解析源/目标路径...
       源: C:\Users\foo\AppData\Local\Social Auto Upload Web UI
       目标: D:\proj\ai\social-auto-upload-web-ui\data
[2/5] 备份当前 data → data.bak.20260605_153012 ...
       ✓ 已备份 (342 MB)
[3/5] 探测后端健康状态 (http://127.0.0.1:5409)...
       ✓ 后端正常
[4/5] 拷贝 cookies/cookiesFile/db ...
       ✓ cookies/         复制 12 个文件
       ✓ cookiesFile/     复制 10 个文件
       ✓ db/database.db   复制 1 个文件
[5/5] 迁移素材库 (videoFile/)...
       [1/45] 上传 大理女孩-成品.mp4 ... ✓
       [2/45] 上传 西安女孩-动态分镜版.mp4 ... ✓
       ...
       [45/45] 跳过 制作《大理女孩》封面图.png (非素材类型) ⊘

========================================
迁移报告
========================================
  cookies/        复制 12 个文件
  cookiesFile/    复制 10 个文件
  db/             复制 1 个文件
  videoFile/      成功 38，失败 2，跳过 5
  备份位置:       data.bak.20260605_153012
  耗时:           1m 23s
========================================
```

## 3. 阶段流程

| 阶段 | 动作 | 失败行为 |
|------|------|----------|
| 1. 解析路径 | 展开 `%LOCALAPPDATA%`，解析 `--source`/`--target`/`--api-base` | 路径不存在 → 退出码 1 |
| 2. 备份 | 把整个 `data/` 复制到 `data.bak.YYYYMMDD_HHMMSS/` | 备份失败 → 退出码 2，不动目标 |
| 3. 后端探测 | `GET {api}/api/materials/list?page=1&page_size=1`，2s 超时 | 非 200 → 提示"请先执行 start.bat/start.sh"，退出码 3 |
| 4. 拷贝 | `shutil.copy2` 遍历 `cookies/`、`cookiesFile/`、`db/` 三个目录到目标 | 单文件失败 → 打印错误，继续；阶段报告失败数 |
| 5. 迁移素材 | 遍历 `videoFile/` 调用 `POST /api/materials/upload` | 单文件失败 → 打印文件名+错误，继续；阶段报告 |

## 4. 关键算法

### 4.1 路径解析

```python
def default_source() -> Path:
    # Windows: %LOCALAPPDATA%\Social Auto Upload Web UI
    # 非 Windows（开发/测试）: ./data/legacy_fixture/
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "Social Auto Upload Web UI"
    return Path(__file__).parent / "legacy_fixture"

def default_target() -> Path:
    # 与 backend/conf.py 对齐：SAU_DATA_DIR 优先，否则 {脚本父目录的父目录}/data
    env = os.environ.get("SAU_DATA_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "data"
```

> 目标 `data/` 不存在时，脚本会 `mkdir(parents=True, exist_ok=True)`，并创建 `cookies/cookiesFile/db/materials` 必要子目录（与 `backend/conf.py` 一致）。但仍建议先启动一次后端以初始化完整结构。

### 4.2 uuid 前缀剥离

```python
UUID_PREFIX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_",
    re.IGNORECASE,
)

def strip_uuid_prefix(name: str) -> str:
    return UUID_PREFIX.sub("", name, count=1)
```

例：`1781ca06-5427-11f1-8000-bc2411b9d4e7_大理女孩-成品.mp4` → `大理女孩-成品.mp4`

### 4.3 文件类型白名单

```python
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v", ".wmv", ".mpeg", ".mpg"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
ALLOWED_EXTS = VIDEO_EXTS | IMAGE_EXTS
```

不在白名单的文件（如 `.DS_Store`、`Thumbs.db`、`*.tmp`）计入"已跳过"。

### 4.4 HTTP 上传

```python
with open(file_path, "rb") as f:
    resp = requests.post(
        f"{api_base}/api/materials/upload",
        files={"file": (original_filename, f, mime_type)},
        timeout=300,  # 大文件
    )
resp.raise_for_status()
```

后端响应 `data.id`、`data.stored_path`、`data.thumbnail_path` 不需要回传——后端已自动落库。

### 4.5 mime 推断

复用 `mimetypes.guess_type()` 即可（系统自带），不引入额外依赖。

## 5. 错误处理

| 错误 | 行为 |
|------|------|
| 源路径不存在 | 退出码 1，打印"未找到旧版数据目录" |
| 目标 data 不存在 | 退出码 1，提示"请先启动一次后端以初始化 data 目录" |
| 备份失败（磁盘满等） | 退出码 2，不动目标 |
| 后端不可达 | 退出码 3，提示运行 `start.bat`/`start.sh` |
| 单个 cookies/cookiesFile/db 文件拷贝失败 | 打印 `ERROR: <path>: <err>`，继续；阶段报告失败数 |
| 单个素材上传失败（非 2xx / 网络异常） | 打印 `ERROR: <name>: HTTP {code} {body[:200]}`，继续；阶段报告失败数 |
| 全部素材失败 | 最终退出码 0（按"单项失败跳过"约定），但报告标注 `videoFile 0 成功` |

## 6. 测试策略

在开发机（macOS/Linux）无法访问 `%LOCALAPPDATA%`，需提供"假旧版"夹具：

```
scripts/legacy_fixture/
├─ cookies/foo.json
├─ cookiesFile/xhs.json
├─ db/database.db
└─ videoFile/
   ├─ {uuid}_test1.mp4
   ├─ {uuid}_test2.png
   └─ .DS_Store         # 应被跳过
```

测试用例（手工 + 集成）：

| 场景 | 断言 |
|------|------|
| 默认路径探测 | `default_source()` 在非 Windows 下指向 `scripts/legacy_fixture/` |
| uuid 前缀剥离 | `strip_uuid_prefix("a-b-c-d-e_test.mp4") == "test.mp4"` |
| 拷贝阶段 | 目标 `data/cookies/foo.json` 存在且内容一致 |
| 上传阶段 | `materials` 表新增记录数 == videoFile 白名单文件数；`data/materials/YYYY/MM/` 下有新文件 |
| 跳过 | `.DS_Store` 不出现在 `materials` 表 |
| 备份 | `data.bak.YYYYMMDD_HHMMSS/data/cookies/foo.json` 存在 |
| 后端不可达 | 退出码 3 |
| dry-run | 目标 `data/` 无任何修改；终端打印将执行的操作列表 |

测试入口：`python scripts/migrate_legacy_data.py --dry-run --source scripts/legacy_fixture`

## 7. 退出码

| 码 | 含义 |
|----|------|
| 0 | 全部阶段完成（即使个别素材失败也算 0，由报告反映） |
| 1 | 参数/路径错误 |
| 2 | 备份失败 |
| 3 | 后端不可达 |

## 8. 影响范围

| 文件 | 变更 |
|------|------|
| `scripts/migrate_legacy_data.py` | **新增** — 迁移脚本本体 |
| `scripts/legacy_fixture/` | **新增** — 开发测试用假旧版目录 |
| `requirements.txt` | 不变（`requests` 已存在） |
| `docs/superpowers/specs/2026-06-05-legacy-data-migration-design.md` | 本设计文档 |

未来可能的二次改动（**不在本次范围**）：

- 接入 `start.bat` / `start.sh` 自动探测旧版数据并询问是否迁移
- 支持"断点续传"（记录已迁移文件清单到 `data/.migration_state.json`）
- 把迁移能力封装为后端 `/api/admin/migrate-from-legacy` 端点供 Tauri 桌面端调用

## 9. 开放问题

无 — 全部设计决策已在 brainstorming 阶段与用户对齐。

## 10. 自审记录

- **Placeholder scan**：无 TBD/TODO。
- **Internal consistency**：阶段流程（3）↔ 错误处理（5）↔ 退出码（7）三者一致。
- **Scope**：单一脚本，可被单一实施计划覆盖。
- **Ambiguity**：uuid 前缀剥离用 `count=1` 限定仅剥一次；白名单用集合精确匹配；备份命名格式 `data.bak.YYYYMMDD_HHMMSS` 唯一；dry-run 不修改任何文件，明确写在 CLI 说明与测试用例中。
