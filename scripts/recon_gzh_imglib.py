# -*- coding: utf-8 -*-
"""侦察: filetransfer scene=1 上传是否进公众号图片库 + js_imagedialog 对话框结构。"""
import asyncio
import base64
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
SHOT = REPO / "data" / "screenshots"
COVER_FILE = (
    REPO / "data" / "materials" / "2026" / "09" / "14"
    / "e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)


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

        # 1. 打开文章编辑页(需要编辑页上下文的凭证)
        await page.goto(
            "https://mp.weixin.qq.com/cgi-bin/appmsg"
            "?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77"
            f"&token={token}&lang=zh_CN",
            wait_until="domcontentloaded",
            timeout=40000,
        )
        await asyncio.sleep(10)

        # 2. scene=1 上传(素材库/图片库)
        b64 = base64.b64encode(COVER_FILE.read_bytes()).decode()
        up = await page.evaluate(
            """async (b64) => {
              const d = (window.wx && window.wx.commonData &&
                         window.wx.commonData.data) || {};
              const urlToken =
                new URLSearchParams(location.search).get('token') || d.t || '';
              const q = new URLSearchParams({
                action: 'upload_material', f: 'json', scene: '1',
                writetype: 'doublewrite', groupid: '1',
                ticket_id: String(d.uin || ''), ticket: String(d.ticket || ''),
                token: String(urlToken), lang: 'zh_CN',
                svr_time: String(Math.floor(Date.now() / 1000)),
              });
              const bin = atob(b64);
              const arr = new Uint8Array(bin.length);
              for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
              const fd = new FormData();
              fd.append('file', new Blob([arr], {type: 'image/jpeg'}), 'cover.jpg');
              const resp = await fetch('/cgi-bin/filetransfer?' + q.toString(), {
                method: 'POST', body: fd, credentials: 'include',
              });
              return await resp.json();
            }""",
            b64,
        )
        print("SCENE1 UPLOAD:", json.dumps(up, ensure_ascii=False)[:400])
        cdn = up.get("cdn_url") or up.get("content") or ""
        content_id = up.get("content", "")
        print("cdn:", cdn[:80], "content_id:", content_id)

        # 3. 点「从图片库选择」(js_imagedialog) — 无封面态菜单在 #js_cover_null
        opened = await page.evaluate(
            """() => {
              const el = document.querySelector(
                '#js_cover_null .js_imagedialog');
              if (!el) return false;
              const opts = {bubbles: true, cancelable: true, view: window};
              el.dispatchEvent(new MouseEvent('mousedown', opts));
              el.dispatchEvent(new MouseEvent('mouseup', opts));
              el.dispatchEvent(new MouseEvent('click', opts));
              return true;
            }"""
        )
        print("opened image-library dialog:", opened)
        await asyncio.sleep(4)
        await page.screenshot(path=str(SHOT / "gzh_imglib_dialog.png"))

        # 4. 对话框结构 + 是否能找到刚上传的图
        panel = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const dlg = [...document.querySelectorAll(
                  '.weui-desktop-dialog__wrp')].filter(vis)[0];
              const btns = [];
              for (const el of document.querySelectorAll('button')) {
                if (!vis(el)) continue;
                const t = (el.innerText || '').trim();
                if (t && t.length < 14 && !btns.includes(t)) btns.push(t);
              }
              // 找所有含 background-image 的缩略块
              const thumbs = [];
              for (const el of document.querySelectorAll(
                  '[style*="background-image"], img')) {
                if (!vis(el)) continue;
                const bg = el.style.backgroundImage || '';
                const src = el.src || '';
                const u = (bg.match(/url\\("?([^")]+)"?\\)/) || [])[1] || src;
                if (u) thumbs.push({cls: String(el.className).slice(0, 60),
                                    url: u.slice(0, 90)});
              }
              return {
                dlgCls: dlg ? String(dlg.className).slice(0, 90) : null,
                btns: btns.slice(0, 20),
                thumbs: thumbs.slice(0, 10),
              };
            }"""
        )
        print("PANEL:", json.dumps(panel, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
