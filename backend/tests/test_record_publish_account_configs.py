"""_record_publish 接受 account_configs 参数并写入 publish_details.account_configs。

注意：_record_publish 在 Task 6 重构后写的是新表 publish_batches + publish_details
（不是旧表 publish_tasks），所以这两个测试必须用新 schema 才能通过。
"""
import json
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _make_db_with_new_schema(db_path):
    """在给定 db_path 建好 publish_batches + publish_details 新表 schema。"""
    import sqlite3
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


def test_record_publish_writes_account_configs():
    """_record_publish 接受 account_configs 形参并 JSON 序列化写入 publish_details.account_configs。"""
    from app import _record_publish
    import sqlite3

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    _make_db_with_new_schema(db_path)

    detail_id = "uuid-1"
    with patch("app.DB_PATH", db_path):
        _record_publish(
            "uuid-1",
            detail_id,
            platform="douyin",
            account_name="测试账号",
            account_id=0,
            video_path="/tmp/v.mp4",
            title="t",
            description="d",
            tags=["a"],
            status="running",
            started_at="2026-06-08T10:00:00",
            account_configs={"douyin": {"title": "per-platform title", "tags": ["x"]}},
        )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT account_configs FROM publish_details WHERE id = ?", (detail_id,)
    ).fetchone()
    stored = json.loads(row[0])
    assert stored == {"douyin": {"title": "per-platform title", "tags": ["x"]}}
    conn.close()


def test_record_publish_default_account_configs():
    """不传 account_configs 时默认写 '{}'。"""
    from app import _record_publish
    import sqlite3

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    _make_db_with_new_schema(db_path)

    detail_id = "uuid-2"
    with patch("app.DB_PATH", db_path):
        _record_publish(
            "uuid-2",
            detail_id,
            platform="douyin",
            account_name="x",
            account_id=0,
            video_path="/v",
            title="t",
            description="",
            tags=[],
            status="running",
            started_at="2026-06-08T10:00:00",
            account_configs={},
        )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT account_configs FROM publish_details WHERE id = ?", (detail_id,)
    ).fetchone()
    assert row[0] == "{}"
    conn.close()
