# -*- coding: utf-8 -*-
"""诊断发布 v5: 抓 /api/v4/content/publish 的响应体。"""
import asyncio
import json
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
        await page.set_viewport_size({"width": 1600, "height": 900})

        body_holder = {}

        async def on_response(resp):
            if "/api/v4/content/publish" in resp.url:
                try:
                    body = await resp.json()
                except Exception:
                    body = {"_raw": "non-json"}
                body_holder["body"] = body
                body_holder["status"] = resp.status
                req = resp.request
                body_holder["req_headers"] = {
                    k: req.headers.get(k, "")
                    for k in ("content-type",)
                }
                try:
                    body_holder["req_post"] = req.post_data
                except Exception:
                    pass

        page.on("response", on_response)

        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)
        tb = page.locator("textarea.Input").first
        await tb.wait_for(state="visible", timeout=15000)
        await tb.fill("发布诊断v5")
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
            "<p>发布诊断正文v5。测试内容,可删除。</p>",
        )
        await asyncio.sleep(5)

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
        await page.mouse.click(box["x"], box["y"])
        for _ in range(10):
            if "body" in body_holder:
                break
            await asyncio.sleep(1)
        await asyncio.sleep(3)
        print("HTTP:", body_holder.get("status"))
        print("REQ POST:", str(body_holder.get("req_post"))[:500])
        print("RESP:", json.dumps(
            body_holder.get("body"), ensure_ascii=False, indent=1
        )[:2000])
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
