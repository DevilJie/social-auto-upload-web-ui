# -*- coding: utf-8 -*-
"""诊断: 创作声明(xpath 修复后)/话题 chip/内容来源确认 的逐步行为。"""
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
    await page.screenshot(path=str(SHOT / f"diag_{tag}.png"), full_page=True)
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
        await tb.fill("诊断脚本")
        # 等设置区渲染(创作声明触发器可见)
        try:
            await page.locator("text=无声明").first.wait_for(
                state="visible", timeout=20000
            )
        except Exception:
            await snap(page, "0_no_settings")
            labels = await page.evaluate(
                """() => [...document.querySelectorAll('label')]
                  .filter((e) => e.getBoundingClientRect().height > 0)
                  .map((e) => (e.innerText || '')
                    .replace(/[\\u200B-\\u200D\\uFEFF]/g, '')
                    .replace(/\\n/g, '|').trim().slice(0, 30))"""
            )
            print("可见 labels:", json.dumps(labels, ensure_ascii=False))
            print("URL:", page.url)
        await asyncio.sleep(1)

        # ===== 1. 创作声明(xpath 修复验证) =====
        row_xpath = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const clean = (s) => (s || '')
                .replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
              const label = [...document.querySelectorAll('label, div, span')]
                .filter(vis)
                .find((e) => {
                  const t = clean(e.innerText).trim();
                  return t.startsWith('创作声明') && t.length <= 6;
                });
              if (!label) return 'no-label';
              let row = label;
              for (let d = 0; d < 4 && row; d++) {
                const t = clean(row.innerText).trim();
                if (t.length > 4 && row.querySelector('button, input')) break;
                row = row.parentElement;
              }
              if (!row) return 'no-row';
              const abs = [];
              let el = row;
              while (el && el.nodeType === 1 && el.tagName !== 'HTML') {
                let idx = 1;
                let sib = el;
                while ((sib = sib.previousElementSibling)) {
                  if (sib.tagName === el.tagName) idx++;
                }
                abs.unshift(`${el.tagName.toLowerCase()}[${idx}]`);
                el = el.parentElement;
              }
              return '//' + abs.join('/');
            }"""
        )
        print("声明行 xpath:", row_xpath)
        trig = page.locator(f"xpath={row_xpath}").locator(
            'button[role="combobox"]'
        ).first
        await trig.scroll_into_view_if_needed(timeout=10000)
        await trig.click()
        await asyncio.sleep(1.5)
        await snap(page, "1_decl_open")
        opt = page.locator(
            'div[role="listbox"] button[role="option"]', has_text="虚构创作"
        ).first
        await opt.click(timeout=5000)
        await asyncio.sleep(1.5)
        new_text = (await trig.inner_text()).strip()
        print("声明触发器文本:", new_text)

        # ===== 2. 话题 chip 诊断 =====
        tinput = page.locator('input[aria-label="搜索话题"]').first
        if not await tinput.is_visible():
            await page.locator('button:has-text("添加话题")').first.click()
            await asyncio.sleep(1.5)
        tinput = page.locator('input[aria-label="搜索话题"]').first
        await tinput.click()
        await tinput.press_sequentially("软件测试", delay=150)
        await asyncio.sleep(3)
        await snap(page, "2_topic_suggest")
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const kw = '软件测试';
              const cands = [...document.querySelectorAll('div, ul')]
                .filter(vis)
                .filter((el) => (el.innerText || '').includes(kw)
                  && !el.querySelector('input, textarea')
                  && el.getBoundingClientRect().height < 400
                  && el.getBoundingClientRect().height > 20);
              const leaf = cands.filter(
                (el) => !cands.some((o) => o !== el && el.contains(o)));
              for (const el of leaf) {
                const btns = [...el.querySelectorAll('button')].filter(vis);
                const exact = btns.find(
                  (b) => (b.innerText || '').trim() === kw);
                if (exact) { exact.click(); return 'exact:' + kw; }
                if (btns[0]) { btns[0].click(); return 'first:' + (btns[0].innerText || '').trim(); }
              }
              return null;
            }"""
        )
        print("话题点击:", clicked)
        await asyncio.sleep(2.5)
        await snap(page, "3_topic_after")
        row_chain = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const clean = (s) => (s || '')
                .replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
              const label = [...document.querySelectorAll('*')].find(
                (e) => vis(e)
                  && clean(e.innerText).trim().startsWith('文章话题')
                  && clean(e.innerText).trim().length <= 6);
              if (!label) return 'no-label';
              const chain = [];
              let el = label;
              for (let d = 0; d < 5 && el; d++) {
                chain.push({
                  depth: d,
                  tag: el.tagName,
                  cls: String(el.className).slice(0, 40),
                  text: clean(el.innerText).replace(/\\n/g, '|').slice(0, 80),
                });
                el = el.parentElement;
              }
              return chain;
            }"""
        )
        print("话题行向上链:", json.dumps(row_chain, ensure_ascii=False, indent=1))

        # ===== 3. 内容来源诊断 =====
        entry = page.locator('button:has-text("添加来源")').first
        await entry.scroll_into_view_if_needed(timeout=8000)
        await entry.click(timeout=8000)
        await asyncio.sleep(2)
        await snap(page, "4_source_modal")
        trig2 = page.locator('.Modal-inner button[role="combobox"]').first
        n = await trig2.count()
        print("Modal 内 combobox 数:", n)
        if n == 0:
            # dump modal 内全部 button
            btns = await page.evaluate(
                """() => [...document.querySelectorAll('.Modal-inner button')]
                  .map((b) => ({text: (b.innerText || '').trim().slice(0, 20),
                                role: b.getAttribute('role') || '',
                                cls: String(b.className).slice(0, 60)}))"""
            )
            print("Modal buttons:", json.dumps(btns, ensure_ascii=False, indent=1))
        else:
            await trig2.click()
            await asyncio.sleep(1.5)
            await snap(page, "5_source_opts")
            opt2 = page.locator(
                'div[role="listbox"] button[role="option"]', has_text="新闻报道"
            ).first
            cnt = await opt2.count()
            print("新闻报道 option 数:", cnt)
            if cnt:
                await opt2.click(timeout=5000)
                await asyncio.sleep(1.5)
            trig_txt = (await trig2.inner_text()).strip()
            print("来源触发器文本:", trig_txt)
        # 开关
        sw_state = await page.evaluate(
            """() => {
              const sw = document.querySelector(
                '.Modal-inner label.Switch input.Switch-input');
              if (!sw) return 'no-switch';
              if (!sw.checked) sw.click();
              return sw.checked;
            }"""
        )
        print("开关状态:", sw_state)
        await asyncio.sleep(1)
        conf = page.locator('.Modal-inner button:has-text("确认添加")').first
        print("确认添加 disabled?", await conf.is_disabled())
        await snap(page, "6_source_before_confirm")
        await conf.click()
        await asyncio.sleep(3)
        modal_open = await page.evaluate(
            """() => {
              const m = document.querySelector('.Modal-inner');
              if (!m) return false;
              const r = m.getBoundingClientRect();
              return r.width > 0 && r.height > 0;
            }"""
        )
        print("确认后 modal 仍开?", modal_open)
        await snap(page, "7_source_after_confirm")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
