# -*- coding: utf-8 -*-
"""知乎图片上传侦察: 工具栏「图片」按钮的 file input + 上传接口,以及
粘贴带图床 URL 的 HTML 是否直接渲染。"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"
SHOT = REPO / "data" / "screenshots"
IMG_FILE = (
    REPO / "data" / "materials" / "2026" / "09" / "14"
    / "e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()

        img_uploads = []
        page.on(
            "response",
            lambda r: img_uploads.append(
                {"status": r.status, "url": r.url[:180],
                 "body": None}
            )
            if any(k in (r.url or "") for k in ("upload", "images", "pic1", "zhimg"))
            else None,
        )

        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)

        # 点击工具栏「图片」按钮 → 触发 file chooser
        img_btn = page.locator('button:has-text("图片")').first
        await img_btn.click()
        await asyncio.sleep(2)

        # 找 file input
        inputs = await page.evaluate(
            """() => [...document.querySelectorAll('input[type=file]')].map(
                (el) => ({accept: (el.accept || '').slice(0, 60),
                          cls: String(el.className).slice(0, 60),
                          vis: el.getBoundingClientRect().width > 0}))"""
        )
        print("FILE INPUTS:", json.dumps(inputs, ensure_ascii=False, indent=1))

        # 上传文件(编辑器图片通道: accept 含 image 的隐藏 input)
        if inputs:
            ok = False
            for i, inp in enumerate(inputs):
                if "image" in inp["accept"]:
                    await page.set_input_files(
                        f'input[type=file] >> nth={i}', str(IMG_FILE)
                    )
                    print(f"file uploaded via image input #{i}")
                    ok = True
                    break
            if not ok:
                print("no image input found", json.dumps(inputs))
        else:
            # file chooser 弹窗模式
            async with page.expect_file_chooser(timeout=5000) as fc:
                await img_btn.click()
            chooser = await fc.value
            await chooser.set_files(str(IMG_FILE))
            print("file uploaded via chooser")

        # 等上传完成(图片出现在编辑器,src 为 zhimg)
        zhimg_src = ""
        for i in range(15):
            await asyncio.sleep(2)
            zhimg_src = await page.evaluate(
                """() => {
                  const img = document.querySelector(
                    '.public-DraftEditor-content img');
                  return img ? (img.src || '') : '';
                }"""
            )
            if zhimg_src.startswith("http"):
                print(f"[{i}] img src:", zhimg_src[:120])
                break
            print(f"[{i}] waiting... src={zhimg_src[:60]}")

        print("UPLOAD NET:", json.dumps(img_uploads[-6:], ensure_ascii=False, indent=1))
        await page.screenshot(path=str(SHOT / "zhihu_img_upload.png"), full_page=True)

        # 把图床 URL 拼进 HTML 再粘贴验证
        if zhimg_src.startswith("http"):
            paste_html = (
                "<h2>图床URL粘贴验证</h2>"
                f'<p><img src="{zhimg_src}" alt="图"></p><p>结尾。</p>'
            )
            await page.evaluate(
                """(html) => {
                  const ed = document.querySelector(
                      '[contenteditable="true"]');
                  ed.focus();
                  const dt = new DataTransfer();
                  dt.setData('text/html', html);
                  ed.dispatchEvent(new ClipboardEvent('paste', {
                    bubbles: true, cancelable: true, clipboardData: dt,
                  }));
                }""",
                paste_html,
            )
            await asyncio.sleep(6)
            res = await page.evaluate(
                """() => {
                  const body = document.querySelector(
                      '.public-DraftEditor-content');
                  const imgs = [...body.querySelectorAll('img')].map(
                      (im) => (im.src || '').slice(0, 100));
                  return {imgCount: imgs.length, imgs: imgs.slice(0, 5),
                          failed: body.innerText.includes('导入失败')};
                }"""
            )
            print("PASTE-URL-RESULT:", json.dumps(res, ensure_ascii=False, indent=1))
            await page.screenshot(
                path=str(SHOT / "zhihu_paste_url.png"), full_page=True
            )
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
