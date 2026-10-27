# -*- coding: utf-8 -*-
"""验证 draft67 设置区对齐: 滚动到创作声明并截图。"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

SHOT = REPO / "data" / "screenshots"


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser)
        page = await ctx.new_page()
        await page.set_viewport_size({"width": 1600, "height": 900})
        await page.goto(
            "http://localhost:5173/#/article-publish?draft_id=67",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        try:
            await page.locator("text=哈罗").first.click(timeout=8000)
            await asyncio.sleep(2)
        except Exception:
            pass
        # 滚动内部容器到「创作声明」
        await page.evaluate(
            """() => {
              const el = [...document.querySelectorAll('*')].find(
                (e) => (e.innerText || '').trim() === '创作声明');
              if (el) el.scrollIntoView({block: 'center'});
            }"""
        )
        await asyncio.sleep(1.5)
        await page.screenshot(path=str(SHOT / "verify_draft67_panel.png"))
        print("done")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
