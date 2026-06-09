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


if __name__ == "__main__":
    unittest.main()
