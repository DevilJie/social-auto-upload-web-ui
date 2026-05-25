import sys
from pathlib import Path

import typer

# Add backend/ to sys.path so backend modules can be imported (dev mode only)
_BACKEND_DIR = Path(__file__).parent.parent / "backend"
if _BACKEND_DIR.is_dir() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from cli.state import state
from cli.commands import config, account, material, draft

app = typer.Typer(
    name="sau",
    help="社交媒体自动上传 CLI 工具",
    no_args_is_help=True,
)


@app.callback()
def main(
    data_dir: str = typer.Option(
        None,
        "--data-dir",
        help="数据目录路径",
        envvar="SAU_DATA_DIR",
    ),
):
    """社交媒体自动上传 CLI"""
    state.resolve_data_dir(data_dir)


@app.command("login")
def login_cmd(
    platform: str = typer.Argument(help="平台名称 (如 douyin, xiaohongshu)"),
):
    """扫码登录平台账号"""
    from cli.commands.login import do_login
    do_login(platform)


@app.command("publish")
def publish_cmd(
    video_path: str = typer.Argument(help="视频文件路径"),
    title: str = typer.Option(..., "--title", "-t", help="视频标题"),
    desc: str = typer.Option("", "--desc", "-d", help="视频描述"),
    tags: str = typer.Option("", "--tags", help="标签，逗号分隔"),
    cover: str = typer.Option("", "--cover", help="封面图路径"),
    platforms: str = typer.Option("", "--platforms", "-p", help="目标平台，逗号分隔"),
    accounts: str = typer.Option("", "--accounts", "-a", help="指定账号ID，逗号分隔"),
    schedule: str = typer.Option("", "--schedule", "-s", help="定时发布 YYYY-MM-DD HH:MM"),
    save_draft: bool = typer.Option(False, "--draft", help="保存为草稿"),
    settings: str = typer.Option("", "--settings", help="平台设置 key=value,key=value"),
):
    """发布视频到社交平台"""
    from cli.commands.publish import do_publish
    do_publish(video_path, title, desc, tags, cover, platforms, accounts, schedule, save_draft, settings)


app.add_typer(config.app, name="config")
app.add_typer(account.app, name="accounts")
app.add_typer(material.app, name="materials")
app.add_typer(draft.app, name="drafts")
