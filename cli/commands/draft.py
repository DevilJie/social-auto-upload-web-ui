import json

import typer

from cli.db import get_connection
from cli.output import console, print_success, print_error, create_table
from cli.state import state

app = typer.Typer(help="草稿箱", no_args_is_help=True)


@app.command("list")
def drafts_list():
    """列出所有草稿"""
    conn = get_connection(state.db_path)
    try:
        rows = conn.execute("SELECT * FROM drafts ORDER BY updated_at DESC").fetchall()
    finally:
        conn.close()

    if not rows:
        console.print("[dim]暂无草稿。[/dim]")
        return

    table = create_table("草稿箱", ["ID", "标题", "渠道", "更新时间"])
    for row in rows:
        channels = row["channels_summary"] or ""
        try:
            channel_list = json.loads(channels)
            channels_display = ", ".join(channel_list) if isinstance(channel_list, list) else channels
        except (json.JSONDecodeError, TypeError):
            channels_display = channels
        table.add_row(
            str(row["id"]),
            row["title"] or "(无标题)",
            channels_display,
            row["updated_at"] or "",
        )

    console.print(table)


@app.command("show")
def drafts_show(
    draft_id: int = typer.Argument(help="草稿 ID"),
):
    """查看草稿详情"""
    conn = get_connection(state.db_path)
    try:
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        print_error(f"草稿不存在: {draft_id}")
        raise typer.Exit(1)

    console.print(f"[bold]标题:[/bold] {row['title']}")
    console.print(f"[bold]封面:[/bold] {row['cover_path'] or '无'}")
    console.print(f"[bold]创建时间:[/bold] {row['created_at']}")
    console.print(f"[bold]更新时间:[/bold] {row['updated_at']}")

    if row["channels_summary"]:
        try:
            channels = json.loads(row["channels_summary"])
            console.print(f"[bold]发布渠道:[/bold] {', '.join(channels) if isinstance(channels, list) else channels}")
        except (json.JSONDecodeError, TypeError):
            console.print(f"[bold]发布渠道:[/bold] {row['channels_summary']}")

    if row["draft_data"]:
        try:
            data = json.loads(row["draft_data"])
            console.print(f"\n[bold]完整配置:[/bold]")
            console.print_json(json.dumps(data, indent=2, ensure_ascii=False))
        except (json.JSONDecodeError, TypeError):
            console.print(f"\n[bold]原始数据:[/bold] {row['draft_data'][:500]}")


@app.command("publish")
def drafts_publish(
    draft_id: int = typer.Argument(help="草稿 ID"),
):
    """从草稿发布"""
    conn = get_connection(state.db_path)
    try:
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        print_error(f"草稿不存在: {draft_id}")
        raise typer.Exit(1)

    try:
        draft_data = json.loads(row["draft_data"])
    except (json.JSONDecodeError, TypeError):
        print_error("草稿数据格式错误")
        raise typer.Exit(1)

    from cli.commands.publish import do_publish
    video_path = draft_data.get("video_path", "")
    title = draft_data.get("title", row["title"])
    desc = draft_data.get("desc", "")
    tags = ",".join(draft_data.get("tags", []))
    cover = draft_data.get("cover", "")
    platforms = ",".join(draft_data.get("platforms", []))
    accounts = ",".join(str(a) for a in draft_data.get("account_ids", []))
    schedule = draft_data.get("schedule", "")
    settings = ""

    do_publish(video_path, title, desc, tags, cover, platforms, accounts, schedule, False, settings)


@app.command("delete")
def drafts_delete(
    draft_id: int = typer.Argument(help="草稿 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """删除草稿"""
    conn = get_connection(state.db_path)
    try:
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        print_error(f"草稿不存在: {draft_id}")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"确定删除草稿「{row['title']}」？")
        if not confirm:
            raise typer.Abort()

    conn = get_connection(state.db_path)
    try:
        conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
        conn.commit()
    finally:
        conn.close()

    print_success(f"已删除草稿: {row['title']}")
