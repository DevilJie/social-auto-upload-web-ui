# -*- coding: utf-8 -*-
"""封面全流程终版: 选图 → 下一步 → 裁剪确认 → 验证封面数据。"""
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
SHOT = REPO / "data" / "screenshots"

IMG_URL = (
    "http://127.0.0.1:5409/api/materials/file/"
    "materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)
HTML = (
    "<h2>封面全流程终版</h2><p>正文。</p>"
    f'<p><img src="{IMG_URL}" alt="配图"></p>'
    "<p>结尾。</p>"
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

        await page.goto(
            "https://mp.weixin.qq.com/cgi-bin/appmsg"
            "?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77"
            f"&token={token}&lang=zh_CN",
            wait_until="domcontentloaded",
            timeout=40000,
        )
        await asyncio.sleep(10)

        n = await page.evaluate(
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
              return body.innerHTML.length;
            }""",
            HTML,
        )
        print("pasted:", n)
        await asyncio.sleep(2)

        # 1. 从正文选择
        await page.evaluate(
            """() => {
              const el = document.querySelector(
                '#js_cover_null .js_selectCoverFromContent');
              const opts = {bubbles: true, cancelable: true, view: window};
              el.dispatchEvent(new MouseEvent('mousedown', opts));
              el.dispatchEvent(new MouseEvent('mouseup', opts));
              el.dispatchEvent(new MouseEvent('click', opts));
            }"""
        )
        print("opened img-picker")
        await asyncio.sleep(3)

        # 2. 点第一张缩略图(span.appmsg_content_img.cover 的父级 div)
        picked = await page.evaluate(
            """() => {
              const item = document.querySelector(
                  '.appmsg_content_img_list .appmsg_content_img_item');
              if (!item) return 'no-item';
              const target = item.querySelector('div') || item;
              const opts = {bubbles: true, cancelable: true, view: window};
              target.dispatchEvent(new MouseEvent('mousedown', opts));
              target.dispatchEvent(new MouseEvent('mouseup', opts));
              target.dispatchEvent(new MouseEvent('click', opts));
              return 'clicked';
            }"""
        )
        print("picked:", picked)
        await asyncio.sleep(1.5)

        # 3. 下一步(disabled 消失后点)
        next_ok = False
        for i in range(8):
            clicked = await page.evaluate(
                """() => {
                  for (const b of document.querySelectorAll(
                      'button.weui-desktop-btn_primary')) {
                    const r = b.getBoundingClientRect();
                    if (r.width <= 0) continue;
                    if ((b.innerText || '').trim() === '下一步'
                        && !b.className.includes('weui-desktop-btn_disabled')) {
                      const opts = {bubbles: true, cancelable: true, view: window};
                      b.dispatchEvent(new MouseEvent('mousedown', opts));
                      b.dispatchEvent(new MouseEvent('mouseup', opts));
                      b.dispatchEvent(new MouseEvent('click', opts));
                      return true;
                    }
                  }
                  return false;
                }"""
            )
            if clicked:
                next_ok = True
                print(f"next clicked (attempt {i})")
                break
            await asyncio.sleep(1)
        if not next_ok:
            print("FAILED: next never enabled")
            return
        await asyncio.sleep(4)
        await page.screenshot(path=str(SHOT / "gzh_cover_final_2.png"))

        # 4. dump 第二步(裁剪?)
        step2 = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const btns = [];
              for (const el of document.querySelectorAll('button')) {
                if (!vis(el)) continue;
                const t = (el.innerText || '').trim();
                const cls = String(el.className);
                if (t && t.length < 12) btns.push(`${t}[${cls.includes('primary') ? 'P' : 'n'}${cls.includes('disabled') ? 'D' : ''}]`);
              }
              const texts = [];
              for (const el of document.querySelectorAll(
                  '.weui-desktop-dialog, .img_crop_panel, [class*=crop]')) {
                if (!vis(el)) continue;
                const t = (el.innerText || '').trim().replace(/\\s+/g, ' ');
                if (t && t.length < 100) texts.push(t);
              }
              return {btns: btns.slice(0, 20), texts: [...new Set(texts)].slice(0, 5)};
            }"""
        )
        print("STEP2:", json.dumps(step2, ensure_ascii=False, indent=1))

        # 5. 点「确认」完成裁剪
        confirmed = await page.evaluate(
            """() => {
              for (const b of document.querySelectorAll('button')) {
                const r = b.getBoundingClientRect();
                if (r.width <= 0) continue;
                if ((b.innerText || '').trim() === '确认') {
                  const opts = {bubbles: true, cancelable: true, view: window};
                  b.dispatchEvent(new MouseEvent('mousedown', opts));
                  b.dispatchEvent(new MouseEvent('mouseup', opts));
                  b.dispatchEvent(new MouseEvent('click', opts));
                  return true;
                }
              }
              return false;
            }"""
        )
        print("confirmed:", confirmed)
        await asyncio.sleep(4)
        await page.screenshot(path=str(SHOT / "gzh_cover_final_done.png"))

        # 6. 验证封面数据: js_file_id 有值 + 封面预览出现
        cover_state = await page.evaluate(
            """() => {
              const fileId = document.querySelector('#js_cover_area .js_file_id');
              const cdn = document.querySelector('#js_cover_area .js_cdn_url');
              const preview = document.querySelector(
                  '#js_cover_area .js_cover_preview_new');
              const btnText = document.querySelector(
                  '#js_cover_area .js_share_type_none_image');
              return {
                fileId: fileId ? fileId.value : null,
                cdn: cdn ? (cdn.value || '').slice(0, 80) : null,
                previewDisplay: preview ? getComputedStyle(preview).display : null,
                previewBg: preview ? (preview.style.backgroundImage || '').slice(0, 90) : null,
                btnTextShown: btnText ? btnText.innerText : null,
                btnTextDisplay: btnText ? getComputedStyle(btnText).display : null,
              };
            }"""
        )
        print("COVER STATE:", json.dumps(cover_state, ensure_ascii=False, indent=1))
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
