# -*- coding: utf-8 -*-
"""验证文章发布页(draft_id=67)渲染无控制台错误。"""
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
        page.on("console", lambda m: errors.append(m.text)
                if m.type in ("error",) else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(
            "http://localhost:5173/#/article-publish?draft_id=67",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        await page.screenshot(
            path=str(SHOT / "verify_draft67.png"), full_page=True
        )
        # 检查知乎面板字段是否渲染
        has_decl = await page.locator("text=创作声明").first.is_visible()
        has_topic = await page.locator("text=文章话题").first.is_visible()
        has_source = await page.locator("text=内容来源").first.is_visible()
        print("创作声明可见:", has_decl)
        print("文章话题可见:", has_topic)
        print("内容来源可见:", has_source)
        print("console errors:", json.dumps(errors[:5], ensure_ascii=False)
              if (errors := [e for e in errors if "favicon" not in e]) else "无")
    finally:
        await browser.close()


if __name__ == "__main__":
    import json
    asyncio.run(main())
