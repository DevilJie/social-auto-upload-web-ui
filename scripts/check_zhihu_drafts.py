# -*- coding: utf-8 -*-
"""查知乎草稿箱,验证 dry-run 文章已自动保存。"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.goto(
            "https://zhuanlan.zhihu.com/drafts",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        items = await page.evaluate(
            """() => {
              const out = [];
              for (const el of document.querySelectorAll(
                  '.List-item, [class*=ContentItem], article')) {
                const t = (el.innerText || '').trim().replace(/\\s+/g, ' ');
                if (t && t.length > 5 && t.length < 150 && !out.includes(t)) {
                  out.push(t.slice(0, 120));
                }
              }
              return out.slice(0, 6);
            }"""
        )
        print(json.dumps(items, ensure_ascii=False, indent=1))
        await page.screenshot(
            path=str(REPO / "data" / "screenshots" / "zhihu_drafts.png")
        )
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
