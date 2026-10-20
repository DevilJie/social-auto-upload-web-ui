# -*- coding: utf-8 -*-
"""列出草稿箱卡片标题(验证清理结果)。"""
import asyncio
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "f3cfc68b-8a7d-11f1-a26f-bc24114cad59.json"
TOKEN_RE = re.compile(r"[?&]token=(\d+)")


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.goto(
            "https://mp.weixin.qq.com/", wait_until="domcontentloaded", timeout=30000
        )
        loop = asyncio.get_event_loop()
        token = ""
        deadline = loop.time() + 20
        while loop.time() < deadline:
            m = TOKEN_RE.search(page.url or "")
            if m:
                token = m.group(1)
                break
            await asyncio.sleep(0.5)
        assert token

        await page.goto(
            f"https://mp.weixin.qq.com/cgi-bin/appmsg?begin=0&count=10"
            f"&type=77&action=list_card&token={token}&lang=zh_CN",
            wait_until="domcontentloaded",
            timeout=40000,
        )
        await asyncio.sleep(8)
        titles = await page.evaluate(
            """() => {
              const out = [];
              for (const el of document.querySelectorAll(
                '.weui-desktop-card, .card_masssend, tr, .js_card')) {
                const t = (el.innerText || '').trim().split('\\n')[0];
                if (t && t.length > 4 && t.length < 60 && !out.includes(t)) out.push(t);
              }
              return out.slice(0, 12);
            }"""
        )
        print(json.dumps(titles, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


import json

if __name__ == "__main__":
    asyncio.run(main())
