import asyncio
import json
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cli.db import get_connection
from cli.output import console, print_success, print_error, print_warning
from cli.platform import resolve_platform, get_platform_name
from cli.state import state


def _parse_accounts_arg(accounts_str: str) -> list[int]:
    if not accounts_str:
        return []
    return [int(a.strip()) for a in accounts_str.split(",") if a.strip()]


def _parse_platforms_arg(platforms_str: str) -> list[int]:
    if not platforms_str:
        return []
    ids = []
    for p in platforms_str.split(","):
        p = p.strip()
        if not p:
            continue
        pid = resolve_platform(p)
        if pid is None:
            print_error(f"未知平台: {p}")
            raise typer.Exit(1)
        ids.append(pid)
    return ids


def _parse_settings(settings_str: str) -> dict:
    if not settings_str:
        return {}
    result = {}
    for pair in settings_str.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _get_target_accounts(platform_ids: list[int], account_ids: list[int]) -> list[dict]:
    conn = get_connection(state.db_path)
    try:
        if account_ids:
            placeholders = ",".join("?" * len(account_ids))
            rows = conn.execute(
                f"SELECT * FROM user_info WHERE id IN ({placeholders}) AND status = 1",
                account_ids,
            ).fetchall()
        elif platform_ids:
            placeholders = ",".join("?" * len(platform_ids))
            rows = conn.execute(
                f"SELECT * FROM user_info WHERE type IN ({placeholders}) AND status = 1",
                platform_ids,
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM user_info WHERE status = 1").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _save_draft(video_path: str, title: str, desc: str, tags: str, platforms: str, schedule: str, settings: str):
    draft_data = json.dumps({
        "video_path": video_path,
        "title": title,
        "desc": desc,
        "tags": tags.split(",") if tags else [],
        "platforms": platforms.split(",") if platforms else [],
        "schedule": schedule,
        "settings": settings,
    }, ensure_ascii=False)

    conn = get_connection(state.db_path)
    try:
        conn.execute(
            "INSERT INTO drafts (title, draft_data, channels_summary, created_at, updated_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (title, draft_data, json.dumps(platforms.split(",") if platforms else [])),
        )
        conn.commit()
    finally:
        conn.close()
    print_success(f"已保存为草稿: {title}")


def do_publish(
    video_path: str, title: str, desc: str, tags: str, cover: str,
    platforms: str, accounts: str, schedule: str, save_draft: bool, settings: str,
) -> None:
    """Core publish logic."""
    video = Path(video_path).resolve()
    if not video.exists():
        print_error(f"视频文件不存在: {video_path}")
        raise typer.Exit(1)

    if save_draft:
        _save_draft(video_path, title, desc, tags, platforms, schedule, settings)
        return

    platform_ids = _parse_platforms_arg(platforms)
    account_ids = _parse_accounts_arg(accounts)

    if not platform_ids and not account_ids:
        print_error("请指定 --platforms 或 --accounts")
        raise typer.Exit(1)

    target_accounts = _get_target_accounts(platform_ids, account_ids)
    if not target_accounts:
        print_warning("无有效账号，请先运行 sau login <platform>")
        raise typer.Exit(1)

    from impl.registry import get_platform
    platform_groups: dict[int, list[dict]] = {}
    for acc in target_accounts:
        pid = acc["type"]
        if platform_ids and pid not in platform_ids:
            continue
        platform_groups.setdefault(pid, []).append(acc)

    if not platform_groups:
        print_warning("无匹配的账号")
        raise typer.Exit(1)

    console.print(f"\n📤 正在发布 [bold]{title}[/bold]\n")
    for pid, accs in platform_groups.items():
        names = ", ".join(a["userName"] for a in accs)
        console.print(f"  {get_platform_name(pid)}: {names}")
    console.print()

    parsed_settings = _parse_settings(settings)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    results = []

    for pid, accs in platform_groups.items():
        platform = get_platform(pid)
        if not platform:
            for acc in accs:
                results.append({"account": acc["userName"], "platform": get_platform_name(pid), "status": "❌", "time": "-", "error": "不支持的平台"})
            continue

        for acc in accs:
            start = time.time()
            try:
                kwargs = {
                    "title": title,
                    "file_path": str(video),
                    "tags": tag_list,
                    "publish_date": schedule or None,
                    "account_file": acc["filePath"],
                    "description": desc,
                    "cover_path": cover or None,
                    **parsed_settings,
                }
                success = asyncio.run(platform.publish_video(**kwargs))
                elapsed = int(time.time() - start)
                if success:
                    results.append({"account": acc["userName"], "platform": get_platform_name(pid), "status": "✅", "time": f"{elapsed}s", "error": ""})
                else:
                    results.append({"account": acc["userName"], "platform": get_platform_name(pid), "status": "❌", "time": f"{elapsed}s", "error": "发布失败"})
            except Exception as e:
                elapsed = int(time.time() - start)
                results.append({"account": acc["userName"], "platform": get_platform_name(pid), "status": "❌", "time": f"{elapsed}s", "error": str(e)[:50]})

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("账号")
    table.add_column("平台")
    table.add_column("状态")
    table.add_column("耗时")
    table.add_column("备注")

    success_count = 0
    for r in results:
        status_style = "green" if r["status"] == "✅" else "red"
        table.add_row(
            r["account"],
            r["platform"],
            f"[{status_style}]{r['status']}[/{status_style}]",
            r["time"],
            r["error"],
        )
        if r["status"] == "✅":
            success_count += 1

    console.print(table)

    fail_count = len(results) - success_count
    if fail_count == 0:
        console.print(f"\n[bold green]发布完成: 全部 {success_count} 个成功[/bold green]")
    else:
        console.print(f"\n[bold yellow]发布完成: {success_count} 成功, {fail_count} 失败[/bold yellow]")


app = typer.Typer(help="发布管理", no_args_is_help=True)
