# -*- coding: utf-8 -*-
"""侦察知乎发布设置区: 投稿至问题/创作声明/话题/定时/内容来源 的 DOM 与交互。"""
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


async def main() -> None:
    browser = await create_browser(headless=True)
    try:
        ctx = await create_context(browser, storage_state=str(COOKIE))
        page = await ctx.new_page()
        await page.goto(
            "https://zhuanlan.zhihu.com/write",
            wait_until="domcontentloaded", timeout=40000,
        )
        await asyncio.sleep(10)

        async def dump_settings(tag):
            info = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  // 发布设置区 = 「发布设置」标题之后的区域
                  const settings = [];
                  const rows = [...document.querySelectorAll('*')].filter(
                    (el) => vis(el) && /^(投稿至问题|创作声明|文章话题|定时发布|内容来源|添加封面)$/
                      .test((el.innerText || '').trim()));
                  for (const r of rows) {
                    const row = r.closest('[class]');
                    const ctrl = row ? row.parentElement : null;
                    const controls = [];
                    if (ctrl) {
                      for (const c of ctrl.querySelectorAll(
                          'input, textarea, button, [class*=Select], [class*=switch], [class*=dropdown], [class*=popover]')) {
                        controls.push({
                          tag: c.tagName,
                          cls: String(c.className).slice(0, 80),
                          ph: c.getAttribute('placeholder') || '',
                          type: c.getAttribute('type') || '',
                          aria: c.getAttribute('aria-label') || '',
                          role: c.getAttribute('role') || '',
                        });
                      }
                    }
                    settings.push({label: (r.innerText || '').trim(), controls: controls.slice(0, 8)});
                  }
                  return settings;
                }"""
            )
            print(f"--- {tag} ---")
            print(json.dumps(info, ensure_ascii=False, indent=1)[:3000])

        await dump_settings("初始")

        # 1. 创作声明下拉点开
        decl = page.locator("text=创作声明").first
        await decl.scroll_into_view_if_needed()
        # 下拉通常在同行的 Select 控件,点击「无声明」文本
        try:
            await page.locator("text=无声明").first.click(timeout=5000)
            await asyncio.sleep(2)
            options = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll(
                      '[class*=Menu-item], [role=option], li, [class*=option]')]
                    .filter(vis)
                    .map((el) => (el.innerText || '').trim())
                    .filter((t) => t && t.length < 30)
                    .slice(0, 15);
                }"""
            )
            print("声明选项:", json.dumps(options, ensure_ascii=False))
            await page.keyboard.press("Escape")
        except Exception as e:
            print("decl err:", str(e)[:100])
        await asyncio.sleep(1)

        # 2. 定时发布开关点开
        try:
            sw = page.locator("text=定时发布").first
            await sw.scroll_into_view_if_needed()
            # 开关在同行——点开关本体(Switch 按钮)
            sw_btn = await page.evaluate(
                """() => {
                  const label = [...document.querySelectorAll('*')].find(
                    (el) => (el.innerText || '').trim() === '定时发布');
                  if (!label) return null;
                  const row = label.closest('[class]');
                  const btn = row ? row.querySelector('button, [role=switch], [class*=switch]') : null;
                  if (btn) { btn.click(); return String(btn.className).slice(0, 60); }
                  return null;
                }"""
            )
            print("定时开关:", sw_btn)
            await asyncio.sleep(2)
            await page.screenshot(path=str(SHOT / "zhihu_schedule_on.png"), full_page=True)
        except Exception as e:
            print("schedule err:", str(e)[:100])

        # 3. 话题添加交互
        try:
            add_topic = page.locator("text=添加话题").first
            await add_topic.scroll_into_view_if_needed()
            await add_topic.click()
            await asyncio.sleep(2)
            topic_dom = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const inputs = [...document.querySelectorAll(
                      'input, [contenteditable=true]')]
                    .filter(vis)
                    .map((el) => ({tag: el.tagName,
                                   ph: el.getAttribute('placeholder') || '',
                                   cls: String(el.className).slice(0, 60)}));
                  return inputs.slice(0, 8);
                }"""
            )
            print("话题输入:", json.dumps(topic_dom, ensure_ascii=False, indent=1))
            await page.keyboard.press("Escape")
        except Exception as e:
            print("topic err:", str(e)[:100])

        # 4. 投稿至问题下拉点开
        try:
            tq = page.locator("text=投稿至问题").first
            await tq.scroll_into_view_if_needed()
            await asyncio.sleep(1)
            # 点击同行 Select
            clicked = await page.evaluate(
                """() => {
                  const label = [...document.querySelectorAll('*')].find(
                    (el) => (el.innerText || '').trim() === '投稿至问题');
                  if (!label) return false;
                  const row = label.closest('[class]');
                  const sel = row ? row.querySelector(
                      '[class*=Select], input, [role=combobox]') : null;
                  if (sel) { sel.click(); return true; }
                  return false;
                }"""
            )
            print("投稿点击:", clicked)
            await asyncio.sleep(2)
            await page.screenshot(path=str(SHOT / "zhihu_target_q.png"), full_page=True)
        except Exception as e:
            print("target-q err:", str(e)[:100])

        await dump_settings("交互后")
        await page.screenshot(path=str(SHOT / "zhihu_settings_final.png"), full_page=True)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
