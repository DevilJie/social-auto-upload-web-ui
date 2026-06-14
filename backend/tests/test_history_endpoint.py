"""
测试 GET /api/v2/history 读 publish_batches + publish_details 的行为。
"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# 把 backend 目录加进 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _setup_db(db_path: Path):
    """初始化临时 DB 并塞 2 个 batch（一个 3 账号全部成功，一个 2 账号 1 失败）

    不能直接调 init_db.init_database()，因为 init_db.DB_PATH 在 import 时已绑定。
    直接对临时 DB 跑 schema 脚本（与 init_db.py 保持一致）。
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA_SQL)
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, failed_count, created_at) VALUES ('b1', 'video', '测试视频1', 'success', 3, 3, 0, '2026-06-01 10:00:00')")
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, failed_count, created_at) VALUES ('b2', 'image', '测试图文1', 'partial', 2, 1, 1, '2026-06-02 10:00:00')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d1', 'b1', '账号A', '抖音', '{\"title\":\"测试视频1\"}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d2', 'b1', '账号B', '小红书', '{\"title\":\"测试视频1\"}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d3', 'b1', '账号C', 'B站', '{\"title\":\"测试视频1\"}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d4', 'b2', '账号D', '抖音', '{}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d5', 'b2', '账号E', '小红书', '{}', 'failed')")
    conn.commit()
    conn.close()


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


class TestHistoryEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 临时数据目录 + DB 路径都建在 setUpClass 里，避免模块级 setup 污染其他测试
        cls._tmpdir = tempfile.mkdtemp()
        os.environ['SAU_DATA_DIR'] = cls._tmpdir
        cls.DB_PATH = Path(cls._tmpdir) / "db" / "database.db"
        _setup_db(cls.DB_PATH)
        from ext_api import app
        cls.client = app.test_client()

    def setUp(self):
        # 强制 ext_api._db_conn() 用测试 DB（ext_api.DB_PATH 在 import 时已绑定）
        self._db_path_patch = patch('ext_api.DB_PATH', self.DB_PATH)
        self._db_path_patch.start()

    def tearDown(self):
        self._db_path_patch.stop()

    def test_returns_batches_with_items(self):
        """应返回 batch 列表，每个含 items 明细子数组"""
        resp = self.client.get('/api/v2/history')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['code'], 200)
        self.assertIn('items', data['data'])
        items = data['data']['items']
        self.assertEqual(len(items), 2)
        # 最新的 b2 排第一
        self.assertEqual(items[0]['id'], 'b2')
        self.assertEqual(items[0]['type'], 'image')
        self.assertEqual(len(items[0]['items']), 2)

    def test_filter_by_type(self):
        """type=video 只返回视频 batch"""
        resp = self.client.get('/api/v2/history?type=video')
        data = resp.get_json()
        items = data['data']['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['type'], 'video')
        self.assertEqual(len(items[0]['items']), 3)

    def test_items_have_required_fields(self):
        """items 子项必须有 id/account_name/platform/status"""
        resp = self.client.get('/api/v2/history')
        items = resp.get_json()['data']['items']
        first_item = items[0]['items'][0]
        for field in ('id', 'account_name', 'platform', 'status'):
            self.assertIn(field, first_item)

    def test_history_when_account_configs_cover_is_dict(self):
        """account_configs.coverLandscape/coverPortrait 是 dict 时不应 500。

        场景:草稿批量发布等路径把 task.cover_landscape(dict | None)原样
        写进 account_configs。当 batch 没有物质 ID(封面来自抽帧)时,
        _serialize_batch_with_items 会走 fallback_cover_url 分支,把 dict
        传给 _resolve_cover_from_path,触发 re.search 报
        "expected string or bytes-like object, got 'dict'"。
        """
        with sqlite3.connect(str(self.DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, title, status, account_count, success_count, failed_count, created_at) "
                "VALUES ('b3', 'video', 'cover-as-dict', 'success', 1, 1, 0, '2026-06-03 10:00:00')"
            )
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d6', 'b3', '账号F', '抖音', ?, 'success')",
                (json.dumps({
                    'title': 'cover-as-dict',
                    'coverLandscape': {'stored_path': '/data/materials/2026/06/13/abc.jpg', 'url': ''},
                    'coverPortrait': {'path': '/data/materials/2026/06/13/xyz.jpg'},
                    'thumbnail_path': '/data/materials/2026/06/13/thumb.jpg',
                }),)
            )
            conn.commit()

        try:
            resp = self.client.get('/api/v2/history?type=video')
            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
            data = resp.get_json()
            self.assertEqual(data['code'], 200)
            target = next((b for b in data['data']['items'] if b['id'] == 'b3'), None)
            self.assertIsNotNone(target)
            self.assertIn('cover_url', target)
        finally:
            with sqlite3.connect(str(self.DB_PATH)) as conn:
                conn.execute("DELETE FROM publish_details WHERE id = 'd6'")
                conn.execute("DELETE FROM publish_batches WHERE id = 'b3'")
                conn.commit()


if __name__ == '__main__':
    unittest.main()
