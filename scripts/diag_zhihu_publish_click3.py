# -*- coding: utf-8 -*-
"""诊断发布按钮 v3: 粘贴后轮询按钮状态 + 字数,再真实鼠标点击。"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"
SHOT = REPO / "data" / "screenshots"


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.set_viewport_size({"width": 1600, "height": 900})
        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)
        tb = page.locator("textarea.Input").first
        await tb.wait_for(state="visible", timeout=15000)
        await tb.fill("发布诊断v3")

        async def probe(tag):
            info = await page.evaluate(
                """() => {
                  let btn = null;
                  for (const b of document.querySelectorAll('button')) {
                    if (b.getBoundingClientRect().width <= 0) continue;
                    if ((b.innerText || '').trim() === '发布') {
                      btn = b;
                      break;
                    }
                  }
                  // 底栏字数(「字数: N」所在行)
                  const chars = [...document.querySelectorAll('*')]
                    .filter((e) => {
                      const t = e.innerText || '';
                      return /^字数[:：]/.test(t.trim())
                        && t.length < 12
                        && e.getBoundingClientRect().height > 0;
                    })
                    .map((e) => e.innerText.trim())[0];
                  return {
                    disabled: btn ? btn.disabled : null,
                    ariaDisabled: btn ? btn.getAttribute('aria-disabled') : null,
                    cls: btn ? String(btn.className).slice(0, 60) : null,
                    chars,
                  };
                }"""
            )
            print(f"[{tag}] {json.dumps(info, ensure_ascii=False)}")

        await probe("粘贴前")
        await page.evaluate(
            """(html) => {
              const ed = document.querySelector('.public-DraftEditor-content');
              ed.focus();
              const dt = new DataTransfer();
              dt.setData('text/html', html);
              ed.dispatchEvent(new ClipboardEvent('paste', {
                  bubbles: true, cancelable: true, clipboardData: dt,
              }));
            }""",
            "<p>发布按钮诊断正文段落v3,验证发表流程。测试内容,可删除。</p>",
        )
        for i in range(8):
            await asyncio.sleep(2)
            await probe(f"粘贴后{i*2}s")

        # 真实鼠标点击
        box = await page.evaluate(
            """() => {
              for (const b of document.querySelectorAll('button')) {
                if (b.getBoundingClientRect().width <= 0) continue;
                if ((b.innerText || '').trim() === '发布') {
                  const r = b.getBoundingClientRect();
                  return {x: r.x + r.width / 2, y: r.y + r.height / 2,
                          disabled: b.disabled};
                }
              }
              return null;
            }"""
        )
        print("按钮坐标:", json.dumps(box))
        if box and not box["disabled"]:
            await page.mouse.click(box["x"], box["y"])
            print("已真实鼠标点击")
            url0 = page.url
            for i in range(10):
                await asyncio.sleep(2)
                cur = page.url
                done = cur != url0 and "/edit" not in cur
                print(f"[点击后{i*2}s] url_changed={done} cur={cur}")
                if done:
                    await page.screenshot(
                        path=str(SHOT / "pub3_published.png"), full_page=True
                    )
                    print("✓ 发表跳转成功")
                    break
        else:
            await page.screenshot(
                path=str(SHOT / "pub3_still_disabled.png"), full_page=True
            )
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
