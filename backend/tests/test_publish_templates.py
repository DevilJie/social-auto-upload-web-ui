"""GET /api/v2/publish-templates 端点测试。"""
import json
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _open_test_conn(db_path):
    """镜像 production `_db_conn`：返回 row_factory=Row 的连接（但不跑 _ensure_tables）。"""
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


def _make_db():
    """创建一个临时 SQLite + 完整 publish_batches + publish_details schema，返回 db_path。

    注：postVideo 写路径相关测试（test_postvideo_*）单独在文件末尾的
    _postvideo_roundtrip_db_path() 里用旧表 schema，因为 _record_publish 仍写旧表
    （Task 6 会重构 /postVideo 写路径，届时这些 fixture 一并迁移到新表）。
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
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
        CREATE TABLE materials (
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
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_video_batch(conn, batch_id, status, account_configs_per_platform, created_at='2026-06-08T10:00:00', title='t', cover_material_id=None):
    """插 1 个 video batch + N 个 publish_details（每个 platform 一行）。"""
    conn.execute(
        """INSERT INTO publish_batches
           (id, type, title, status, account_count, success_count, failed_count,
            landscape_cover_material_id, created_at)
           VALUES (?, 'video', ?, ?, ?, ?, 0, ?, ?)""",
        (batch_id, title, status, len(account_configs_per_platform),
         sum(1 for _ in account_configs_per_platform) if status == 'success' else 0,
         cover_material_id or '', created_at)
    )
    for platform, cfg in account_configs_per_platform.items():
        conn.execute(
            """INSERT INTO publish_details
               (id, batch_id, account_name, platform, account_configs, status)
               VALUES (?, ?, ?, ?, ?, 'success')""",
            (str(uuid.uuid4()), batch_id, f"acc-{platform}", platform,
             json.dumps(cfg, ensure_ascii=False))
        )


def test_video_templates_filters_success_and_nonempty():
    """只返回 status=success 且有 detail 带非空 account_configs 的 batch。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _insert_video_batch(conn, "1", "success", {"douyin": {"title": "ok"}}, "2026-06-08T10:00:00", "task 1")
    _insert_video_batch(conn, "2", "success", {}, "2026-06-08T09:00:00", "task 2")  # 空 configs
    _insert_video_batch(conn, "3", "failed", {"douyin": {"title": "bad"}}, "2026-06-08T08:00:00", "task 3")
    _insert_video_batch(conn, "4", "success", {"douyin": {"title": "ok2"}}, "2026-06-08T07:00:00", "task 4")
    conn.commit()
    conn.close()

    import ext_api as ext
    with patch.object(ext, "_db_conn", lambda: _open_test_conn(db_path)):
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
    # 先插一张 material 让 cover_material_id 能解析
    conn.execute(
        "INSERT INTO materials (id, original_filename, stored_path, file_type, mime_type, file_size, storage_type) "
        "VALUES ('mat-thumb-1', 'thumb.png', 'thumbs/2026/06/08/thumb.png', 'image', 'image/png', 100, 'local')"
    )
    _insert_video_batch(
        conn, "1", "success",
        {"douyin": {"title": "ok"}, "xiaohongshu": {"title": "xhs"}},
        "2026-06-08T10:00:00", "My Title", cover_material_id="mat-thumb-1"
    )
    conn.commit()
    conn.close()

    import ext_api as ext
    with patch.object(ext, "_db_conn", lambda: _open_test_conn(db_path)):
        with ext.app.test_request_context("/api/v2/publish-templates?type=video"):
            resp = get_publish_templates()
            data = resp.get_json()
            item = data['data']['list'][0]
            assert item['type'] == 'video'
            assert item['title'] == 'My Title'
            assert item['thumbnail_path'] == 'thumbs/2026/06/08/thumb.png'
            # account_configs 取第一个 detail 的（按 created_at ASC），是该 platform 的单条配置
            assert item['account_configs'] == {"title": "ok"}
            platforms = [c['platform'] for c in item['channels']]
            assert set(platforms) == {'douyin', 'xiaohongshu'}


def test_image_templates_returns_image_with_first_image_id():
    """图文返回 first_image_id 和 account_configs。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    # 1 个 image batch + 2 个 detail
    conn.execute(
        """INSERT INTO publish_batches
           (id, type, title, status, account_count, success_count, failed_count,
            image_material_ids, created_at)
           VALUES ('img-batch-1', 'image', 'img title', 'success', 2, 2, 0,
                   '["img-uuid-1", "img-uuid-2"]', '2026-06-08T10:00:00')"""
    )
    conn.execute(
        """INSERT INTO publish_details
           (id, batch_id, account_id, account_name, platform, account_configs, status)
           VALUES (?, ?, ?, ?, ?, ?, 'success')""",
        (str(uuid.uuid4()), 'img-batch-1', 2, 'douyin-acc', 'douyin',
         json.dumps({"title": "img title", "description": "d", "account_id": 2, "platform": "douyin"}, ensure_ascii=False))
    )
    conn.execute(
        """INSERT INTO publish_details
           (id, batch_id, account_id, account_name, platform, account_configs, status)
           VALUES (?, ?, ?, ?, ?, ?, 'success')""",
        (str(uuid.uuid4()), 'img-batch-1', 3, 'xhs-acc', 'xiaohongshu',
         json.dumps({"title": "xhs", "description": "d2", "account_id": 3, "platform": "xiaohongshu"}, ensure_ascii=False))
    )
    conn.commit()
    conn.close()

    import ext_api as ext
    with patch.object(ext, "_db_conn", lambda: _open_test_conn(db_path)):
        with ext.app.test_request_context("/api/v2/publish-templates?type=image"):
            resp = get_publish_templates()
            data = resp.get_json()
            item = data['data']['list'][0]
            assert item['type'] == 'image'
            assert item['first_image_id'] == 'img-uuid-1'
            assert item['title'] == 'img title'
            # 第一个 detail 的 account_configs
            assert isinstance(item['account_configs'], dict)
            assert item['account_configs'].get('title') == 'img title'
            # channels 列表含两个 platform
            platforms = [c['platform'] for c in item['channels']]
            assert set(platforms) == {'douyin', 'xiaohongshu'}


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
        _insert_video_batch(
            conn, f"id{i}", "success", {"douyin": {"i": i}},
            f"2026-06-08T10:{i:02d}:00", f"task {i}"
        )
    conn.commit()
    conn.close()

    import ext_api as ext
    with patch.object(ext, "_db_conn", lambda: _open_test_conn(db_path)):
        with ext.app.test_request_context("/api/v2/publish-templates?type=video&page=2&page_size=10"):
            resp = get_publish_templates()
            data = resp.get_json()
            assert data['data']['total'] == 25
            assert len(data['data']['list']) == 10


def _postvideo_roundtrip_db_path():
    """Create a temp DB with new publish_batches + publish_details schema (Task 6).

    之前 /postVideo → _record_publish 写旧 publish_tasks 表；Task 6 重构后写到新表。
    这些 roundtrip 测试现在用新 schema，断言改查 publish_details。
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
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
    return db_path


def test_postvideo_stores_account_configs_with_string_key_douyin():
    """/postVideo 收到 type=3 抖音时，platform 列存中文 '抖音'，account_configs JSON 不含数字 '3'。"""
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
        "SELECT platform, account_configs FROM publish_details ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "抖音", f"Expected platform='抖音', got {row[0]!r}"
    stored = json.loads(row[1])
    assert "3" not in stored, f"Expected no numeric '3' key in {stored}"
    assert stored["title"] == "测试"
    assert stored["tags"] == ["a"]
    conn.close()


def test_postvideo_stores_account_configs_with_string_key_xiaohongshu():
    """/postVideo 收到 type=1 小红书时，platform 列存中文 '小红书'，account_configs JSON 不含数字 '1'。"""
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
        "SELECT platform, account_configs FROM publish_details ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "小红书", f"Expected platform='小红书', got {row[0]!r}"
    stored = json.loads(row[1])
    assert "1" not in stored, f"Expected no numeric '1' key in {stored}"
    conn.close()
