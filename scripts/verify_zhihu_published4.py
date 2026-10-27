# -*- coding: utf-8 -*-
"""内容管理 → 文章 tab,查验证稿状态。"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"
SHOT = REPO / "data" / "screenshots"


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.set_viewport_size({"width": 1600, "height": 900})
        await page.goto(
            "https://www.zhihu.com/creator/manage/creation",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        # 点「文章」tab
        tab = page.locator(
            '[role="tab"]:has-text("文章"), button:has-text("文章"), '
            'a:has-text("文章")'
        ).first
        await tab.click(timeout=8000)
        await asyncio.sleep(5)
        await page.screenshot(
            path=str(SHOT / "verify4_articles.png"), full_page=True
        )
        info = await page.evaluate(
            """() => {
              const t = (document.body.innerText || '')
                .replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
              const idx = t.indexOf('千帆同步');
              return {
                found: idx >= 0,
                context: idx >= 0 ? t.slice(Math.max(0, idx - 60), idx + 150)
                  .replace(/\\s+/g, ' ') : null,
                tail: t.replace(/\\s+/g, ' ').slice(0, 500),
              };
            }"""
        )
        print(json.dumps(info, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
