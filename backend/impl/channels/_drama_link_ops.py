"""视频号(channels)剧集/小程序剧集 picker 帧级 DOM 操作库。

所有函数接受 frame-like 对象(Page/Frame)作为参数。
picker.py 和 platform.py 共用这套 DOM 操作代码。

设计原则:
- 纯 DOM 操作,不持有会话状态
- 行为轨迹: search_keyword + page(用于发布时复现)
- 失败时抛异常或返回空,由调用方处理

DOM 锚点(2026-08 视频号发布页实测):
- 关联视频号剧集入口: 「选择需要添加的视频号剧集」placeholder 元素
- 关联小程序剧集入口: 「选择需要添加的短剧」placeholder 元素
- 弹窗: ``div.weui-desktop-dialog`` 标题「选择需要关联的短剧」(两个入口共用同一弹窗)
- 搜索框: ``input[placeholder="搜索内容"].weui-desktop-form__input``
- 表格行: ``tr.drama-row`` 含 data-row-key(剧集 ID)
- 剧信息: ``.drama-cover`` (img src) + ``.drama-title`` + ``.extinfo`` (集数 N集) +
            ``.source-cell .source-name`` (播放小程序) + 第二个 ``.source-cell--right .source-name`` (版权所属)
- 禁用行: ``tr.drama-row.drama-row--disabled``(含「视频播放异常」unusable 标识)
- 分页: ``.weui-desktop-pagination__nav`` 含 ``.__num__wrp label.__num`` 数字按钮 + 「下一页」``a.weui-desktop-btn``
- 弹窗关闭: ``.weui-desktop-dialog__close-btn``
- 弹窗 footer: ``.weui-desktop-dialog__ft`` 「确定」按钮(如有)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from util._logger import get_channel_logger

logger = get_channel_logger("channels")


# ---------- trace 签名 ----------

def trace_signature(trace: dict) -> tuple[str, int]:
    """trace 签名: (keyword, page)。"""
    return (trace.get("keyword", ""), int(trace.get("page", 1)))


# ---------- 辅助: 行 → drama dict ----------

async def _row_to_drama_dict(row_locator) -> dict:
    """从一个 tr 抓取剧集信息(在浏览器内一次性 evaluate 读全字段)。"""
    return await row_locator.evaluate(
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

# 各链接类型的 DOM 文本(用于点选下拉项)
LINK_OPTIONS = {
    "article": "公众号文章",
    "red_envelope": "红包封面",
    "drama": "视频号剧集",
    "mini_drama": "小程序短剧",
}

# 各类型对应的子区 placeholder 文案
LINK_PLACEHOLDERS = {
    "drama": "选择需要添加的视频号剧集",
    "mini_drama": "选择需要添加的短剧",
}


async def _wait_link_section_ready(page, timeout_s: int = 10) -> None:
    """等 .post-link-wrap 容器出现(视频号发布页加载完成标志)。"""
    wrap = page.locator(".post-link-wrap").first
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            if await wrap.count() > 0 and await wrap.is_visible():
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(
        "[DramaPicker] 视频号发布页未出现「.post-link-wrap」容器"
        "(可能 cookie 失效或页面改版)"
    )


async def _open_link_dropdown(page, timeout_s: int = 5) -> None:
    """点 .link-display-wrap 打开 4 选项下拉。"""
    display = page.locator(".post-link-wrap .link-display-wrap").first
    try:
        await display.wait_for(state="visible", timeout=timeout_s * 1000)
    except Exception as exc:
        raise RuntimeError(
            f"[DramaPicker] 找不到 .link-display-wrap(打不开链接下拉): {exc}"
        ) from exc
    await display.click()
    # 等下拉项可见
    options = page.locator(".post-link-wrap .link-list-options .link-option-item")
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            if await options.count() > 0 and await options.first.is_visible():
                return
        except Exception:
            pass
        await asyncio.sleep(0.3)
    raise RuntimeError("[DramaPicker] 链接下拉打开后未出现 .link-option-item")


async def _select_link_option(page, link_type: str) -> None:
    """在 .link-list-options 里点指定 link_type 对应的那一项。"""
    label = LINK_OPTIONS[link_type]
    option = page.locator(
        '.post-link-wrap .link-list-options .link-option-item:has-text("' + label + '")'
    ).first
    try:
        await option.wait_for(state="visible", timeout=5000)
    except Exception as exc:
        raise RuntimeError(
            f"[DramaPicker] 找不到下拉项「{label}」({link_type}): {exc}"
        ) from exc
    await option.click()
    await asyncio.sleep(0.4)


async def _wait_drama_entry(page, link_type: str, timeout_s: int = 10) -> None:
    """选了 link_type 之后等子区出现(含对应 placeholder 文本的 .content-wrap)。"""
    placeholder_text = LINK_PLACEHOLDERS[link_type]
    sel = '.content-wrap:has-text("' + placeholder_text + '")'
    entry = page.locator(sel).first
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            if await entry.count() > 0 and await entry.is_visible():
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(
        "[DramaPicker] 选了「" + LINK_OPTIONS[link_type] + "」后未出现含「"
        + placeholder_text + "」的子区入口(可能 cookie 失效、页面改版、或当前账号无权关联剧集)"
    )


async def _click_drama_entry(page, link_type: str) -> None:
    """点子区入口(整个 .content-wrap 块可点)触发剧集弹窗。"""
    placeholder_text = LINK_PLACEHOLDERS[link_type]
    sel = '.content-wrap:has-text("' + placeholder_text + '")'
    entry = page.locator(sel).first
    try:
        await entry.wait_for(state="visible", timeout=5000)
    except Exception as exc:
        raise RuntimeError(
            f"[DramaPicker] 等不到「{placeholder_text}」入口可点: {exc}"
        ) from exc
    await entry.click()
    await asyncio.sleep(1.0)


async def open_drama_panel(page, link_type: str = "drama") -> None:
    """Open the video-drama picker popup via the real DOM flow."""
    logger.info("[DramaPicker] 1) wait .post-link-wrap")
    await _wait_link_section_ready(page)
    logger.info("[DramaPicker] 2) open link dropdown")
    await _open_link_dropdown(page)
    logger.info("[DramaPicker] 3) select option %s", LINK_OPTIONS[link_type])
    await _select_link_option(page, link_type)
    logger.info("[DramaPicker] 4) wait drama entry")
    await _wait_drama_entry(page, link_type)
    logger.info("[DramaPicker] 5) click drama entry")
    await _click_drama_entry(page, link_type)


async def wait_panel_ready(page, timeout_s: int = 10) -> None:
    """等弹窗内表格第一行出现(确认数据已渲染)。"""
    dialog = page.locator(".weui-desktop-dialog").filter(
        has_text=DIALOG_TITLE
    ).first
    rows = dialog.locator("tr.drama-row")
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            if await rows.count() > 0:
                return
        except Exception:
            pass
        await asyncio.sleep(0.4)
    raise RuntimeError(
        f"[ChannelsDrama] 等不到剧集表格行(超时 {timeout_s}s)"
    )


async def close_panel(page) -> None:
    """点弹窗关闭按钮(X)。"""
    try:
        dialog = page.locator(".weui-desktop-dialog").filter(
            has_text=DIALOG_TITLE
        ).first
        close_btn = dialog.locator(".weui-desktop-dialog__close-btn").first
        if await close_btn.count() > 0 and await close_btn.is_visible():
            await close_btn.click()
            await asyncio.sleep(0.4)
    except Exception as exc:
        logger.info("[ChannelsDrama] 关闭弹窗异常(忽略): %s", exc)


# ---------- 搜索 + 翻页 + 抓取 ----------

async def search(page, keyword: str) -> None:
    """在弹窗内搜索框输入 keyword 并回车。"""
    dialog = page.locator(".weui-desktop-dialog").filter(
        has_text=DIALOG_TITLE
    ).first
    inp = dialog.locator(
        'input[placeholder="搜索内容"].weui-desktop-form__input'
    ).first
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
    dialog = page.locator(".weui-desktop-dialog").filter(
        has_text=DIALOG_TITLE
    ).first
    rows = dialog.locator("tr.drama-row")
    n = await rows.count()
    if n == 0:
        return []
    out = []
    for i in range(n):
        row = rows.nth(i)
        try:
            d = await _row_to_drama_dict(row)
            out.append(d)
        except Exception as exc:
            logger.info("[ChannelsDrama] 第 %d 行解析失败: %s", i, exc)
    return out


async def scrape_page_info(page) -> dict:
    """抓当前页码 + 总页数 + 总条数(从分页器读)。"""
    dialog = page.locator(".weui-desktop-dialog").filter(
        has_text=DIALOG_TITLE
    ).first
    return await dialog.evaluate(
        """(root) => {
            const pager = root.querySelector('.weui-desktop-pagination__nav');
            if (!pager) return {page: 1, total: 0, totalPages: 1};
            const nums = Array.from(pager.querySelectorAll('.weui-desktop-pagination__num'))
                .map(l => (l.textContent || '').trim());
            let page = 1;
            const cur = pager.querySelector('.weui-desktop-pagination__num_current');
            if (cur) page = parseInt((cur.textContent || '1').trim()) || 1;
            let totalPages = page;
            for (const n of nums) {
                const x = parseInt(n);
                if (!isNaN(x) && x > totalPages) totalPages = x;
            }
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
    dialog = page.locator(".weui-desktop-dialog").filter(
        has_text=DIALOG_TITLE
    ).first
    pager = dialog.locator(".weui-desktop-pagination__nav").first
    await pager.wait_for(state="visible", timeout=5_000)

    # 1) 优先点页码按钮
    sel = '.weui-desktop-pagination__num:has-text("' + str(target_page) + '")'
    page_btn = dialog.locator(sel).first
    if await page_btn.count() > 0 and await page_btn.is_visible():
        await page_btn.click()
        await asyncio.sleep(1.0)
        return

    # 2) 否则用跳页输入框
    jump_input = dialog.locator(".weui-desktop-pagination__input").first
    if await jump_input.count() > 0:
        await jump_input.fill(str(target_page))
        jump_link = dialog.locator(".weui-desktop-link:has-text('跳转')").first
        if await jump_link.count() > 0:
            await jump_link.click()
            await asyncio.sleep(1.0)
            return

    # 3) 连续点「下一页」
    nxt = dialog.locator(".weui-desktop-btn:has-text('下一页')").first
    if await nxt.count() > 0:
        for _ in range(target_page):
            try:
                if not (await nxt.is_visible() and await nxt.is_enabled()):
                    break
            except Exception:
                break
            await nxt.click()
            await asyncio.sleep(1.0)
        return

    raise RuntimeError(f"[ChannelsDrama] 无法翻到第 {target_page} 页")


# ---------- 选中 + 确认 ----------

async def select_drama_by_id(page, drama_id: str) -> dict:
    """点指定 row(已在当前页),返回该 row 完整信息。"""
    dialog = page.locator(".weui-desktop-dialog").filter(
        has_text=DIALOG_TITLE
    ).first
    row = dialog.locator(
        'tr.drama-row[data-row-key="' + str(drama_id) + '"]'
    ).first
    if await row.count() == 0:
        raise RuntimeError(
            "[ChannelsDrama] 找不到 row[data-row-key=" + repr(drama_id)
            + "],需先翻到该 row 所在页"
        )
    # 先抓数据再点(点完行被选中后 DOM 可能变化)
    info = await _row_to_drama_dict(row)
    await row.click()
    await asyncio.sleep(0.6)
    return info


async def confirm_selection(page) -> None:
    """点弹窗底部「确定」按钮(如无则 Esc 关弹窗)。"""
    dialog = page.locator(".weui-desktop-dialog").filter(
        has_text=DIALOG_TITLE
    ).first
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
    # 兜底:Esc 关弹窗
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.4)
    except Exception:
        pass
