# -*- coding: utf-8 -*-
"""侦察知乎定时发布: 开关点开后的时间选择控件 DOM。"""
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

        # 点定时开关(checkbox)
        await page.evaluate(
            """() => {
              const cb = document.querySelector(
                  'input[type=checkbox].css-1i5t6yb')
                || document.querySelector(
                  '[class*=setting] input[type=checkbox]');
              if (cb) { cb.click(); return true; }
              return false;
            }"""
        )
        await asyncio.sleep(3)
        await page.screenshot(path=str(SHOT / "zhihu_sched_on.png"), full_page=True)

        # dump 时间选择区 DOM
        dom = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const rows = [...document.querySelectorAll('*')].filter(
                (el) => vis(el)
                  && (el.innerText || '').trim() === '定时发布');
              const out = [];
              const seen = new Set();
              for (const r of rows) {
                let node = r.parentElement;
                for (let d = 0; d < 3 && node; d++) {
                  for (const c of node.querySelectorAll(
                      'input, select, button, [class*=date], [class*=time], '
                      + '[class*=picker], [class*=Select]')) {
                    if (!vis(c)) continue;
                    const key = String(c.className).slice(0, 40)
                      + c.tagName + (c.getAttribute('placeholder') || '');
                    if (seen.has(key)) continue;
                    seen.add(key);
                    out.push({
                      tag: c.tagName,
                      cls: String(c.className).slice(0, 70),
                      ph: c.getAttribute('placeholder') || '',
                      type: c.getAttribute('type') || '',
                      text: (c.innerText || '').trim().slice(0, 30),
                    });
                  }
                  node = node.parentElement;
                }
              }
              return out.slice(0, 15);
            }"""
        )
        print("定时控件:", json.dumps(dom, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
