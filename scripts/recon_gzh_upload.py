# -*- coding: utf-8 -*-
"""第三轮侦察：图片上传凭证 + 直调上传接口 + 保存草稿行为。

实验项：
1. dump window.wx.commonData.data（找 ticket_id/ticket）
2. 浏览器 context 内直调 filetransfer?action=upload_material 上传 PNG → 拿 cdn_url
3. 粘贴带 mmbiz cdn_url 的 HTML → 看是否直接渲染
4. 点「保存为草稿」抓请求 → 看正文图片是否被转存 / 拿草稿 appMsgId

产物: data/screenshots/gzh_upload_recon.json + 截图
"""
import asyncio
import base64
import json
import re
import struct
import sys
import zlib
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "f3cfc68b-8a7d-11f1-a26f-bc24114cad59.json"
SHOT_DIR = REPO / "data" / "screenshots"
TOKEN_RE = re.compile(r"[?&]token=(\d+)")


def make_test_png(width: int = 240, height: int = 160) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    # 渐变色行，避免太素
    rows = b""
    for y in range(height):
        r = int(255 * y / height)
        rows += b"\x00" + bytes([r, 80, 255 - r]) * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


async def main() -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    png_bytes = make_test_png()

    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()

        net: list[list] = []
        page.on(
            "response",
            lambda r: net.append([r.status, r.request.method, r.url[:220]])
            if "/cgi-bin/" in (r.url or "")
            else None,
        )

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
        print("TOKEN:", token)
        assert token, "token 解析失败"

        edit_url = (
            "https://mp.weixin.qq.com/cgi-bin/appmsg"
            "?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77"
            f"&token={token}&lang=zh_CN"
        )
        await page.goto(edit_url, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(10)

        # ---- 1. dump commonData.data ----
        cd_data = await page.evaluate(
            """() => {
              try {
                const d = window.wx.commonData.data || {};
                const pick = {};
                for (const k of Object.keys(d)) {
                  const v = d[k];
                  if (v === null || v === undefined) continue;
                  const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
                  pick[k] = s.slice(0, 80);
                }
                return pick;
              } catch (e) { return {'err': String(e)}; }
            }"""
        )
        print("COMMON_DATA:", json.dumps(cd_data, ensure_ascii=False, indent=1))

        # ---- 2. 直调 filetransfer 上传 ----
        upload_result = None
        try:
            # 用页面 fetch 发 multipart（自动带 cookie/referer，绕过 requests 拼 cookie 的麻烦）
            b64 = base64.b64encode(png_bytes).decode()
            upload_result = await page.evaluate(
                """async (b64) => {
                  const cd = window.wx.commonData;
                  const d = cd.data || {};
                  const ticket = d.ticket || cd.ticket || '';
                  const ticket_id = d.ticket_id || cd.ticket_id || cd.uin || '';
                  const q = new URLSearchParams({
                    action: 'upload_material', f: 'json',
                    scene: '8', writetype: 'doublewrite', groupid: '1',
                    ticket_id: String(ticket_id), ticket: String(ticket),
                    token: String(d.token || ''), lang: 'zh_CN',
                    svr_time: String(Math.floor(Date.now() / 1000)),
                  });
                  const bin = atob(b64);
                  const arr = new Uint8Array(bin.length);
                  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                  const fd = new FormData();
                  fd.append('file', new Blob([arr], {type: 'image/png'}), 'recon_test.png');
                  const resp = await fetch('/cgi-bin/filetransfer?' + q.toString(), {
                    method: 'POST', body: fd, credentials: 'include',
                  });
                  const text = await resp.text();
                  return {status: resp.status, ticket: String(ticket).slice(0, 12),
                          ticket_id: String(ticket_id), body: text.slice(0, 600)};
                }""",
                b64,
            )
        except Exception as e:
            upload_result = {"error": str(e)}
        print("UPLOAD_RESULT:", json.dumps(upload_result, ensure_ascii=False, indent=1))

        # ---- 3. 粘贴带 cdn_url 的 HTML ----
        cdn_url = ""
        try:
            body = json.loads(upload_result.get("body", "{}"))
            cdn_url = body.get("cdn_url") or body.get("content") or ""
        except Exception:
            pass
        print("CDN_URL:", cdn_url)

        paste_html = (
            "<h1>上传接口验证</h1><p>如果下面图片显示为微信 CDN 图，说明直调上传链路可行。</p>"
            f'<p><img src="{cdn_url or "data:image/png;base64," + base64.b64encode(png_bytes).decode()}" alt="图"></p>'
            "<p>结尾。</p>"
        )
        paste_ret = await page.evaluate(
            """(html) => {
              const pms = [...document.querySelectorAll('.ProseMirror')]
                .filter((el) => el.getBoundingClientRect().height > 0);
              const body = pms.length > 1 ? pms[1] : pms[0];
              body.focus();
              const dt = new DataTransfer();
              dt.setData('text/html', html);
              body.dispatchEvent(new ClipboardEvent('paste', {
                bubbles: true, cancelable: true, clipboardData: dt,
              }));
              return 'ok';
            }""",
            paste_html,
        )
        print("PASTE:", paste_ret)
        await asyncio.sleep(4)
        await page.screenshot(path=str(SHOT_DIR / "gzh_upload_paste.png"), full_page=True)

        # ---- 4. 保存为草稿 ----
        save_resp = []
        page.once(
            "response",
            lambda r: save_resp.append([r.status, r.url[:200]])
            if "operate_appmsg" in r.url or "save" in r.url.lower()
            else None,
        )
        clicked = False
        try:
            btn = page.get_by_text("保存为草稿", exact=True).first
            await btn.click(timeout=8000)
            clicked = True
        except Exception as e:
            print("click save draft (non-fatal):", e)
        await asyncio.sleep(6)
        await page.screenshot(
            path=str(SHOT_DIR / "gzh_after_save.png"), full_page=True
        )
        body_html = await page.evaluate(
            """() => {
              const pms = [...document.querySelectorAll('.ProseMirror')]
                .filter((el) => el.getBoundingClientRect().height > 0);
              const body = pms.length > 1 ? pms[1] : pms[0];
              return body ? body.innerHTML.slice(0, 2500) : '';
            }"""
        )
        print("AFTER_SAVE_HTML:", body_html[:1200])
        print("SAVE_RESP:", save_resp)
        print("URL_NOW:", page.url)

        result = {
            "common_data": cd_data,
            "upload_result": upload_result,
            "cdn_url": cdn_url,
            "net_tail": net[-30:],
            "after_save_html": body_html,
        }
        out = SHOT_DIR / "gzh_upload_recon.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print("saved →", out)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
