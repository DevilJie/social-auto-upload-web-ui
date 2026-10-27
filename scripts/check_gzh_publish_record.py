# -*- coding: utf-8 -*-
"""查公众号发表记录,验证文章是否真实群发成功。"""
import asyncio
import json
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
            f"https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list"
            f"&begin=0&count=10&token={token}&lang=zh_CN",
            wait_until="domcontentloaded",
            timeout=40000,
        )
        await asyncio.sleep(8)
        await page.screenshot(
            path=str(REPO / "data" / "screenshots" / "gzh_publish_record.png"),
            full_page=True,
        )
        records = await page.evaluate(
            """() => {
              const out = [];
              const seen = new Set();
              for (const el of document.querySelectorAll(
                  '.weui-desktop-card, .publish_record_list_item, tr, .js_record')) {
                const t = (el.innerText || '').trim().replace(/\\s+/g, ' ');
                if (t && t.length > 8 && t.length < 200 && !seen.has(t)) {
                  seen.add(t);
                  out.push(t.slice(0, 150));
                }
              }
              return out.slice(0, 8);
            }"""
        )
        print(json.dumps(records, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
