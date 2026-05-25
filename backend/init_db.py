import logging
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from conf import BASE_DIR

logger = logging.getLogger(__name__)

DB_DIR = BASE_DIR / "db"
DB_PATH = DB_DIR / "database.db"


def init_database():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 原始表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type INTEGER NOT NULL,
        filePath TEXT NOT NULL,
        userName TEXT NOT NULL,
        status INTEGER DEFAULT 0,
        avatar TEXT DEFAULT ''
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS file_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        filesize REAL,
        upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        file_path TEXT
    )
    """)

    # 阶段二：发布任务表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS publish_tasks (
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
        finished_at TIMESTAMP
    )
    """)

    # 阶段二：发布日志表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS publish_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        level TEXT DEFAULT 'info',
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (task_id) REFERENCES publish_tasks(id)
    )
    """)

    # 阶段二：系统设置表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def migrate_database():
    """增量迁移 — 添加新列（幂等）"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # user_info 添加 avatar 列
    try:
        cursor.execute('ALTER TABLE user_info ADD COLUMN avatar TEXT DEFAULT ""')
        logger.info("已添加 avatar 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    # publish_tasks 添加 thumbnail_path 列
    try:
        cursor.execute('ALTER TABLE publish_tasks ADD COLUMN thumbnail_path TEXT DEFAULT ""')
        logger.info("已添加 thumbnail_path 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_database()
    migrate_database()
