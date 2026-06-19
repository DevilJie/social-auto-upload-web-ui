"""postVideo 视频时长/大小校验测试"""
import os
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER DEFAULT 0,
    storage_type TEXT NOT NULL DEFAULT 'local',
    duration REAL DEFAULT 0,
    thumbnail_path TEXT DEFAULT '',
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type INTEGER NOT NULL,
    filePath TEXT NOT NULL,
    userName TEXT NOT NULL,
    status INTEGER DEFAULT 0,
    avatar TEXT DEFAULT ''
);
"""


def _setup():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


class TestPostVideoVideoValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()
        from app import app
        cls.app = app

    def setUp(self):
        self.client = self.app.test_client()
        # 隔离 DB：mock DB_PATH，避免污染生产库
        self._db_patches = [
            patch("app.DB_PATH", DB_PATH),
            patch("app._get_db_path", return_value=DB_PATH),
        ]
        for p in self._db_patches:
            p.start()

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM materials")
        conn.commit()
        conn.close()

        # 屏蔽真实 platform publish_video 与文件路径解析
        self._patches = [
            patch("app._resolve_material_path", side_effect=lambda p: p or "/tmp/fake.mp4"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._db_patches:
            p.stop()
        for p in self._patches:
            p.stop()

    def _insert_material(self, mid, file_size, duration, stored_path="materials/2026/06/19/test.mp4"):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT INTO materials (id, original_filename, stored_path, file_type, file_size, duration)
               VALUES (?, ?, ?, 'video', ?, ?)""",
            (mid, "test.mp4", stored_path, file_size, duration),
        )
        conn.commit()
        conn.close()

    def _fake_platform(self, key="douyin"):
        """构造 platform mock，platform_key 必须是真实字符串（供 validate 使用）"""
        p = MagicMock(spec=["platform_key", "publish_video"])
        p.platform_key = key
        p.publish_video = MagicMock(return_value=True)
        return p

    @patch("app.get_platform")
    def test_postVideo_rejects_video_too_long_for_douyin(self, mock_get_platform):
        """4000 秒视频到抖音应被拒（> 3600）"""
        self._insert_material("vid-long", 100 * 1024**2, 4000)
        mock_get_platform.return_value = self._fake_platform("douyin")

        r = self.client.post("/postVideo", json={
            "type": 3,
            "title": "测试视频",
            "fileList": ["materials/2026/06/19/test.mp4"],
            "thumbnailLandscape": "",
            "thumbnailPortrait": "",
        })
        assert r.status_code == 400, r.data
        body = r.get_json()
        assert "抖音" in body["msg"]
        assert "时长" in body["msg"]

    @patch("app.get_platform")
    def test_postVideo_accepts_video_within_douyin_range(self, mock_get_platform):
        """30 秒视频到抖音应通过"""
        self._insert_material("vid-ok", 100 * 1024**2, 30)
        mock_get_platform.return_value = self._fake_platform("douyin")

        r = self.client.post("/postVideo", json={
            "type": 3,
            "title": "测试视频",
            "fileList": ["materials/2026/06/19/test.mp4"],
            "thumbnailLandscape": "",
            "thumbnailPortrait": "",
        })
        assert r.status_code == 200

    @patch("app.get_platform")
    def test_postVideo_accepts_video_without_material_record(self, mock_get_platform):
        """找不到材料记录（旧路径直接上传）→ 跳过校验"""
        mock_get_platform.return_value = self._fake_platform("douyin")

        r = self.client.post("/postVideo", json={
            "type": 3,
            "title": "测试视频",
            "fileList": ["materials/2026/06/19/missing.mp4"],
            "thumbnailLandscape": "",
            "thumbnailPortrait": "",
        })
        assert r.status_code == 200

    @patch("app.get_platform")
    def test_postVideo_rejects_oversized_for_bilibili(self, mock_get_platform):
        """B站 17G 视频应被拒（> 16G）"""
        self._insert_material("vid-big", 17 * 1024**3, 30)
        mock_get_platform.return_value = self._fake_platform("bilibili")

        r = self.client.post("/postVideo", json={
            "type": 5,
            "title": "测试视频",
            "fileList": ["materials/2026/06/19/test.mp4"],
            "thumbnailLandscape": "",
            "thumbnailPortrait": "",
        })
        assert r.status_code == 400
        assert "B站" in r.get_json()["msg"]
        assert "G" in r.get_json()["msg"]


if __name__ == '__main__':
    unittest.main()