# -*- coding: utf-8 -*-
"""清理知乎测试草稿 v2: 从「删除」链接向上爬行容器匹配关键词。"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl._browser import create_browser, create_context  # noqa: E402

COOKIE = REPO / "data" / "cookiesFile" / "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"

KEYWORDS = ["千帆同步", "诊断", "侦察"]


async def main() -> None:
    browser = await create_browser(headless=True)
    deleted = 0
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.goto(
            "https://zhuanlan.zhihu.com/drafts",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(8)

        # 先 dump 第一个「删除」向上链,了解结构
        chain = await page.evaluate(
            """() => {
              const del = [...document.querySelectorAll('a, button, span')]
                .filter((e) => (e.innerText || '').trim() === '删除')[0];
              if (!del) return 'no-del';
              const out = [];
              let cur = del;
              for (let d = 0; d < 6 && cur; d++) {
                out.push({
                  d,
                  tag: cur.tagName,
                  cls: String(cur.className).slice(0, 50),
                  text: (cur.innerText || '').replace(/\\s+/g, ' ')
                    .slice(0, 60),
                });
                cur = cur.parentElement;
              }
              return out;
            }"""
        )
        print("删除链接向上链:", chain)

        for _round in range(40):
            clicked = await page.evaluate(
                """(keywords) => {
                  const dels = [...document.querySelectorAll('a, button, span')]
                    .filter((e) => {
                      if ((e.innerText || '').trim() !== '删除') return false;
                      const r = e.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    });
                  for (const del of dels) {
                    let cur = del;
                    for (let d = 0; d < 6 && cur; d++) {
                      const t = cur.innerText || '';
                      if (keywords.some((k) => t.includes(k))) {
                        del.click();
                        return t.replace(/\\s+/g, ' ').slice(0, 40);
                      }
                      cur = cur.parentElement;
                    }
                  }
                  return null;
                }""",
                KEYWORDS,
            )
            if not clicked:
                break
            await asyncio.sleep(1.5)
            # 确认弹窗(实测按钮文案为「确认」)
            await page.evaluate(
                """() => {
                  const m = document.querySelector('.Modal-inner');
                  if (!m) return;
                  for (const b of m.querySelectorAll('button')) {
                    if ((b.innerText || '').trim() === '确认') { b.click(); return; }
                  }
                }"""
            )
            await asyncio.sleep(2)
            deleted += 1
            print(f"deleted: {clicked}")
        print(f"total deleted {deleted} draft(s)")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
