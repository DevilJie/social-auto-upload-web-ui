# -*- coding: utf-8 -*-
"""诊断2: 内容来源弹窗全流程(拍摄时间日历 DOM dump + 逐步验证)。"""
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
    await page.screenshot(path=str(SHOT / f"diag3_{tag}.png"), full_page=True)
    print(f"[shot] {tag}")


async def modal_open(page):
    return await page.evaluate(
        """() => {
          const m = document.querySelector('.Modal-inner');
          if (!m) return false;
          const r = m.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        }"""
    )


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
        await tb.fill("诊断3")

        entry = page.locator('button:has-text("添加来源")').first
        await entry.scroll_into_view_if_needed(timeout=8000)
        await entry.click(timeout=8000)
        await asyncio.sleep(2)

        # 选来源
        trig = page.locator('.Modal-inner button[role="combobox"]').first
        await trig.click()
        await asyncio.sleep(1.5)
        opt = page.locator(
            'div[role="listbox"] button[role="option"]', has_text="新闻报道"
        ).first
        await opt.click(timeout=5000)
        await asyncio.sleep(1)
        print("来源触发器:", (await trig.inner_text()).strip())

        # 开开关
        await page.evaluate(
            """() => {
              const sw = document.querySelector(
                '.Modal-inner label.Switch input.Switch-input');
              if (sw && !sw.checked) sw.click();
            }"""
        )
        await asyncio.sleep(1.5)

        # 点拍摄时间 → dump 日历 DOM
        time_trig = page.locator(
            '.Modal-inner button:has-text("选择拍摄时间")'
        ).first
        await time_trig.click()
        await asyncio.sleep(1.5)
        cal = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              // 日历面板 = 含「今天」文本的可见容器
              const today = [...document.querySelectorAll('*')]
                .filter(vis)
                .filter((e) => (e.innerText || '').trim() === '今天');
              if (!today.length) return 'no-today-elem';
              const el = today[today.length - 1];
              const chain = [];
              let cur = el;
              for (let d = 0; d < 6 && cur; d++) {
                chain.push({
                  d,
                  tag: cur.tagName,
                  cls: String(cur.className).slice(0, 70),
                  text: (cur.innerText || '').replace(/\\s+/g, '|').slice(0, 60),
                });
                cur = cur.parentElement;
              }
              return chain;
            }"""
        )
        print("「今天」元素向上链:", json.dumps(cal, ensure_ascii=False, indent=1))
        await snap(page, "1_cal_open")

        # 策略1: 点「今天」所在 button
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const cands = [...document.querySelectorAll('button')]
                .filter(vis)
                .filter((b) => (b.innerText || '').trim() === '今天');
              if (!cands.length) return false;
              cands[cands.length - 1].click();
              return true;
            }"""
        )
        print("点今天(button):", clicked)
        await asyncio.sleep(2)
        txt = ""
        try:
            txt = (await time_trig.inner_text()).strip()
        except Exception:
            txt = "(触发器文本变化,has-text 失配)"
        print("拍摄时间触发器文本:", txt)
        await snap(page, "2_after_today")

        # 若没生效,试策略2: 直接点日历上今天数字
        if txt.startswith("选择拍摄时间"):
            clicked2 = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  // 今天数字 = 日历内高亮 cell(常见 .Calendar-day--today / .is-today)
                  const sels = [
                    '.Calendar-day--today', '.is-today', '[class*=today]',
                  ];
                  for (const s of sels) {
                    const el = [...document.querySelectorAll(s)].filter(vis)[0];
                    if (el) { el.click(); return 'sel:' + s; }
                  }
                  return null;
                }"""
            )
            print("策略2:", clicked2)
            await asyncio.sleep(2)
            try:
                txt = (await time_trig.inner_text()).strip()
            except Exception:
                txt = "(失配)"
            print("拍摄时间触发器文本2:", txt)
            await snap(page, "3_after_today2")

        # 省份/城市
        prov = page.locator('.Modal-inner button[role="combobox"]').nth(1)
        await prov.click()
        await asyncio.sleep(1.5)
        popt = page.locator(
            'div[role="listbox"] button[role="option"]', has_text="北京"
        ).first
        await popt.click(timeout=5000)
        await asyncio.sleep(1.5)
        print("省份触发器:", (await prov.inner_text()).strip())

        city = page.locator('.Modal-inner button[role="combobox"]').nth(2)
        await city.click()
        await asyncio.sleep(1.5)
        copt = page.locator(
            'div[role="listbox"] button[role="option"]', has_text="北京"
        ).first
        await copt.click(timeout=5000)
        await asyncio.sleep(1.5)
        print("城市触发器:", (await city.inner_text()).strip())
        await snap(page, "4_filled")

        conf = page.locator('.Modal-inner button:has-text("确认添加")').first
        print("确认 disabled?", await conf.is_disabled())
        await conf.click()
        await asyncio.sleep(3)
        print("modal 仍开?", await modal_open(page))
        await snap(page, "5_after_confirm")

        # 行状态
        row = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const clean = (s) => (s || '')
                .replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
              const label = [...document.querySelectorAll('label')].find(
                (e) => vis(e)
                  && clean(e.innerText).trim().startsWith('内容来源')
                  && clean(e.innerText).trim().length <= 6);
              if (!label) return 'no-label';
              return clean(label.parentElement.innerText)
                .replace(/\\n/g, '|').slice(0, 100);
            }"""
        )
        print("内容来源行:", row)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
