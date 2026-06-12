"""DELETE /api/v2/drafts/batch 端点集成测试。"""
import json
import sys
import sqlite3
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _setup_db(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript("""
        CREATE TABLE drafts (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL DEFAULT 'video',
            title TEXT NOT NULL DEFAULT '',
            cover_path TEXT NOT NULL DEFAULT '',
            draft_data TEXT NOT NULL DEFAULT '{}',
            channels_summary TEXT NOT NULL DEFAULT '[]',
            video_duration REAL NOT NULL DEFAULT 0,
            video_file_size INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def test_batch_delete_happy_path(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO drafts (id, type) VALUES (1, 'video'), (2, 'video'), (3, 'video')")
        conn.commit()

    from app import app
    client = app.test_client()
    resp = client.delete('/api/v2/drafts/batch', json={'draft_ids': [1, 2]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['deleted'] == [1, 2]
    assert data['failed'] == []

    # 验证 DB 中 1, 2 已被删除，3 还在
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT id FROM drafts").fetchall()
    assert [r[0] for r in rows] == [3]


def test_batch_delete_partial_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO drafts (id, type) VALUES (1, 'video')")
        conn.commit()

    from app import app
    client = app.test_client()
    resp = client.delete('/api/v2/drafts/batch', json={'draft_ids': [1, 99]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['deleted'] == [1]
    assert len(data['failed']) == 1
    assert data['failed'][0]['draft_id'] == 99


def test_batch_delete_empty(tmp_path, monkeypatch):
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.delete('/api/v2/drafts/batch', json={'draft_ids': []})
    assert resp.status_code == 400


def test_batch_delete_no_body(tmp_path, monkeypatch):
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.delete('/api/v2/drafts/batch', json={})
    assert resp.status_code == 400