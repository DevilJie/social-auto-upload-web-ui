# -*- coding: utf-8 -*-
"""侦察自行拍摄子表单: 拍摄时间/省份/城市 三个必填控件的结构与选项。"""
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
OUT = {}


async def dump(page, tag, js):
    try:
        info = await page.evaluate(js)
        print(f"===== [{tag}] =====")
        print(json.dumps(info, ensure_ascii=False, indent=1)[:5000])
        OUT[tag] = info
    except Exception as e:
        print(f"[{tag}] ERR: {e}")


async def snap(page, tag):
    await page.screenshot(path=str(SHOT / f"diag2_{tag}.png"), full_page=True)
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
        await tb.fill("自行拍摄侦察")
        await asyncio.sleep(2)

        # 打开来源弹窗 + 开自行拍摄
        entry = page.locator('button:has-text("添加来源")').first
        await entry.scroll_into_view_if_needed(timeout=8000)
        await entry.click(timeout=8000)
        await asyncio.sleep(2)
        await page.evaluate(
            """() => {
              const sw = document.querySelector(
                '.Modal-inner label.Switch input.Switch-input');
              if (sw && !sw.checked) sw.click();
            }"""
        )
        await asyncio.sleep(1.5)
        await snap(page, "1_subform")

        # dump 子表单结构
        await dump(page, "subform", """() => {
          const m = document.querySelector('.Modal-inner');
          if (!m) return 'no-modal';
          const serialize = (el, depth) => {
            if (depth > 7) return null;
            const obj = {
              tag: el.tagName,
              cls: String(el.className).slice(0, 55),
              role: el.getAttribute('role') || '',
              ph: el.getAttribute('placeholder') || '',
              type: el.getAttribute('type') || '',
              aria: el.getAttribute('aria-label') || '',
            };
            if (el.tagName === 'BUTTON') obj.text = (el.innerText || '').trim().slice(0, 20);
            if (el.tagName === 'INPUT') obj.val = (el.value || '').slice(0, 20);
            if (el.children.length && depth < 7) {
              obj.children = [...el.children].slice(0, 10)
                .map((c) => serialize(c, depth + 1));
            } else if (!obj.text && !obj.val) {
              obj.text = (el.innerText || '').trim().slice(0, 30) || undefined;
            }
            return obj;
          };
          // 找含「拍摄时间」的子树
          const holder = [...m.querySelectorAll('*')].find(
            (e) => (e.innerText || '').includes('选择拍摄时间'));
          if (!holder) return 'no-holder';
          let root = holder;
          for (let d = 0; d < 5; d++) {
            root = root.parentElement;
            if (!root) break;
            if (String(root.className).includes('Modal-content')) break;
          }
          return serialize(root || holder, 0);
        }""")

        # 1. 拍摄时间控件: 点击触发器看下拉
        time_trig = page.locator(
            '.Modal-inner button:has-text("选择拍摄时间")'
        ).first
        cnt = await time_trig.count()
        print("拍摄时间触发器:", cnt)
        if cnt:
            await time_trig.click()
            await asyncio.sleep(1.5)
            await snap(page, "2_time_open")
            await dump(page, "time_opts", """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const roots = [...document.querySelectorAll(
                  '[role=listbox], [class*=Calendar], [class*=DatePicker], '
                + '[class*=Popover], [class*=picker]')]
                .filter(vis)
                .map((el) => ({
                  cls: String(el.className).slice(0, 80),
                  text: (el.innerText || '').replace(/\\s+/g, '|').slice(0, 150),
                }));
              return roots.slice(0, 6);
            }""")
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

        # 2. 省份控件
        prov_trig = page.locator(
            '.Modal-inner button[role="combobox"]'
        ).nth(1)
        n = await prov_trig.count()
        print("省份触发器(nth(1)):", n)
        if n:
            await prov_trig.click()
            await asyncio.sleep(1.5)
            await snap(page, "3_prov_open")
            await dump(page, "prov_opts", """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const roots = [...document.querySelectorAll('[role=listbox]')]
                .filter(vis);
              const root = roots[roots.length - 1];
              if (!root) return 'no-listbox';
              return {
                cls: String(root.className).slice(0, 80),
                items: [...root.querySelectorAll('button[role=option], li')]
                  .filter(vis)
                  .map((el) => (el.innerText || '').trim().slice(0, 20))
                  .slice(0, 40),
              };
            }""")
            # 选一个省份看城市联动
            opt = page.locator(
                'div[role="listbox"] button[role="option"]', has_text="北京"
            ).first
            if await opt.count():
                await opt.click(timeout=5000)
                await asyncio.sleep(1.5)
                city_trig = page.locator(
                    '.Modal-inner button[role="combobox"]'
                ).nth(2)
                print("城市触发器存在:", await city_trig.count())
                await city_trig.click()
                await asyncio.sleep(1.5)
                await snap(page, "4_city_open")
                await dump(page, "city_opts", """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const roots = [...document.querySelectorAll('[role=listbox]')]
                    .filter(vis);
                  const root = roots[roots.length - 1];
                  if (!root) return 'no-listbox';
                  return {
                    items: [...root.querySelectorAll('button[role=option], li')]
                      .filter(vis)
                      .map((el) => (el.innerText || '').trim().slice(0, 20))
                      .slice(0, 40),
                  };
                }""")
                await page.keyboard.press("Escape")

        out_path = REPO / "data" / "screenshots" / "diag2_result.json"
        out_path.write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding="utf-8")
        print("saved:", out_path)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
