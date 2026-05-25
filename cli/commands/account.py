import typer

from cli.db import get_connection
from cli.output import console, print_success, print_error, create_table
from cli.platform import get_platform_name
from cli.state import state

app = typer.Typer(help="账号管理", no_args_is_help=True)


@app.command("list")
def accounts_list():
    """列出所有账号"""
    conn = get_connection(state.db_path)
    try:
        rows = conn.execute("SELECT * FROM user_info ORDER BY id").fetchall()
    finally:
        conn.close()

    if not rows:
        console.print("[dim]暂无账号。运行 sau login <platform> 添加账号。[/dim]")
        return

    table = create_table("账号列表", ["ID", "平台", "昵称", "状态"])
    for row in rows:
        platform_name = get_platform_name(row["type"])
        status_text = "[green]✅ 有效[/green]" if row["status"] == 1 else "[red]❌ 过期[/red]"
        table.add_row(str(row["id"]), platform_name, row["userName"], status_text)

    console.print(table)


@app.command("check")
def accounts_check(
    account_id: int = typer.Argument(help="账号 ID"),
):
    """检查账号 Cookie 有效性"""
    conn = get_connection(state.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM user_info WHERE id = ?", (account_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        print_error(f"账号不存在: {account_id}")
        raise typer.Exit(1)

    import asyncio
    from impl.registry import get_platform

    platform = get_platform(row["type"])
    if not platform:
        print_error(f"不支持的平台类型: {row['type']}")
        raise typer.Exit(1)

    console.print(f"正在检查 [bold]{row['userName']}[/bold] ({get_platform_name(row['type'])})...")

    valid = asyncio.run(platform.check_cookie(row["filePath"]))

    conn = get_connection(state.db_path)
    try:
        conn.execute(
            "UPDATE user_info SET status = ? WHERE id = ?",
            (1 if valid else 0, account_id),
        )
        conn.commit()
    finally:
        conn.close()

    if valid:
        print_success(f"Cookie 有效: {row['userName']}")
    else:
        print_error(f"Cookie 已过期: {row['userName']}，请重新登录")


@app.command("sync")
def accounts_sync(
    account_id: int = typer.Argument(help="账号 ID"),
):
    """同步账号昵称和头像"""
    conn = get_connection(state.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM user_info WHERE id = ?", (account_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        print_error(f"账号不存在: {account_id}")
        raise typer.Exit(1)

    import asyncio
    from impl.registry import get_platform

    platform = get_platform(row["type"])
    if not platform:
        print_error(f"不支持的平台类型: {row['type']}")
        raise typer.Exit(1)

    console.print(f"正在同步 [bold]{row['userName']}[/bold]...")
    name, avatar = asyncio.run(platform.sync_profile(row["filePath"]))

    if name:
        conn = get_connection(state.db_path)
        try:
            conn.execute(
                "UPDATE user_info SET userName = ?, avatar = ? WHERE id = ?",
                (name, avatar or "", account_id),
            )
            conn.commit()
        finally:
            conn.close()
        print_success(f"已同步: {name}")
    else:
        print_error("同步失败，Cookie 可能已过期")


@app.command("delete")
def accounts_delete(
    account_id: int = typer.Argument(help="账号 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """删除账号"""
    conn = get_connection(state.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM user_info WHERE id = ?", (account_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        print_error(f"账号不存在: {account_id}")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(
            f"确定删除账号 {row['userName']} ({get_platform_name(row['type'])})？"
        )
        if not confirm:
            raise typer.Abort()

    cookie_path = state.cookies_dir / row["filePath"]
    if cookie_path.exists():
        cookie_path.unlink()

    conn = get_connection(state.db_path)
    try:
        conn.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
        conn.commit()
    finally:
        conn.close()

    print_success(f"已删除账号: {row['userName']}")
