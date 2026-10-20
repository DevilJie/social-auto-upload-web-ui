# -*- coding: utf-8 -*-
"""侦察公众号文章编辑页（type=77 新编辑器）。

四通道采集（skill 规范）：截图 / DOM 清单 / 网络监听 / 最终 URL。
产物: data/screenshots/gzh_article_edit.png + gzh_article_recon.json
"""
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
SHOT_DIR = REPO / "data" / "screenshots"

TOKEN_RE = re.compile(r"[?&]token=(\d+)")


async def main() -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()

        net: list[list] = []
        page.on(
            "response",
            lambda r: net.append([r.status, r.url[:220]])
            if "/cgi-bin/" in (r.url or "")
            else None,
        )

        # 1. token 解析
        await page.goto(
            "https://mp.weixin.qq.com/",
            wait_until="domcontentloaded",
            timeout=30000,
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
        if not token:
            await page.screenshot(path=str(SHOT_DIR / "gzh_token_fail.png"))
            print("FINAL_URL:", page.url)
            return

        # 2. 首页 DOM：找「写新图文/图文消息」入口链接
        await page.goto(
            f"https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token={token}",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(3)
        home_entries = await page.evaluate(
            """() => {
              const out = [];
              for (const a of document.querySelectorAll('a[href]')) {
                const t = (a.innerText || '').trim();
                const h = a.getAttribute('href') || '';
                if (t && t.length < 16 && /appmsg|newdraft|editor/i.test(h)) {
                  out.push({text: t, href: h.slice(0, 160)});
                }
              }
              return out.slice(0, 30);
            }"""
        )
        print("HOME_ENTRIES:", json.dumps(home_entries, ensure_ascii=False, indent=1))
        await page.screenshot(path=str(SHOT_DIR / "gzh_home.png"))

        # 3. 文章编辑页（type=77 新编辑器）
        edit_url = (
            "https://mp.weixin.qq.com/cgi-bin/appmsg"
            "?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77"
            f"&token={token}&lang=zh_CN"
        )
        try:
            await page.goto(edit_url, wait_until="domcontentloaded", timeout=40000)
        except Exception as e:
            print("goto edit page (non-fatal):", e)
        await asyncio.sleep(12)

        await page.screenshot(
            path=str(SHOT_DIR / "gzh_article_edit.png"), full_page=True
        )

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
                  cls: String(el.className || '').slice(0, 140),
                  ph: el.getAttribute('placeholder') || '',
                  text: (el.value || el.innerText || '').trim().slice(0, 40),
                  vis: vis(el),
                }));
              return {
                url: location.href,
                docTitle: document.title,
                inputs: grab('input[type=text], textarea'),
                editables: grab('[contenteditable="true"]'),
                iframes: [...document.querySelectorAll('iframe')].map((f) => ({
                  id: f.id,
                  cls: String(f.className || '').slice(0, 80),
                  src: (f.src || '').slice(0, 160),
                })),
                buttons: [...document.querySelectorAll(
                  'button, .weui-desktop-btn, a.weui-desktop-btn, .tool_area a, .js_save')]
                  .filter(vis)
                  .map((b) => (b.innerText || '').trim())
                  .filter((t) => t && t.length < 24)
                  .slice(0, 60),
                hasProseMirror: !!document.querySelector('.ProseMirror'),
                hasUEditor: !!document.querySelector('#ueditor_0, .edui-editor'),
                wxCommonData: (() => {
                  try {
                    const cd = window.wx && window.wx.commonData;
                    if (!cd) return null;
                    return {
                      ticket_id: cd.ticket_id || '', ticket: cd.ticket || '',
                      uin: cd.uin || '', data_seq: cd.data_seq || '',
                      appid: cd.appid || '',
                    };
                  } catch (e) { return String(e); }
                })(),
                prosemirrorSample: (() => {
                  const pm = document.querySelector('.ProseMirror');
                  if (!pm) return null;
                  return {cls: pm.className.slice(0, 140), htmlHead: pm.innerHTML.slice(0, 400)};
                })(),
              };
            }"""
        )
        inv["net_tail"] = net[-40:]
        out = SHOT_DIR / "gzh_article_recon.json"
        out.write_text(
            json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print("=== RECON SUMMARY ===")
        print("URL:", inv["url"])
        print("hasProseMirror:", inv["hasProseMirror"], " hasUEditor:", inv["hasUEditor"])
        print("wxCommonData:", inv["wxCommonData"])
        print("editables:", json.dumps(inv["editables"], ensure_ascii=False))
        print("buttons:", json.dumps(inv["buttons"], ensure_ascii=False))
        print("saved →", out)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
