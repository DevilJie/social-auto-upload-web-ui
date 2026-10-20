# -*- coding: utf-8 -*-
"""知乎编辑器粘贴实验: HTML(含 base64 图) → Draft.js 解析行为。"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402
from recon_zhihu_write import make_test_png, TEST_HTML  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"
SHOT = REPO / "data" / "screenshots"


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()

        uploads = []
        page.on(
            "response",
            lambda r: uploads.append([r.status, r.url[:150]])
            if any(k in (r.url or "") for k in ("upload", "sign", "zhuanlan/api"))
            else None,
        )

        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)

        # 粘贴 HTML(直接选 .public-DraftEditor-content)
        paste_ret = await page.evaluate(
            """(html) => {
              const body = document.querySelector(
                  '.public-DraftEditor-content');
              if (!body) return {err: 'no editor'};
              const ed = body.closest('[contenteditable="true"]') || body;
              ed.focus();
              const dt = new DataTransfer();
              dt.setData('text/html', html);
              ed.dispatchEvent(new ClipboardEvent('paste', {
                bubbles: true, cancelable: true, clipboardData: dt,
              }));
              return {ok: true, cls: ed.className.slice(0, 80)};
            }""",
            TEST_HTML,
        )
        print("PASTE:", paste_ret)
        await asyncio.sleep(8)
        await page.screenshot(path=str(SHOT / "zhihu_paste_test.png"), full_page=True)

        content = await page.evaluate(
            """() => {
              const body = document.querySelector('.public-DraftEditor-content');
              if (!body) return null;
              const html = body.innerHTML;
              return {
                len: html.length,
                hasB64: html.includes('data:image'),
                hasH1: html.includes('<h1>'),
                hasImg: html.includes('<img'),
                imgCount: (html.match(/<img/g) || []).length,
                head: html.slice(0, 500),
              };
            }"""
        )
        print("CONTENT:", json.dumps(content, ensure_ascii=False, indent=1)[:1500])
        print("UPLOAD NET:", json.dumps(uploads[-8:], ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
