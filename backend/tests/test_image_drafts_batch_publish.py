"""POST /api/image-publish/drafts/batch-publish 端点集成测试。"""
import json
import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _setup_db(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript("""
        CREATE TABLE image_drafts (
            id INTEGER PRIMARY KEY,
            image_ids TEXT NOT NULL DEFAULT '[]',
            account_configs TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def _valid_image_draft_config():
    return {
        'platform': 'xiaohongshu', 'account_id': 1, 'account_name': 'a',
        'filePath': '/cookies/x1', 'title': 'T', 'description': '',
        'aiContent': '内容由AI生成', 'isOriginal': True,
    }


def test_image_batch_publish_happy_path(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO image_drafts (id, image_ids, account_configs) VALUES (1, ?, ?)",
            (json.dumps(['img-1', 'img-2']), json.dumps(_valid_image_draft_config())),
        )
        conn.commit()

    called = []
    def fake_publish():
        called.append(True)
        from flask import jsonify
        return jsonify({"code": 200, "msg": "ok"}), 200

    # Mock image_publish endpoint
    monkeypatch.setattr('blueprints.image_publish_bp.publish_images', fake_publish)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/image-publish/drafts/batch-publish', json={'draft_ids': [1]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['failed'] == []
    assert len(called) == 1   # publish_images 被调一次


def test_image_batch_publish_missing_image_ids(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO image_drafts (id, image_ids, account_configs) VALUES (1, '[]', ?)",
            (json.dumps(_valid_image_draft_config()),),
        )
        conn.commit()

    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/image-publish/drafts/batch-publish', json={'draft_ids': [1]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['failed']) == 1
    assert data['failed'][0]['draft_id'] == 1


def test_image_batch_publish_draft_not_found(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/image-publish/drafts/batch-publish', json={'draft_ids': [99]})
    assert resp.status_code == 404


def test_image_batch_publish_empty(tmp_path, monkeypatch):
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.post('/api/image-publish/drafts/batch-publish', json={'draft_ids': []})
    assert resp.status_code == 400