"""GET /api/v2/publish-templates 端点测试。"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _make_db():
    """创建一个临时 SQLite + 完整 publish_tasks + image_publish_tasks schema，返回 db_path。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE publish_tasks (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            account_name TEXT NOT NULL,
            video_path TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT DEFAULT '',
            publish_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            thumbnail_path TEXT DEFAULT '',
            account_configs TEXT DEFAULT '{}'
        );
        CREATE TABLE image_publish_tasks (
            id TEXT PRIMARY KEY,
            image_ids TEXT NOT NULL,
            account_configs TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            scheduled_at TEXT,
            published_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_video(conn, id_, status, account_configs, created_at='2026-06-08T10:00:00', title='t', thumbnail_path='thumb.png'):
    conn.execute(
        "INSERT INTO publish_tasks (id, platform, account_name, video_path, title, status, account_configs, thumbnail_path, created_at) VALUES (?, 'douyin', 'x', '/v', ?, ?, ?, ?, ?)",
        (id_, title, status, json.dumps(account_configs, ensure_ascii=False), thumbnail_path, created_at)
    )


def test_video_templates_filters_success_and_nonempty():
    """只返回 status=success 且 account_configs 非空的记录。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    _insert_video(conn, "1", "success", {"douyin": {"title": "ok"}}, "2026-06-08T10:00:00", "task 1")
    _insert_video(conn, "2", "success", {}, "2026-06-08T09:00:00", "task 2")
    _insert_video(conn, "3", "failed", {"douyin": {"title": "bad"}}, "2026-06-08T08:00:00", "task 3")
    _insert_video(conn, "4", "success", {"douyin": {"title": "ok2"}}, "2026-06-08T07:00:00", "task 4")
    conn.commit()
    conn.close()

    import ext_api as ext
    with patch.object(ext, "_db_conn", lambda: sqlite3.connect(str(db_path))):
        with ext.app.test_request_context("/api/v2/publish-templates?type=video"):
            resp = get_publish_templates()
            data = resp.get_json()
            ids = [r['id'] for r in data['data']['list']]
            assert ids == ["1", "4"]
            assert data['data']['total'] == 2


def test_video_templates_returns_expected_fields():
    """响应字段含 type, title, description, thumbnail_path, channels, account_configs, created_at。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    _insert_video(
        conn, "1", "success", {"douyin": {"title": "ok"}, "xiaohongshu": {"title": "xhs"}},
        "2026-06-08T10:00:00", "My Title", "thumb.png"
    )
    conn.commit()
    conn.close()

    import ext_api as ext
    with patch.object(ext, "_db_conn", lambda: sqlite3.connect(str(db_path))):
        with ext.app.test_request_context("/api/v2/publish-templates?type=video"):
            resp = get_publish_templates()
            data = resp.get_json()
            item = data['data']['list'][0]
            assert item['type'] == 'video'
            assert item['title'] == 'My Title'
            assert item['thumbnail_path'] == 'thumb.png'
            assert item['account_configs'] == {"douyin": {"title": "ok"}, "xiaohongshu": {"title": "xhs"}}
            platforms = [c['platform'] for c in item['channels']]
            assert set(platforms) == {'douyin', 'xiaohongshu'}


def test_image_templates_returns_image_with_first_image_id():
    """图文返回 first_image_id 和 account_configs 数组。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO image_publish_tasks (id, image_ids, account_configs, status, created_at) VALUES (?, ?, ?, 'success', '2026-06-08T10:00:00')",
        (
            "img-1",
            json.dumps(["img-uuid-1", "img-uuid-2"]),
            json.dumps([
                {"account_id": 2, "platform": "douyin", "title": "img title", "description": "d"},
                {"account_id": 3, "platform": "xiaohongshu", "title": "xhs", "description": "d2"},
            ], ensure_ascii=False),
        )
    )
    conn.commit()
    conn.close()

    import ext_api as ext
    with patch.object(ext, "_db_conn", lambda: sqlite3.connect(str(db_path))):
        with ext.app.test_request_context("/api/v2/publish-templates?type=image"):
            resp = get_publish_templates()
            data = resp.get_json()
            item = data['data']['list'][0]
            assert item['type'] == 'image'
            assert item['first_image_id'] == 'img-uuid-1'
            assert item['title'] == 'img title'
            assert isinstance(item['account_configs'], list)
            assert len(item['account_configs']) == 2
            assert item['account_configs'][0]['account_id'] == 2


def test_publish_templates_invalid_type_returns_400():
    """type 参数不是 video/image 返 400。"""
    from ext_api import get_publish_templates

    import ext_api as ext
    with ext.app.test_request_context("/api/v2/publish-templates?type=foo"):
        resp = get_publish_templates()
        assert resp[1] == 400
        assert 'type' in resp[0].get_json()['msg']


def test_publish_templates_pagination():
    """page / page_size 生效。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    for i in range(25):
        _insert_video(
            conn, f"id{i}", "success", {"douyin": {"i": i}},
            f"2026-06-08T1{i % 10}:00:00" if i < 10 else f"2026-06-08T0{i // 10}:00:00", f"task {i}"
        )
    conn.commit()
    conn.close()

    import ext_api as ext
    with patch.object(ext, "_db_conn", lambda: sqlite3.connect(str(db_path))):
        with ext.app.test_request_context("/api/v2/publish-templates?type=video&page=2&page_size=10"):
            resp = get_publish_templates()
            data = resp.get_json()
            assert data['data']['total'] == 25
            assert len(data['data']['list']) == 10


def _postvideo_roundtrip_db_path():
    """Create a temp DB with publish_tasks (so _ensure_db 看到表就跳过初始化)."""
    return _make_db()


def test_postvideo_stores_account_configs_with_string_key_douyin():
    """/postVideo 收到 type=3 抖音时，存到 account_configs 的 key 必须是 'douyin'。"""
    from app import app

    db_path = _postvideo_roundtrip_db_path()
    fake_platform = MagicMock()
    fake_platform.publish_video = MagicMock(return_value=True)

    with patch("app.get_platform", return_value=fake_platform), \
         patch("app.DB_PATH", db_path), \
         patch("app._get_db_path", return_value=db_path), \
         patch("app._resolve_material_path", side_effect=lambda p: p or "/tmp/v.mp4"):
        client = app.test_client()
        r = client.post("/postVideo", json={
            "type": 3,  # 抖音
            "title": "测试",
            "description": "d",
            "tags": ["a"],
            "fileList": ["/tmp/v.mp4"],
            "accountList": ["/tmp/cookie.json"],
        })
        assert r.status_code == 200, r.get_data(as_text=True)

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT account_configs FROM publish_tasks ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    stored = json.loads(row[0])
    assert "douyin" in stored, f"Expected key 'douyin' in {stored}"
    assert "3" not in stored, f"Expected no numeric '3' key in {stored}"
    assert stored["douyin"]["title"] == "测试"
    assert stored["douyin"]["tags"] == ["a"]
    conn.close()


def test_postvideo_stores_account_configs_with_string_key_xiaohongshu():
    """/postVideo 收到 type=1 小红书时，存到 account_configs 的 key 必须是 'xiaohongshu'。"""
    from app import app

    db_path = _postvideo_roundtrip_db_path()
    fake_platform = MagicMock()
    fake_platform.publish_video = MagicMock(return_value=True)

    with patch("app.get_platform", return_value=fake_platform), \
         patch("app.DB_PATH", db_path), \
         patch("app._get_db_path", return_value=db_path), \
         patch("app._resolve_material_path", side_effect=lambda p: p or "/tmp/v.mp4"):
        client = app.test_client()
        r = client.post("/postVideo", json={
            "type": 1,  # 小红书
            "title": "xhs",
            "description": "",
            "tags": [],
            "fileList": ["/tmp/v.mp4"],
            "accountList": ["/tmp/cookie.json"],
        })
        assert r.status_code == 200, r.get_data(as_text=True)

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT account_configs FROM publish_tasks ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    stored = json.loads(row[0])
    assert "xiaohongshu" in stored, f"Expected key 'xiaohongshu' in {stored}"
    assert "1" not in stored, f"Expected no numeric '1' key in {stored}"
    conn.close()
