"""测试 TaskQueue.add_task 写入新表的行为"""
import os
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"

# 测试用 DB 的 schema（与 init_db.py 一致）
# 绕过 init_db.init_database() 的 env-var 冻结问题（conf.BASE_DIR 在首次 import 时固化）
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


def _setup():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()


class TestTaskQueueWrites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()
        from ext_api.task_queue import PublishTask, TaskStatus
        cls.PublishTask = PublishTask
        cls.TaskStatus = TaskStatus
        # 把 test 自己的 DB_PATH 注入到 task_queue 模块
        # (因为 task_queue 加载时 conf.BASE_DIR 可能已固化到错误路径)
        from ext_api import task_queue as _tq_mod
        _tq_mod.DB_PATH = DB_PATH

    def test_publish_task_has_batch_id_field(self):
        t = self.PublishTask(batch_id='abc-123')
        self.assertEqual(t.batch_id, 'abc-123')

    def test_to_dict_includes_batch_id(self):
        t = self.PublishTask(batch_id='abc-123', title='t', platform='抖音')
        d = t.to_dict()
        self.assertEqual(d['batch_id'], 'abc-123')

    def test_insert_creates_batch_and_detail(self):
        t = self.PublishTask(
            batch_id='qbatch-1',
            platform='抖音',
            platform_type=3,
            account_name='账号A',
            account_cookie_path='/tmp/cookie.json',
            video_path='/tmp/v.mp4',
            title='t',
            description='d',
            tags=['a', 'b'],
        )
        # 直接调 _insert_db（不走 queue 启动）
        from ext_api.task_queue import TaskQueue
        tq = TaskQueue(max_concurrent=1)
        tq._insert_db(t)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        batch = conn.execute("SELECT * FROM publish_batches WHERE id = 'qbatch-1'").fetchone()
        details = conn.execute("SELECT * FROM publish_details WHERE batch_id = 'qbatch-1'").fetchall()
        conn.close()
        self.assertIsNotNone(batch)
        self.assertEqual(batch['type'], 'video')
        self.assertEqual(len(details), 1)
        d = details[0]
        self.assertEqual(d['account_name'], '账号A')
        self.assertEqual(d['platform'], '抖音')


if __name__ == '__main__':
    unittest.main()
