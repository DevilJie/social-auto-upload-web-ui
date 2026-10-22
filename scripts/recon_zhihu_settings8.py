# -*- coding: utf-8 -*-
"""侦察 v8: 完整 happy-path 验证 — 全部设置控件端到端走一遍。

顺序: 创作声明 → 话题 → 投稿至问题 → 内容来源 → dump 全部行状态。
"""
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


async def modal_open(page) -> bool:
    return await page.evaluate(
        """() => {
          const m = document.querySelector('.Modal-inner');
          if (!m) return false;
          const r = m.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        }"""
    )


async def close_any_modal(page):
    for _ in range(3):
        if not await modal_open(page):
            return
        try:
            await page.evaluate(
                """() => {
                  const w = document.querySelector('.Modal-wrapper');
                  if (w) w.click();
                }"""
            )
            await asyncio.sleep(1)
        except Exception:
            pass
        if await modal_open(page):
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(1)
            except Exception:
                pass
    print("modal still open?", await modal_open(page))


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
        try:
            tb = page.locator("textarea.Input").first
            await tb.wait_for(state="visible", timeout=15000)
            await tb.fill("侦察v8 完整链路")
        except Exception as e:
            print("title err:", e)
        await asyncio.sleep(2)

        # ============ 1. 创作声明 → 虚构创作 ============
        decl_trigger = page.locator("text=无声明").first
        await decl_trigger.scroll_into_view_if_needed()
        await decl_trigger.click(timeout=8000)
        await asyncio.sleep(1.5)
        opt = page.locator(
            'div[role="listbox"] button[role="option"]:has-text("虚构创作")'
        ).first
        await opt.click(timeout=5000)
        await asyncio.sleep(1)
        print("1. 创作声明已选虚构创作")

        # ============ 2. 话题: 搜索 + 选择 ============
        add_btn = page.locator('button:has-text("添加话题")').first
        await add_btn.scroll_into_view_if_needed()
        tinput = page.locator('input[aria-label="搜索话题"]').first
        vis = await tinput.is_visible()
        print("话题输入框已可见:", vis)
        if not vis:
            await add_btn.click(timeout=5000)
            await asyncio.sleep(1.5)
        tinput = page.locator('input[aria-label="搜索话题"]').first
        await tinput.click(timeout=5000)
        await tinput.press_sequentially("测试", delay=150)
        await asyncio.sleep(3)
        await dump(page, "topic_suggest", """() => {
          const vis = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          };
          const cands = [...document.querySelectorAll('div, ul')]
            .filter(vis)
            .filter((el) => (el.innerText || '').includes('测试')
              && !el.querySelector('input, textarea')
              && el.getBoundingClientRect().height < 400
              && el.getBoundingClientRect().height > 20);
          const leaf = cands.filter(
            (el) => !cands.some((o) => o !== el && el.contains(o)));
          const out = [];
          for (const el of leaf.slice(0, 3)) {
            out.push({
              cls: String(el.className).slice(0, 90),
              rect: [Math.round(el.getBoundingClientRect().width),
                     Math.round(el.getBoundingClientRect().height)],
              text: (el.innerText || '').replace(/\\s+/g, ' | ').slice(0, 150),
              items: [...el.querySelectorAll('*')]
                .filter((i) => {
                  if (!vis(i)) return false;
                  const t = (i.innerText || '').trim();
                  return t && !t.includes('\\n') && i.children.length <= 1;
                })
                .map((i) => ({tag: i.tagName, cls: String(i.className).slice(0, 70),
                              text: (i.innerText || '').trim().slice(0, 40)}))
                .slice(0, 6),
            });
          }
          return out;
        }""")
        await page.screenshot(path=str(SHOT / "recon8_topic_suggest.png"))
        # 点击第一个联想项
        picked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              // 联想浮层 = 含「测试」无 input 的最小容器;点它内部第一个项
              const cands = [...document.querySelectorAll('div, ul')]
                .filter(vis)
                .filter((el) => (el.innerText || '').includes('测试')
                  && !el.querySelector('input, textarea')
                  && el.getBoundingClientRect().height < 400
                  && el.getBoundingClientRect().height > 20);
              const leaf = cands.filter(
                (el) => !cands.some((o) => o !== el && el.contains(o)));
              if (!leaf.length) return null;
              const el = leaf[0];
              const items = [...el.querySelectorAll('*')]
                .filter((i) => vis(i) && (i.innerText || '').trim()
                  && (i.innerText || '').trim().length < 60);
              if (!items.length) return null;
              const t = (items[0].innerText || '').trim();
              items[0].click();
              return t;
            }"""
        )
        print("话题已点:", picked)
        await asyncio.sleep(2)
        await dump(page, "topic_row_after", """() => {
          const vis = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          };
          const label = [...document.querySelectorAll('*')].find(
            (e) => vis(e) && /^文章话题/.test((e.innerText || '').trim())
              && (e.innerText || '').trim().length < 12);
          if (!label) return 'no-label';
          let row = label.closest('[class]');
          for (let d = 0; d < 4 && row; d++) {
            const t = (row.innerText || '').trim();
            if (t.length > 4 && t.includes('文章话题')) {
              return {rowCls: String(row.className).slice(0, 60),
                      rowText: t.slice(0, 100),
                      rowHtml: row.innerHTML.slice(0, 2000)};
            }
            row = row.parentElement;
          }
          return 'no-row';
        }""")
        await page.screenshot(path=str(SHOT / "recon8_topic_after.png"))

        # ============ 3. 投稿至问题: 搜索 + 选择 + 确定 ============
        tq_trigger = page.locator("text=未选择").first
        await tq_trigger.scroll_into_view_if_needed()
        await tq_trigger.click(timeout=8000)
        await asyncio.sleep(2)
        print("投稿弹窗打开:", await modal_open(page))
        search = page.locator('.Modal-inner input[placeholder*="查找问题"]').first
        await search.fill("测试")
        await asyncio.sleep(0.5)
        await search.press("Enter")
        await asyncio.sleep(3)
        # dump 结果行 + 点击第一个「选择」(scope 到 Modal, 精确文本)
        rows = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              return [...document.querySelectorAll('.Modal-inner button')]
                .filter((b) => vis(b) && (b.innerText || '').trim() === '选择')
                .map((b) => String(b.className).slice(0, 80));
            }"""
        )
        print("选择按钮:", rows)
        choose = page.locator('.Modal-inner button:has-text("选择")').first
        await choose.click(timeout=5000)
        await asyncio.sleep(1.5)
        await dump(page, "tq_chosen", """() => {
          const counter = [...document.querySelectorAll('*')].find(
            (e) => {
              const r = e.getBoundingClientRect();
              return r.width > 0 && r.height > 0
                && /最多选择/.test(e.innerText || '')
                && (e.innerText || '').length < 40;
            });
          const cancelBtn = [...document.querySelectorAll('.Modal-inner button')]
            .filter((b) => /已选择|取消选择/.test((b.innerText || '').trim()))
            .map((b) => (b.innerText || '').trim().slice(0, 20));
          return {counter: counter ? counter.innerText.trim() : '', cancelBtn};
        }""")
        await page.screenshot(path=str(SHOT / "recon8_tq_chosen.png"))
        ok = page.locator('.Modal-inner button:has-text("确定")').first
        await ok.click(timeout=5000)
        await asyncio.sleep(2)
        print("投稿弹窗关闭:", not await modal_open(page))
        await dump(page, "tq_after", """() => {
          const vis = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          };
          const label = [...document.querySelectorAll('*')].find(
            (e) => vis(e) && /^投稿至问题/.test((e.innerText || '').trim())
              && (e.innerText || '').trim().length < 12);
          if (!label) return 'no-label';
          let row = label.closest('[class]');
          for (let d = 0; d < 4 && row; d++) {
            const t = (row.innerText || '').trim();
            if (t.length > 4 && t.includes('投稿至问题')) {
              return {rowCls: String(row.className).slice(0, 60),
                      rowText: t.slice(0, 150)};
            }
            row = row.parentElement;
          }
          return 'no-row';
        }""")
        await page.screenshot(path=str(SHOT / "recon8_tq_after.png"))

        # ============ 4. 内容来源: 新闻报道 + 确认添加 ============
        src_btn = page.locator('button:has-text("添加来源")').first
        await src_btn.scroll_into_view_if_needed()
        await src_btn.click(timeout=8000)
        await asyncio.sleep(2)
        print("来源弹窗打开:", await modal_open(page))
        # dump Switch 内部结构
        await dump(page, "source_switch", """() => {
          const sw = document.querySelector('.Modal-inner label.Switch');
          return sw ? sw.outerHTML.slice(0, 800) : 'no-switch';
        }""")
        trig = page.locator('.Modal-inner button[role="combobox"]').first
        await trig.click(timeout=5000)
        await asyncio.sleep(1.5)
        news = page.locator(
            'div[role="listbox"] button[role="option"]:has-text("新闻报道")'
        ).first
        await news.click(timeout=5000)
        await asyncio.sleep(1)
        conf = page.locator('.Modal-inner button:has-text("确认添加")').first
        await conf.click(timeout=5000)
        await asyncio.sleep(2)
        print("来源弹窗关闭:", not await modal_open(page))
        await dump(page, "source_after", """() => {
          const vis = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          };
          const label = [...document.querySelectorAll('*')].find(
            (e) => vis(e) && /^内容来源/.test((e.innerText || '').trim())
              && (e.innerText || '').trim().length < 12);
          if (!label) return 'no-label';
          let row = label.closest('[class]');
          for (let d = 0; d < 4 && row; d++) {
            const t = (row.innerText || '').trim();
            if (t.length > 4 && t.includes('内容来源')) {
              return {rowCls: String(row.className).slice(0, 60),
                      rowText: t.slice(0, 150)};
            }
            row = row.parentElement;
          }
          return 'no-row';
        }""")
        await page.screenshot(path=str(SHOT / "recon8_source_after.png"))

        # ============ 全部行最终状态 ============
        await dump(page, "all_rows_final", """() => {
          const vis = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          };
          const labels = ['添加封面', '投稿至问题', '创作声明', '文章话题', '定时发布', '内容来源'];
          const rows = [];
          for (const el of document.querySelectorAll('label, div')) {
            if (!vis(el)) continue;
            const t = (el.innerText || '').trim();
            for (const lb of labels) {
              if (t.startsWith(lb) && t.length < 150 && !rows.some((r) => r.label === lb)) {
                const clean = t.replace(/[\\u200B-\\u200D\\uFEFF]/g, '');
                rows.push({label: lb, tag: el.tagName,
                           cls: String(el.className).slice(0, 50), text: clean.slice(0, 140)});
              }
            }
          }
          return rows;
        }""")

        out_path = REPO / "data" / "screenshots" / "recon8_result.json"
        out_path.write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding="utf-8")
        print("saved:", out_path)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
