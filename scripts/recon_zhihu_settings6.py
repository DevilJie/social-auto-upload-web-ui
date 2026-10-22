# -*- coding: utf-8 -*-
"""侦察 v6: DOM 级精确采集各设置控件的弹层结构。

1. 创作声明下拉 → 打开后 dump 选项 DOM
2. 投稿至问题 → 打开弹窗 dump 结构 → 搜索 → dump 结果行 → 选择 → 确定
3. 内容来源 → 打开弹窗 dump 结构 → 来源下拉选项 dump → 自行拍摄开关
4. 文章话题 → 输入 → dump 联想下拉 → 选中 → dump chip
5. 封面 → set_input_files → dump 上传后状态(裁剪弹窗?)
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

# 一张测试封面图(素材库里已有的)
COVER = None
for p in (REPO / "data" / "materials").rglob("*.jpg"):
    COVER = str(p)
    break


async def dump_tree(page, tag, js):
    try:
        info = await page.evaluate(js)
        print(f"===== [{tag}] =====")
        print(json.dumps(info, ensure_ascii=False, indent=1)[:6000])
        OUT[tag] = info
    except Exception as e:
        print(f"[{tag}] ERR: {e}")


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
            await tb.fill("侦察v6")
        except Exception as e:
            print("title err:", e)
        await asyncio.sleep(2)

        # ============ 1. 创作声明下拉 ============
        try:
            await page.locator("text=无声明").first.scroll_into_view_if_needed()
            await page.locator("text=无声明").first.click(timeout=8000)
            await asyncio.sleep(2)
            await dump_tree(page, "decl_open", """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              // 找含「无声明」或「包含剧透」的可见容器及其列表结构
              const anchor = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && /包含剧透/.test(e.innerText || ''));
              if (!anchor) return 'no-anchor';
              // 向上找列表根(含多个选项的容器)
              let root = anchor;
              for (let d = 0; d < 6; d++) {
                const p = root.parentElement;
                if (!p) break;
                root = p;
                if (root.querySelectorAll('li, [role=option], [class*=Menu-item]').length >= 3) break;
              }
              const serialize = (el, depth) => {
                if (depth > 4) return null;
                const r = el.getBoundingClientRect();
                const obj = {
                  tag: el.tagName,
                  cls: String(el.className).slice(0, 70),
                  role: el.getAttribute('role') || '',
                  aria: el.getAttribute('aria-label') || '',
                  rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
                };
                if (el.children.length && depth < 4) {
                  obj.children = [...el.children].slice(0, 12).map((c) => serialize(c, depth + 1));
                } else {
                  obj.text = (el.innerText || '').trim().slice(0, 40);
                }
                return obj;
              };
              return serialize(root, 0);
            }""")
            await page.screenshot(path=str(SHOT / "recon6_decl.png"))
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
        except Exception as e:
            print("decl err:", str(e)[:200])

        # ============ 2. 投稿至问题弹窗 ============
        try:
            await page.locator("text=未选择").first.scroll_into_view_if_needed()
            await page.locator("text=未选择").first.click(timeout=8000)
            await asyncio.sleep(2)
            await dump_tree(page, "targetq_modal", """() => {
              const anchor = [...document.querySelectorAll('*')].find(
                (e) => (e.innerText || '').trim() === '投稿至问题'
                  && e.getBoundingClientRect().height > 0
                  && e.getBoundingClientRect().height < 60);
              if (!anchor) return 'no-modal';
              // modal 根 = 向上找到含搜索框和按钮的容器
              let root = anchor;
              for (let d = 0; d < 10; d++) {
                const p = root.parentElement;
                if (!p) break;
                root = p;
                if (root.querySelectorAll('input').length >= 1
                    && root.querySelectorAll('button').length >= 2) break;
              }
              const serialize = (el, depth) => {
                if (depth > 6) return null;
                const obj = {
                  tag: el.tagName,
                  cls: String(el.className).slice(0, 60),
                  role: el.getAttribute('role') || '',
                  ph: el.getAttribute('placeholder') || '',
                  aria: el.getAttribute('aria-label') || '',
                };
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') obj.isInput = true;
                if (el.tagName === 'BUTTON') obj.text = (el.innerText || '').trim().slice(0, 20);
                if (el.children.length && depth < 6) {
                  obj.children = [...el.children].slice(0, 10).map((c) => serialize(c, depth + 1));
                } else if (!obj.text) {
                  obj.text = (el.innerText || '').trim().slice(0, 50) || undefined;
                }
                return obj;
              };
              return serialize(root, 0);
            }""")
            await page.screenshot(path=str(SHOT / "recon6_tq_modal.png"))

            # 搜索问题
            search = page.locator('input[placeholder*="查找问题"]').first
            await search.fill("测试")
            await asyncio.sleep(0.5)
            await search.press("Enter")
            await asyncio.sleep(3)
            await dump_tree(page, "targetq_results", """() => {
              // 搜索后 dump 结果列表: 每行标题/元信息/选择按钮的 DOM 路径
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const rows = [];
              const chooseBtns = [...document.querySelectorAll('button')]
                .filter((b) => vis(b) && (b.innerText || '').trim() === '选择');
              for (const btn of chooseBtns.slice(0, 3)) {
                // 行根 = 向上到含标题文本的容器
                let row = btn;
                for (let d = 0; d < 6; d++) {
                  row = row.parentElement;
                  if (!row) break;
                  if ((row.innerText || '').includes('回答')) break;
                }
                rows.push({
                  rowCls: row ? String(row.className).slice(0, 60) : '',
                  rowText: row ? (row.innerText || '').replace(/\\s+/g, ' | ').slice(0, 120) : '',
                  btnCls: String(btn.className).slice(0, 70),
                });
              }
              // 已选择计数区
              const counter = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && /最多选择/.test(e.innerText || '')
                  && (e.innerText || '').length < 40);
              return {
                rows,
                counterCls: counter ? String(counter.className).slice(0, 60) : '',
                counterText: counter ? counter.innerText.trim() : '',
              };
            }""")
            await page.screenshot(path=str(SHOT / "recon6_tq_results.png"))

            # 点第一个「选择」→ 确定
            choose = page.locator('button:has-text("选择")').first
            await choose.click(timeout=5000)
            await asyncio.sleep(1)
            await dump_tree(page, "targetq_chosen", """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const counter = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && /最多选择/.test(e.innerText || '')
                  && (e.innerText || '').length < 40);
              const chosen = [...document.querySelectorAll('button')]
                .filter((b) => vis(b) && /已选择|已选/.test((b.innerText || '').trim()))
                .map((b) => (b.innerText || '').trim().slice(0, 30));
              const ok = [...document.querySelectorAll('button')]
                .filter((b) => vis(b) && (b.innerText || '').trim() === '确定')
                .map((b) => String(b.className).slice(0, 70));
              return {counter: counter ? counter.innerText.trim() : '', chosen, ok};
            }""")
            ok_btn = page.locator('button:has-text("确定")').first
            await ok_btn.click(timeout=5000)
            await asyncio.sleep(2)
            await dump_tree(page, "targetq_after", """() => {
              // 弹窗关闭后,投稿至问题行的下拉触发器显示什么
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const label = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && /^投稿至问题/.test((e.innerText || '').trim())
                  && (e.innerText || '').trim().length < 12);
              if (!label) return 'no-label';
              let row = label.closest('[class]');
              for (let d = 0; d < 3 && row; d++) {
                const t = (row.innerText || '').trim();
                if (t && t.length > 4 && t.includes('投稿至问题')) {
                  return {rowCls: String(row.className).slice(0, 80), rowText: t.slice(0, 120)};
                }
                row = row.parentElement;
              }
              return 'no-row';
            }""")
            await page.screenshot(path=str(SHOT / "recon6_tq_after.png"))
        except Exception as e:
            print("targetq err:", str(e)[:200])

        # ============ 3. 内容来源弹窗 ============
        try:
            await page.locator("text=添加来源").first.scroll_into_view_if_needed()
            await page.locator("text=添加来源").first.click(timeout=8000)
            await asyncio.sleep(2)
            await dump_tree(page, "source_modal", """() => {
              const anchor = [...document.querySelectorAll('*')].find(
                (e) => (e.innerText || '').trim() === '添加内容来源'
                  && e.getBoundingClientRect().height > 0
                  && e.getBoundingClientRect().height < 60);
              if (!anchor) return 'no-modal';
              let root = anchor;
              for (let d = 0; d < 10; d++) {
                const p = root.parentElement;
                if (!p) break;
                root = p;
                if (root.querySelectorAll('button').length >= 2) break;
              }
              const serialize = (el, depth) => {
                if (depth > 6) return null;
                const r = el.getBoundingClientRect();
                const obj = {
                  tag: el.tagName,
                  cls: String(el.className).slice(0, 60),
                  role: el.getAttribute('role') || '',
                  ph: el.getAttribute('placeholder') || '',
                  aria: el.getAttribute('aria-label') || '',
                  type: el.getAttribute('type') || '',
                  rect: [Math.round(r.width), Math.round(r.height)],
                };
                if (el.tagName === 'BUTTON') obj.text = (el.innerText || '').trim().slice(0, 20);
                if (el.children.length && depth < 6) {
                  obj.children = [...el.children].slice(0, 8).map((c) => serialize(c, depth + 1));
                } else if (!obj.text) {
                  obj.text = (el.innerText || '').trim().slice(0, 40) || undefined;
                }
                return obj;
              };
              return serialize(root, 0);
            }""")
            await page.screenshot(path=str(SHOT / "recon6_source_modal.png"))

            # 打开「选择具体的信息来源」下拉
            trigger = page.locator(
                '[class*="Modal"] button[role="combobox"], '
                '[aria-label*="来源"] button[role="combobox"], '
                'button[role="combobox"]:has-text("选择具体的信息来源")'
            ).first
            await trigger.click(timeout=5000)
            await asyncio.sleep(2)
            await dump_tree(page, "source_options", """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const anchor = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && /新闻媒体|自媒体|机构/.test(e.innerText || '')
                  && (e.innerText || '').length < 200);
              if (!anchor) {
                // 兜底: 全部可见 li/[role=option]
                return [...document.querySelectorAll('li, [role=option]')]
                  .filter(vis)
                  .map((el) => ({cls: String(el.className).slice(0, 60),
                                 text: (el.innerText || '').trim().slice(0, 30)}))
                  .filter((o) => o.text).slice(0, 15);
              }
              let root = anchor;
              for (let d = 0; d < 6; d++) {
                const p = root.parentElement;
                if (!p) break;
                root = p;
                if (root.querySelectorAll('li, [role=option]').length >= 3) break;
              }
              return [...root.querySelectorAll('li, [role=option], [class*=Menu-item]')]
                .filter(vis)
                .map((el) => ({tag: el.tagName, cls: String(el.className).slice(0, 70),
                               role: el.getAttribute('role') || '',
                               text: (el.innerText || '').trim().slice(0, 30)}));
            }""")
            await page.screenshot(path=str(SHOT / "recon6_source_opts.png"))
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
            # 关闭来源弹窗(取消添加)
            try:
                cancel = page.locator('button:has-text("取消添加")').first
                await cancel.click(timeout=5000)
                await asyncio.sleep(1)
            except Exception:
                await page.keyboard.press("Escape")
        except Exception as e:
            print("source err:", str(e)[:200])

        # ============ 4. 文章话题 ============
        try:
            topic_input = page.locator('input[aria-label="搜索话题"], input[placeholder*="搜索话题"]').first
            await topic_input.scroll_into_view_if_needed(timeout=8000)
            # 若输入框未出现,先点添加话题
            if not await topic_input.is_visible():
                await page.locator("text=添加话题").first.click(timeout=5000)
                await asyncio.sleep(1.5)
            await topic_input.click()
            await topic_input.press_sequentially("测试", delay=150)
            await asyncio.sleep(3)
            await dump_tree(page, "topic_suggest", """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              // 联想下拉 = 含「测试」文本的浮层(排除输入框本身)
              const cands = [...document.querySelectorAll(
                  '[class*=Menu], [class*=Popover], [class*=popover], [class*=dropdown], '
                + '[class*=Popup], [role=listbox], [role=menu], ul, [class*=Modal]')]
                .filter(vis)
                .filter((el) => (el.innerText || '').includes('测试')
                  && !el.querySelector('input'))
                .map((el) => ({
                  cls: String(el.className).slice(0, 80),
                  role: el.getAttribute('role') || '',
                  text: (el.innerText || '').replace(/\\s+/g, ' | ').slice(0, 200),
                  items: [...el.querySelectorAll('li, [role=option], button, [class*=item]')]
                    .filter(vis)
                    .map((i) => ({tag: i.tagName, cls: String(i.className).slice(0, 60),
                                  text: (i.innerText || '').trim().slice(0, 40)}))
                    .slice(0, 8),
                }));
              return cands.slice(0, 6);
            }""")
            await page.screenshot(path=str(SHOT / "recon6_topic_suggest.png"))
            # 选第一个联想项(通用: 点击含「话题」高亮或第一个 li)
            picked = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  // 常见结构: 浮层里的 li/button;点第一个
                  const items = [...document.querySelectorAll(
                      '[role=option], [class*=Menu-item], li')]
                    .filter(vis)
                    .filter((el) => (el.innerText || '').trim()
                      && el.getBoundingClientRect().top > 300);
                  if (items.length) {
                    const t = (items[0].innerText || '').trim().slice(0, 40);
                    items[0].click();
                    return t;
                  }
                  return null;
                }"""
            )
            print("topic picked:", picked)
            await asyncio.sleep(2)
            await dump_tree(page, "topic_chip", """() => {
              // 话题行: label「文章话题」所在行 dump
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const label = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && /^文章话题/.test((e.innerText || '').trim())
                  && (e.innerText || '').trim().length < 12);
              if (!label) return 'no-label';
              let row = label.closest('[class]');
              for (let d = 0; d < 3 && row; d++) {
                const t = (row.innerText || '').trim();
                if (t.length > 4 && t.includes('文章话题')) {
                  return {rowCls: String(row.className).slice(0, 80),
                          rowHtml: row.innerHTML.slice(0, 1500)};
                }
                row = row.parentElement;
              }
              return 'no-row';
            }""")
            await page.screenshot(path=str(SHOT / "recon6_topic_chip.png"))
        except Exception as e:
            print("topic err:", str(e)[:200])

        # ============ 5. 封面上传后状态 ============
        if COVER:
            try:
                cover_input = page.locator(
                    'input[type=file].UploadPicture-input, '
                    'input[type=file][accept=".jpeg, .jpg, .png"]'
                ).first
                await cover_input.set_input_files(COVER)
                await asyncio.sleep(6)
                await dump_tree(page, "cover_after", """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  // 封面行 dump + 是否出现裁剪弹窗/按钮
                  const label = [...document.querySelectorAll('*')].find(
                    (e) => vis(e) && /^添加封面$/.test((e.innerText || '').trim()));
                  let rowHtml = '';
                  if (label) {
                    let row = label.closest('[class]');
                    for (let d = 0; d < 3 && row; d++) {
                      const t = (row.innerText || '').trim();
                      if (t.length > 4 && t.includes('添加封面')) {
                        rowHtml = row.innerHTML.slice(0, 1500);
                        break;
                      }
                      row = row.parentElement;
                    }
                  }
                  const modalBtns = [...document.querySelectorAll('button')]
                    .filter(vis)
                    .map((b) => (b.innerText || '').trim())
                    .filter((t) => t && t.length < 15);
                  const imgs = [...document.querySelectorAll('img')]
                    .filter(vis)
                    .map((im) => ({src: im.src.slice(0, 80),
                                   cls: String(im.className).slice(0, 50)}))
                    .slice(0, 6);
                  return {rowHtml, modalBtns: modalBtns.slice(0, 20), imgs};
                }""")
                await page.screenshot(path=str(SHOT / "recon6_cover_after.png"))
            except Exception as e:
                print("cover err:", str(e)[:200])

        out_path = REPO / "data" / "screenshots" / "recon6_result.json"
        out_path.write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding="utf-8")
        print("saved:", out_path)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
