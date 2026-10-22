# -*- coding: utf-8 -*-
"""侦察 v7: 补齐创作声明下拉/内容来源弹窗/话题联想 的 DOM。

v6 教训: 投稿弹窗未关会遮挡后续步骤;每个控件做完必须确认弹窗关闭。
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
        """() => !!document.querySelector('.Modal-inner') && (() => {
             const m = document.querySelector('.Modal-inner');
             const r = m.getBoundingClientRect();
             return r.width > 0 && r.height > 0;
           })()"""
    )


async def close_any_modal(page):
    """关闭可能打开的弹窗: Modal-wrapper 点击 → Escape 兜底。"""
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
            await tb.fill("侦察v7")
        except Exception as e:
            print("title err:", e)
        await asyncio.sleep(2)

        # ============ 1. 创作声明下拉: dump listbox ============
        try:
            trigger = page.locator("text=无声明").first
            await trigger.scroll_into_view_if_needed()
            await trigger.click(timeout=8000)
            await asyncio.sleep(2)
            await dump(page, "decl_listbox", """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              // 全页找可见 listbox/menu 容器
              const roots = [...document.querySelectorAll(
                  '[role=listbox], [role=menu], [class*=Menu], [class*=menu-list], '
                + '[class*=Select-menu], [class*=options]')]
                .filter(vis)
                .filter((el) => /无声明|包含剧透/.test(el.innerText || ''));
              if (!roots.length) return 'no-root';
              const root = roots[roots.length - 1];
              const items = [...root.querySelectorAll(
                  'li, [role=option], [role=menuitem], button, div')]
                .filter(vis)
                .filter((el) => {
                  const t = (el.innerText || '').trim();
                  return t && t.length < 40 && el.children.length <= 2;
                });
              return {
                rootCls: String(root.className).slice(0, 90),
                rootRole: root.getAttribute('role') || '',
                rootTag: root.tagName,
                items: items.map((el) => ({
                  tag: el.tagName,
                  cls: String(el.className).slice(0, 80),
                  role: el.getAttribute('role') || '',
                  aria: el.getAttribute('aria-label') || '',
                  text: (el.innerText || '').trim().slice(0, 40),
                })).slice(0, 12),
              };
            }""")
            await page.screenshot(path=str(SHOT / "recon7_decl.png"))
            # 点「虚构创作」选项(文本精确)
            opt = page.locator(
                '[role=option]:has-text("虚构创作"), li:has-text("虚构创作")'
            ).first
            await opt.click(timeout=5000)
            await asyncio.sleep(1.5)
            await dump(page, "decl_after", """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const label = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && /^创作声明/.test((e.innerText || '').trim())
                  && (e.innerText || '').trim().length < 12);
              if (!label) return 'no-label';
              let row = label.closest('[class]');
              for (let d = 0; d < 4 && row; d++) {
                const t = (row.innerText || '').trim();
                if (t.length > 4 && t.includes('创作声明')) {
                  return {rowCls: String(row.className).slice(0, 60),
                          rowText: t.slice(0, 80),
                          comboboxes: [...row.querySelectorAll('button[role=combobox]')]
                            .map((b) => ({cls: String(b.className).slice(0, 80),
                                          text: (b.innerText || '').trim()}))};
                }
                row = row.parentElement;
              }
              return 'no-row';
            }""")
        except Exception as e:
            print("decl err:", str(e)[:200])

        await close_any_modal(page)

        # ============ 2. 内容来源弹窗 ============
        try:
            btn = page.locator('button:has-text("添加来源")').first
            await btn.scroll_into_view_if_needed(timeout=8000)
            await btn.click(timeout=8000)
            await asyncio.sleep(2)
            ok = await modal_open(page)
            print("source modal open:", ok)
            if ok:
                await dump(page, "source_modal", """() => {
                  const m = document.querySelector('.Modal-inner');
                  const serialize = (el, depth) => {
                    if (depth > 6) return null;
                    const obj = {
                      tag: el.tagName,
                      cls: String(el.className).slice(0, 60),
                      role: el.getAttribute('role') || '',
                      ph: el.getAttribute('placeholder') || '',
                      type: el.getAttribute('type') || '',
                      checked: el.type === 'checkbox' ? el.checked : undefined,
                    };
                    if (el.tagName === 'BUTTON') obj.text = (el.innerText || '').trim().slice(0, 20);
                    if (el.children.length && depth < 6) {
                      obj.children = [...el.children].slice(0, 8)
                        .map((c) => serialize(c, depth + 1));
                    } else if (!obj.text) {
                      obj.text = (el.innerText || '').trim().slice(0, 40) || undefined;
                    }
                    return obj;
                  };
                  return serialize(m, 0);
                }""")
                await page.screenshot(path=str(SHOT / "recon7_source_modal.png"))

                # 打开来源下拉
                trig = page.locator(
                    '.Modal-inner button[role="combobox"]'
                ).first
                await trig.click(timeout=5000)
                await asyncio.sleep(2)
                await dump(page, "source_options", """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const roots = [...document.querySelectorAll(
                      '[role=listbox], [role=menu], [class*=Menu]')]
                    .filter(vis)
                    .filter((el) => (el.innerText || '').trim().length > 2);
                  const root = roots[roots.length - 1];
                  if (!root) return 'no-root';
                  const items = [...root.querySelectorAll(
                      'li, [role=option], [role=menuitem], button, div')]
                    .filter(vis)
                    .filter((el) => {
                      const t = (el.innerText || '').trim();
                      return t && t.length < 40 && el.children.length <= 2;
                    });
                  return {
                    rootCls: String(root.className).slice(0, 90),
                    items: items.map((el) => ({
                      tag: el.tagName,
                      cls: String(el.className).slice(0, 80),
                      role: el.getAttribute('role') || '',
                      text: (el.innerText || '').trim().slice(0, 40),
                    })).slice(0, 12),
                  };
                }""")
                await page.screenshot(path=str(SHOT / "recon7_source_opts.png"))
                await page.keyboard.press("Escape")
                await asyncio.sleep(1)
                # 确认添加(开开关+选来源会报错吗?先只点确认看行为)
                conf = page.locator('.Modal-inner button:has-text("确认添加")').first
                await conf.click(timeout=5000)
                await asyncio.sleep(2)
                print("after confirm, modal open:", await modal_open(page))
                await page.screenshot(path=str(SHOT / "recon7_source_done.png"))
                # 若还开着(校验失败),点取消添加
                if await modal_open(page):
                    await page.locator('.Modal-inner button:has-text("取消添加")').first.click()
                    await asyncio.sleep(1)
        except Exception as e:
            print("source err:", str(e)[:200])

        await close_any_modal(page)

        # ============ 3. 文章话题联想 ============
        try:
            add_btn = page.locator('button:has-text("添加话题")').first
            await add_btn.scroll_into_view_if_needed(timeout=8000)
            # 搜索输入可能已在,先查
            tinput = page.locator('input[aria-label="搜索话题"]').first
            if not await tinput.is_visible().catch(lambda: False):
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
              // 找含「测试」且不含 input 的可见容器(浮层)
              const cands = [...document.querySelectorAll('div, ul')]
                .filter(vis)
                .filter((el) => (el.innerText || '').includes('测试')
                  && !el.querySelector('input, textarea')
                  && el.getBoundingClientRect().height < 400
                  && el.getBoundingClientRect().height > 20);
              // 取最内层的候选(子节点里还有匹配的就不选)
              const leaf = cands.filter(
                (el) => !cands.some((o) => o !== el && el.contains(o)));
              const out = [];
              for (const el of leaf.slice(0, 4)) {
                out.push({
                  cls: String(el.className).slice(0, 90),
                  rect: [Math.round(el.getBoundingClientRect().width),
                         Math.round(el.getBoundingClientRect().height)],
                  text: (el.innerText || '').replace(/\\s+/g, ' | ').slice(0, 200),
                  html: el.innerHTML.slice(0, 800),
                });
              }
              return out;
            }""")
            await page.screenshot(path=str(SHOT / "recon7_topic_suggest.png"))
        except Exception as e:
            print("topic err:", str(e)[:200])

        out_path = REPO / "data" / "screenshots" / "recon7_result.json"
        out_path.write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding="utf-8")
        print("saved:", out_path)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
