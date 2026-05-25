from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_help_shows_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "login" in result.output
    assert "publish" in result.output
    assert "config" in result.output
    assert "accounts" in result.output
    assert "materials" in result.output
    assert "drafts" in result.output


def test_full_workflow_config_init(tmp_path):
    data_dir = tmp_path / "integration-data"

    # Init
    result = runner.invoke(app, ["--data-dir", str(data_dir), "config", "init"])
    assert result.exit_code == 0
    assert (data_dir / "db" / "database.db").exists()

    # Show config
    result = runner.invoke(app, ["--data-dir", str(data_dir), "config", "show"])
    assert result.exit_code == 0

    # List empty accounts
    result = runner.invoke(app, ["--data-dir", str(data_dir), "accounts", "list"])
    assert result.exit_code == 0

    # List empty materials
    result = runner.invoke(app, ["--data-dir", str(data_dir), "materials", "list"])
    assert result.exit_code == 0

    # List empty drafts
    result = runner.invoke(app, ["--data-dir", str(data_dir), "drafts", "list"])
    assert result.exit_code == 0
