# -*- coding: utf-8 -*-
"""逐步诊断: 点删除 → 截图 → 点确认 → 截图 → 验证行消失。"""
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

        # 用 Playwright 真实点击第一行「千帆同步」草稿的删除按钮
        del_btn = page.locator(
            'button.ColumnDraftItem-deleteButton'
        ).first
        n = await del_btn.count()
        print("删除按钮数:", n)
        row_text = await page.evaluate(
            """() => {
              const rows = [...document.querySelectorAll('.ColumnDraftItem')];
              return rows.slice(0, 3).map(
                (r) => (r.innerText || '').replace(/\\s+/g, ' ').slice(0, 50));
            }"""
        )
        print("前3行:", json.dumps(row_text, ensure_ascii=False))
        await del_btn.click()
        print("已真实点击删除")
        await asyncio.sleep(2)
        await page.screenshot(
            path=str(SHOT / "delstep_1_modal.png"), full_page=True
        )
        # 真实点击「确认」
        conf = page.locator('.Modal-inner button:has-text("确认")').first
        cn = await conf.count()
        print("确认按钮数:", cn)
        if cn:
            await conf.click()
            print("已真实点击确认")
            await asyncio.sleep(3)
            await page.screenshot(
                path=str(SHOT / "delstep_2_after.png"), full_page=True
            )
            rows = await page.evaluate(
                """() => {
                  const rows = [...document.querySelectorAll('.ColumnDraftItem')];
                  return {
                    count: rows.length,
                    first: rows.slice(0, 2).map(
                      (r) => (r.innerText || '')
                        .replace(/\\s+/g, ' ').slice(0, 50)),
                  };
                }"""
            )
            print("删除后:", json.dumps(rows, ensure_ascii=False))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
