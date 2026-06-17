"""测试 /api/image-publish/publish 写入新表的行为"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY
);
"""


def _setup():
    """在测试自己的 DB_PATH 建好 schema"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()


class TestImagePublishEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()
        from app import app
        cls.app = app

    def setUp(self):
        # mock 掉真实 platform publish_image，避免启动 Chromium（每次 3 分钟）
        # get_platform 在 image_publish_bp 中是函数内 import，
        # 所以 patch 它在 impl.registry 模块里的位置
        self._fake_platform = MagicMock()
        self._fake_platform.publish_image = MagicMock(return_value=True)
        self._patches = [
            patch("impl.registry.get_platform", return_value=self._fake_platform),
            patch("blueprints.image_publish_bp.DB_PATH", DB_PATH),
            patch("blueprints.image_publish_bp.resolve_material_path",
                  side_effect=lambda p: p or "/tmp/fake.jpg"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_creates_batch_and_detail(self):
        """单次 /api/image-publish/publish 应插 1 batch + 1 detail（type='image'）"""
        client = self.app.test_client()
        # account_configs 是单个 dict（不是 list），按 spec §3.4
        resp = client.post('/api/image-publish/publish', json={
            'image_ids': [],
            'account_configs': {
                'account_id': 1,
                'platform': 'douyin',
                'filePath': '/tmp/fake_cookie.json',
                'title': '测试图文',
                'description': '描述',
                'tags': ['标签1'],
            },
            'batchId': 'batch-img-1',
            'landscapeCoverMaterialId': '',
            'portraitCoverMaterialId': 'mat-cover-p-1',
        })
        # 不在意 200 还是 4xx，关键是数据写入
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        batch = conn.execute("SELECT * FROM publish_batches WHERE id = 'batch-img-1'").fetchone()
        details = conn.execute("SELECT * FROM publish_details WHERE batch_id = 'batch-img-1'").fetchall()
        conn.close()
        self.assertIsNotNone(batch)
        self.assertEqual(batch['type'], 'image')
        self.assertEqual(batch['portrait_cover_material_id'], 'mat-cover-p-1')
        self.assertEqual(len(details), 1)

    def test_publish_endpoint_routes_weibo_to_platform_11(self):
        """POST /api/image-publish/publish 带 platform='weibo' 或 '微博' 时,
        路由到 platform_id=11,setUp 中的 self._fake_platform.publish_image 被调。

        间接验证 platform_map 含 'weibo': 11 / '微博': 11
        （platform_map 是 publish_images() 内局部变量,模块导入不可见）。
        """
        # 准备 materials 表里的一张图片,让 image_files 非空,从而走 platform 调用分支
        conn = sqlite3.connect(str(DB_PATH))
        # 复用测试 schema 临时扩展列(测试库独立,不影响生产)
        conn.execute("ALTER TABLE materials ADD COLUMN stored_path TEXT DEFAULT ''")
        conn.execute(
            "INSERT INTO materials (id, stored_path) VALUES (?, ?)",
            ('img1', '/tmp/fake_img1.jpg'),
        )
        conn.commit()
        conn.close()

        # patch storage.get_local_path,确保返回本地路径
        from storage import local as storage_local
        with patch.object(storage_local.LocalStorage, 'get_local_path',
                          return_value='/tmp/fake_img1.jpg'):
            client = self.app.test_client()
            self._fake_platform.publish_image.reset_mock()

            # Case 1: platform='weibo' → platform_id=11
            resp = client.post('/api/image-publish/publish', json={
                'image_ids': ['img1'],
                'account_configs': {
                    'account_id': 1,
                    'platform': 'weibo',
                    'filePath': '/tmp/fake_cookie.json',
                    'title': '测试微博图集',
                    'description': '测试描述',
                    'tags': ['测试'],
                    'aiContent': '内容由AI生成',
                },
                'batchId': 'batch-weibo-1',
            })
            # Case 2: platform='微博' (中文) → platform_id=11
            resp2 = client.post('/api/image-publish/publish', json={
                'image_ids': ['img1'],
                'account_configs': {
                    'account_id': 1,
                    'platform': '微博',
                    'filePath': '/tmp/fake_cookie.json',
                    'title': '测试微博图集中文',
                    'description': '测试描述',
                    'tags': ['测试'],
                    'aiContent': '内容由AI生成',
                },
                'batchId': 'batch-weibo-2',
            })

        # 验证 setUp 的 fake_platform.publish_image 被调 2 次(weibo + 微博)
        self.assertEqual(self._fake_platform.publish_image.call_count, 2)

        # 验证 kwargs 透传正确
        call1 = self._fake_platform.publish_image.call_args_list[0]
        self.assertEqual(call1.kwargs['title'], '测试微博图集')
        self.assertEqual(call1.kwargs['desc'], '测试描述')
        self.assertEqual(call1.kwargs['ai_content'], '内容由AI生成')
        self.assertEqual(call1.kwargs['files'], ['/tmp/fake_img1.jpg'])
        self.assertEqual(call1.kwargs['account_file'], ['/tmp/fake_cookie.json'])

        call2 = self._fake_platform.publish_image.call_args_list[1]
        self.assertEqual(call2.kwargs['title'], '测试微博图集中文')


if __name__ == '__main__':
    unittest.main()
