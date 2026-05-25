import sqlite3
from pathlib import Path

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS user_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type INTEGER NOT NULL,
    filePath TEXT NOT NULL,
    userName TEXT NOT NULL,
    status INTEGER DEFAULT 0,
    avatar TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS file_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    filesize REAL,
    upload_time DATETIME,
    file_path TEXT
);
CREATE TABLE IF NOT EXISTS publish_tasks (
    id TEXT PRIMARY KEY,
    platform TEXT,
    account_name TEXT,
    video_path TEXT,
    title TEXT,
    description TEXT,
    tags TEXT,
    status TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    publish_url TEXT,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS publish_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    level TEXT,
    message TEXT,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    cover_path TEXT,
    draft_data TEXT,
    channels_summary TEXT,
    video_duration REAL DEFAULT 0,
    video_file_size INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db(db_path: Path) -> None:
    conn = get_connection(db_path)
    conn.executescript(_CREATE_TABLES_SQL)
    conn.close()
