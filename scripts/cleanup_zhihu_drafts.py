# -*- coding: utf-8 -*-
"""清理知乎草稿箱里的测试草稿(标题含「千帆同步」)。"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"


async def main() -> None:
    browser = await create_browser(headless=True)
    deleted = 0
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.goto(
            "https://zhuanlan.zhihu.com/drafts",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)

        for _round in range(5):
            clicked = await page.evaluate(
                """() => {
                  const cards = [...document.querySelectorAll(
                      '.List-item, [class*=ContentItem], article')];
                  for (const card of cards) {
                    const t = (card.innerText || '').trim();
                    if (!t.includes('千帆同步')) continue;
                    const del = [...card.querySelectorAll('a, button, span')]
                      .find((el) => (el.innerText || '').trim() === '删除');
                    if (del) { del.click(); return true; }
                  }
                  return false;
                }"""
            )
            if not clicked:
                break
            await asyncio.sleep(2)
            # 确认弹窗(知乎删除草稿可能无确认,容错点「确定」)
            await page.evaluate(
                """() => {
                  for (const b of document.querySelectorAll('button')) {
                    if ((b.innerText || '').trim() === '确定') { b.click(); return; }
                  }
                }"""
            )
            await asyncio.sleep(2.5)
            deleted += 1
        print(f"deleted {deleted} draft(s)")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
