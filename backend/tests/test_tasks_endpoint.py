"""测试 /api/v2/tasks 读新表的行为（TaskCenter 用）"""
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


def _setup():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    import init_db as init_db_module
    init_db_module.DB_PATH = DB_PATH
    from init_db import init_database, migrate_database
    init_database()
    migrate_database()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, created_at) VALUES ('tb1', 'video', 'batch', 'running', 2, '2026-06-01')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('td1', 'tb1', '账号A', '抖音', '{}', 'running')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('td2', 'tb1', '账号B', '小红书', '{}', 'pending')")
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, created_at) VALUES ('tb2', 'video', 'batch2', 'success', 1, '2026-06-02')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('td3', 'tb2', '账号C', '抖音', '{}', 'success')")
    conn.commit()
    conn.close()


class TestTasksEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()
        import ext_api
        ext_api.DB_PATH = DB_PATH
        from ext_api import app
        cls.client = app.test_client()

    def test_get_tasks_returns_details_with_batch_id(self):
        """返回的每条 task 必须是 publish_details 行（含 batch_id 字段）"""
        resp = self.client.get('/api/v2/tasks')
        data = resp.get_json()
        items = data['data']['list']
        self.assertGreaterEqual(len(items), 3)
        for it in items:
            self.assertIn('batch_id', it)
            self.assertIn('account_name', it)
            self.assertIn('platform', it)
            self.assertIn('status', it)

    def test_get_tasks_filter_by_status(self):
        resp = self.client.get('/api/v2/tasks?status=running')
        items = resp.get_json()['data']['list']
        for it in items:
            self.assertEqual(it['status'], 'running')


if __name__ == '__main__':
    unittest.main()
