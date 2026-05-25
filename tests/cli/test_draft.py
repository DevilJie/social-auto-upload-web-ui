import json
from typer.testing import CliRunner

from cli.main import app
from cli.db import get_connection

runner = CliRunner()


def _create_draft(conn, title="测试草稿", data=None):
    draft_data = json.dumps(data or {"title": title, "platforms": ["douyin"]})
    conn.execute(
        "INSERT INTO drafts (title, draft_data, channels_summary) VALUES (?, ?, ?)",
        (title, draft_data, json.dumps(["抖音"])),
    )
    conn.commit()


def test_drafts_list_empty(temp_data_dir):
    result = runner.invoke(app, ["--data-dir", str(temp_data_dir), "drafts", "list"])
    assert result.exit_code == 0


def test_drafts_list_with_data(temp_data_dir):
    conn = get_connection(temp_data_dir / "db" / "database.db")
    _create_draft(conn, "我的草稿1")
    _create_draft(conn, "我的草稿2")
    conn.close()

    result = runner.invoke(app, ["--data-dir", str(temp_data_dir), "drafts", "list"])
    assert result.exit_code == 0
    assert "我的草稿1" in result.output
    assert "我的草稿2" in result.output


def test_drafts_show(temp_data_dir):
    conn = get_connection(temp_data_dir / "db" / "database.db")
    _create_draft(conn, "草稿详情测试", {"title": "草稿详情测试", "desc": "测试描述"})
    conn.close()

    result = runner.invoke(app, ["--data-dir", str(temp_data_dir), "drafts", "show", "1"])
    assert result.exit_code == 0
    assert "草稿详情测试" in result.output


def test_drafts_delete(temp_data_dir):
    conn = get_connection(temp_data_dir / "db" / "database.db")
    _create_draft(conn, "待删除草稿")
    conn.close()

    result = runner.invoke(
        app, ["--data-dir", str(temp_data_dir), "drafts", "delete", "1", "--yes"]
    )
    assert result.exit_code == 0

    conn = get_connection(temp_data_dir / "db" / "database.db")
    count = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
    conn.close()
    assert count == 0
