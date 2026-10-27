# -*- coding: utf-8 -*-
"""验证已发表文章的详情页: 封面/话题/内容来源/创作声明 展示。"""
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
        # 创作中心内容管理
        await page.goto(
            "https://www.zhihu.com/creator/content",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)
        await page.screenshot(
            path=str(SHOT / "verify_creator_content.png"), full_page=True
        )
        # 找验证稿链接
        link = await page.evaluate(
            """() => {
              const els = [...document.querySelectorAll('a')];
              for (const a of els) {
                if ((a.innerText || '').includes('千帆同步知乎全功能验证稿')) {
                  return a.href;
                }
                const parent = a.closest('[class*=Item], tr, li');
                if (parent && (parent.innerText || '')
                    .includes('千帆同步知乎全功能验证稿')) {
                  const inner = parent.querySelector('a[href*="/p/"]');
                  if (inner) return inner.href;
                }
              }
              return null;
            }"""
        )
        print("文章链接:", link)
        if not link:
            # 兜底: 直接搜个人主页最新文章
            print("未在内容管理找到,尝试草稿页 URL 形态")
            return
        await page.goto(link, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(8)
        await page.screenshot(
            path=str(SHOT / "verify_article_detail.png"), full_page=True
        )
        meta = await page.evaluate(
            """() => {
              const t = (document.body.innerText || '')
                .replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
              const pick = (kw) => {
                const idx = t.indexOf(kw);
                return idx >= 0 ? t.slice(Math.max(0, idx - 20), idx + 60)
                  .replace(/\\s+/g, ' ') : null;
              };
              return {
                title: (document.title || '').slice(0, 60),
                topics: pick('软件测试'),
                source: pick('来源于'),
                decl: pick('虚构创作'),
                hasCover: !!document.querySelector(
                  '.Post-SideActions img, img[alt*="封面"], '
                  + '.Post-Main img[src*="zhimg"]'),
                url: location.href,
              };
            }"""
        )
        print(json.dumps(meta, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
