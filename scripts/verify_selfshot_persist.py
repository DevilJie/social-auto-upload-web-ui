# -*- coding: utf-8 -*-
"""验证自行拍摄勾选状态持久化: 取消勾选→更新草稿→刷新→应保持未勾选。"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

SHOT = REPO / "data" / "screenshots"
URL = "http://localhost:5173/#/article-publish?draft_id=67"


async def get_checkbox_state(page):
    return await page.evaluate(
        """() => {
          // 知乎面板的自行拍摄 checkbox: 文本「图片/视频为自行拍摄」同卡片内
          const labels = [...document.querySelectorAll('.el-checkbox__label')]
            .filter((e) => (e.innerText || '').includes('自行拍摄'));
          if (!labels.length) return null;
          const box = labels[0].closest('label');
          return box ? box.classList.contains('is-checked') : null;
        }"""
    )


async def load_page(ctx):
    page = await ctx.new_page()
    await page.set_viewport_size({"width": 1600, "height": 900})
    await page.goto(URL, wait_until="domcontentloaded", timeout=40000)
    await asyncio.sleep(8)
    try:
        await page.locator("text=哈罗").first.click(timeout=8000)
        await asyncio.sleep(2)
    except Exception:
        pass
    # 滚到设置区
    await page.evaluate(
        """() => {
          const el = [...document.querySelectorAll('*')].find(
            (e) => (e.innerText || '').trim() === '创作声明');
          if (el) el.scrollIntoView({block: 'center'});
        }"""
    )
    await asyncio.sleep(1)
    return page


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser)

        # ---- 第一次加载: 勾选 → 更新草稿 ----
        page = await load_page(ctx)
        state0 = await get_checkbox_state(page)
        print("初始状态:", state0)
        if not state0:
            cb = page.locator(".el-checkbox__label")
            lbl = [e for e in await cb.all_inner_texts()
                   if "自行拍摄" in e][0]
            await page.locator(
                f'.el-checkbox:has-text("自行拍摄")'
            ).first.click()
            await asyncio.sleep(1.5)
        else:
            # 已勾选 → 先取消(测试目标场景)
            await page.locator(
                '.el-checkbox:has-text("自行拍摄")'
            ).first.click()
            await asyncio.sleep(1.5)
        state1 = await get_checkbox_state(page)
        print("点击后状态:", state1)
        # 更新草稿
        await page.evaluate(
            """() => {
              const el = [...document.querySelectorAll('*')].find(
                (e) => (e.innerText || '').trim() === '创作声明');
              if (el) el.scrollIntoView({block: 'start'});
            }"""
        )
        await page.locator('button:has-text("更新草稿")').first.click()
        await asyncio.sleep(3)
        await page.close()

        # ---- 重新加载: 状态应保持 ----
        page2 = await load_page(ctx)
        state2 = await get_checkbox_state(page2)
        print("刷新后状态:", state2, "(应与点击后一致:", state1, ")")
        verdict = "PASS" if state2 == state1 else "FAIL"
        print("结论:", verdict)
        await page2.screenshot(
            path=str(SHOT / "verify_selfshot_persist.png")
        )
        await page2.close()
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
