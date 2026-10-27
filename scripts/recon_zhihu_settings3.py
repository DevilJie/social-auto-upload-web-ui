# -*- coding: utf-8 -*-
"""侦察知乎设置区 v3: 先展开「发布设置」,再采创作声明/话题/投稿。"""
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


async def safe(name, coro):
    try:
        await coro
    except Exception as e:
        print(f"[{name}] ERR: {type(e).__name__} {str(e)[:150]}")


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

        # 展开发布设置(底部「发布设置」展开器)
        async def expand():
            btn = page.locator("text=发布设置").first
            await btn.scroll_into_view_if_needed(timeout=10000)
            await btn.click(timeout=8000)
            await asyncio.sleep(2)
            # 验证: 投稿至问题可见
            await page.locator("text=投稿至问题").first.wait_for(
                state="visible", timeout=8000
            )
            print("设置区已展开")

        await safe("expand", expand())

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
                  return [...document.querySelectorAll('li, [role=option]')]
                    .filter(vis)
                    .map((el) => (el.innerText || '').trim().replace(/\\s+/g, ' '))
                    .filter((t) => t && t.length < 40)
                    .slice(0, 15);
                }"""
            )
            print("声明选项:", json.dumps(opts, ensure_ascii=False))
            await page.screenshot(path=str(SHOT / "zhihu_decl.png"))
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
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

        await safe("topic", step_topic())

        # 3. 投稿至问题
        async def step_target():
            await page.locator("text=未选择").first.click(timeout=8000)
            await asyncio.sleep(2)
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
                  return inputs.slice(0, 8);
                }"""
            )
            print("投稿面板:", json.dumps(info, ensure_ascii=False, indent=1))
            await page.screenshot(path=str(SHOT / "zhihu_targetq2.png"))
            await page.keyboard.press("Escape")

        await safe("target", step_target())

        print("done")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
