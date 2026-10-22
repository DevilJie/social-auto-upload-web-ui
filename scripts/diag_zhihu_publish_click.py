# -*- coding: utf-8 -*-
"""诊断发布按钮: 点击「发布」后的真实行为(弹窗/校验/URL 变化)。"""
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
    await page.screenshot(path=str(SHOT / f"pub_{tag}.png"), full_page=True)
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
        await tb.fill("发布按钮诊断稿")
        await asyncio.sleep(1)
        url0 = page.url
        print("点击前 URL:", url0)

        # 发布按钮状态
        state = await page.evaluate(
            """() => {
              for (const b of document.querySelectorAll('button')) {
                if (b.getBoundingClientRect().width <= 0) continue;
                if ((b.innerText || '').trim() === '发布') {
                  return {
                    disabled: b.disabled,
                    cls: String(b.className).slice(0, 90),
                    aria: b.getAttribute('aria-label') || '',
                    type: b.getAttribute('type') || '',
                  };
                }
              }
              return null;
            }"""
        )
        print("发布按钮状态:", json.dumps(state, ensure_ascii=False))

        # 真实点击(Playwright)
        btn = page.locator('button:has-text("发布")').first
        # 精确过滤文本恰为「发布」
        btn = page.locator(
            'button', has_text="发布"
        ).filter(
            has_text=lambda: False
        ) if False else btn
        # 用 evaluate 找到精确按钮的序号,再用 nth 点(保证真实输入事件)
        idx = await page.evaluate(
            """() => {
              const btns = [...document.querySelectorAll('button')]
                .filter((b) => b.getBoundingClientRect().width > 0);
              return btns.findIndex(
                (b) => (b.innerText || '').trim() === '发布');
            }"""
        )
        print("发布按钮序号:", idx)
        real_btn = page.locator("button", has_text="").nth(idx) if idx >= 0 else None
        # 上面 nth 不精确;直接用 JS 全事件序列点击
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
                  return true;
                }
              }
              return false;
            }"""
        )
        print("JS 全事件点击:", clicked)
        await asyncio.sleep(2)
        await snap(page, "1_after_click_2s")
        print("URL 2s后:", page.url)

        # 弹窗检测
        for i in range(10):
            await asyncio.sleep(2)
            modal = await page.evaluate(
                """() => {
                  const m = document.querySelector('.Modal-inner');
                  if (!m) return null;
                  const r = m.getBoundingClientRect();
                  if (r.width <= 0) return null;
                  return {
                    title: (m.querySelector('.Modal-title') || {})
                      .innerText || '',
                    text: (m.innerText || '').replace(/\\s+/g, ' ')
                      .slice(0, 200),
                    buttons: [...m.querySelectorAll('button')]
                      .map((b) => (b.innerText || '').trim())
                      .filter((t) => t).slice(0, 8),
                  };
                }"""
            )
            cur_url = page.url
            changed = cur_url != url0 and "/edit" not in cur_url
            print(f"[{i}] url={cur_url} changed={changed} modal={json.dumps(modal, ensure_ascii=False) if modal else None}")
            if modal:
                await snap(page, f"2_modal_{i}")
                break
            if changed:
                await snap(page, "3_published")
                break
        print("最终 URL:", page.url)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
