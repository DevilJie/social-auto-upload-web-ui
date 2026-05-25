import json
from typer.testing import CliRunner

from cli.main import app
from cli.db import get_connection

runner = CliRunner()


def _insert_account(conn, id, platform_type=3, name="测试用户", status=1):
    conn.execute(
        "INSERT INTO user_info (id, type, filePath, userName, status) VALUES (?, ?, ?, ?, ?)",
        (id, platform_type, "test.json", name, status),
    )
    conn.commit()


def test_publish_no_video(temp_data_dir):
    result = runner.invoke(
        app,
        ["--data-dir", str(temp_data_dir), "publish", "/nonexistent.mp4", "--title", "测试"],
    )
    assert result.exit_code == 1


def test_publish_no_accounts(temp_data_dir):
    video = temp_data_dir / "test.mp4"
    video.write_bytes(b"fake video")

    result = runner.invoke(
        app,
        ["--data-dir", str(temp_data_dir), "publish", str(video), "--title", "测试", "--platforms", "douyin"],
    )
    assert "无有效账号" in result.output or result.exit_code == 1


def test_publish_save_draft(temp_data_dir):
    video = temp_data_dir / "test.mp4"
    video.write_bytes(b"fake video")

    result = runner.invoke(
        app,
        [
            "--data-dir", str(temp_data_dir),
            "publish", str(video),
            "--title", "草稿测试",
            "--platforms", "douyin",
            "--draft",
        ],
    )
    assert result.exit_code == 0

    conn = get_connection(temp_data_dir / "db" / "database.db")
    row = conn.execute("SELECT * FROM drafts WHERE title = '草稿测试'").fetchone()
    conn.close()
    assert row is not None
