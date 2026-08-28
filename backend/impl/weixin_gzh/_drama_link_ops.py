"""视频号剧集 picker 帧级 DOM 操作库。

所有函数接受 frame-like 对象(Page/Frame)作为参数。
picker.py 和 platform.py 共用这套 DOM 操作代码,保证选品/发布两条路径行为一致。

设计原则:
- 纯 DOM 操作,不持有会话状态
- 行为轨迹: search_keyword + page + drama_id(剧集 trace 用)
- 失败时抛异常或返回空,由调用方处理

DOM 锚点(2026-08 视频号发布页 appmsg_edit_v2 实际 DOM):
- 关联视频号剧集入口: 「选择需要添加的视频号剧集」placeholder 元素
- 弹窗: ``div.weui-desktop-dialog`` 宽度 ~1000px 标题「选择需要关联的短剧」
- 弹窗内搜索: ``input[placeholder="搜索内容"].weui-desktop-form__input``
- 表格行: ``tr.drama-row`` 含 data-row-key(剧集 ID)
- 剧信息: ``.drama-cover`` (img src) + ``.drama-title`` + ``.extinfo`` (集数 N集) +
            ``.source-cell .source-name`` (小程序名) + 第二个 ``.source-cell--right .source-name`` (版权所属)
- 分页: ``.weui-desktop-pagination__nav`` 含 ``.__num__wrp label.__num`` 数字按钮 + 「下一页」``a.weui-desktop-btn``
- 弹窗关闭: ``.weui-desktop-dialog__close-btn``
- 弹窗 footer: ``.weui-desktop-dialog__ft`` 「确定」按钮(如有)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from util._logger import get_channel_logger

logger = get_channel_logger("weixin_gzh")


# ---------- trace 签名 ----------

def trace_signature(trace: dict) -> tuple[str, int]:
    """trace 签名: (keyword, page)。"""
    return (trace.get("keyword", ""), int(trace.get("page", 1)))


# ---------- 辅助: 行 → drama dict ----------

def _row_to_drama_dict(row_locator, idx: int) -> dict:
    """从一个 tr 抓取剧集信息(同步传 row_locator + 索引,内部用 evaluate 一次性读全字段)。"""
    return row_locator.evaluate(
        """(el) => {
            const cover = el.querySelector('.drama-cover');
            const title = el.querySelector('.drama-title');
            const extinfo = el.querySelector('.extinfo');
            const sources = el.querySelectorAll('.source-cell .source-name');
            const sourceLeft = sources[0] ? sources[0].textContent.trim() : '';
            const sourceRight = sources[1] ? sources[1].textContent.trim() : '';
            const unusable = !!el.querySelector('.drama-unusable_reason');
            return {
                key: el.getAttribute('data-row-key') || '',
                title: title ? (title.textContent || '').trim() : '',
                cover: cover ? (cover.getAttribute('src') || '') : '',
                extinfo: extinfo ? (extinfo.textContent || '').trim() : '',
                sourceLeft,
                sourceRight,
                unusable,
            };
        }""",
    )


# ---------- 弹窗开关 ----------

DIALOG_TITLE = "选择需要关联的短剧"


async def open_drama_panel(page, entry_placeholder: str = "选择需要添加的视频号剧集") -> None:
    """在视频号发布页里点「关联视频号剧集」入口,弹出剧集选择弹窗。

    Args:
        page: video 号发布页 (appmsg_edit_v2 的 page2, 由 platform.py 传过来)
        entry_placeholder: 入口 placeholder 文本,精确匹配
            - "选择需要添加的视频号剧集" → 视频号剧集
            - "选择需要添加的短剧" → 小程序剧集(同弹窗不同入口)
    """
    entry = page.locator(f'.content-wrap:has-text("{entry_placeholder}")').first
    await entry.wait_for(state="visible", timeout=10_000)
    await entry.click()
    await asyncio.sleep(1.2)
    # 等弹窗标题出现
    dialog = page.locator(".weui-desktop-dialog").filter(has_text=DIALOG_TITLE).first
    await dialog.wait_for(state="visible", timeout=10_000)
    logger.info(f"[DramaPicker] ✓ 已打开剧集弹窗(入口: {entry_placeholder})")


async def wait_panel_ready(page, timeout_s: int = 10) -> None:
    """等弹窗内表格第一行出现(确认数据已渲染)。"""
    dialog = page.locator(".weui-desktop-dialog").filter(has_text=DIALOG_TITLE).first
    rows = dialog.locator("tr.drama-row")
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            if await rows.count() > 0:
                return
        except Exception:
            pass
        await asyncio.sleep(0.4)
    raise RuntimeError(f"[DramaPicker] 等不到剧集表格行(超时 {timeout_s}s)")


async def close_panel(page) -> None:
    """点弹窗关闭按钮(X)。"""
    try:
        close_btn = page.locator(".weui-desktop-dialog").filter(
            has_text=DIALOG_TITLE
        ).first.locator(".weui-desktop-dialog__close-btn")
        if await close_btn.count() > 0:
            await close_btn.click()
            await asyncio.sleep(0.4)
    except Exception as exc:
        logger.info(f"[DramaPicker] 关闭弹窗异常(忽略): {exc}")


# ---------- 搜索 + 翻页 + 抓取 ----------

async def search(page, keyword: str) -> None:
    """在弹窗内搜索框输入 keyword 并回车。"""
    dialog = page.locator(".weui-desktop-dialog").filter(has_text=DIALOG_TITLE).first
    inp = dialog.locator('input[placeholder="搜索内容"].weui-desktop-form__input').first
    await inp.wait_for(state="visible", timeout=5_000)
    await inp.click()
    await inp.fill("")
    if keyword:
        await inp.fill(keyword)
    await asyncio.sleep(0.3)
    await inp.press("Enter")
    await asyncio.sleep(1.2)


async def scrape_rows(page) -> list[dict]:
    """抓当前弹窗可见的所有剧集行。"""
    dialog = page.locator(".weui-desktop-dialog").filter(has_text=DIALOG_TITLE).first
    rows = dialog.locator("tr.drama-row")
    n = await rows.count()
    if n == 0:
        return []
    out = []
    for i in range(n):
        row = rows.nth(i)
        try:
            d = await _row_to_drama_dict(row, i)
            out.append(d)
        except Exception as exc:
            logger.info(f"[DramaPicker] 第 {i} 行解析失败: {exc}")
    return out


async def scrape_page_info(page) -> dict:
    """抓当前页码 + 总页数 + 总条数(从分页器读)。"""
    dialog = page.locator(".weui-desktop-dialog").filter(has_text=DIALOG_TITLE).first
    return await dialog.evaluate(
        """(root) => {
            const pager = root.querySelector('.weui-desktop-pagination__nav');
            if (!pager) return {page: 1, total: 0, totalPages: 1};
            const nums = Array.from(pager.querySelectorAll('.weui-desktop-pagination__num'))
                .map(l => (l.textContent || '').trim());
            // 当前页(有 current 类)
            let page = 1;
            const cur = pager.querySelector('.weui-desktop-pagination__num_current');
            if (cur) page = parseInt((cur.textContent || '1').trim()) || 1;
            // 总页数 = 最后一个数字(去除 '...')的最大数字
            let totalPages = page;
            for (const n of nums) {
                const x = parseInt(n);
                if (!isNaN(x) && x > totalPages) totalPages = x;
            }
            // 跳页输入框可能有 total (「共 N 条」)。先看 span 文本
            let total = 0;
            const totalSpan = pager.parentElement.querySelector('.weui-desktop-pagination__total');
            if (totalSpan) {
                const m = (totalSpan.textContent || '').match(/\\d+/);
                if (m) total = parseInt(m[0]);
            }
            return {page, total, totalPages};
        }""",
    )


async def go_page(page, target_page: int) -> None:
    """跳到指定页码(从 1 开始)。点击页码按钮 / 下一页 / 跳页输入。"""
    dialog = page.locator(".weui-desktop-dialog").filter(has_text=DIALOG_TITLE).first
    pager = dialog.locator(".weui-desktop-pagination__nav").first
    await pager.wait_for(state="visible", timeout=5_000)

    # 1) 优先点页码按钮
    page_btn = dialog.locator(
        '.weui-desktop-pagination__num:has-text("' + str(target_page) + '")'
    ).first
    if await page_btn.count() > 0 and await page_btn.is_visible():
        await page_btn.click()
        await asyncio.sleep(1.0)
        return

    # 2) 否则用跳页输入框
    jump_input = dialog.locator(".weui-desktop-pagination__input").first
    if await jump_input.count() > 0:
        await jump_input.fill(str(target_page))
        # 点「跳转」链接
        jump_link = dialog.locator(".weui-desktop-link:has-text('跳转')").first
        if await jump_link.count() > 0:
            await jump_link.click()
            await asyncio.sleep(1.0)
            return

    # 3) 连续点「下一页」
    nxt = dialog.locator(".weui-desktop-btn:has-text('下一页')").first
    if await nxt.count() > 0:
        # 最多点 target_page 次(防呆)
        for _ in range(target_page):
            try:
                if not (await nxt.is_visible() and await nxt.is_enabled()):
                    break
            except Exception:
                break
            await nxt.click()
            await asyncio.sleep(1.0)
        return

    raise RuntimeError(f"[DramaPicker] 无法翻到第 {target_page} 页")


# ---------- 选中 + 确认 ----------

async def select_drama_by_id(page, drama_id: str) -> dict:
    """点指定 row(已在当前页),返回该 row 完整信息。"""
    dialog = page.locator(".weui-desktop-dialog").filter(has_text=DIALOG_TITLE).first
    row = dialog.locator(f'tr.drama-row[data-row-key="{drama_id}"]').first
    if await row.count() == 0:
        raise RuntimeError(f"[DramaPicker] 找不到 row[data-row-key={drama_id!r}],需先翻到该 row 所在页")
    # 先抓数据再点(点完行被选中后 DOM 可能变化)
    info = await _row_to_drama_dict(row, 0)
    await row.click()
    await asyncio.sleep(0.6)
    return info


async def confirm_selection(page) -> None:
    """点弹窗底部「确定」按钮(如无则 Esc 关弹窗)。"""
    dialog = page.locator(".weui-desktop-dialog").filter(has_text=DIALOG_TITLE).first
    footer_btn = dialog.locator(
        ".weui-desktop-dialog__ft .weui-desktop-btn_primary, "
        ".weui-desktop-dialog__ft .weui-desktop-btn:has-text('确定'), "
        ".dialog-footer .weui-desktop-btn_primary, "
        ".dialog-footer .weui-desktop-btn:has-text('确定')"
    ).first
    try:
        if await footer_btn.count() > 0 and await footer_btn.is_visible():
            await footer_btn.click()
            await asyncio.sleep(0.6)
            return
    except Exception:
        pass
    # 没找到确定按钮 → Esc 关弹窗(微信很多弹窗是直接 Esc 关闭并保存)
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.4)
    except Exception:
        pass
