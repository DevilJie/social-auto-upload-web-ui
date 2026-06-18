"""POST /api/materials/<id>/probe 测试"""
import os
import sys
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = os.path.join(_tmpdir, "db", "database.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER DEFAULT 0,
    storage_type TEXT NOT NULL DEFAULT 'local',
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    duration REAL DEFAULT 0,
    thumbnail_path TEXT DEFAULT '',
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def _setup_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def _insert_material(mid, file_type="video", duration=0, file_size=0, stored_path="fake.mp4"):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO materials (id, original_filename, stored_path, file_type, file_size, duration)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (mid, "test.mp4", stored_path, file_type, file_size, duration),
    )
    conn.commit()
    conn.close()


class TestProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup_db()
        from app import app
        cls.app = app

    def setUp(self):
        self.client = self.app.test_client()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM materials")
        conn.commit()
        conn.close()

    def test_probe_video_writes_duration_and_size(self):
        _insert_material("vid-1", file_type="video", stored_path="/tmp/fake.mp4")
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1234567), \
             patch("blueprints.materials_bp.get_video_duration_safe", return_value=42.0):
            r = self.client.post("/api/materials/vid-1/probe")
        assert r.status_code == 200, r.data
        data = r.get_json()["data"]
        assert data["duration"] == 42.0
        assert data["file_size"] == 1234567

    def test_probe_image_returns_400(self):
        _insert_material("img-1", file_type="image")
        r = self.client.post("/api/materials/img-1/probe")
        assert r.status_code == 400

    def test_probe_not_found_returns_404(self):
        r = self.client.post("/api/materials/nonexistent/probe")
        assert r.status_code == 404

    def test_probe_missing_file_returns_400(self):
        _insert_material("vid-missing", file_type="video", stored_path="/tmp/does-not-exist.mp4")
        with patch("os.path.isfile", return_value=False):
            r = self.client.post("/api/materials/vid-missing/probe")
        assert r.status_code == 400
