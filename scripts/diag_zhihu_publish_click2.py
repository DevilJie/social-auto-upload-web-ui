# -*- coding: utf-8 -*-
"""诊断发布按钮 v2: 带正文粘贴,点击后观察 30s(弹窗/URL/截图)。"""
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


async def snap(page, tag):
    await page.screenshot(path=str(SHOT / f"pub2_{tag}.png"), full_page=True)
    print(f"[shot] {tag}")


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
        await tb.fill("发布诊断v2")

        # 粘贴正文(与 publish_article 同方式)
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
            "<p>发布按钮诊断正文段落,验证发表流程。测试内容,可删除。</p>",
        )
        await asyncio.sleep(4)

        state = await page.evaluate(
            """() => {
              for (const b of document.querySelectorAll('button')) {
                if (b.getBoundingClientRect().width <= 0) continue;
                if ((b.innerText || '').trim() === '发布') {
                  return {disabled: b.disabled};
                }
              }
              return null;
            }"""
        )
        print("发布按钮状态:", json.dumps(state, ensure_ascii=False))

        url0 = page.url
        clicked = await page.evaluate(
            """() => {
              for (const b of document.querySelectorAll('button')) {
                if (b.getBoundingClientRect().width <= 0) continue;
                if ((b.innerText || '').trim() === '发布') {
                  const opts = {
                      bubbles: true, cancelable: true, view: window,
                  };
                  b.dispatchEvent(new PointerEvent('pointerdown', opts));
                  b.dispatchEvent(new MouseEvent('mousedown', opts));
                  b.dispatchEvent(new PointerEvent('pointerup', opts));
                  b.dispatchEvent(new MouseEvent('mouseup', opts));
                  b.dispatchEvent(new MouseEvent('click', opts));
                  return !b.disabled;
                }
              }
              return false;
            }"""
        )
        print("点击(按钮可用?):", clicked)

        for i in range(15):
            await asyncio.sleep(2)
            cur = page.url
            modal = await page.evaluate(
                """() => {
                  const m = document.querySelector('.Modal-inner');
                  if (!m) return null;
                  const r = m.getBoundingClientRect();
                  if (r.width <= 0) return null;
                  return {
                    title: ((m.querySelector('.Modal-title') || {}).innerText || '').trim(),
                    text: (m.innerText || '').replace(/\\s+/g, ' ').slice(0, 250),
                    buttons: [...m.querySelectorAll('button')]
                      .map((b) => ({t: (b.innerText || '').trim(),
                                    disabled: b.disabled}))
                      .filter((x) => x.t).slice(0, 8),
                  };
                }"""
            )
            done = cur != url0 and "/edit" not in cur
            toast = await page.evaluate(
                """() => {
                  const els = [...document.querySelectorAll(
                      '[class*=Toast], [class*=toast], [class*=Notice]')];
                  return els
                    .filter((e) => e.getBoundingClientRect().height > 0)
                    .map((e) => (e.innerText || '').trim().slice(0, 60))
                    .filter((t) => t).slice(0, 3);
                }"""
            )
            print(f"[{i*2}s] url_changed={done} modal={json.dumps(modal, ensure_ascii=False) if modal else '-'} toast={toast}")
            if i == 0:
                await snap(page, "0_after_2s")
            if modal:
                await snap(page, f"1_modal_{i*2}s")
                # 尝试点弹窗内确认类按钮
                ok = await page.evaluate(
                    """() => {
                      const m = document.querySelector('.Modal-inner');
                      if (!m) return null;
                      for (const b of m.querySelectorAll('button')) {
                        const t = (b.innerText || '').trim();
                        if (['确认发布', '确认', '发布', '继续发布'].includes(t)
                            && !b.disabled) {
                          b.click();
                          return t;
                        }
                      }
                      return null;
                    }"""
                )
                print("点弹窗按钮:", ok)
                await asyncio.sleep(3)
                continue
            if done:
                await snap(page, "2_done")
                print("✓ 发表跳转成功:", cur)
                break
        print("最终 URL:", page.url)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
