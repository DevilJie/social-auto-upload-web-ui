# -*- coding: utf-8 -*-
"""侦察 v4: 精确定位底部「发布设置」展开器(y 坐标区分)并展开。"""
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
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)

        # 枚举含「发布设置」的可见元素及坐标
        elems = await page.evaluate(
            """() => {
              const out = [];
              for (const el of document.querySelectorAll('*')) {
                const t = (el.innerText || '').trim();
                if (!t.startsWith('发布设置') || t.length > 12) continue;
                const r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                out.push({tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                          w: Math.round(r.width), h: Math.round(r.height),
                          cls: String(el.className).slice(0, 50)});
              }
              return out;
            }"""
        )
        print("发布设置元素:", json.dumps(elems, ensure_ascii=False, indent=1))

        # 底部展开按钮 = BUTTON 且文本以「发布设置」开头
        target = None
        for e in elems:
            if e["tag"] == "BUTTON":
                target = e
                break
        if target:
            print("点击底部展开器:", target)
            await page.mouse.click(target["x"] + target["w"] / 2,
                                   target["y"] + target["h"] / 2)
            await asyncio.sleep(2.5)
            visible = await page.evaluate(
                """() => {
                  const el = [...document.querySelectorAll('*')].find(
                    (e) => (e.innerText || '').trim() === '投稿至问题');
                  if (!el) return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                }"""
            )
            print("投稿至问题可见:", visible)
            await page.screenshot(
                path=str(SHOT / "zhihu_expanded.png"), full_page=True
            )
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
