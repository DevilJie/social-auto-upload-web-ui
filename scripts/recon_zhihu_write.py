# -*- coding: utf-8 -*-
"""侦察知乎文章编辑器(zhuanlan.zhihu.com/write)。

四通道采集 + 编辑器类型判断 + 粘贴 HTML 实验(含 base64 图)。
产物: data/screenshots/zhihu_write_*.png + zhihu_write_recon.json
"""
import asyncio
import base64
import json
import struct
import sys
import zlib
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"
SHOT = REPO / "data" / "screenshots"


def make_test_png(width: int = 200, height: int = 120) -> str:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    rows = b""
    for y in range(height):
        r = int(255 * y / height)
        rows += b"\x00" + bytes([r, 120, 255 - r]) * width
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode()


TEST_HTML = (
    "<h1>知乎图文测试标题</h1>"
    "<p>这是<strong>加粗</strong>与<em>斜体</em>混排段落。</p>"
    "<ul><li>列表一</li><li>列表二</li></ul>"
    "<blockquote>引用块测试。</blockquote>"
    f'<p><img src="{make_test_png()}" alt="图"></p>'
    "<p>结尾段落。</p>"
)


async def main() -> None:
    SHOT.mkdir(parents=True, exist_ok=True)
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()

        net = []
        page.on(
            "response",
            lambda r: net.append([r.status, r.request.method, r.url[:200]])
            if any(k in (r.url or "") for k in ("upload", "zhuanlan", "api"))
            else None,
        )

        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded",
            timeout=40000,
        )
        await asyncio.sleep(10)
        print("URL:", page.url)
        await page.screenshot(path=str(SHOT / "zhihu_write_1.png"), full_page=True)

        # DOM 清单
        inv = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const grab = (sel) =>
                [...document.querySelectorAll(sel)].map((el) => ({
                  tag: el.tagName,
                  id: el.id || '',
                  cls: String(el.className || '').slice(0, 120),
                  ph: el.getAttribute('placeholder')
                      || el.getAttribute('data-placeholder') || '',
                  text: (el.value || el.innerText || '').trim().slice(0, 30),
                  vis: vis(el),
                }));
              return {
                url: location.href,
                title: document.title,
                textareas: grab('textarea'),
                editables: grab('[contenteditable="true"]'),
                buttons: [...document.querySelectorAll('button')]
                  .filter(vis)
                  .map((b) => (b.innerText || '').trim())
                  .filter((t) => t && t.length < 14)
                  .slice(0, 40),
                hasDraft: !!document.querySelector(
                    '.public-DraftEditor-content, [class*=DraftEditor]'),
                hasProseMirror: !!document.querySelector('.ProseMirror'),
                inputs: grab('input[type=text], input:not([type])').slice(0, 10),
              };
            }"""
        )
        print("INV:", json.dumps(inv, ensure_ascii=False, indent=1)[:2500])

        # 粘贴实验: 往正文编辑器 dispatch paste(text/html 含 base64 图)
        paste_ret = await page.evaluate(
            """(html) => {
              const eds = [...document.querySelectorAll('[contenteditable="true"]')]
                .filter((el) => el.getBoundingClientRect().height > 100);
              if (eds.length === 0) return {err: 'no editor'};
              const body = eds[0];
              body.focus();
              const dt = new DataTransfer();
              dt.setData('text/html', html);
              body.dispatchEvent(new ClipboardEvent('paste', {
                bubbles: true, cancelable: true, clipboardData: dt,
              }));
              return {count: eds.length, cls: body.className.slice(0, 80)};
            }""",
            TEST_HTML,
        )
        print("PASTE:", paste_ret)
        await asyncio.sleep(6)
        await page.screenshot(path=str(SHOT / "zhihu_write_paste.png"), full_page=True)

        content = await page.evaluate(
            """() => {
              const eds = [...document.querySelectorAll('[contenteditable="true"]')]
                .filter((el) => el.getBoundingClientRect().height > 100);
              const body = eds[0];
              if (!body) return '';
              const html = body.innerHTML;
              return {
                len: html.length,
                hasB64: html.includes('data:image'),
                head: html.slice(0, 600),
              };
            }"""
        )
        print("CONTENT:", json.dumps(content, ensure_ascii=False, indent=1)[:1200])
        net_tail = [n for n in net if 'upload' in n[2].lower() or 'api' in n[2]]
        print("NET(up/api):", json.dumps(net_tail[-10:], ensure_ascii=False))

        out = SHOT / "zhihu_write_recon.json"
        out.write_text(
            json.dumps(
                {"inv": inv, "paste_ret": paste_ret, "content": content,
                 "net": net_tail[-15:]},
                ensure_ascii=False, indent=1,
            ),
            encoding="utf-8",
        )
        print("saved →", out)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
