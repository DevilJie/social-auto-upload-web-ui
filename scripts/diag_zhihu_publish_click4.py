# -*- coding: utf-8 -*-
"""诊断发布 v4: 监听网络,点击发布后抓 API 请求与响应。"""
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

        events = []

        def on_response(resp):
            url = resp.url
            if any(k in url for k in (
                "/api/", "publish", "article", "upload", "sign",
            )):
                events.append({
                    "type": "resp",
                    "status": resp.status,
                    "method": resp.request.method,
                    "url": url[:130],
                })

        page.on("response", on_response)

        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)
        events.clear()
        tb = page.locator("textarea.Input").first
        await tb.wait_for(state="visible", timeout=15000)
        await tb.fill("发布诊断v4")
        await page.evaluate(
            """(html) => {
              const ed = document.querySelector('.public-DraftEditor-content');
              ed.focus();
              const dt = new DataTransfer();
              dt.setData('text/html', html);
              ed.dispatchEvent(new ClipboardEvent('paste', {
                  bubbles: true, cancelable: true, clipboardData: dt,
              }));
            }""",
            "<p>发布诊断正文v4。测试内容,可删除。</p>",
        )
        await asyncio.sleep(5)
        events.clear()

        box = await page.evaluate(
            """() => {
              for (const b of document.querySelectorAll('button')) {
                if (b.getBoundingClientRect().width <= 0) continue;
                if ((b.innerText || '').trim() === '发布') {
                  const r = b.getBoundingClientRect();
                  return {x: r.x + r.width / 2, y: r.y + r.height / 2,
                          disabled: b.disabled};
                }
              }
              return null;
            }"""
        )
        print("按钮:", json.dumps(box))
        await page.mouse.click(box["x"], box["y"])
        print("已点击,监听网络 15s...")
        await asyncio.sleep(15)
        for e in events:
            print(json.dumps(e, ensure_ascii=False))
        await page.screenshot(
            path=str(SHOT / "pub4_after_click.png"), full_page=True
        )
        print("最终 URL:", page.url)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
