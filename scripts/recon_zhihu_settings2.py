# -*- coding: utf-8 -*-
"""侦察知乎设置区 v2: 创作声明选项/话题输入/投稿至问题。"""
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


async def safe(step_name, coro):
    try:
        await coro
    except Exception as e:
        print(f"[{step_name}] ERR: {type(e).__name__} {str(e)[:120]}")


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)

        # 1. 创作声明下拉
        async def step_decl():
            await page.locator("text=无声明").first.click(timeout=8000)
            await asyncio.sleep(2)
            opts = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll(
                      '[class*=Menu] li, [role=option], [class*=menu] li, [class*=Select] li')]
                    .filter(vis)
                    .map((el) => (el.innerText || '').trim().replace(/\\s+/g, ' '))
                    .filter((t) => t && t.length < 40)
                    .slice(0, 15);
                }"""
            )
            print("声明选项:", json.dumps(opts, ensure_ascii=False))
            await page.screenshot(path=str(SHOT / "zhhu_decl.png"))
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

        await safe("decl", step_decl())

        # 2. 话题输入
        async def step_topic():
            await page.locator("text=添加话题").first.click(timeout=8000)
            await asyncio.sleep(2)
            info = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll(
                      'input, [contenteditable=true]')]
                    .filter(vis)
                    .map((el) => ({tag: el.tagName,
                                   ph: el.getAttribute('placeholder') || '',
                                   cls: String(el.className).slice(0, 50)}))
                    .slice(0, 10);
                }"""
            )
            print("话题输入:", json.dumps(info, ensure_ascii=False, indent=1))
            await page.screenshot(path=str(SHOT / "zhihu_topic.png"))
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

        await safe("topic", step_topic())

        # 3. 投稿至问题
        async def step_target():
            # 点击「未选择」(投稿行的 Select 展示文本)
            await page.locator("text=未选择").first.click(timeout=8000)
            await asyncio.sleep(2)
            await page.screenshot(path=str(SHOT / "zhihu_targetq.png"))
            info = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const inputs = [...document.querySelectorAll(
                      'input, [contenteditable=true], textarea')]
                    .filter(vis)
                    .map((el) => ({tag: el.tagName,
                                   ph: el.getAttribute('placeholder') || '',
                                   cls: String(el.className).slice(0, 50)}));
                  const menus = [...document.querySelectorAll(
                      '[class*=Menu], [role=listbox], [class*=popover]')]
                    .filter(vis)
                    .map((el) => (el.innerText || '').trim().slice(0, 80));
                  return {inputs: inputs.slice(0, 8), menus: menus.slice(0, 5)};
                }"""
            )
            print("投稿面板:", json.dumps(info, ensure_ascii=False, indent=1))
            await page.keyboard.press("Escape")

        await safe("target", step_target())

        print("done")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
