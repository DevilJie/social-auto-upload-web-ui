"""
测试 DELETE /api/v2/history/<batch_id> 单条删除 和
DELETE /api/v2/history/batch 批量删除端点。

重点验证:
- 单条删除后 batch 与关联 details 都消失（SQLite 默认未启用外键级联，需手动删 details）
- 不存在的 batch_id → 404
- 批量删除返回 deleted / failed 明细
- 批量删除入参校验（空 / 超过 50 / 非列表）
"""
import os
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


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
    source TEXT NOT NULL DEFAULT '',
    draft_id INTEGER NOT NULL DEFAULT 0,
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


def _setup_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA_SQL)
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, failed_count, created_at) VALUES ('b1', 'video', '视频1', 'success', 2, 2, 0, '2026-06-01 10:00:00')")
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, failed_count, created_at) VALUES ('b2', 'image', '图文1', 'success', 1, 1, 0, '2026-06-02 10:00:00')")
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, failed_count, created_at) VALUES ('b3', 'video', '视频2', 'failed', 3, 0, 3, '2026-06-03 10:00:00')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d1', 'b1', '账号A', '抖音', '{\"coverLandscape\":{\"stored_path\":\"/x.jpg\"}}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d2', 'b1', '账号B', '小红书', '{\"coverLandscape\":{\"stored_path\":\"/x.jpg\"}}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d3', 'b2', '账号C', '抖音', '{\"coverLandscape\":{\"stored_path\":\"/x.jpg\"}}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d4', 'b3', '账号D', 'B站', '{\"coverLandscape\":{\"stored_path\":\"/x.jpg\"}}', 'failed')")
    conn.commit()
    conn.close()


class TestHistoryDeleteEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp()
        os.environ['SAU_DATA_DIR'] = cls._tmpdir
        cls.DB_PATH = Path(cls._tmpdir) / "db" / "database.db"
        _setup_db(cls.DB_PATH)
        from ext_api import app
        cls.client = app.test_client()

    def setUp(self):
        self._db_path_patch = patch('ext_api.DB_PATH', self.DB_PATH)
        self._db_path_patch.start()

    def tearDown(self):
        self._db_path_patch.stop()

    def _count_details(self, batch_id):
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM publish_details WHERE batch_id = ?", (batch_id,)
            ).fetchone()[0]

    def _batch_exists(self, batch_id):
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            return conn.execute(
                "SELECT 1 FROM publish_batches WHERE id = ?", (batch_id,)
            ).fetchone() is not None

    def test_delete_single_removes_batch_and_details(self):
        """删除 b1 后 batch 与 2 条 details 都应消失"""
        self.assertTrue(self._batch_exists('b1'))
        self.assertEqual(self._count_details('b1'), 2)

        resp = self.client.delete('/api/v2/history/b1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['code'], 200)

        self.assertFalse(self._batch_exists('b1'))
        # 关键:外键级联未启用,必须手动删 details
        self.assertEqual(self._count_details('b1'), 0)

    def test_delete_single_not_found(self):
        """不存在的 batch_id → 404"""
        resp = self.client.delete('/api/v2/history/does-not-exist')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()['code'], 404)

    def test_batch_delete_partial(self):
        """批量删除:存在的删掉,不存在的进 failed"""
        # b2 存在, b9 不存在
        resp = self.client.delete(
            '/api/v2/history/batch',
            json={'batch_ids': ['b2', 'b9']}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['code'], 200)
        self.assertEqual(data['deleted'], ['b2'])
        self.assertEqual(len(data['failed']), 1)
        self.assertEqual(data['failed'][0]['batch_id'], 'b9')

        # b2 连同 detail d3 一起删除
        self.assertFalse(self._batch_exists('b2'))
        self.assertEqual(self._count_details('b2'), 0)

    def test_batch_delete_cascades_details(self):
        """批量删除 b3(含 detail d4)后 details 也清空"""
        self.assertEqual(self._count_details('b3'), 1)
        resp = self.client.delete(
            '/api/v2/history/batch',
            json={'batch_ids': ['b3']}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['deleted'], ['b3'])
        self.assertEqual(self._count_details('b3'), 0)

    def test_batch_delete_rejects_empty(self):
        """空 batch_ids → 400"""
        resp = self.client.delete('/api/v2/history/batch', json={'batch_ids': []})
        self.assertEqual(resp.status_code, 400)

    def test_batch_delete_rejects_missing_field(self):
        """缺 batch_ids 字段 → 400"""
        resp = self.client.delete('/api/v2/history/batch', json={})
        self.assertEqual(resp.status_code, 400)

    def test_batch_delete_rejects_too_many(self):
        """超过 50 个 → 400"""
        ids = [f'x{i}' for i in range(51)]
        resp = self.client.delete('/api/v2/history/batch', json={'batch_ids': ids})
        self.assertEqual(resp.status_code, 400)


if __name__ == '__main__':
    unittest.main()
