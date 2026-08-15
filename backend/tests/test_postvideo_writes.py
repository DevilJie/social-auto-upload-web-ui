"""测试 /postVideo 写入 publish_batches + publish_details"""
import os
import sys
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _wait_publish_done(client, resp, timeout=10.0):
    """异步发布：轮询 /postVideo/status/<taskId> 直到终态，返回状态 dict。"""
    body = resp.get_json() or {}
    task_id = (body.get('data') or {}).get('taskId')
    assert task_id, f"postVideo 应返回 taskId: {body}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(f'/postVideo/status/{task_id}')
        assert st.status_code == 200, f"status 查询失败: {st.status_code}"
        task = st.get_json()['data']
        if task['status'] in ('success', 'failed'):
            return task
        time.sleep(0.05)
    raise AssertionError('发布任务超时未结束')

sys.path.insert(0, str(Path(__file__).parent.parent))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"

# 测试用 DB 的 schema（与 init_db.py 一致）
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
CREATE TABLE IF NOT EXISTS user_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT
);
"""


def _setup():
    """在测试自己的 DB_PATH 建好 schema"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()


class TestPostVideoWrites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()
        from app import app
        cls.app = app

    def setUp(self):
        # mock 掉真实 platform publish_video，避免启动 Chromium（每次 3 分钟）
        self._fake_platform = MagicMock()
        self._fake_platform.publish_video = MagicMock(return_value=True)
        self._patches = [
            patch("app.get_platform", return_value=self._fake_platform),
            patch("app.DB_PATH", DB_PATH),
            patch("app._get_db_path", return_value=DB_PATH),
            patch("app._resolve_material_path", side_effect=lambda p: p or "/tmp/fake.mp4"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_post_video_creates_batch_and_detail(self):
        client = self.app.test_client()
        resp = client.post('/postVideo', json={
            'type': 3,
            'title': '测试视频',
            'description': '描述',
            'fileList': ['/tmp/fake.mp4'],
            'accountList': ['/tmp/fake_cookie.json'],
            'tags': ['标签1'],
            'batchId': 'batch-uuid-1',
            'videoMaterialId': 'mat-vid-1',
            'landscapeCoverMaterialId': 'mat-cover-l-1',
            'portraitCoverMaterialId': 'mat-cover-p-1',
        })
        self.assertEqual(resp.status_code, 200)
        # 异步发布：轮询任务状态到终态，再校验落库结果
        task = _wait_publish_done(client, resp)
        self.assertEqual(task['status'], 'success', f"发布任务失败: {task}")
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        batch = conn.execute("SELECT * FROM publish_batches WHERE id = 'batch-uuid-1'").fetchone()
        details = conn.execute("SELECT * FROM publish_details WHERE batch_id = 'batch-uuid-1'").fetchall()
        conn.close()
        self.assertIsNotNone(batch, "publish_batches 行应存在")
        self.assertEqual(batch['type'], 'video')
        self.assertEqual(batch['title'], '测试视频')
        self.assertEqual(batch['video_material_id'], 'mat-vid-1')
        self.assertEqual(len(details), 1)
        d = details[0]
        self.assertEqual(d['batch_id'], 'batch-uuid-1')
        # 异步执行完成后，detail 应被后台线程标成 success
        self.assertEqual(d['status'], 'success')
        self.assertIsNotNone(d['finished_at'])
        # 用 dict 比较避免依赖 JSON 字段顺序（Flask get_json 之后 key 顺序可能与发送时不同）
        self.assertEqual(json.loads(d['account_configs']), {
            'title': '测试视频', 'description': '描述', 'tags': ['标签1'],
            'videoMaterialId': 'mat-vid-1',
            'landscapeCoverMaterialId': 'mat-cover-l-1',
            'portraitCoverMaterialId': 'mat-cover-p-1',
        })


if __name__ == '__main__':
    unittest.main()
