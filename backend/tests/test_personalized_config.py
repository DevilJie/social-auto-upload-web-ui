"""测试个性化配置：视频/封面/全 per-platform form 字段持久化到 account_configs"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL DEFAULT '',
    draft_id INTEGER NOT NULL DEFAULT 0
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
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    stored_path TEXT DEFAULT ''
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
        # 把 test 自己的 DB_PATH 注入到 task_queue 模块
        # 镜像 test_task_queue_writes.py:74-75 的模式,避免 test 间 DB_PATH 互扰
        from ext_api import task_queue as _tq_mod
        _tq_mod.DB_PATH = DB_PATH
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


class TestPostVideoPassthrough(unittest.TestCase):
    """验证 /postVideo 路由把新字段（videoLandscape/coverLandscape/aiContent 等）
    透传到 _before_publish 并写入 publish_details.account_configs"""

    def setUp(self):
        _setup_db()
        # 把 test 自己的 DB_PATH 注入到 task_queue 模块
        # 镜像 test_task_queue_writes.py:74-75 的模式,避免 test 间 DB_PATH 互扰
        from ext_api import task_queue as _tq_mod
        _tq_mod.DB_PATH = DB_PATH
        # 同步 app.DB_PATH（app.py:154 顶层常量），让 _record_publish 写到 test DB
        import app as _app_mod
        _app_mod.DB_PATH = DB_PATH

    def tearDown(self):
        # 清空 test DB 的 publish_batches/publish_details，避免跨测试污染
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DELETE FROM publish_details")
            conn.execute("DELETE FROM publish_batches")
            conn.commit()

    def test_postvideo_writes_overrides_to_publish_details(self):
        """前端传 videoLandscape/videoPortrait/coverLandscape/coverPortrait/aiContent/isOriginal
        → _before_publish 写入 publish_details.account_configs → DB 能查到这些键"""
        # 延迟 import，避免 setUp 之前 import 时把生产 DB_PATH 写进 app.DB_PATH
        from app import app
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

        # _ensure_db 是 app.before_request，会试图 init_database 覆盖我们的 test schema
        # 屏蔽掉。_before_publish 真实跑，_after_publish 也真实跑（仅写 status）
        # 屏蔽 platform.publish_video（不需要真发）
        with patch('app._ensure_db'), \
             patch('app.get_platform') as mock_get_platform:
            mock_platform = MagicMock()
            mock_platform.publish_video.return_value = {"code": 200, "status": "success"}
            mock_get_platform.return_value = mock_platform
            r = client.post('/postVideo', json=payload)
            self.assertEqual(r.status_code, 200, f"postVideo 失败: {r.get_json()}")

        # 检查 DB
        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT account_configs FROM publish_details ORDER BY created_at DESC LIMIT 1"
            ).fetchall()
        self.assertEqual(len(rows), 1, "publish_details 应该被 _before_publish 插入 1 行")
        cfg = json.loads(rows[0][0])
        self.assertEqual(cfg["videoLandscape"]["id"], "v-uuid")
        self.assertEqual(cfg["videoPortrait"]["id"], "v-uuid2")
        self.assertEqual(cfg["coverLandscape"]["id"], "c-uuid")
        self.assertEqual(cfg["coverPortrait"]["id"], "c-uuid2")
        self.assertEqual(cfg["videoFormat"], "portrait")
        self.assertEqual(cfg["aiContent"], "内容由AI生成")
        self.assertTrue(cfg["isOriginal"])
        # spec §2.2 视频 account_configs 必须含 scheduleTime
        # （此前 scheduleTime 在 excluded 里，本 fix 后已可透传，回归测试）
        self.assertIn("scheduleTime", cfg)
        self.assertEqual(cfg["scheduleTime"], "")
        self.assertEqual(cfg["enableTimer"], 0)


class TestImagePublishPersistsOverrides(unittest.TestCase):
    def setUp(self):
        _setup_db()
        # image_publish_bp 用模块级 DB_PATH 常量，注入到 test DB
        # 镜像 test_image_publish_endpoint.py:85 的模式
        from blueprints import image_publish_bp as _img_bp_mod
        _img_bp_mod.DB_PATH = DB_PATH

    def tearDown(self):
        # 清空 test DB 的 publish_batches/publish_details，避免跨测试污染
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DELETE FROM publish_details")
            conn.execute("DELETE FROM publish_batches")
            conn.commit()

    def test_publish_images_stores_images_and_cover_in_account_configs(self):
        """图文发布的 account_configs 应包含 images 列表和 coverImage 对象"""
        from app import app
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
                "filePath": "/tmp/cookie.json",
                "images": [
                    {"id": "img-1", "stored_path": "uploads/1.jpg", "name": "1.jpg"},
                    {"id": "img-2", "stored_path": "uploads/2.jpg", "name": "2.jpg"},
                ],
                "coverImage": {"id": "img-1", "stored_path": "uploads/1.jpg"},
                "enableTimer": 0,
                "scheduleTime": "",
            },
        }

        with patch('impl.registry.get_platform') as mock_get_platform:
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
        # filePath 已在 publish_details.account_id 体现，不重复持久化
        self.assertNotIn("filePath", cfg)


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

    def test_personalized_true_when_image_cover_differs_from_first(self):
        """图文 coverImage 与 batch 首图不同 → personalized"""
        from ext_api._personalized import compute_personalized
        cfg = {"images": [{"id": "i1"}, {"id": "i2"}], "coverImage": {"id": "i3"}}
        batch = {"image_material_ids": '["i1","i2"]'}
        self.assertTrue(compute_personalized(cfg, batch))

    def test_personalized_false_when_image_cover_matches_first(self):
        from ext_api._personalized import compute_personalized
        cfg = {"images": [{"id": "i1"}, {"id": "i2"}], "coverImage": {"id": "i1"}}
        batch = {"image_material_ids": '["i1","i2"]'}
        self.assertFalse(compute_personalized(cfg, batch))


if __name__ == "__main__":
    unittest.main()
