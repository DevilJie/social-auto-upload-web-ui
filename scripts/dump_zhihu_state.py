# -*- coding: utf-8 -*-
"""dump 知乎 write 页全文,看当前渲染状态。"""
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
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        for i in range(4):
            await asyncio.sleep(5)
            text = await page.evaluate(
                "() => document.body.innerText.replace(/\\n{2,}/g, '\\n').slice(0, 900)"
            )
            print(f"=== t={((i+1)*5)}s ===")
            print(text)
            print()
        await page.screenshot(path=str(REPO / "data" / "screenshots" / "zhihu_state.png"))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
