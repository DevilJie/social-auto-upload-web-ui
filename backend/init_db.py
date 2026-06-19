import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("init_db")

DB_DIR = BASE_DIR / "db"
DB_PATH = DB_DIR / "database.db"


def init_database():
    # 确保 data/ 下的所有必要子目录存在
    for subdir in ["db", "logs", "cookies", "cookiesFile", "uploads", "thumbnails", "upload_chunks"]:
        (BASE_DIR / subdir).mkdir(parents=True, exist_ok=True)

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

    # 阶段二：系统设置表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 草稿箱表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT DEFAULT 'video',
        title TEXT DEFAULT '',
        cover_path TEXT DEFAULT '',
        draft_data TEXT DEFAULT '{}',
        channels_summary TEXT DEFAULT '[]',
        video_duration REAL DEFAULT 0,
        video_file_size INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 图文草稿表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS image_drafts (
        id TEXT PRIMARY KEY,
        image_ids TEXT NOT NULL,
        account_configs TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 图片上传记录表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS image_records (
        id TEXT PRIMARY KEY,
        original_filename TEXT NOT NULL,
        stored_filename TEXT NOT NULL,
        filesize REAL DEFAULT 0,
        width INTEGER DEFAULT 0,
        height INTEGER DEFAULT 0,
        upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 阶段二：发布主记录表（每次"发布"=1 行）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS publish_batches (
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
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_batches_created ON publish_batches(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_batches_status ON publish_batches(status)")

    # 阶段二：发布明细表（每个账号 1 行）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS publish_details (
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
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_details_batch ON publish_details(batch_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_details_status ON publish_details(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_details_platform ON publish_details(platform)")

    # 素材库表
    cursor.execute("""
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
    )
    """)

    # 分片上传会话表（用于大文件分片上传 + 断点续传）
    cursor.execute("""
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
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS upload_chunks (
        upload_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        chunk_size INTEGER NOT NULL,
        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (upload_id, chunk_index),
        FOREIGN KEY (upload_id) REFERENCES upload_sessions(upload_id) ON DELETE CASCADE
    )
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_upload_sessions_status
    ON upload_sessions(status, updated_at)
    """)

    # 标签表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        color TEXT DEFAULT '#8b5cf6',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 账号-标签关联表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS account_tags (
        account_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        PRIMARY KEY (account_id, tag_id),
        FOREIGN KEY (account_id) REFERENCES user_info(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
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

    # image_drafts 添加 draft_data 列（支持完整状态存储）
    try:
        cursor.execute('ALTER TABLE image_drafts ADD COLUMN draft_data TEXT DEFAULT "{}"')
        logger.info("已添加 image_drafts.draft_data 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    # materials 添加 thumbnail_path 列
    try:
        cursor.execute('ALTER TABLE materials ADD COLUMN thumbnail_path TEXT DEFAULT ""')
        logger.info("已添加 materials.thumbnail_path 列")
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 草稿批量发布用：溯源到草稿
    try:
        cursor.execute("ALTER TABLE publish_batches ADD COLUMN source TEXT NOT NULL DEFAULT ''")
        logger.info("已添加 publish_batches.source 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    try:
        cursor.execute("ALTER TABLE publish_batches ADD COLUMN draft_id INTEGER NOT NULL DEFAULT 0")
        logger.info("已添加 publish_batches.draft_id 列")
    except sqlite3.OperationalError:
        pass  # 列已存在
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_batches_draft ON publish_batches(source, draft_id)")
        logger.info("已创建 idx_publish_batches_draft 索引")
    except sqlite3.OperationalError:
        pass  # 索引已存在

    # 确保 tags 表存在（幂等）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '#8b5cf6',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_tags (
            account_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (account_id, tag_id),
            FOREIGN KEY (account_id) REFERENCES user_info(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_database()
    migrate_database()
