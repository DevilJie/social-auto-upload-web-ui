from typer.testing import CliRunner

from cli.main import app
from cli.db import get_connection

runner = CliRunner()


def _insert_account(conn, id, platform_type=3, name="测试用户", status=1, filepath="test.json"):
    conn.execute(
        "INSERT INTO user_info (id, type, filePath, userName, status, avatar) VALUES (?, ?, ?, ?, ?, '')",
        (id, platform_type, filepath, name, status),
    )
    conn.commit()


def test_accounts_list_empty(temp_data_dir):
    result = runner.invoke(app, ["--data-dir", str(temp_data_dir), "accounts", "list"])
    assert result.exit_code == 0


def test_accounts_list_with_data(temp_data_dir):
    conn = get_connection(temp_data_dir / "db" / "database.db")
    _insert_account(conn, 1, 3, "用户A", 1)
    _insert_account(conn, 2, 1, "用户B", 0)
    conn.close()

    result = runner.invoke(app, ["--data-dir", str(temp_data_dir), "accounts", "list"])
    assert result.exit_code == 0
    assert "用户A" in result.output
    assert "用户B" in result.output


def test_accounts_delete(temp_data_dir):
    conn = get_connection(temp_data_dir / "db" / "database.db")
    _insert_account(conn, 1, 3, "用户A", 1)
    conn.close()

    result = runner.invoke(
        app, ["--data-dir", str(temp_data_dir), "accounts", "delete", "1", "--yes"]
    )
    assert result.exit_code == 0

    conn = get_connection(temp_data_dir / "db" / "database.db")
    count = conn.execute("SELECT COUNT(*) FROM user_info").fetchone()[0]
    conn.close()
    assert count == 0


def test_accounts_delete_nonexistent(temp_data_dir):
    result = runner.invoke(
        app, ["--data-dir", str(temp_data_dir), "accounts", "delete", "999", "--yes"]
    )
    assert result.exit_code == 1
