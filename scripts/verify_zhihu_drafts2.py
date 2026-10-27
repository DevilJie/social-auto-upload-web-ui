# -*- coding: utf-8 -*-
"""查草稿箱: 验证稿是否还在草稿箱(即实际未发表)。"""
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
            "https://zhuanlan.zhihu.com/drafts",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        info = await page.evaluate(
            """() => {
              const t = (document.body.innerText || '')
                .replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
              const out = [];
              for (const kw of ['全功能验证稿', '全设置测试', '千帆同步']) {
                const idx = t.indexOf(kw);
                out.push({kw, found: idx >= 0,
                          ctx: idx >= 0 ? t.slice(Math.max(0, idx - 30),
                            idx + 80).replace(/\\s+/g, ' ') : null});
              }
              return {items: out, head: t.replace(/\\s+/g, ' ').slice(0, 400)};
            }"""
        )
        print(json.dumps(info, ensure_ascii=False, indent=1))
        await page.screenshot(
            path=str(SHOT / "verify5_drafts.png"), full_page=True
        )
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
