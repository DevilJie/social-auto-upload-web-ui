# 个性化发布配置 + 发布历史明细卡片化 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 PublishCenter.vue / ImagePublish.vue 增加平台级 + 账号级"个性化配置"复选框，让用户能在一个批次里给不同账号配不同的视频/封面/标题描述/标签；将合并后的完整数据写入 `publish_details.account_configs`；把 PublishHistory 的明细行全部重设计为卡片，呈现每个账号实际发布的内容。

**Architecture:**
- 前后端协同：前端 `mergeConfig` 按"账号覆写 > 平台覆写 > 渠道默认 > 公共区域"4 级优先级合并；后端接收合并结果存入 `account_configs` JSON
- 派生字段 `personalized` 在后端响应时按规则计算（不存库）
- 草稿 JSON 扩 4 个键：platformOverrides / accountOverrides / platformChecked / accountChecked
- 草稿后端先做"透传验证"，不通过则改后端

**Tech Stack:** Vue 3 (Composition API) + Element Plus + Pinia / Flask + SQLite + Playwright

**关联 Spec:** `docs/superpowers/specs/2026-06-09-personalized-publish-config-design.md`

---

## 文件结构（按职责）

| 文件 | 职责 |
|---|---|
| `scripts/verify_draft_passthrough.py` | 验证草稿后端透传新键（前置） |
| `backend/ext_api/task_queue.py` | `PublishTask` 加字段、`_insert_db` cfg 扩字段 |
| `backend/app.py` | `/postVideo` 路由透传新字段到 task |
| `backend/blueprints/image_publish_bp.py` | `/api/image-publish/publish` 扩 account_configs 字段 |
| `backend/ext_api/__init__.py` | `/api/v2/history` 抽 `_compute_personalized()` + 注入字段 |
| `backend/tests/test_personalized_config.py` | 新增测试 |
| `frontend/src/components/douyin/ImagePublishPanel.vue` | 新增 `getConfig()` 方法（仅） |
| `frontend/src/components/xiaohongshu/ImagePublishPanel.vue` | 同上 |
| `frontend/src/components/kuaishou/ImagePublishPanel.vue` | 同上 |
| `frontend/src/views/PublishCenter.vue` | 加覆写区 state/UI、mergeConfig、saveDraft/loadDraft 改造 |
| `frontend/src/views/ImagePublish.vue` | 同上 |
| `frontend/src/views/PublishHistory.vue` | `.detail-row` → `.detail-card` 卡片化 |

---

## Task 0: 草稿后端透传验证（前置）

**Files:**
- Create: `scripts/verify_draft_passthrough.py`

- [ ] **Step 1: 写一个最小测试脚本验证草稿后端透传新键**

```python
"""验证 /api/drafts 透传 platformOverrides / accountOverrides / platformChecked / accountChecked。
实施前必跑——如果失败则需要改后端（参考 spec §4.4）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

BASE = "http://127.0.0.1:5409"
NEW_KEYS = {
    "platformOverrides": {"douyin": {"title": "ov-title"}},
    "accountOverrides": {"1": {"title": "acc-ov-title"}},
    "platformChecked": {"douyin": True},
    "accountChecked": {"1": True},
}


def test_drafts_passthrough():
    payload = {
        "type": "video",
        "name": "verify-draft-passthrough",
        "data": {
            "commonConfig": {},
            "platformConfigs": {},
            **NEW_KEYS,
        },
    }
    r = requests.post(f"{BASE}/api/drafts", json=payload, timeout=5)
    assert r.status_code == 200, f"POST 失败: {r.status_code} {r.text}"
    draft_id = r.json()["data"]["id"]

    r2 = requests.get(f"{BASE}/api/drafts/{draft_id}", timeout=5)
    assert r2.status_code == 200
    body = r2.json()["data"]
    data = json.loads(body["data"]) if isinstance(body["data"], str) else body["data"]

    for key, expected in NEW_KEYS.items():
        assert data.get(key) == expected, f"键 {key} 透传失败: 期望 {expected}, 实际 {data.get(key)}"
    print("✓ 草稿后端透传 4 个新键成功")

    # 清理
    requests.delete(f"{BASE}/api/drafts/{draft_id}", timeout=5)


if __name__ == "__main__":
    test_drafts_passthrough()
```

- [ ] **Step 2: 启动后端（端口 5409），跑验证脚本**

```bash
# 终端 1：启后端
cd backend && python3 app.py

# 终端 2：跑验证
python3 scripts/verify_draft_passthrough.py
```

期望：输出 `✓ 草稿后端透传 4 个新键成功`

- [ ] **Step 3: 若失败，定位并修复后端**

- 查看 `backend/app.py` 的 `/api/drafts` 路由（行号约 631、663、688）
- 入参是否做了白名单校验 → 去掉白名单或补 4 个键
- 出参是否做了字段过滤 → 补 4 个键
- 数据库 `drafts.data` / `image_drafts.data` 列类型 → 确认是 TEXT 够大
- 重复 Step 2 直到通过

- [ ] **Step 4: 提交（如果改了后端）**

```bash
git add scripts/verify_draft_passthrough.py backend/app.py
git commit -m "feat(draft): 草稿后端透传 platformOverrides/accountOverrides 等 4 个新键"
```

---

## Task 1: 扩展 `PublishTask` dataclass + `_insert_db` cfg dict（视频）

**Files:**
- Modify: `backend/ext_api/task_queue.py:30-80`（PublishTask 类）、`285-315`（_insert_db）

- [ ] **Step 1: 写测试**

创建 `backend/tests/test_personalized_config.py`：

```python
"""测试个性化配置：视频/封面/全 per-platform form 字段持久化到 account_configs"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS publish_batches (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    video_material_id TEXT DEFAULT '',
    image_material_ids TEXT DEFAULT '[]',
    landscape_cover_material_id TEXT DEFAULT '',
    portrait_cover_material_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    account_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    schedule_time TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS publish_details (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    account_id INTEGER,
    account_name TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    account_configs TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    error_message TEXT NOT NULL DEFAULT '',
    publish_url TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES publish_batches(id) ON DELETE CASCADE
);
"""


def _setup_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    for stmt in _SCHEMA_SQL.split(";") :
        s = stmt.strip()
        if s:
            conn.execute(s)
    conn.commit()
    conn.close()


_setup_db()

from ext_api.task_queue import PublishTask, TaskQueue  # noqa: E402


class TestPublishTaskPersonalizedFields(unittest.TestCase):
    def setUp(self):
        _setup_db()
        # 每个测试用独立 task id 避免互扰
        self.t = PublishTask(
            id="task-1",
            batch_id="batch-1",
            account_name="accA",
            platform="抖音",
            platform_type=3,
            title="夏日穿搭",
            description="三套穿搭分享",
            tags=["#穿搭"],
            thumbnail_path="uploads/cover.jpg",
            video_landscape={"id": "v1", "stored_path": "uploads/v1.mp4"},
            video_portrait={"id": "v2", "stored_path": "uploads/v2.mp4"},
            cover_landscape={"id": "c1", "stored_path": "uploads/c1.jpg"},
            cover_portrait={"id": "c2", "stored_path": "uploads/c2.jpg"},
            video_format="portrait",
            enable_timer=0,
            schedule_time="",
            ai_content="内容由AI生成",
            is_original=True,
        )

    def test_account_configs_contains_video_landscape(self):
        # 验证 cfg 包含视频/封面/平台字段（不入库，只构造）
        from ext_api.task_queue import _build_account_configs  # 见 Step 3
        cfg = _build_account_configs(self.t)
        self.assertEqual(cfg["videoLandscape"]["id"], "v1")
        self.assertEqual(cfg["videoPortrait"]["id"], "v2")
        self.assertEqual(cfg["coverLandscape"]["id"], "c1")
        self.assertEqual(cfg["coverPortrait"]["id"], "c2")

    def test_account_configs_contains_per_platform_fields(self):
        from ext_api.task_queue import _build_account_configs  # 见 Step 3
        cfg = _build_account_configs(self.t)
        self.assertEqual(cfg["videoFormat"], "portrait")
        self.assertEqual(cfg["enableTimer"], 0)
        self.assertEqual(cfg["scheduleTime"], "")
        self.assertEqual(cfg["aiContent"], "内容由AI生成")
        self.assertTrue(cfg["isOriginal"])

    def test_insert_db_persists_full_config(self):
        q = TaskQueue()
        q._insert_db(self.t)

        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT account_configs FROM publish_details WHERE id = ?", ("task-1",)
            ).fetchone()
        self.assertIsNotNone(row)
        cfg = json.loads(row[0])
        self.assertEqual(cfg["videoLandscape"]["id"], "v1")
        self.assertEqual(cfg["aiContent"], "内容由AI生成")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认 FAIL**

```bash
cd backend && python3 -m pytest tests/test_personalized_config.py -v
```

期望：FAIL（`PublishTask` 缺新字段，`_build_account_configs` 不存在）

- [ ] **Step 3: 在 `backend/ext_api/task_queue.py` 改 `PublishTask` + 抽 `_build_account_configs`**

修改 `PublishTask` dataclass（文件顶，约 30-80 行），在已有字段后追加：

```python
@dataclass
class PublishTask:
    # ... 现有字段 ...
    title: str = ''
    description: str = ''
    tags: list = field(default_factory=list)
    thumbnail_path: str = ''
    platform_type: int = 0

    # 新增：个性化配置字段
    video_landscape: dict | None = None
    video_portrait: dict | None = None
    cover_landscape: dict | None = None
    cover_portrait: dict | None = None
    video_format: str | None = None
    enable_timer: int | None = None
    schedule_time: str | None = None
    ai_content: str | None = None
    is_original: bool | None = None
```

在 `PublishTask` 定义后（约 80 行附近）添加独立函数：

```python
def _build_account_configs(task: 'PublishTask') -> dict:
    """构造写入 publish_details.account_configs 的 dict。
    含全 per-platform form 字段，让历史卡片能完整还原发布时的内容。"""
    return {
        'title': task.title,
        'description': task.description,
        'tags': task.tags,
        'thumbnail_path': task.thumbnail_path,
        'platform_type': task.platform_type,
        'videoLandscape': task.video_landscape,
        'videoPortrait': task.video_portrait,
        'coverLandscape': task.cover_landscape,
        'coverPortrait': task.cover_portrait,
        'videoFormat': task.video_format,
        'enableTimer': task.enable_timer,
        'scheduleTime': task.schedule_time,
        'aiContent': task.ai_content,
        'isOriginal': task.is_original,
    }
```

修改 `_insert_db`（约 285-315 行）：

```python
def _insert_db(self, task: PublishTask):
    """插 1 行 publish_batches（如果不存在）+ 1 行 publish_details"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO publish_batches
                   (id, type, title, description, video_material_id,
                    landscape_cover_material_id, portrait_cover_material_id,
                    account_count, status, created_at, updated_at)
                   VALUES (?, 'video', ?, ?, '', '', '', 0, 'pending', ?, ?)""",
                (task.batch_id or task.id, task.title, task.description,
                 task.created_at, task.created_at)
            )
            cfg = _build_account_configs(task)
            conn.execute(
                """INSERT INTO publish_details
                   (id, batch_id, account_id, account_name, platform, account_configs,
                    status, created_at)
                   VALUES (?, ?, NULL, ?, ?, ?, ?, ?)""",
                (task.id, task.batch_id or task.id, task.account_name, task.platform,
                 json.dumps(cfg, ensure_ascii=False), task.status, task.created_at)
            )
    except Exception as e:
        logger.info(f"[TaskQueue] 插入数据库失败: {e}")
```

- [ ] **Step 4: 跑测试，确认 PASS**

```bash
cd backend && python3 -m pytest tests/test_personalized_config.py -v
```

期望：3 个 test 全 PASS

- [ ] **Step 5: 跑现有测试，确认无回归**

```bash
cd backend && python3 -m pytest tests/ -v
```

期望：现有测试（`test_postvideo_writes.py` / `test_task_queue_writes.py` / `test_publish_templates_v2.py` 等）仍 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/ext_api/task_queue.py backend/tests/test_personalized_config.py
git commit -m "feat(task-queue): PublishTask 加个性化配置字段，account_configs 存全 per-platform form"
```

---

## Task 2: `/postVideo` 路由透传新字段

**Files:**
- Modify: `backend/app.py:445-509`（postVideo 路由）

- [ ] **Step 1: 写测试**

追加到 `backend/tests/test_personalized_config.py`：

```python
class TestPostVideoPassthrough(unittest.TestCase):
    def setUp(self):
        _setup_db()

    def test_postvideo_writes_overrides_to_publish_details(self):
        """验证 /postVideo 接收 videoLandscape/videoPortrait/coverLandscape/coverPortrait
        并写入 publish_details.account_configs"""
        from app import app  # 直接 import Flask app
        client = app.test_client()

        payload = {
            "type": 3,  # 抖音
            "title": "测试标题",
            "description": "测试描述",
            "tags": ["#tag1"],
            "fileList": ["uploads/test.mp4"],
            "accountList": [],
            "thumbnailLandscape": "",
            "thumbnailPortrait": "",
            "videoLandscape": {"id": "v-uuid", "stored_path": "uploads/v.mp4", "name": "v.mp4"},
            "videoPortrait": {"id": "v-uuid2", "stored_path": "uploads/v2.mp4"},
            "coverLandscape": {"id": "c-uuid", "stored_path": "uploads/c.jpg"},
            "coverPortrait": {"id": "c-uuid2", "stored_path": "uploads/c2.jpg"},
            "videoFormat": "portrait",
            "aiContent": "内容由AI生成",
            "isOriginal": True,
            "enableTimer": 0,
            "scheduleTime": "",
        }

        with patch('app._resolve_material_path', return_value="uploads/test.mp4"), \
             patch('app.get_platform') as mock_get_platform, \
             patch('app._before_publish'), \
             patch('app._after_publish', side_effect=lambda r: r):
            mock_platform = MagicMock()
            mock_platform.publish_video.return_value = {"code": 200, "status": "success"}
            mock_get_platform.return_value = mock_platform

            r = client.post('/postVideo', json=payload)
            self.assertEqual(r.status_code, 200)

        # 检查 DB
        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT account_configs FROM publish_details ORDER BY created_at DESC LIMIT 1"
            ).fetchall()
        self.assertEqual(len(rows), 1)
        cfg = json.loads(rows[0][0])
        self.assertEqual(cfg["videoLandscape"]["id"], "v-uuid")
        self.assertEqual(cfg["coverPortrait"]["id"], "c-uuid2")
        self.assertEqual(cfg["aiContent"], "内容由AI生成")
        self.assertTrue(cfg["isOriginal"])
```

- [ ] **Step 2: 跑测试，确认 FAIL**

```bash
cd backend && python3 -m pytest tests/test_personalized_config.py::TestPostVideoPassthrough -v
```

期望：FAIL（后端 `/postVideo` 没把新字段写到 task）

- [ ] **Step 3: 在 `/postVideo` 路由加新字段提取并传给 `publish_video`**

修改 `backend/app.py` 路由（约 445-540 行）。在现有参数提取（约 468-475 行 `activities = data.get(...)` 之后）追加：

```python
# 个性化配置：视频/封面/平台字段
video_landscape = data.get('videoLandscape')
video_portrait = data.get('videoPortrait')
cover_landscape = data.get('coverLandscape')
cover_portrait = data.get('coverPortrait')
video_format = data.get('videoFormat', 'portrait')
enable_timer = data.get('enableTimer', 0)
schedule_time = data.get('scheduleTime', '')
ai_content = data.get('aiContent', '')
is_original = data.get('isOriginal', False)
```

把 `publish_video` 调用（约 478-509 行）改为在调用前构造 `PublishTask` 并把字段塞进去。具体：

找到 `_before_publish` 调用（约 525 行附近）；`/postVideo` 路由实际上**没显式构造 `PublishTask`**——它把字段透传给 `platform.publish_video`，再由 `_before_publish` 钩子构造 `PublishTask`。

去查 `backend/app.py` 的 `_before_publish`（行号 737）和 `_record_publish`（行号 638）。在 `_before_publish` 里构造 `PublishTask` 时（应该就在那一段），把新字段加进去。

具体改动示例（如果 `_before_publish` 里有 `PublishTask(...title=..., description=..., tags=..., thumbnail_path=...)`，改成）：

```python
from ext_api.task_queue import PublishTask  # 如果没 import 就加

task = PublishTask(
    id=detail_id,
    batch_id=batch_id,
    account_name=account_name,
    platform=platform_name,
    platform_type=platform_type,
    title=title,
    description=description,
    tags=tags,
    thumbnail_path=thumbnail_path,
    video_landscape=data.get('videoLandscape'),
    video_portrait=data.get('videoPortrait'),
    cover_landscape=data.get('coverLandscape'),
    cover_portrait=data.get('coverPortrait'),
    video_format=data.get('videoFormat'),
    enable_timer=data.get('enableTimer'),
    schedule_time=data.get('scheduleTime'),
    ai_content=data.get('aiContent'),
    is_original=data.get('isOriginal'),
)
```

> **注意**：实施前先 `Read` `backend/app.py:737-820` 看 `_before_publish` 实际怎么构造 task，按实际情况改。不一定是 dataclass 构造，也可能是 setattr 或 dict 形式。

- [ ] **Step 4: 跑测试，确认 PASS**

```bash
cd backend && python3 -m pytest tests/test_personalized_config.py::TestPostVideoPassthrough -v
```

期望：PASS

- [ ] **Step 5: 跑全套测试，确认无回归**

```bash
cd backend && python3 -m pytest tests/ -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/app.py
git commit -m "feat(postVideo): 透传 videoLandscape/coverLandscape/aiContent 等个性化字段到 PublishTask"
```

---

## Task 3: `/api/image-publish/publish` 扩 account_configs 字段

**Files:**
- Modify: `backend/blueprints/image_publish_bp.py:79-145`（publish_images 路由）

- [ ] **Step 1: 写测试**

追加到 `backend/tests/test_personalized_config.py`：

```python
class TestImagePublishPersistsOverrides(unittest.TestCase):
    def setUp(self):
        _setup_db()

    def test_publish_images_stores_images_and_cover_in_account_configs(self):
        """图文发布的 account_configs 应包含 images 列表和 coverImage 对象"""
        from blueprints.image_publish_bp import image_publish_bp
        from flask import Flask
        app = Flask(__name__)
        app.register_blueprint(image_publish_bp)

        client = app.test_client()
        payload = {
            "image_ids": ["img-1", "img-2"],
            "batchId": "batch-img-1",
            "account_configs": {
                "platform": "抖音",
                "account_id": 10,
                "account_name": "账号A",
                "title": "图文标题",
                "description": "图文描述",
                "tags": ["#t1"],
                "images": [
                    {"id": "img-1", "stored_path": "uploads/1.jpg", "name": "1.jpg"},
                    {"id": "img-2", "stored_path": "uploads/2.jpg", "name": "2.jpg"},
                ],
                "coverImage": {"id": "img-1", "stored_path": "uploads/1.jpg"},
                "enableTimer": 0,
                "scheduleTime": "",
            },
        }

        with patch('blueprints.image_publish_bp.get_platform') as mock_get_platform:
            mock_platform = MagicMock()
            mock_platform.publish_image = MagicMock(return_value={"code": 200, "status": "success"})
            mock_get_platform.return_value = mock_platform

            r = client.post('/api/image-publish/publish', json=payload)
            self.assertEqual(r.status_code, 200, r.json)

        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT account_configs FROM publish_details ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        cfg = json.loads(row[0])
        self.assertEqual(len(cfg["images"]), 2)
        self.assertEqual(cfg["images"][0]["id"], "img-1")
        self.assertEqual(cfg["coverImage"]["id"], "img-1")
        self.assertEqual(cfg["title"], "图文标题")
```

- [ ] **Step 2: 跑测试，确认 FAIL**

```bash
cd backend && python3 -m pytest tests/test_personalized_config.py::TestImagePublishPersistsOverrides -v
```

期望：FAIL（`account_configs` 当前过滤掉了 `images` / `coverImage`）

- [ ] **Step 3: 改 `image_publish_bp.py` 不再过滤 images/coverImage**

在 `backend/blueprints/image_publish_bp.py` 的 `publish_images` 函数（约 79-145 行）找到：

```python
excluded = {'landscapeCoverMaterialId', 'portraitCoverMaterialId'}
account_configs = {k: v for k, v in config.items() if k not in excluded}
```

**改 excluded 集合**加上 `'filePath'`（因为 filePath 已经在 `image_ids` 体现，不需要重复）：

```python
excluded = {'landscapeCoverMaterialId', 'portraitCoverMaterialId', 'filePath'}
```

> `images` 和 `coverImage` 不加入 excluded，所以会写入 `account_configs` JSON。

- [ ] **Step 4: 跑测试，确认 PASS**

```bash
cd backend && python3 -m pytest tests/test_personalized_config.py::TestImagePublishPersistsOverrides -v
```

期望：PASS

- [ ] **Step 5: 跑现有 `test_image_publish_endpoint.py` 确认无回归**

```bash
cd backend && python3 -m pytest tests/test_image_publish_endpoint.py -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/blueprints/image_publish_bp.py
git commit -m "feat(image-publish): account_configs 持久化 images/coverImage 覆写"
```

---

## Task 4: `/api/v2/history` 加 `personalized` 派生字段

**Files:**
- Modify: `backend/ext_api/__init__.py:285-405`（get_history）+ 顶部 import 区域

- [ ] **Step 1: 写测试**

追加到 `backend/tests/test_personalized_config.py`：

```python
class TestComputePersonalized(unittest.TestCase):
    """测试 _compute_personalized 函数"""

    def test_personalized_true_when_title_differs(self):
        from ext_api._personalized import compute_personalized
        cfg = {"title": "渠道专属标题", "description": "公共描述"}
        batch = {"title": "公共标题", "description": "公共描述"}
        self.assertTrue(compute_personalized(cfg, batch))

    def test_personalized_false_when_identical(self):
        from ext_api._personalized import compute_personalized
        cfg = {"title": "公共标题", "description": "公共描述"}
        batch = {"title": "公共标题", "description": "公共描述"}
        self.assertFalse(compute_personalized(cfg, batch))

    def test_personalized_true_when_cover_differs(self):
        from ext_api._personalized import compute_personalized
        cfg = {"coverLandscape": {"id": "c-ov"}, "title": "t", "description": "d"}
        batch = {"landscape_cover_material_id": "c-default", "title": "t", "description": "d"}
        self.assertTrue(compute_personalized(cfg, batch))

    def test_personalized_true_when_video_differs(self):
        from ext_api._personalized import compute_personalized
        cfg = {"videoLandscape": {"id": "v-ov"}, "title": "t", "description": "d"}
        batch = {"video_material_id": "v-default", "title": "t", "description": "d"}
        self.assertTrue(compute_personalized(cfg, batch))

    def test_personalized_skips_tags(self):
        from ext_api._personalized import compute_personalized
        # publish_batches 不存 tags，所以即使 tags 不同也不算 personalized
        cfg = {"tags": ["#a"], "title": "t", "description": "d"}
        batch = {"title": "t", "description": "d"}
        self.assertFalse(compute_personalized(cfg, batch))

    def test_personalized_image_differs(self):
        from ext_api._personalized import compute_personalized
        cfg = {"images": [{"id": "i1"}, {"id": "i2"}]}
        batch = {"image_material_ids": '["i1","i3"]'}
        self.assertTrue(compute_personalized(cfg, batch))

    def test_personalized_image_same(self):
        from ext_api._personalized import compute_personalized
        cfg = {"images": [{"id": "i1"}, {"id": "i2"}]}
        batch = {"image_material_ids": '["i1","i2"]'}
        self.assertFalse(compute_personalized(cfg, batch))

    def test_personalized_handles_missing_fields(self):
        """老数据缺字段时不报错"""
        from ext_api._personalized import compute_personalized
        cfg = {}  # 全空
        batch = {"title": "t", "description": "d"}
        self.assertFalse(compute_personalized(cfg, batch))
```

- [ ] **Step 2: 跑测试，确认 FAIL**

```bash
cd backend && python3 -m pytest tests/test_personalized_config.py::TestComputePersonalized -v
```

期望：FAIL（`ext_api._personalized` 模块不存在）

- [ ] **Step 3: 创建 `backend/ext_api/_personalized.py`**

```python
"""派生字段 personalized 计算逻辑。
对比 account_configs 与 publish_batches 的公共值，任一非跳过字段不一致 → True。
数据库不存，仅在 /api/v2/history 响应中计算。"""
import json


def compute_personalized(account_configs: dict, batch_row: dict) -> bool:
    cfg = account_configs or {}
    batch = batch_row or {}

    # 文本字段
    if (cfg.get('title') or '') != (batch.get('title') or ''):
        return True
    if (cfg.get('description') or '') != (batch.get('description') or ''):
        return True

    # 视频/封面（ID 比较）
    video_id = (cfg.get('videoLandscape') or {}).get('id') or (cfg.get('videoPortrait') or {}).get('id')
    if video_id and video_id != (batch.get('video_material_id') or ''):
        return True

    cover_l_id = (cfg.get('coverLandscape') or {}).get('id')
    if cover_l_id and cover_l_id != (batch.get('landscape_cover_material_id') or ''):
        return True

    cover_p_id = (cfg.get('coverPortrait') or {}).get('id')
    if cover_p_id and cover_p_id != (batch.get('portrait_cover_material_id') or ''):
        return True

    # 图文图片（ID 列表比较）
    cfg_image_ids = [img.get('id', '') for img in (cfg.get('images') or [])]
    if cfg_image_ids:
        try:
            batch_image_ids = json.loads(batch.get('image_material_ids') or '[]')
        except (json.JSONDecodeError, TypeError):
            batch_image_ids = []
        if cfg_image_ids != batch_image_ids:
            return True

    # 标签、平台特有字段：不存公共值，跳过
    return False
```

- [ ] **Step 4: 跑测试，确认 PASS**

```bash
cd backend && python3 -m pytest tests/test_personalized_config.py::TestComputePersonalized -v
```

期望：8 个 test 全 PASS

- [ ] **Step 5: 在 `/api/v2/history` 注入 `personalized` 字段**

修改 `backend/ext_api/__init__.py:285` 附近的 `get_history` 函数。在顶部 import 区域加：

```python
from ext_api._personalized import compute_personalized
```

在 for-loop 处理 `batches` 时（约 364 行起），给每个 `items[i]` 注入 `personalized`：

找到这段：

```python
for d in detail_rows:
    dd = dict(d)
    try:
        dd['account_configs'] = json.loads(dd.get('account_configs', '{}'))
    except json.JSONDecodeError:
        dd['account_configs'] = {}
    # 计算 duration
    if dd.get('started_at') and dd.get('finished_at'):
        ...
    details_by_batch.setdefault(dd['batch_id'], []).append(dd)
```

在 `details_by_batch.setdefault(...)` 之前加：

```python
    dd['personalized'] = compute_personalized(dd['account_configs'], batch_row_dict)
```

但注意：`dd` 在这个循环里是 detail 行，访问不到 `batch_row_dict`。需要重构：要么把 `compute_personalized` 移到 for-loop 外面，要么用 batch 的字段重新读。

**最简改法**：在 for-loop 处理 `batches` 时（约 364 行起），先构造 `batch_dict = b`（b 已经是 dict），然后注入 `personalized`：

找到这段：

```python
items = []
for b in batches:
    batch_details = details_by_batch.get(b['id'], [])
    ...
    items.append({
        'id': b['id'],
        ...
    })
```

在 `items.append(...)` 之前加：

```python
    for d_item in batch_details:
        d_item['personalized'] = compute_personalized(d_item.get('account_configs') or {}, b)
```

- [ ] **Step 6: 跑历史相关测试**

```bash
cd backend && python3 -m pytest tests/test_history_endpoint.py -v
```

- [ ] **Step 7: 提交**

```bash
git add backend/ext_api/_personalized.py backend/ext_api/__init__.py
git commit -m "feat(history): /api/v2/history 派生 personalized 字段（按 account_configs 对比）"
```

---

## Task 5: PublishCenter.vue — 新增覆写区 state + 辅助函数

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`（script setup 区域，state 定义附近）

- [ ] **Step 1: 加 4 个 reactive 对象 + 2 个辅助函数**

在 `frontend/src/views/PublishCenter.vue` 的 `<script setup>` 中找 `const commonConfig = reactive({...})`（行号约 562）的位置，在它之后加：

```js
// 平台级覆写（spec §3.3）
const platformOverrides = reactive({})         // { [platformKey]: { title, description, tags, coverPortrait, coverLandscape, videoPortrait, videoLandscape, ... } }
const platformChecked = reactive({})           // { [platformKey]: boolean }

// 账号级覆写
const accountOverrides = reactive({})          // { [accountId]: { ...同 platformOverrides } }
const accountChecked = reactive({})            // { [accountId]: boolean }

// 覆写区专用的封面/库编辑目标（覆盖区用同一对话框/库时区分目标）
const platformCoverEditorTarget = ref(null)    // 'portrait' | 'landscape' | null
const platformLibraryTarget = ref(null)        // { type: 'cover', ratio: 'portrait' | 'landscape' } | null
const accountCoverEditorTarget = ref(null)
const accountLibraryTarget = ref(null)

function hasPlatformOverrideContent(platformKey) {
  const ov = platformOverrides[platformKey]
  if (!ov) return false
  return !!(
    ov.title || ov.description ||
    (ov.tags && ov.tags.length > 0) ||
    ov.coverPortrait || ov.coverLandscape ||
    ov.videoPortrait  || ov.videoLandscape
  )
}

function hasAccountOverrideContent(accountId) {
  const ov = accountOverrides[accountId]
  if (!ov) return false
  return !!(
    ov.title || ov.description ||
    (ov.tags && ov.tags.length > 0) ||
    ov.coverPortrait || ov.coverLandscape ||
    ov.videoPortrait  || ov.videoLandscape
  )
}
```

- [ ] **Step 2: 提交（独立中间提交，便于 review）**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "refactor(PublishCenter): 新增 platformOverrides/accountOverrides 状态（覆写功能前置）"
```

---

## Task 6: PublishCenter.vue — 覆写区 UI（模板 + 交互）

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`（template 区域，line 156 "PLATFORM-SPECIFIC SETTINGS" 上方）

- [ ] **Step 1: 在模板中插入"渠道级配置区"和"账号级配置区"**

找到 `<div v-if="currentPlatformConfig" class="config-section">`（PLATFORM-SPECIFIC SETTINGS 区域，约 line 157）。**在它之前**插入：

```vue
<!-- ===== 平台级个性化覆写区 ===== -->
<div v-if="currentPlatformConfig" class="config-section platform-override-section">
  <div class="section-bar">
    <div class="bar" :style="{ background: currentPlatformConfig.color }"></div>
    <span class="section-label">{{ currentPlatformConfig.name }} 渠道个性化</span>
    <el-checkbox
      v-model="platformChecked[selectedPlatform]"
      @change="onPlatformCheckChange"
    >使用个性化配置</el-checkbox>
  </div>
  <div v-show="platformChecked[selectedPlatform]" class="override-body">
    <div class="form-field">
      <div class="field-head"><span>渠道标题</span></div>
      <el-input v-model="platformOverrides[selectedPlatform].title" placeholder="渠道标题" maxlength="100" />
    </div>
    <div class="form-field">
      <div class="field-head"><span>渠道描述</span></div>
      <el-input v-model="platformOverrides[selectedPlatform].description" type="textarea" :rows="3" placeholder="渠道描述" maxlength="2000" />
    </div>
    <div class="form-field">
      <div class="field-head"><span>渠道标签</span></div>
      <el-input
        :model-value="platformOverrides[selectedPlatform].tagInput || ''"
        @update:model-value="v => platformOverrides[selectedPlatform].tagInput = v"
        @keyup.enter="addPlatformTag"
        placeholder="输入标签后回车"
        clearable
      />
      <div v-if="platformOverrides[selectedPlatform].tags?.length" style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;">
        <el-tag
          v-for="(t, i) in platformOverrides[selectedPlatform].tags"
          :key="i"
          closable
          @close="platformOverrides[selectedPlatform].tags.splice(i, 1)"
          size="small"
        >#{{ t }}</el-tag>
      </div>
    </div>
    <div class="form-field">
      <div class="field-head"><span>横版封面（渠道）</span></div>
      <CoverCard
        v-model="platformOverrides[selectedPlatform].coverLandscape"
        :has-video="!!(platformOverrides[selectedPlatform].videoPortrait || platformOverrides[selectedPlatform].videoLandscape)"
        @edit="openPlatformCoverEditor('landscape')"
        @open-library="openPlatformLibrary('cover', 'landscape')"
      />
    </div>
    <div class="form-field">
      <div class="field-head"><span>竖版封面（渠道）</span></div>
      <CoverCard
        v-model="platformOverrides[selectedPlatform].coverPortrait"
        :has-video="!!(platformOverrides[selectedPlatform].videoPortrait || platformOverrides[selectedPlatform].videoLandscape)"
        @edit="openPlatformCoverEditor('portrait')"
        @open-library="openPlatformLibrary('cover', 'portrait')"
      />
    </div>
  </div>
</div>

<!-- ===== 账号级个性化覆写区 ===== -->
<div v-if="selectedAccountId" class="config-section account-override-section">
  <div class="section-bar">
    <div class="bar" :style="{ background: currentPlatformConfig.color }"></div>
    <span class="section-label">{{ getAccountName(selectedAccountId) }} 账号个性化</span>
    <el-checkbox
      v-model="accountChecked[selectedAccountId]"
      :disabled="!platformChecked[selectedPlatform]"
      @change="onAccountCheckChange"
    >使用个性化配置</el-checkbox>
  </div>
  <div v-show="accountChecked[selectedAccountId]" class="override-body">
    <div class="form-field">
      <div class="field-head"><span>账号标题</span></div>
      <el-input v-model="accountOverrides[selectedAccountId].title" placeholder="账号标题" maxlength="100" />
    </div>
    <div class="form-field">
      <div class="field-head"><span>账号描述</span></div>
      <el-input v-model="accountOverrides[selectedAccountId].description" type="textarea" :rows="3" placeholder="账号描述" maxlength="2000" />
    </div>
    <div class="form-field">
      <div class="field-head"><span>账号标签</span></div>
      <el-input
        :model-value="accountOverrides[selectedAccountId].tagInput || ''"
        @update:model-value="v => accountOverrides[selectedAccountId].tagInput = v"
        @keyup.enter="addAccountTag"
        placeholder="输入标签后回车"
        clearable
      />
      <div v-if="accountOverrides[selectedAccountId].tags?.length" style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;">
        <el-tag
          v-for="(t, i) in accountOverrides[selectedAccountId].tags"
          :key="i"
          closable
          @close="accountOverrides[selectedAccountId].tags.splice(i, 1)"
          size="small"
        >#{{ t }}</el-tag>
      </div>
    </div>
    <div class="form-field">
      <div class="field-head"><span>横版封面（账号）</span></div>
      <CoverCard
        v-model="accountOverrides[selectedAccountId].coverLandscape"
        :has-video="!!(accountOverrides[selectedAccountId].videoPortrait || accountOverrides[selectedAccountId].videoLandscape)"
      />
    </div>
    <div class="form-field">
      <div class="field-head"><span>竖版封面（账号）</span></div>
      <CoverCard
        v-model="accountOverrides[selectedAccountId].coverPortrait"
        :has-video="!!(accountOverrides[selectedAccountId].videoPortrait || accountOverrides[selectedAccountId].videoLandscape)"
      />
    </div>
  </div>
</div>
```

- [ ] **Step 2: 在 `<script setup>` 加 4 个交互函数**

在 `hasAccountOverrideContent` 函数定义之后加：

```js
function onPlatformCheckChange(checked) {
  if (!checked && hasPlatformOverrideContent(selectedPlatform.value)) {
    ElMessageBox.confirm(
      '取消个性化配置后，本渠道的覆写将丢失，恢复使用公共默认，是否继续？',
      '确认取消', { confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning' }
    ).then(() => {
      delete platformOverrides[selectedPlatform.value]
    }).catch(() => {
      platformChecked[selectedPlatform.value] = true
    })
  } else if (checked) {
    platformOverrides[selectedPlatform.value] = {
      title: '', description: '', tags: [], tagInput: '',
      coverPortrait: null, coverLandscape: null,
      videoPortrait: null, videoLandscape: null,
    }
  }
}

function onAccountCheckChange(checked) {
  if (!checked && hasAccountOverrideContent(selectedAccountId.value)) {
    ElMessageBox.confirm(
      '取消个性化配置后，本账号的覆写将丢失，恢复使用渠道默认，是否继续？',
      '确认取消', { confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning' }
    ).then(() => {
      delete accountOverrides[selectedAccountId.value]
    }).catch(() => {
      accountChecked[selectedAccountId.value] = true
    })
  } else if (checked) {
    accountOverrides[selectedAccountId.value] = {
      title: '', description: '', tags: [], tagInput: '',
      coverPortrait: null, coverLandscape: null,
      videoPortrait: null, videoLandscape: null,
    }
  }
}

function addPlatformTag() {
  const v = (platformOverrides[selectedPlatform.value]?.tagInput || '').trim()
  if (!v) return
  platformOverrides[selectedPlatform.value].tags.push(v)
  platformOverrides[selectedPlatform.value].tagInput = ''
}

function addAccountTag() {
  const v = (accountOverrides[selectedAccountId.value]?.tagInput || '').trim()
  if (!v) return
  accountOverrides[selectedAccountId.value].tags.push(v)
  accountOverrides[selectedAccountId.value].tagInput = ''
}

function openPlatformCoverEditor(type) {
  // 复用全局 CoverEditorDialog，但让它的输出写入 platformOverrides
  platformCoverEditorTarget.value = type  // 'portrait' | 'landscape'
  coverEditorRef.value?.open(type)
}

function openPlatformLibrary(coverType, ratio) {
  // 复用全局素材库，但让选择结果写入 platformOverrides
  platformLibraryTarget.value = { type: coverType, ratio }
  materialSelectRef.value?.open()
}

// 同样的镜像函数给账号级
function openAccountCoverEditor(type) {
  accountCoverEditorTarget.value = type
  coverEditorRef.value?.open(type)
}
function openAccountLibrary(coverType, ratio) {
  accountLibraryTarget.value = { type: coverType, ratio }
  materialSelectRef.value?.open()
}
```

- [ ] **Step 3: 改造现有的 `onMaterialSelect` 支持多 target 分发**

现有的 `onMaterialSelect`（约 999 行）只更新 `commonConfig`。改成先看 `platformLibraryTarget` / `accountLibraryTarget` 是否被设置，再决定写入哪里：

```js
function onMaterialSelect(material) {
  // 平台覆写区 target
  if (platformLibraryTarget.value) {
    const ov = platformOverrides[selectedPlatform.value]
    if (!ov) { platformLibraryTarget.value = null; return }
    if (platformLibraryTarget.value.type === 'cover' && platformLibraryTarget.value.ratio === 'portrait') {
      ov.coverPortrait = material
    } else if (platformLibraryTarget.value.type === 'cover' && platformLibraryTarget.value.ratio === 'landscape') {
      ov.coverLandscape = material
    }
    platformLibraryTarget.value = null
    ElMessage.success('渠道覆写封面已设置')
    return
  }
  // 账号覆写区 target
  if (accountLibraryTarget.value) {
    const ov = accountOverrides[selectedAccountId.value]
    if (!ov) { accountLibraryTarget.value = null; return }
    if (accountLibraryTarget.value.type === 'cover' && accountLibraryTarget.value.ratio === 'portrait') {
      ov.coverPortrait = material
    } else if (accountLibraryTarget.value.type === 'cover' && accountLibraryTarget.value.ratio === 'landscape') {
      ov.coverLandscape = material
    }
    accountLibraryTarget.value = null
    ElMessage.success('账号覆写封面已设置')
    return
  }
  // 原有逻辑（写入 commonConfig）
  if (materialLibraryMode.value === 'cover') {
    if (materialLibraryCoverTarget.value === 'portrait') {
      commonConfig.coverPortrait = material
    } else {
      commonConfig.coverLandscape = material
    }
    ElMessage.success('封面已设置')
  } else {
    if (materialLibraryVideoTarget.value === 'portrait') {
      commonConfig.videoPortrait = material
    } else {
      commonConfig.videoLandscape = material
    }
    ElMessage.success('视频已设置')
    if (appStore.autoFillTitle) {
      const title = material.name.replace(/\.[^.]+$/, '')
      for (const key of Object.keys(platformConfigs)) {
        platformConfigs[key].title = title
      }
    }
  }
}
```

- [ ] **Step 4: CoverEditorDialog 的输出也要分发到覆写区**

找到 `CoverEditorDialog` 绑定的位置（约 82-92 行）：

```vue
<CoverEditorDialog
  ref="coverEditorRef"
  :video-landscape="commonConfig.videoLandscape"
  :video-portrait="commonConfig.videoPortrait"
  :cover-landscape="commonConfig.coverLandscape"
  :cover-portrait="commonConfig.coverPortrait"
  :portrait-ratio="appStore.portraitRatio"
  :landscape-ratio="appStore.landscapeRatio"
  @update:cover-landscape="commonConfig.coverLandscape = $event"
  @update:cover-portrait="commonConfig.coverPortrait = $event"
/>
```

**改造**：增加一个 `target` 状态（'common' | 'platform' | 'account'），根据 `platformCoverEditorTarget` / `accountCoverEditorTarget` 决定把 video/cover 传哪个 source，把 update 写到哪个 target。最简实现：

在 `<script setup>` 加：

```js
const editorSource = computed(() => {
  if (platformCoverEditorTarget.value) {
    return {
      videoLandscape: platformOverrides[selectedPlatform.value]?.videoLandscape,
      videoPortrait:  platformOverrides[selectedPlatform.value]?.videoPortrait,
      coverLandscape: platformOverrides[selectedPlatform.value]?.coverLandscape,
      coverPortrait:  platformOverrides[selectedPlatform.value]?.coverPortrait,
    }
  }
  if (accountCoverEditorTarget.value) {
    return {
      videoLandscape: accountOverrides[selectedAccountId.value]?.videoLandscape,
      videoPortrait:  accountOverrides[selectedAccountId.value]?.videoPortrait,
      coverLandscape: accountOverrides[selectedAccountId.value]?.coverLandscape,
      coverPortrait:  accountOverrides[selectedAccountId.value]?.coverPortrait,
    }
  }
  return {
    videoLandscape: commonConfig.videoLandscape,
    videoPortrait:  commonConfig.videoPortrait,
    coverLandscape: commonConfig.coverLandscape,
    coverPortrait:  commonConfig.coverPortrait,
  }
})

function onEditorUpdate({ coverLandscape, coverPortrait }) {
  if (platformCoverEditorTarget.value) {
    const ov = platformOverrides[selectedPlatform.value] || {}
    if (coverLandscape) ov.coverLandscape = coverLandscape
    if (coverPortrait)  ov.coverPortrait  = coverPortrait
    platformOverrides[selectedPlatform.value] = ov
  } else if (accountCoverEditorTarget.value) {
    const ov = accountOverrides[selectedAccountId.value] || {}
    if (coverLandscape) ov.coverLandscape = coverLandscape
    if (coverPortrait)  ov.coverPortrait  = coverPortrait
    accountOverrides[selectedAccountId.value] = ov
  } else {
    if (coverLandscape) commonConfig.coverLandscape = coverLandscape
    if (coverPortrait)  commonConfig.coverPortrait  = coverPortrait
  }
}
```

把 `<CoverEditorDialog>` 改为：

```vue
<CoverEditorDialog
  ref="coverEditorRef"
  :video-landscape="editorSource.videoLandscape"
  :video-portrait="editorSource.videoPortrait"
  :cover-landscape="editorSource.coverLandscape"
  :cover-portrait="editorSource.coverPortrait"
  :portrait-ratio="appStore.portraitRatio"
  :landscape-ratio="appStore.landscapeRatio"
  @update:cover-landscape="onEditorUpdate({coverLandscape: $event})"
  @update:cover-portrait="onEditorUpdate({coverPortrait: $event})"
/>
```

并把 `openCoverEditor` 改为：

```js
function openCoverEditor(tab = 'landscape') {
  platformCoverEditorTarget.value = null
  accountCoverEditorTarget.value = null
  coverEditorRef.value?.open(tab)
}
```

- [ ] **Step 5: 确认 import 完整**

确保 `<script setup>` 顶部 import 了：
- `import { ElMessageBox } from 'element-plus'`（如果还没 import）
- `import CoverCard from '@/components/CoverCard.vue'`（已 import）

- [ ] **Step 6: 启动前端 dev server，手动测 UI**

```bash
cd frontend && npm run dev
# 浏览器打开 http://localhost:5173 → 视频发布页
# 验证：
#   1. 平台个性化 checkbox 可见
#   2. 勾选后覆写区展开
#   3. 取消勾选（有内容时）弹确认弹窗
#   4. 取消勾选（无内容时）直接关闭
#   5. 账号级 checkbox 在平台级未勾选时禁用
#   6. 覆写区的封面/库点击 → 选完后写入覆写区（不污染 commonConfig）
```

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat(PublishCenter): 新增平台/账号级个性化覆写区 UI + 改造 onMaterialSelect 多 target"
```

---

## Task 7: PublishCenter.vue — `mergeConfig` + `publishAll` 改造

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`（publishAll 函数附近）

- [ ] **Step 1: 加 `resolveAccountConfig` + `mergeConfig` 函数**

在 `onAccountCheckChange` 函数之后加：

```js
function resolveAccountConfig(platformKey, accountId) {
  // 4 级优先级：accountOv > platformOv > platformDefault > common
  const accountOv = (accountChecked[accountId] && accountOverrides[accountId]) || null
  const platformOv = (platformChecked[platformKey] && platformOverrides[platformKey]) || null
  const platformDefault = platformConfigs[platformKey] || null
  return mergeConfig(commonConfig, platformDefault, platformOv, accountOv)
}

function mergeConfig(common, platformDefault, platformOv, accountOv) {
  return {
    // 文本字段走 platformDefault 兜底（commonConfig 不存文本）
    title: accountOv?.title ?? platformOv?.title ?? platformDefault?.title ?? '',
    description: accountOv?.description ?? platformOv?.description ?? platformDefault?.description ?? '',
    tags: accountOv?.tags ?? platformOv?.tags ?? platformDefault?.tags ?? [],
    // 视频/封面走 commonConfig 兜底
    coverLandscape: accountOv?.coverLandscape ?? platformOv?.coverLandscape ?? common.coverLandscape,
    coverPortrait:  accountOv?.coverPortrait  ?? platformOv?.coverPortrait  ?? common.coverPortrait,
    videoLandscape: accountOv?.videoLandscape ?? platformOv?.videoLandscape ?? common.videoLandscape,
    videoPortrait:  accountOv?.videoPortrait  ?? platformOv?.videoPortrait  ?? common.videoPortrait,
    // 平台特有字段走 platformDefault 兜底
    videoFormat: accountOv?.videoFormat ?? platformOv?.videoFormat ?? platformDefault?.videoFormat ?? 'portrait',
    enableTimer: accountOv?.enableTimer ?? platformOv?.enableTimer ?? platformDefault?.enableTimer ?? 0,
    scheduleTime: accountOv?.scheduleTime ?? platformOv?.scheduleTime ?? platformDefault?.scheduleTime ?? '',
    aiContent: accountOv?.aiContent ?? platformOv?.aiContent ?? platformDefault?.aiContent ?? '',
    isOriginal: accountOv?.isOriginal ?? platformOv?.isOriginal ?? platformDefault?.isOriginal ?? false,
  }
}
```

- [ ] **Step 2: 改 `publishAll` 用 `resolveAccountConfig`**

找到 `async function publishAll()`（行号约 1100）。在循环里 `for (const account of selectedAccounts)` 调 `postVideo` 的地方，**先**用 `resolveAccountConfig` 合并再发：

```js
async function publishAll() {
  const batchId = crypto.randomUUID()
  for (const account of selectedAccounts) {
    const merged = resolveAccountConfig(account.platform, account.id)
    // 找到原 postVideo 调用，把 data 替换为 {...merged, ...}
    await postVideo({
      ...merged,
      accountId: account.id,
      batchId,
      // ... 其他原有字段
    })
  }
}
```

> **注意**：`platformOverrides[account.platform]?.coverLandscape` 等是 `Material` 对象（含 id/stored_path/url）。`postVideo` 后端期待 `videoLandscape: {id, stored_path, ...}` 字典。可以直接传对象。

- [ ] **Step 3: 手动测一次真实发布（不开真实平台 publish，用 mock）**

```bash
cd frontend && npm run dev
# 浏览器视频发布页：
#   1. 选 1 个抖音账号
#   2. 不勾选任何覆写
#   3. 点击发布
#   4. 检查 Network → /postVideo 请求体含 videoLandscape / coverLandscape
#   5. 检查后端 DB：SELECT account_configs FROM publish_details ORDER BY created_at DESC LIMIT 1;
#      确认 JSON 含 videoLandscape / coverLandscape
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat(PublishCenter): mergeConfig 4 级优先级 + publishAll 集成覆写区"
```

---

## Task 8: PublishCenter.vue — `saveDraft` / `loadDraft` 改造

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`（saveDraft / loadDraft 函数）

- [ ] **Step 1: 改 `saveDraft` 增加 4 个键**

找到 `saveDraft` 函数（行号约 250-270 草稿保存位置）。在返回对象里加：

```js
function saveDraft() {
  return {
    commonConfig: cloneDeep(commonConfig),
    platformConfigs: cloneDeep(platformConfigs),
    platformOverrides: cloneDeep(platformOverrides),  // 新增
    accountOverrides: cloneDeep(accountOverrides),    // 新增
    platformChecked: { ...platformChecked },          // 新增
    accountChecked: { ...accountChecked },            // 新增
    // ... 现有其他字段
  }
}
```

- [ ] **Step 2: 改 `loadDraft` 恢复 4 个键**

找到 `loadDraft` 函数（行号约 262-278）。在现有恢复逻辑后加：

```js
function loadDraft(d) {
  // ... 现有恢复逻辑
  if (d.platformOverrides) Object.assign(platformOverrides, d.platformOverrides)
  if (d.accountOverrides)  Object.assign(accountOverrides,  d.accountOverrides)
  if (d.platformChecked)   Object.assign(platformChecked,   d.platformChecked)
  if (d.accountChecked)    Object.assign(accountChecked,    d.accountChecked)
}
```

- [ ] **Step 3: 手动测草稿往返**

```bash
cd frontend && npm run dev
# 浏览器：
#   1. 视频发布页 → 勾选平台覆写 + 账号覆写 + 改内容
#   2. 保存草稿
#   3. 刷新页面 → 加载草稿
#   4. 确认 4 个 reactive 对象 + 勾选状态都恢复
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat(PublishCenter): saveDraft/loadDraft 持久化 platformOverrides/accountOverrides"
```

---

## Task 9: 3 个 ImagePublishPanel 加 `getConfig()` 方法

**Files:**
- Modify: `frontend/src/components/douyin/ImagePublishPanel.vue:205` 附近
- Modify: `frontend/src/components/xiaohongshu/ImagePublishPanel.vue:142` 附近
- Modify: `frontend/src/components/kuaishou/ImagePublishPanel.vue:144` 附近

- [ ] **Step 1: 读 douyin panel 的 defineExpose 区域**

```bash
sed -n '195,215p' /home/czy/workspace/ai/social-auto-upload-web-ui/frontend/src/components/douyin/ImagePublishPanel.vue
```

- [ ] **Step 2: 在 publicApi 对象加 `getConfig` 方法**

找到形如 `const publicApi = { ... }` 或 `function getConfig()` 的位置。每个 panel 都有 `defineExpose(publicApi)`。在 `publicApi` 对象字面量里加：

```js
getConfig() {
  // 返回当前 panel form state（作为 publishAll 的"渠道默认"值）
  return {
    title: form.title,
    description: form.description,
    tags: [...(form.tags || [])],
    images: form.images ? form.images.map(img => ({ ...img })) : [],
    coverImage: form.coverImage ? { ...form.coverImage } : null,
    enableTimer: form.enableTimer,
    scheduleTime: form.scheduleTime,
    aiContent: form.aiContent,
    isOriginal: form.isOriginal,
    // 其他 panel 特有字段
  }
}
```

> 实际字段名要看 panel 的 `form` 对象定义。打开 panel 文件，搜 `const form = reactive` 或类似，列出所有字段。

- [ ] **Step 3: 同样改 xiaohongshu / kuaishou panel**

按同样模式加 `getConfig()`。字段名可能略有差异（如小红书有 `xiaohongshuTopics`），按实际 panel form 改。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/douyin/ImagePublishPanel.vue \
        frontend/src/components/xiaohongshu/ImagePublishPanel.vue \
        frontend/src/components/kuaishou/ImagePublishPanel.vue
git commit -m "feat(image-panel): 3 个 ImagePublishPanel 新增 getConfig() 方法（暴露渠道默认 form）"
```

---

## Task 10: ImagePublish.vue — state + 覆写区 UI + mergeConfig + saveDraft

**Files:**
- Modify: `frontend/src/views/ImagePublish.vue`（script setup 区域 + template）

- [ ] **Step 1: 加 4 个 reactive 对象 + 辅助函数**

在 `<script setup>` 找 `const commonConfig = reactive(...)`（行号约 355）。在它之后加：

```js
// 平台级覆写
const platformOverrides = reactive({})
const platformChecked = reactive({})

// 账号级覆写
const accountOverrides = reactive({})
const accountChecked = reactive({})

function hasPlatformOverrideContent(platformKey) {
  const ov = platformOverrides[platformKey]
  if (!ov) return false
  return !!(
    ov.title || ov.description ||
    (ov.tags && ov.tags.length > 0) ||
    (ov.images && ov.images.length > 0) ||
    ov.coverImage
  )
}

function hasAccountOverrideContent(accountId) {
  const ov = accountOverrides[accountId]
  if (!ov) return false
  return !!(
    ov.title || ov.description ||
    (ov.tags && ov.tags.length > 0) ||
    (ov.images && ov.images.length > 0) ||
    ov.coverImage
  )
}
```

- [ ] **Step 2: 模板插入覆写区**

在 `<DouyinImagePublishPanel ...>`（或 platform-default panel）**之前**插入 platform-override-section；**之后**插入 account-override-section。结构和 PublishCenter 类似，但字段换成 `images` / `coverImage`（用 `ImageUploader` / `ImageCoverUpload`）：

```vue
<!-- 平台级覆写区（spec §3.4） -->
<div v-if="currentPlatformConfig" class="config-section platform-override-section">
  <div class="section-bar">
    <div class="bar" :style="{ background: currentPlatformConfig.color }"></div>
    <span class="section-label">{{ currentPlatformConfig.name }} 渠道个性化</span>
    <el-checkbox v-model="platformChecked[selectedPlatform]" @change="onPlatformCheckChange">
      使用个性化配置
    </el-checkbox>
  </div>
  <div v-show="platformChecked[selectedPlatform]" class="override-body">
    <div class="form-field">
      <div class="field-head"><span>渠道标题</span></div>
      <el-input v-model="platformOverrides[selectedPlatform].title" placeholder="渠道标题" maxlength="100" />
    </div>
    <div class="form-field">
      <div class="field-head"><span>渠道描述</span></div>
      <el-input v-model="platformOverrides[selectedPlatform].description" type="textarea" :rows="3" placeholder="渠道描述" maxlength="2000" />
    </div>
    <div class="form-field">
      <div class="field-head"><span>渠道标签</span></div>
      <el-input v-model="platformOverrides[selectedPlatform].tagInput" @keyup.enter="addPlatformTag" placeholder="输入标签后回车" clearable />
    </div>
    <div class="form-field">
      <div class="field-head"><span>渠道图片</span></div>
      <ImageUploader v-model="platformOverrides[selectedPlatform].images" :max-count="35" :columns="5" />
    </div>
    <div class="form-field">
      <div class="field-head"><span>渠道封面</span></div>
      <ImageCoverUpload v-model="platformOverrides[selectedPlatform].coverImage" />
    </div>
  </div>
</div>

<!-- 账号级覆写区 -->
<div v-if="selectedAccountId" class="config-section account-override-section">
  <div class="section-bar">
    <div class="bar" :style="{ background: currentPlatformConfig.color }"></div>
    <span class="section-label">{{ getAccountDisplayName(selectedAccountId) }} 账号个性化</span>
    <el-checkbox
      v-model="accountChecked[selectedAccountId]"
      :disabled="!platformChecked[selectedPlatform]"
      @change="onAccountCheckChange"
    >使用个性化配置</el-checkbox>
  </div>
  <div v-show="accountChecked[selectedAccountId]" class="override-body">
    <!-- 同 platform-override 但 v-model 绑到 accountOverrides[selectedAccountId] -->
  </div>
</div>
```

- [ ] **Step 3: 加交互函数 + mergeConfig + saveDraft/loadDraft**

按 PublishCenter 同结构，字段用 image 版的。`mergeConfig` 里 `platformDefault` 从 `getPanel(platformKey)?.getConfig()` 读：

```js
function resolveAccountConfig(platformKey, accountId) {
  const accountOv = (accountChecked[accountId] && accountOverrides[accountId]) || null
  const platformOv = (platformChecked[platformKey] && platformOverrides[platformKey]) || null
  const panelConfig = getPanel(platformKey)?.getConfig?.() || null
  return mergeConfig(commonConfig, panelConfig, platformOv, accountOv)
}

function mergeConfig(common, platformDefault, platformOv, accountOv) {
  return {
    title: accountOv?.title ?? platformOv?.title ?? platformDefault?.title ?? '',
    description: accountOv?.description ?? platformOv?.description ?? platformDefault?.description ?? '',
    tags: accountOv?.tags ?? platformOv?.tags ?? platformDefault?.tags ?? [],
    images: accountOv?.images ?? platformOv?.images ?? platformDefault?.images ?? common.images,
    coverImage: accountOv?.coverImage ?? platformOv?.coverImage ?? platformDefault?.coverImage ?? common.coverImage,
    enableTimer: accountOv?.enableTimer ?? platformOv?.enableTimer ?? platformDefault?.enableTimer ?? 0,
    scheduleTime: accountOv?.scheduleTime ?? platformOv?.scheduleTime ?? platformDefault?.scheduleTime ?? '',
    aiContent: accountOv?.aiContent ?? platformOv?.aiContent ?? platformDefault?.aiContent ?? '',
    isOriginal: accountOv?.isOriginal ?? platformOv?.isOriginal ?? platformDefault?.isOriginal ?? false,
  }
}
```

- [ ] **Step 4: 改 saveDraft / loadDraft（同 PublishCenter 模式）**

- [ ] **Step 5: 手动测图文发布页 UI + 草稿 + mock 一次发布**

```bash
cd frontend && npm run dev
# 浏览器图文发布页：
#   1. 平台/账号级勾选、覆写编辑
#   2. 草稿保存 + 恢复
#   3. mock 一次发布（不开真实平台），检查 Network /api/image-publish/publish 请求体的 account_configs
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/ImagePublish.vue
git commit -m "feat(ImagePublish): 平台/账号级个性化覆写区 + mergeConfig + 草稿支持"
```

---

## Task 11: PublishHistory.vue — `.detail-row` → `.detail-card` 卡片化

**Files:**
- Modify: `frontend/src/views/PublishHistory.vue:137-156`（card-details 区域）

- [ ] **Step 1: 替换 .detail-row 模板**

找到：

```vue
<div v-if="expandedBatchId === batch.id" class="card-details">
  <div v-for="d in batch.items" :key="d.id" class="detail-row">
    <span class="detail-status" :class="`status-${d.status}`">
      {{ d.status === 'success' ? '✓' : d.status === 'failed' ? '✗' : '○' }}
    </span>
    <span class="detail-name">{{ d.account_name }}</span>
    <span class="detail-platform">· {{ d.platform }}</span>
    <span class="detail-duration" v-if="d.duration">· {{ formatDuration(d.duration) }}</span>
    <a v-if="d.publish_url" ... >[链接]</a>
    <div v-if="d.status === 'failed' && d.error_message" class="detail-error">
      错误：{{ d.error_message }}
    </div>
  </div>
</div>
```

**替换为**：

```vue
<div v-if="expandedBatchId === batch.id" class="card-details">
  <div v-for="d in batch.items" :key="d.id" class="detail-card"
       :class="`status-${d.status}`">
    <div class="detail-cover">
      <img v-if="getCoverUrl(d)" :src="getCoverUrl(d)" :alt="d.platform" />
      <div v-else class="cover-placeholder">
        <el-icon :size="24"><Picture /></el-icon>
      </div>
    </div>
    <div class="detail-body">
      <div class="detail-head">
        <span class="detail-platform">{{ d.platform }} · {{ d.account_name }}</span>
        <span class="status-tag" :class="`status-${d.status}`">
          {{ statusLabel(d.status) }} · {{ formatDuration(d.duration) }}
        </span>
        <el-tag v-if="d.personalized" type="warning" size="small" effect="plain">个性化</el-tag>
      </div>
      <div v-if="d.status === 'failed' && d.error_message" class="detail-error">
        错误：{{ d.error_message }}
      </div>
      <template v-else>
        <div class="detail-title">{{ getCfgField(d, 'title') || batch.title || '无标题' }}</div>
        <div class="detail-desc">{{ getCfgField(d, 'description') || batch.description || '无描述' }}</div>
        <div v-if="getCfgField(d, 'tags')?.length" class="detail-tags">
          <el-tag v-for="t in getCfgField(d, 'tags')" :key="t" size="small" effect="plain">#{{ t }}</el-tag>
        </div>
      </template>
      <div class="detail-foot">
        <a v-if="d.publish_url" :href="d.publish_url" target="_blank" rel="noopener noreferrer" @click.stop>[查看发布作品]</a>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: 加辅助函数**

在 `<script setup>` 顶部 import 之后、`onMounted` 之前加：

```js
function getCfgField(d, field) {
  return d.account_configs?.[field]
}

function getCoverUrl(d) {
  const cfg = d.account_configs || {}
  return cfg.coverLandscape?.url || cfg.coverPortrait?.url || d.cover_url || ''
}
```

- [ ] **Step 3: 改 SCSS：`.detail-row` → `.detail-card`（含 .detail-cover / .detail-body 等子样式）**

找到 `<style lang="scss" scoped>` 里的 `.detail-row` 块（约 `.detail-row` ~ 600 行附近）。**替换**为：

```scss
.card-details {
  border-top: 1px solid $border;
  padding: 12px 16px;
  background: $bg-surface;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-card {
  display: flex;
  gap: 12px;
  padding: 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid $border;
  align-items: stretch;

  &.status-failed {
    opacity: 0.7;
  }

  .detail-cover {
    flex-shrink: 0;
    width: 96px;
    aspect-ratio: 16/9;
    background: $bg-surface;
    border-radius: 6px;
    overflow: hidden;
    position: relative;

    img { width: 100%; height: 100%; object-fit: cover; }
    .cover-placeholder {
      position: absolute; inset: 0;
      display: flex; align-items: center; justify-content: center;
      color: $text-muted;
    }
  }

  .detail-body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .detail-head {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .detail-platform {
    font-size: 13px;
    color: $text-primary;
    font-weight: 500;
  }

  .detail-title {
    font-size: 13px;
    color: $text-primary;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .detail-desc {
    font-size: 12px;
    color: $text-secondary;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .detail-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .detail-foot {
    margin-top: auto;
    font-size: 12px;
    a {
      color: $brand-start;
      text-decoration: none;
      &:hover { color: $brand-end; text-decoration: underline; }
    }
  }

  .detail-error {
    color: #f56c6c;
    font-size: 12px;
  }

  .status-tag {
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    &.status-success, &.status-partial {
      background: rgba(82, 196, 26, 0.15); color: #67c23a;
    }
    &.status-failed {
      background: rgba(245, 108, 108, 0.15); color: #f56c6c;
    }
    &.status-running {
      background: rgba(64, 158, 255, 0.15); color: #409eff;
    }
    &.status-pending, &.status-cancelled {
      background: rgba(0, 0, 0, 0.06); color: $text-muted;
    }
  }
}
```

- [ ] **Step 4: 浏览器手动验证**

```bash
cd frontend && npm run dev
# 浏览器打开 http://localhost:5173/publish-history
# 验证：
#   1. 至少发布过 1 个批次（可以用 mock 数据）
#   2. 点击批次卡片展开
#   3. 每个明细显示：封面缩略图、平台·账号、状态徽标、个性化角标、标题、描述、标签
#   4. 失败状态显示错误信息
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/PublishHistory.vue
git commit -m "feat(PublishHistory): 明细行重设计为卡片（封面/标题/描述/标签/个性化角标）"
```

---

## Task 12: 端到端冒烟测试

**Files:**
- 不动文件，只跑测试

- [ ] **Step 1: 跑全部后端测试**

```bash
cd backend && python3 -m pytest tests/ -v
```

期望：所有 test PASS，含新增的 `test_personalized_config.py`

- [ ] **Step 2: 启动 dev 环境**

```bash
# 终端 1：后端
cd backend && python3 app.py

# 终端 2：前端
cd frontend && npm run dev
```

- [ ] **Step 3: 视频发布冒烟（按 spec §6.3）**

打开浏览器视频发布页：
1. 选 1 个抖音账号，公共区域填 1 套内容（视频/封面/标题/描述/标签）
2. 不勾选任何覆写 → 点发布
3. 检查后端 DB：`SELECT account_configs FROM publish_details ORDER BY created_at DESC LIMIT 1;` → 视频/封面/标题都在
4. 切到发布历史页 → 展开刚发布的批次 → 看到 1 张明细卡片，含正确内容
5. 再来一次：3 个账号全用公共区域 → 历史展开看 3 张卡片内容一致
6. 再来一次：3 个账号各自覆写不同标题 → 历史展开看 3 张卡片标题各异，"个性化"角标显示

- [ ] **Step 4: 图文发布冒烟**

同 Step 3，但走图文发布页：
- 公共区域选 1 套图片 + 封面
- 平台级覆写：换 1 张图、改标题
- 账号级覆写：再换 1 张图
- 检查历史卡片：3 张图各异 + 个性化角标

- [ ] **Step 5: 草稿往返冒烟**

1. 视频发布页：勾选平台级 + 账号级、改内容
2. 保存草稿
3. 刷新页面（F5）→ 加载最新草稿
4. 验证 4 个 reactive state + 勾选 checkbox 都恢复

- [ ] **Step 6: 取消勾选弹窗验证**

1. 勾选平台级 + 改视频文件 + 取消勾选 → 弹确认 → 取消 → checkbox 恢复勾选
2. 再次取消 → 弹确认 → 确认 → 平台覆写区清空、checkbox 取消

- [ ] **Step 7: 收尾提交（如有）**

```bash
git status
# 如果有未提交的 fix，按主题分 commit
git commit -m "fix: 冒烟测试发现的小问题"
```

---

## 关键不变量

实施过程中以下事项**不能**改动：

- `backend/impl/*` 任何文件（平台实现）
- `backend/init_db.py` schema（表结构）
- `frontend/src/views/TaskCenter.vue` / `Dashboard.vue` / `AccountManagement.vue` / `MaterialManagement.vue` / `Settings.vue`（不在范围内）
- `mcp__social-auto-upload__*` MCP 工具
- `src-tauri/*` 桌面打包

## 完成标志

- [ ] Task 0-4 全部通过（后端）
- [ ] Task 5-11 全部完成（前端）
- [ ] Task 12 端到端冒烟全过
- [ ] 全部 11+ 个 commit 在分支上
- [ ] `git status` 干净
