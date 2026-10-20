# -*- coding: utf-8 -*-
"""第二轮侦察：验证 ProseMirror 粘贴 HTML（含 base64 图）是否自动上传。

实验项：
1. 枚举页面全局编辑器变量（editor/ueditor/wx.*）
2. 往正文 .ProseMirror dispatch paste(text/html)，HTML 含 h1/p/strong/ul + base64 PNG
3. 监听网络 20s 抓上传接口（filetransfer/upload*）
4. 读回正文 innerHTML，看图片是否被替换成 mmbiz.qpic.cn URL
5. 点开「文章设置」采集设置区 DOM（原创/合集/原文链接/创作来源）
6. 找工具栏「图片」按钮对应的 file input

产物: data/screenshots/gzh_paste_test.png + gzh_paste_recon.json
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


def make_test_png(width: int = 120, height: int = 80) -> str:
    """纯 Python 造一张纯色 PNG，返回 data URL（base64）。"""
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    row = b"\x00" + b"\x33\x99\xff" * width  # filter0 + 蓝色
    raw = row * height
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode()


TEST_HTML = (
    '<h1>一级标题测试</h1>'
    '<p>这是<strong>加粗文字</strong>和普通段落，验证富文本解析。</p>'
    '<ul><li>列表项一</li><li>列表项二</li></ul>'
    f'<p><img src="{make_test_png()}" alt="测试图"></p>'
    '<p>图片之后的段落。结尾段落。</p>'
)

PASTE_JS = """(html) => {
  const pms = [...document.querySelectorAll('.ProseMirror')]
    .filter((el) => el.getBoundingClientRect().height > 0);
  // 正文 = 带 placeholder 提示 / 第二个可见实例（第一个是标题）
  const body = pms.length > 1 ? pms[1] : pms[0];
  body.focus();
  const dt = new DataTransfer();
  dt.setData('text/html', html);
  dt.setData('text/plain', 'rich-text-paste-test');
  const ev = new ClipboardEvent('paste', {
    bubbles: true, cancelable: true, clipboardData: dt,
  });
  body.dispatchEvent(ev);
  return {count: pms.length, usedIndex: pms.indexOf(body)};
}"""


async def main() -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()

        uploads: list[list] = []
        page.on(
            "response",
            lambda r: uploads.append([r.status, r.request.method, r.url[:200]])
            if any(k in (r.url or "") for k in ("filetransfer", "upload", "operappmsg"))
            and "/cgi-bin/" in r.url
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

        # 1. 全局编辑器变量枚举
        globals_info = await page.evaluate(
            """() => {
              const out = {};
              for (const k of Object.keys(window)) {
                if (/editor|ueditor|prose|draft/i.test(k)) {
                  try { out[k] = typeof window[k]; } catch (e) {}
                }
              }
              out['wx.commonData.keys'] = (() => {
                try { return Object.keys(window.wx.commonData || {}).slice(0, 40); }
                catch (e) { return []; }
              })();
              out['window.editor?'] = (() => {
                try {
                  const ed = window.editor;
                  if (!ed) return null;
                  return Object.keys(ed).slice(0, 30);
                } catch (e) { return null; }
              })();
              return out;
            }"""
        )
        print("GLOBALS:", json.dumps(globals_info, ensure_ascii=False, indent=1))

        # 2. 粘贴 HTML（含 base64 图）
        paste_ret = await page.evaluate(PASTE_JS, TEST_HTML)
        print("PASTE_RET:", paste_ret)
        await asyncio.sleep(3)
        await page.screenshot(
            path=str(SHOT_DIR / "gzh_paste_immediate.png"), full_page=True
        )

        # 3. 等图片自动上传（监听网络 + 轮询 innerHTML 变化）
        body_html = ""
        for i in range(12):
            await asyncio.sleep(2.5)
            body_html = await page.evaluate(
                """() => {
                  const pms = [...document.querySelectorAll('.ProseMirror')]
                    .filter((el) => el.getBoundingClientRect().height > 0);
                  const body = pms.length > 1 ? pms[1] : pms[0];
                  return body ? body.innerHTML : '';
                }"""
            )
            has_b64 = "data:image" in body_html
            has_mmbiz = "mmbiz.qpic.cn" in body_html
            print(f"[poll {i}] len={len(body_html)} base64={has_b64} mmbiz={has_mmbiz} "
                  f"uploads={len(uploads)}")
            if has_mmbiz or (i >= 3 and not has_b64 and len(body_html) > 50):
                break

        await page.screenshot(
            path=str(SHOT_DIR / "gzh_paste_test.png"), full_page=True
        )

        # 4. 点「文章设置」展开设置区，采集 DOM
        try:
            await page.get_by_text("文章设置", exact=True).click(timeout=5000)
            await asyncio.sleep(2)
        except Exception as e:
            print("open article settings (non-fatal):", e)
        settings_dom = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const rows = [];
              for (const el of document.querySelectorAll(
                  '.weui-desktop-form__label, .frm_label, .setting_label, label')) {
                if (vis(el)) {
                  const t = (el.innerText || '').trim().replace(/\\s+/g, ' ');
                  if (t && t.length < 20) rows.push(t);
                }
              }
              const files = [...document.querySelectorAll('input[type=file]')].map((el) => ({
                accept: (el.accept || '').slice(0, 60), cls: String(el.className).slice(0, 60),
                vis: vis(el),
              }));
              const labels = [...document.querySelectorAll('a, .weui-desktop-link, [class*=link]')]
                .filter(vis).map((el) => (el.innerText || '').trim())
                .filter((t) => t && t.length < 16);
              return {rows: [...new Set(rows)], fileInputs: files, links: [...new Set(labels)].slice(0, 40)};
            }"""
        )
        print("SETTINGS_DOM:", json.dumps(settings_dom, ensure_ascii=False, indent=1))
        await page.screenshot(
            path=str(SHOT_DIR / "gzh_article_settings.png"), full_page=True
        )

        result = {
            "globals": globals_info,
            "paste_ret": paste_ret,
            "uploads": uploads,
            "body_html_head": body_html[:3000],
            "settings_dom": settings_dom,
        }
        out = SHOT_DIR / "gzh_paste_recon.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print("UPLOADS:", json.dumps(uploads, ensure_ascii=False, indent=1))
        print("saved →", out)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
