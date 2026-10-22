# -*- coding: utf-8 -*-
"""验证 draft67: 1600x900 视口 + 选中知乎账号,检查面板字段。"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

SHOT = REPO / "data" / "screenshots"


async def main() -> None:
    browser = await create_browser(headless=True)
    errors = []
    try:
        ctx = await create_context(browser)
        page = await ctx.new_page()
        await page.set_viewport_size({"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(
            "http://localhost:5173/#/article-publish?draft_id=67",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        # 点击知乎账号(哈罗)选中
        try:
            await page.locator("text=哈罗").first.click(timeout=8000)
            await asyncio.sleep(2)
        except Exception as e:
            print("点账号失败:", str(e)[:100])
        await page.screenshot(
            path=str(SHOT / "verify_draft67_wide.png"), full_page=True
        )
        has_decl = await page.locator("text=创作声明").first.is_visible()
        has_topic = await page.locator("text=文章话题").first.is_visible()
        has_source = await page.locator("text=内容来源").first.is_visible()
        has_q = await page.locator("text=投稿至问题").first.is_visible()
        print("创作声明:", has_decl, "| 文章话题:", has_topic,
              "| 内容来源:", has_source, "| 投稿至问题:", has_q)
        print("pageerrors:", errors[:3] or "无")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
