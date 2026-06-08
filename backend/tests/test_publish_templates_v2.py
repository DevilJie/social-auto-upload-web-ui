"""
测试 GET /api/v2/publish-templates 读新表的行为。
旧的 test_publish_templates.py 仍要更新（Task 5），但本次先新建针对新表语义的测试。
"""
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
    from init_db import init_database
    init_database()
    conn = sqlite3.connect(str(DB_PATH))
    # 1 个视频 batch：1 个 detail 带 account_configs
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, created_at) VALUES ('bv1', 'video', '可复用视频', 'success', 1, 1, '2026-06-01')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('dv1', 'bv1', '账号A', '抖音', '{\"title\":\"可复用视频\",\"description\":\"描述\",\"tags\":[\"标签1\"]}', 'success')")
    # 1 个图文 batch
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, created_at) VALUES ('bi1', 'image', '可复用图文', 'success', 1, 1, '2026-06-02')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('di1', 'bi1', '账号B', '抖音', '{\"title\":\"可复用图文\"}', 'success')")
    # 1 个失败的 batch：不应被返回
    conn.execute("INSERT INTO publish_batches (id, type, title, status, account_count, success_count, created_at) VALUES ('bx1', 'video', '失败视频', 'failed', 1, 0, '2026-06-03')")
    conn.execute("INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) VALUES ('dx1', 'bx1', '账号C', '抖音', '{}', 'failed')")
    conn.commit()
    conn.close()


class TestPublishTemplatesV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()
        from ext_api import app
        cls.client = app.test_client()

    def test_video_type_returns_video_batches(self):
        resp = self.client.get('/api/v2/publish-templates?type=video')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['code'], 200)
        items = data['data']['list']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['type'], 'video')
        self.assertEqual(items[0]['title'], '可复用视频')
        # account_configs 取第一个 detail 的
        self.assertEqual(items[0]['account_configs'].get('title'), '可复用视频')
        self.assertEqual(len(items[0]['channels']), 1)
        self.assertEqual(items[0]['channels'][0]['platform'], '抖音')

    def test_image_type_returns_image_batches(self):
        resp = self.client.get('/api/v2/publish-templates?type=image')
        items = resp.get_json()['data']['list']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['type'], 'image')

    def test_failed_batches_excluded(self):
        """status=failed 的 batch 不应在 templates 列表里（因为 EXIST 过滤 + status IN）"""
        resp = self.client.get('/api/v2/publish-templates?type=video')
        items = resp.get_json()['data']['list']
        ids = [i['id'] for i in items]
        self.assertNotIn('bx1', ids)

    def test_missing_type_returns_400(self):
        resp = self.client.get('/api/v2/publish-templates')
        self.assertEqual(resp.status_code, 400)


if __name__ == '__main__':
    unittest.main()
