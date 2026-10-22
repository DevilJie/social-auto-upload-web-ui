# -*- coding: utf-8 -*-
"""从创作中心找内容管理入口,查验证稿状态(已发表/审核中)。"""
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
            "https://www.zhihu.com/creator",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        navs = await page.evaluate(
            """() => [...document.querySelectorAll('a')]
              .map((a) => ({text: (a.innerText || '').trim().slice(0, 15),
                            href: a.getAttribute('href') || ''}))
              .filter((x) => x.text && x.href)"""
        )
        print("creator 导航:", json.dumps(navs, ensure_ascii=False)[:1500])
        # 找内容管理/内容 link
        target = None
        for n in navs:
            if "内容" in n["text"]:
                target = n["href"]
                break
        print("内容管理 href:", target)
        if target:
            url = target if target.startswith("http") else (
                "https://www.zhihu.com" + target
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            await asyncio.sleep(10)
            await page.screenshot(
                path=str(SHOT / "verify3_content.png"), full_page=True
            )
            rows = await page.evaluate(
                """() => {
                  const t = (document.body.innerText || '')
                    .replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
                  const idx = t.indexOf('千帆同步');
                  return {
                    found: idx >= 0,
                    context: idx >= 0 ? t.slice(idx - 40, idx + 120)
                      .replace(/\\s+/g, ' ') : null,
                    sample: t.replace(/\\s+/g, ' ').slice(0, 600),
                  };
                }"""
            )
            print(json.dumps(rows, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
