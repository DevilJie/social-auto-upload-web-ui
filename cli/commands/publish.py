import typer

app = typer.Typer(help="发布管理", no_args_is_help=True)


def do_publish(
    video_path: str, title: str, desc: str, tags: str, cover: str,
    platforms: str, accounts: str, schedule: str, save_draft: bool, settings: str,
) -> None:
    pass
