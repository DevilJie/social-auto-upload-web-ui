# -*- coding: utf-8 -*-
"""诊断删除: 监听网络响应,确认是否被风控拦截。"""
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
        body_holder = {}

        async def on_response(resp):
            url = resp.url
            if any(k in url for k in ("delete", "draft", "remove")):
                try:
                    body = await resp.json()
                except Exception:
                    body = None
                body_holder.setdefault("events", []).append({
                    "status": resp.status,
                    "method": resp.request.method,
                    "url": url[-80:],
                    "body": body,
                })

        page.on("response", on_response)
        await page.goto(
            "https://zhuanlan.zhihu.com/drafts",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)
        await page.locator("button.ColumnDraftItem-deleteButton").first.click()
        await asyncio.sleep(2)
        await page.locator('.Modal-inner button:has-text("确认")').first.click()
        await asyncio.sleep(5)
        print(json.dumps(
            body_holder.get("events", []), ensure_ascii=False, indent=1
        )[:2500])
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
