# -*- coding: utf-8 -*-
"""验证已发表文章 v2: 个人主页 → 文章 tab → 打开验证稿 → 检查详情。"""
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
        token = await page.evaluate(
            """() => {
              const a = document.querySelector(
                'a[href*="/people/"]');
              if (a) {
                const m = a.href.match(/people\\/([^/?#]+)/);
                if (m) return m[1];
              }
              return null;
            }"""
        )
        print("url_token:", token)
        if not token:
            return
        await page.goto(
            f"https://www.zhihu.com/people/{token}/posts",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        await page.screenshot(
            path=str(SHOT / "verify2_posts.png"), full_page=True
        )
        link = await page.evaluate(
            """() => {
              for (const a of document.querySelectorAll('a')) {
                const t = (a.innerText || '').trim();
                if (t.includes('千帆同步知乎全功能验证稿')
                    && a.href.includes('/p/')) {
                  return a.href;
                }
              }
              // List-item 内层链接
              for (const item of document.querySelectorAll(
                  '.List-item, [class*=ContentItem]')) {
                if ((item.innerText || '')
                    .includes('千帆同步知乎全功能验证稿')) {
                  const a = item.querySelector('a[href*="/p/"]');
                  if (a) return a.href;
                }
              }
              return null;
            }"""
        )
        print("文章链接:", link)
        if not link:
            return
        await page.goto(link, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(8)
        await page.screenshot(
            path=str(SHOT / "verify2_article.png"), full_page=True
        )
        meta = await page.evaluate(
            """() => {
              const t = (document.body.innerText || '')
                .replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
              const pick = (kw) => {
                const idx = t.indexOf(kw);
                return idx >= 0 ? t.slice(Math.max(0, idx - 15), idx + 50)
                  .replace(/\\s+/g, ' ') : null;
              };
              return {
                title: (document.title || '').slice(0, 60),
                topics: pick('软件测试'),
                source: pick('来源于'),
                decl: pick('虚构创作'),
                imgCount: document.querySelectorAll(
                  '.Post-Main img, article img').length,
                url: location.href,
              };
            }"""
        )
        print(json.dumps(meta, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
