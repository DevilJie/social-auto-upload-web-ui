# -*- coding: utf-8 -*-
"""诊断草稿删除确认弹窗结构。"""
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
        await page.goto(
            "https://zhuanlan.zhihu.com/drafts",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        clicked = await page.evaluate(
            """() => {
              const del = [...document.querySelectorAll(
                'button.ColumnDraftItem-deleteButton')][0];
              if (!del) return false;
              del.click();
              return true;
            }"""
        )
        print("点了删除:", clicked)
        await asyncio.sleep(2)
        await page.screenshot(
            path=str(SHOT / "del_confirm.png"), full_page=True
        )
        # dump 全页新出现的浮层
        info = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const cands = [...document.querySelectorAll(
                  '[class*=Modal], [class*=Popover], [class*=popup], '
                + '[class*=Dialog], [class*=confirm]')]
                .filter(vis)
                .map((el) => ({
                  cls: String(el.className).slice(0, 70),
                  text: (el.innerText || '').replace(/\\s+/g, ' ')
                    .slice(0, 120),
                  buttons: [...el.querySelectorAll('button')]
                    .map((b) => ({t: (b.innerText || '').trim(),
                                  cls: String(b.className).slice(0, 40)}))
                    .slice(0, 6),
                }));
              return cands.slice(0, 8);
            }"""
        )
        print(json.dumps(info, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
