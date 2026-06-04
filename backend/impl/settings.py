"""
Settings reader — all settings stored in SQLite `settings` table.
"""

import json
import sqlite3
from datetime import datetime

from conf import BASE_DIR

DB_PATH = BASE_DIR / "db" / "database.db"


def _db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def read_settings() -> dict:
    try:
        conn = _db_conn()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        result = {}
        for row in rows:
            val = row["value"]
            try:
                result[row["key"]] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = val
        return result
    except Exception:
        return {}


def write_setting(key: str, value):
    conn = _db_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        (key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_proxy_url() -> str | None:
    val = read_settings().get("proxyUrl")
    return val if val else None


def get_storage_config() -> dict:
    """读取存储配置。总是返回 dict（损坏值兜底为默认 local）。"""
    cfg = read_settings().get("storage")
    if not isinstance(cfg, dict):
        return {"type": "local", "s3": {}}
    return cfg
