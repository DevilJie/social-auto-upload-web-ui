"""分片上传 Blueprint 端到端测试（init / chunk / merge / status / cancel）。"""
import io
import os
import sys
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"
CHUNK_DIR = Path(_tmpdir) / "upload_chunks"

# 测试用 schema：materials + upload_sessions + upload_chunks（与 init_db.py 一致）
_SCHEMA_SQL = """
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
CREATE TABLE IF NOT EXISTS upload_sessions (
    upload_id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT,
    file_type TEXT,
    chunk_size INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    uploaded_chunks INTEGER DEFAULT 0,
    status TEXT DEFAULT 'uploading',
    material_id TEXT,
    error_message TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS upload_chunks (
    upload_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_size INTEGER NOT NULL,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (upload_id, chunk_index),
    FOREIGN KEY (upload_id) REFERENCES upload_sessions(upload_id) ON DELETE CASCADE
);
"""


def _setup():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()


def _make_zip_bytes(size_mb: int) -> bytes:
    """生成精确指定 MB 大小的 bytes（用原始 bytes，精确控制大小避免 zip overhead）。"""
    return b'x' * (size_mb * 1024 * 1024)


class TestChunkUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()
        from app import app
        cls.app = app

    def setUp(self):
        # patch 掉 _ensure_db / _ensure_materials_table 等 before_request，
        # 防止它们跑 init_database 覆盖我们的测试 schema
        from app import app as flask_app
        self._saved_hooks = list(flask_app.before_request_funcs.get(None, []))
        flask_app.before_request_funcs[None] = [
            fn for fn in self._saved_hooks
            if getattr(fn, '__name__', None) not in ('_ensure_db', '_ensure_materials_table')
        ]
        # patch DB_PATH 和 CHUNK_DIR 到测试目录
        self._patches = [
            patch("blueprints.uploads_bp.BASE_DIR", Path(_tmpdir)),
            patch("blueprints.uploads_bp.DB_PATH", DB_PATH) if False else patch(
                "blueprints.uploads_bp._get_db", self._patched_get_db
            ),
        ]
        for p in self._patches:
            p.start()
        # 清空测试 DB 和 chunk 目录
        conn = sqlite3.connect(str(DB_PATH))
        for tbl in ("materials", "upload_chunks", "upload_sessions"):
            conn.execute(f"DELETE FROM {tbl}")
        conn.commit()
        conn.close()
        if CHUNK_DIR.exists():
            import shutil
            shutil.rmtree(CHUNK_DIR, ignore_errors=True)
        CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        from app import app as flask_app
        flask_app.before_request_funcs[None] = self._saved_hooks

    def _patched_get_db(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    # ─────────────────── init ───────────────────

    def test_init_ok(self):
        client = self.app.test_client()
        resp = client.post('/api/uploads/init', json={
            'filename': 'big.mp4',
            'file_size': 150 * 1024 * 1024,  # 150MB
            'mime_type': 'video/mp4',
            'chunk_size': 50 * 1024 * 1024,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['code'], 200)
        self.assertEqual(data['data']['total_chunks'], 3)
        self.assertEqual(data['data']['chunk_size'], 50 * 1024 * 1024)
        self.assertEqual(data['data']['uploaded_chunks'], [])
        self.assertIn('upload_id', data['data'])
        # session 目录已建
        sid = data['data']['upload_id']
        self.assertTrue((CHUNK_DIR / sid).is_dir())

    def test_init_default_chunk_size(self):
        client = self.app.test_client()
        resp = client.post('/api/uploads/init', json={
            'filename': 'big.mp4', 'file_size': 200 * 1024 * 1024,
        })
        data = resp.get_json()['data']
        self.assertEqual(data['chunk_size'], 50 * 1024 * 1024)  # DEFAULT_CHUNK_SIZE
        self.assertEqual(data['total_chunks'], 4)

    def test_init_rejects_oversize(self):
        client = self.app.test_client()
        resp = client.post('/api/uploads/init', json={
            'filename': 'huge.mp4',
            'file_size': 100 * 1024 * 1024 * 1024,  # 100GB > 50GB
        })
        self.assertEqual(resp.get_json()['code'], 400)

    def test_init_rejects_bad_chunk_size(self):
        client = self.app.test_client()
        # 太大
        resp = client.post('/api/uploads/init', json={
            'filename': 'a.mp4', 'file_size': 1024,
            'chunk_size': 200 * 1024 * 1024,
        })
        self.assertEqual(resp.get_json()['code'], 400)
        # 太小
        resp = client.post('/api/uploads/init', json={
            'filename': 'a.mp4', 'file_size': 1024,
            'chunk_size': 100 * 1024,  # 100KB
        })
        self.assertEqual(resp.get_json()['code'], 400)

    def test_init_rejects_missing_fields(self):
        client = self.app.test_client()
        self.assertEqual(
            client.post('/api/uploads/init', json={'file_size': 100}).get_json()['code'], 400
        )
        self.assertEqual(
            client.post('/api/uploads/init', json={'filename': 'a.mp4'}).get_json()['code'], 400
        )

    # ─────────────────── chunk ───────────────────

    def _init_session(self, filename='test.bin', file_size=10*1024*1024, chunk_size=2*1024*1024):
        client = self.app.test_client()
        resp = client.post('/api/uploads/init', json={
            'filename': filename, 'file_size': file_size,
            'mime_type': 'application/octet-stream', 'chunk_size': chunk_size,
        })
        return resp.get_json()['data']

    def _upload_chunk(self, upload_id, chunk_index, data: bytes):
        client = self.app.test_client()
        return client.post('/api/uploads/chunk', data={
            'upload_id': upload_id,
            'chunk_index': str(chunk_index),
            'file': (io.BytesIO(data), f'chunk_{chunk_index}.bin'),
        }, content_type='multipart/form-data')

    def test_chunk_ok(self):
        init = self._init_session(file_size=6*1024*1024, chunk_size=2*1024*1024)
        upload_id = init['upload_id']
        resp = self._upload_chunk(upload_id, 0, b'A' * 2*1024*1024)
        body = resp.get_json()
        self.assertEqual(body['code'], 200)
        self.assertEqual(body['data']['uploaded_chunks'], 1)
        self.assertEqual(body['data']['total_chunks'], 3)
        # 文件已落盘
        self.assertTrue((CHUNK_DIR / upload_id / '0').is_file())

    def test_chunk_wrong_size(self):
        init = self._init_session(file_size=6*1024*1024, chunk_size=2*1024*1024)
        resp = self._upload_chunk(init['upload_id'], 0, b'A' * 1024)  # 期望 2MB
        self.assertEqual(resp.get_json()['code'], 400)

    def test_chunk_wrong_upload_id(self):
        resp = self._upload_chunk('non-existent-uuid', 0, b'A' * 100)
        self.assertEqual(resp.get_json()['code'], 404)

    def test_chunk_index_out_of_range(self):
        init = self._init_session(file_size=4*1024*1024, chunk_size=2*1024*1024)  # 2 chunks
        resp = self._upload_chunk(init['upload_id'], 5, b'A' * 100)
        self.assertEqual(resp.get_json()['code'], 400)

    def test_chunk_idempotent_rewrite(self):
        """同一 chunk_index 上传两次应该覆盖（断点续传同一分片）"""
        init = self._init_session(file_size=2*1024*1024, chunk_size=2*1024*1024)
        uid = init['upload_id']
        self._upload_chunk(uid, 0, b'A' * 2*1024*1024)
        self._upload_chunk(uid, 0, b'B' * 2*1024*1024)  # 覆盖
        self.assertEqual((CHUNK_DIR / uid / '0').read_bytes(), b'B' * 2*1024*1024)

    # ─────────────────── status ───────────────────

    def test_status_tracks_uploaded_chunks(self):
        init = self._init_session(file_size=6*1024*1024, chunk_size=2*1024*1024)
        uid = init['upload_id']
        self._upload_chunk(uid, 0, b'A' * 2*1024*1024)
        self._upload_chunk(uid, 2, b'C' * 2*1024*1024)  # 跳过 1，先传 2

        client = self.app.test_client()
        resp = client.get(f'/api/uploads/status?upload_id={uid}')
        body = resp.get_json()
        self.assertEqual(body['code'], 200)
        self.assertEqual(sorted(body['data']['uploaded_chunks']), [0, 2])
        self.assertEqual(body['data']['total_chunks'], 3)
        self.assertEqual(body['data']['status'], 'uploading')

    def test_status_404(self):
        client = self.app.test_client()
        resp = client.get('/api/uploads/status?upload_id=non-existent')
        self.assertEqual(resp.get_json()['code'], 404)

    # ─────────────────── cancel ───────────────────

    def test_cancel_ok(self):
        init = self._init_session(file_size=4*1024*1024, chunk_size=2*1024*1024)
        uid = init['upload_id']
        self._upload_chunk(uid, 0, b'A' * 2*1024*1024)

        client = self.app.test_client()
        resp = client.delete(f'/api/uploads/?upload_id={uid}')
        self.assertEqual(resp.get_json()['code'], 200)
        # 临时目录清理
        self.assertFalse((CHUNK_DIR / uid).exists())
        # DB 状态
        conn = sqlite3.connect(str(DB_PATH))
        status = conn.execute(
            "SELECT status FROM upload_sessions WHERE upload_id=?", (uid,)
        ).fetchone()[0]
        conn.close()
        self.assertEqual(status, 'cancelled')

    def test_cancel_after_merge_blocked(self):
        init = self._init_session(file_size=2*1024*1024, chunk_size=2*1024*1024)
        uid = init['upload_id']
        self._upload_chunk(uid, 0, b'X' * 2*1024*1024)
        client = self.app.test_client()
        client.post('/api/uploads/merge', json={'upload_id': uid})
        # 合并后取消
        resp = client.delete(f'/api/uploads/?upload_id={uid}')
        self.assertEqual(resp.get_json()['code'], 400)

    # ─────────────────── merge ───────────────────

    def test_merge_incomplete_chunks(self):
        init = self._init_session(file_size=6*1024*1024, chunk_size=2*1024*1024)
        uid = init['upload_id']
        self._upload_chunk(uid, 0, b'A' * 2*1024*1024)
        # 只传 1/3
        client = self.app.test_client()
        resp = client.post('/api/uploads/merge', json={'upload_id': uid})
        self.assertEqual(resp.get_json()['code'], 400)

    def test_merge_wrong_final_size(self):
        """模拟合并后大小不符（磁盘上有完整分片但内容被改）"""
        init = self._init_session(file_size=6*1024*1024, chunk_size=2*1024*1024)
        uid = init['upload_id']
        self._upload_chunk(uid, 0, b'A' * 2*1024*1024)
        self._upload_chunk(uid, 1, b'B' * 2*1024*1024)
        self._upload_chunk(uid, 2, b'C' * 2*1024*1024)
        # 篡改一个分片大小
        (CHUNK_DIR / uid / '1').write_bytes(b'B' * 1024)  # 篡改成 1KB

        client = self.app.test_client()
        resp = client.post('/api/uploads/merge', json={'upload_id': uid})
        self.assertEqual(resp.get_json()['code'], 400)

    def test_end_to_end_5mb_3chunks(self):
        """完整流程：5MB 文件 / 3 分片 / 全部上传 → merge → 验证 materials + 临时清理"""
        target_bytes = _make_zip_bytes(5)
        self.assertEqual(len(target_bytes), 5 * 1024 * 1024)
        chunk_size = 2 * 1024 * 1024  # 2MB × 3 = 6MB，最后一片 1MB
        init = self._init_session(
            filename='test.zip', file_size=len(target_bytes), chunk_size=chunk_size,
            # 覆盖默认 mime，因为 _make_zip_bytes 返回的是 zip
        )
        # init 已经创建 session，但 mime 是 application/octet-stream，不影响
        uid = init['upload_id']

        # 切 3 片上传
        chunks = [
            target_bytes[i:i+chunk_size]
            for i in range(0, len(target_bytes), chunk_size)
        ]
        self.assertEqual(len(chunks), 3)
        for i, c in enumerate(chunks):
            resp = self._upload_chunk(uid, i, c)
            self.assertEqual(resp.get_json()['code'], 200, f"chunk {i} failed")

        # status 应有 3 片
        status = self.app.test_client().get(
            f'/api/uploads/status?upload_id={uid}'
        ).get_json()['data']
        self.assertEqual(status['uploaded_chunks'], [0, 1, 2])

        # merge
        merge_resp = self.app.test_client().post(
            '/api/uploads/merge', json={'upload_id': uid}
        ).get_json()
        self.assertEqual(merge_resp['code'], 200, merge_resp)
        self.assertEqual(merge_resp['data']['file_size'], len(target_bytes))
        self.assertEqual(merge_resp['data']['file_type'], 'image')  # zip 扩展名兜底

        # 临时目录已清理
        self.assertFalse((CHUNK_DIR / uid).exists())

        # materials 表有记录
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT * FROM materials").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[5], len(target_bytes))  # file_size

        # 合并后的文件内容 = 原始 zip
        from storage import get_storage
        storage = get_storage()
        local_path = storage.get_local_path(row[2])
        if local_path is None:
            local_path = Path(_tmpdir) / row[2]
        with open(local_path, 'rb') as f:
            self.assertEqual(f.read(), target_bytes)


if __name__ == '__main__':
    unittest.main()
