# -*- coding: utf-8 -*-
"""侦察知乎文章发布设置 v5: 完整版编辑器(投稿至问题/创作声明/话题/定时/内容来源)。

采集: 全页截图 + 设置区 DOM 结构 + 逐控件交互后的弹层 DOM。
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

OUT = {"steps": []}


async def snap(page, tag):
    try:
        await page.screenshot(path=str(SHOT / f"recon5_{tag}.png"), full_page=True)
    except Exception as e:
        print(f"[snap {tag}] err: {e}")


async def dump_labels(page, tag):
    """抓当前可见的设置区行: label + 控件概要。"""
    info = await page.evaluate(
        """() => {
          const vis = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          };
          const labels = ['添加封面','投稿至问题','创作声明','文章话题','定时发布','内容来源','发布设置'];
          const rows = [];
          for (const el of document.querySelectorAll('*')) {
            if (!vis(el)) continue;
            const t = (el.innerText || '').trim();
            if (!labels.includes(t)) continue;
            const r = el.getBoundingClientRect();
            rows.push({label: t, tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                       cls: String(el.className).slice(0, 60)});
          }
          // 可见输入控件全景
          const inputs = [...document.querySelectorAll(
              'input, textarea, [contenteditable=true], button[role], [role=combobox], [role=switch]')]
            .filter(vis)
            .map((el) => ({
              tag: el.tagName,
              type: el.getAttribute('type') || '',
              ph: el.getAttribute('placeholder') || '',
              cls: String(el.className).slice(0, 70),
              aria: el.getAttribute('aria-label') || '',
              role: el.getAttribute('role') || '',
              checked: el.type === 'checkbox' ? el.checked : undefined,
              val: (el.value || '').slice(0, 30) || undefined,
            }));
          return {rows, inputs: inputs.slice(0, 25), url: location.href};
        }"""
    )
    print(f"===== [{tag}] =====")
    print(json.dumps(info, ensure_ascii=False, indent=1)[:4000])
    OUT["steps"].append({tag: info})


async def dump_popover(page, tag):
    """抓浮层(portal 渲染的 Menu/Popover/Modal)。"""
    info = await page.evaluate(
        """() => {
          const vis = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          };
          const cands = [...document.querySelectorAll(
              '[class*=Menu], [class*=Popover], [class*=popover], [class*=Modal], '
            + '[class*=modal], [class*=dropdown], [class*=Popup], [role=listbox], '
            + '[role=menu], [role=dialog], [class*=Modal-wrapper]')]
            .filter(vis)
            .map((el) => ({
              cls: String(el.className).slice(0, 90),
              role: el.getAttribute('role') || '',
              text: (el.innerText || '').replace(/\\s+/g, ' | ').slice(0, 400),
              inputs: [...el.querySelectorAll('input, textarea, [contenteditable=true]')]
                .map((i) => ({tag: i.tagName, ph: i.getAttribute('placeholder') || '',
                              type: i.getAttribute('type') || '',
                              cls: String(i.className).slice(0, 50)})),
              buttons: [...el.querySelectorAll('button')]
                .map((b) => ({text: (b.innerText || '').trim().slice(0, 20),
                              cls: String(b.className).slice(0, 50)}))
                .slice(0, 10),
            }));
          return cands.slice(0, 8);
        }"""
    )
    print(f"----- popover [{tag}] -----")
    print(json.dumps(info, ensure_ascii=False, indent=1)[:5000])
    OUT["steps"].append({"popover_" + tag: info})


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

        # 关闭创作助手面板(右上角 X)
        try:
            close_btn = page.locator(
                'button[aria-label="关闭"], [class*="ToolPanel"] button'
            ).first
            await close_btn.click(timeout=3000)
            await asyncio.sleep(1)
        except Exception:
            pass

        # 填标题(部分设置需要内容才可用)
        try:
            tb = page.locator("textarea.Input").first
            await tb.wait_for(state="visible", timeout=15000)
            await tb.fill("侦察测试标题")
        except Exception as e:
            print("title err:", e)
        await asyncio.sleep(2)
        await snap(page, "00_initial")
        await dump_labels(page, "初始")

        # 1. 创作声明下拉(点「无声明」)
        try:
            await page.locator("text=无声明").first.click(timeout=8000)
            await asyncio.sleep(2)
            await dump_popover(page, "声明下拉")
            await snap(page, "01_decl")
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
        except Exception as e:
            print("decl err:", str(e)[:150])

        # 2. 文章话题 → 添加话题
        try:
            await page.locator("text=添加话题").first.click(timeout=8000)
            await asyncio.sleep(2)
            await dump_popover(page, "话题")
            await snap(page, "02_topic")
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
        except Exception as e:
            print("topic err:", str(e)[:150])

        # 3. 投稿至问题(点「未选择」)
        try:
            await page.locator("text=未选择").first.click(timeout=8000)
            await asyncio.sleep(2)
            await dump_popover(page, "投稿")
            await snap(page, "03_targetq")
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
        except Exception as e:
            print("targetq err:", str(e)[:150])

        # 4. 内容来源 → 添加来源
        try:
            await page.locator("text=添加来源").first.click(timeout=8000)
            await asyncio.sleep(2)
            await dump_popover(page, "来源")
            await snap(page, "04_source")
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
        except Exception as e:
            print("source err:", str(e)[:150])

        # 5. 定时发布开关
        try:
            clicked = await page.evaluate(
                """() => {
                  const label = [...document.querySelectorAll('*')].find(
                    (el) => (el.innerText || '').trim() === '定时发布');
                  if (!label) return null;
                  let row = label.closest('[class]');
                  for (let d = 0; d < 3 && row; d++) {
                    const btn = row.querySelector('button, [role=switch], input[type=checkbox]');
                    if (btn) {
                      btn.click();
                      return String(btn.className).slice(0, 60);
                    }
                    row = row.parentElement;
                  }
                  return null;
                }"""
            )
            print("定时开关点击:", clicked)
            await asyncio.sleep(2.5)
            await dump_popover(page, "定时弹窗")
            await snap(page, "05_schedule")
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
        except Exception as e:
            print("schedule err:", str(e)[:150])

        # 6. 添加封面(看裁剪弹窗结构;先 Escape 不真传图)
        try:
            await page.locator("text=添加文章封面").first.click(timeout=8000)
            await asyncio.sleep(2)
            await dump_popover(page, "封面")
            await snap(page, "06_cover")
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
        except Exception as e:
            print("cover err:", str(e)[:150])

        await dump_labels(page, "最终")

        out_path = REPO / "data" / "screenshots" / "recon5_result.json"
        out_path.write_text(
            json.dumps(OUT, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print("saved:", out_path)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
