# -*- coding: utf-8 -*-
"""清理公众号草稿箱中的测试草稿(标题含「千帆同步」或「上传接口验证」)。"""
import asyncio
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
TARGET_MARKS = ("千帆同步", "上传接口验证", "未命名文章", "批量发布验证", "显式封面功能测试")


async def main() -> None:
    browser = await create_browser(headless=True)
    deleted = 0
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
            f"https://mp.weixin.qq.com/cgi-bin/appmsg?begin=0&count=10"
            f"&type=77&action=list_card&token={token}&lang=zh_CN",
            wait_until="domcontentloaded",
            timeout=40000,
        )
        await asyncio.sleep(8)

        # 草稿卡片可能一页放不下,最多清 2 轮
        for round_no in range(2):
            candidates = await page.evaluate(
                """(marks) => {
                  const hits = [];
                  const cards = document.querySelectorAll(
                    '.weui-desktop-card, .card_masssend, tr, .js_card'
                  );
                  for (const card of cards) {
                    const text = (card.innerText || '').trim();
                    if (!text) continue;
                    const isTarget = marks.some((m) => text.includes(m));
                    if (!isTarget) continue;
                    // 卡片内找删除入口(文案「删除」的可点元素)
                    const del = [...card.querySelectorAll(
                      'a, .weui-desktop-link, button, span.js_del, [class*=del]'
                    )].find((el) => (el.innerText || '').trim() === '删除');
                    if (del) hits.push({found: true});
                  }
                  return hits.length;
                }""",
                list(TARGET_MARKS),
            )
            if not candidates:
                break

            clicked = await page.evaluate(
                """(marks) => {
                  const cards = document.querySelectorAll(
                    '.weui-desktop-card, .card_masssend, tr, .js_card'
                  );
                  for (const card of cards) {
                    const text = (card.innerText || '').trim();
                    if (!marks.some((m) => text.includes(m))) continue;
                    const del = [...card.querySelectorAll(
                      'a, .weui-desktop-link, button, span.js_del, [class*=del]'
                    )].find((el) => (el.innerText || '').trim() === '删除');
                    if (del) { del.click(); return true; }
                  }
                  return false;
                }""",
                list(TARGET_MARKS),
            )
            if not clicked:
                break
            await asyncio.sleep(2)
            # 确认弹窗(「确定」/「删除」primary 按钮)
            confirmed = await page.evaluate(
                """() => {
                  const btns = document.querySelectorAll(
                    '.weui-desktop-dialog button.weui-desktop-btn_primary, ' +
                    '.weui-desktop-dialog button'
                  );
                  for (const b of btns) {
                    const t = (b.textContent || '').trim();
                    if ((t === '确定' || t === '删除') &&
                        !b.className.includes('disabled')) {
                      const wrp = b.closest('.weui-desktop-dialog__wrp');
                      if (wrp && wrp.style.display === 'none') continue;
                      b.click();
                      return t;
                    }
                  }
                  return null;
                }"""
            )
            print(f"[round {round_no}] clicked delete, confirm={confirmed}")
            await asyncio.sleep(3)
            deleted += 1

        print(f"deleted {deleted} draft(s)")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
