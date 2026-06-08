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

# 把 backend 目录加进 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# 用临时数据目录跑测试
_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"


def _setup_db():
    """初始化临时 DB 并塞 2 个 batch（一个 3 账号全部成功，一个 2 账号 1 失败）"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 引用 ext_api 的 _db_conn 会自动调 _ensure_tables，但 publish_batches/publish_details
    # 是 init_db.py 里的，需要先跑 init
    from init_db import init_database
    init_database()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, failed_count, created_at) VALUES ('b1', 'video', '测试视频1', 'success', 3, 3, 0, '2026-06-01 10:00:00')")
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, failed_count, created_at) VALUES ('b2', 'image', '测试图文1', 'partial', 2, 1, 1, '2026-06-02 10:00:00')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d1', 'b1', '账号A', '抖音', '{\"title\":\"测试视频1\"}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d2', 'b1', '账号B', '小红书', '{\"title\":\"测试视频1\"}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d3', 'b1', '账号C', 'B站', '{\"title\":\"测试视频1\"}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d4', 'b2', '账号D', '抖音', '{}', 'success')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('d5', 'b2', '账号E', '小红书', '{}', 'failed')")
    conn.commit()
    conn.close()


class TestHistoryEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup_db()
        from ext_api import app
        cls.client = app.test_client()

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


if __name__ == '__main__':
    unittest.main()
