"""POST /api/v2/drafts/batch-publish 端点集成测试。"""
import json
import sys
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _setup_db(tmp_db):
    """建测试数据库（含 drafts + user_info + publish_batches/publish_details）。

    注意：legacy `publish_tasks` 表已删除（commit 71898c0）。`PublishTask` 持久化走
    `publish_details.account_configs` JSON（由 `_build_account_configs(task)` 填充）。
    本 fixture 只需建 `publish_batches` + `publish_details` 即可，因为 Task 12 测试用
    `monkeypatch` mock 了 `add_task`，不会触发真实 `_insert_db`。
    """
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript("""
        CREATE TABLE user_info (
            id INTEGER PRIMARY KEY,
            platform TEXT NOT NULL DEFAULT '',
            file_path TEXT NOT NULL DEFAULT '',
            user_name TEXT NOT NULL DEFAULT ''
        );
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
        CREATE TABLE publish_batches (
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
            source TEXT NOT NULL DEFAULT '',
            draft_id INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE publish_details (
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
    """)
    conn.commit()
    conn.close()


def _insert_user(conn, id, platform, file_path):
    conn.execute("INSERT INTO user_info (id, platform, file_path) VALUES (?, ?, ?)",
                (id, platform, file_path))
    conn.commit()


def _insert_video_draft(conn, id, draft_data, type='video'):
    conn.execute("INSERT INTO drafts (id, type, draft_data) VALUES (?, ?, ?)",
                (id, type, json.dumps(draft_data, ensure_ascii=False)))
    conn.commit()


def _valid_video_draft_data():
    return {
        'commonConfig': {'videoPortrait': {'stored_path': '/abs/v.mp4'},
                         'coverPortrait': {'stored_path': '/abs/c.jpg'}},
        'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait',
                                            'aiContent': '内容由AI生成'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait',
                                    'aiContent': '内容由AI生成'}},
        'publishAccountIds': [1],
    }


def test_batch_publish_happy_path(tmp_path, monkeypatch):
    """1 草稿 + 1 账号 → 1 个 task 入队。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')
        _insert_video_draft(conn, 1, _valid_video_draft_data())

    # mock add_task
    added_tasks = []
    def fake_add_task(task):
        added_tasks.append(task)
        return 'task-1'

    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue', lambda: MagicMock(add_task=fake_add_task))

    # mock DB_PATH
    from app import _get_db_path
    monkeypatch.setattr('app._get_db_path', lambda: db_path)

    # mock init
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()

    resp = client.post('/api/v2/drafts/batch-publish',
                       json={'draft_ids': [1]})

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['task_ids']) == 1
    assert data['failed'] == []
    assert len(added_tasks) == 1
    assert added_tasks[0].source == 'draft'
    assert added_tasks[0].draft_id == 1
    assert added_tasks[0].account_id == 1
    assert added_tasks[0].platform == 'xiaohongshu'
    assert added_tasks[0].platform_type == 1   # xiaohongshu = 1
    assert added_tasks[0].payload['title'] == 'T'
    assert added_tasks[0].payload['ai_content'] == '内容由AI生成'


def test_batch_publish_multi_account_yields_multi_tasks(tmp_path, monkeypatch):
    """1 草稿 + 2 账号（不同平台）→ 2 个 task。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    draft_data = {
        'commonConfig': {'videoPortrait': {'stored_path': '/abs/v.mp4'},
                         'coverPortrait': {'stored_path': '/abs/c.jpg'}},
        'platformConfigs': {
            'xiaohongshu': {'title': 'T-xhs', 'videoFormat': 'portrait', 'aiContent': 'X'},
            'douyin': {'title': 'T-dy', 'videoFormat': 'portrait', 'aiContent': 'X'},
        },
        'platformOverrides': {},
        'accountOverrides': {
            '1': {'title': 'T-xhs', 'videoFormat': 'portrait', 'aiContent': 'X'},
            '2': {'title': 'T-dy', 'videoFormat': 'portrait', 'aiContent': 'X'},
        },
        'publishAccountIds': [1, 2],
    }
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')
        _insert_user(conn, 2, 'douyin', '/cookies/d1')
        _insert_video_draft(conn, 1, draft_data)

    added_tasks = []
    def fake_add_task(task):
        added_tasks.append(task)
        return f'task-{len(added_tasks)}'

    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue', lambda: MagicMock(add_task=fake_add_task))
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['task_ids']) == 2
    assert len(added_tasks) == 2
    assert {t.platform for t in added_tasks} == {'xiaohongshu', 'douyin'}


def test_batch_publish_partial_failure(tmp_path, monkeypatch):
    """1 合法 + 1 缺字段 → 1 task + 1 failed。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    bad_draft = {
        'commonConfig': {'videoPortrait': None, 'videoLandscape': None,
                         'coverPortrait': {'stored_path': '/c.jpg'}},
        'platformConfigs': {'xiaohongshu': {'title': '', 'videoFormat': 'portrait'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': '', 'videoFormat': 'portrait'}},
        'publishAccountIds': [1],
    }
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')
        _insert_video_draft(conn, 1, _valid_video_draft_data())
        _insert_video_draft(conn, 2, bad_draft)

    added_tasks = []
    def fake_add_task(task):
        added_tasks.append(task)
        return f'task-{len(added_tasks)}'

    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue', lambda: MagicMock(add_task=fake_add_task))
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1, 2]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['task_ids']) == 1
    assert len(data['failed']) == 1
    assert data['failed'][0]['draft_id'] == 2


def test_batch_publish_draft_not_found(tmp_path, monkeypatch):
    """draft_ids 包含不存在的 id → 404。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [99]})
    assert resp.status_code == 404
    assert 99 in resp.get_json().get('missing_ids', [])


def test_batch_publish_wrong_type(tmp_path, monkeypatch):
    """type=image 草稿打到视频端点 → 400。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    with sqlite3.connect(str(db_path)) as conn:
        _insert_video_draft(conn, 1, {}, type='image')

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1]})
    assert resp.status_code == 400
    assert 1 in resp.get_json().get('wrong_type_ids', [])


def test_batch_publish_too_many(tmp_path, monkeypatch):
    """>30 个 → 400。"""
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': list(range(31))})
    assert resp.status_code == 400


def test_batch_publish_empty(tmp_path, monkeypatch):
    """空列表 → 400。"""
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': []})
    assert resp.status_code == 400