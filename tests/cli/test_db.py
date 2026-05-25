import sqlite3
from cli.db import get_connection, ensure_db


def test_get_connection_creates_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    assert conn is not None
    conn.close()


def test_ensure_db_creates_tables(temp_data_dir):
    db_path = temp_data_dir / "db" / "database.db"
    ensure_db(db_path)

    conn = sqlite3.connect(str(db_path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row[0] for row in tables}
    assert "user_info" in table_names
    assert "file_records" in table_names
    assert "drafts" in table_names
    conn.close()


def test_ensure_db_idempotent(temp_data_dir):
    db_path = temp_data_dir / "db" / "database.db"
    ensure_db(db_path)
    ensure_db(db_path)

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM user_info").fetchone()[0]
    assert count == 0
    conn.close()
