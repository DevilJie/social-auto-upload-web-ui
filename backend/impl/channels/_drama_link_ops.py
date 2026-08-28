"""视频号(channels)剧集/小程序剧集 picker 帧级 DOM 操作库。

所有函数接受 frame-like 对象(Page/Frame)作为参数。
picker.py 和 platform.py 共用这套 DOM 操作代码。

设计原则:
- 纯 DOM 操作,不持有会话状态
- 行为轨迹: search_keyword + page(用于发布时复现)
- 失败时抛异常或返回空,由调用方处理

DOM 锚点(2026-08 视频号发布页实测):
- ⚠ 发布表单在 iframe(/micro/content/post/create)里 —— page.locator 可穿透 iframe,
  但 page.evaluate 只跑主 frame,一切读写必须走 locator / locator.evaluate。
- 关联视频号剧集入口: 「选择需要添加的视频号剧集」placeholder 元素
- 关联小程序剧集入口: 「选择需要添加的短剧」placeholder 元素
- 弹窗内容有两种结构(按「可见的 .dialog-wrap」定位,不按弹窗标题过滤,标题两入口不一致):
  1) 小程序剧集: wrap 含 ``.drama-table-wrap``,行是 ``tr.drama-row``,
     搜索框 placeholder「搜索内容」/「请输入短剧名称」(两个入口各一个,别按 placeholder 找)
  2) 视频号剧集: wrap 含 ``.common-table-wrap``(ant-table),行是 ``tr.ant-table-row``,
     列为 剧集|小程序|ID|操作,底部 ``.dialog-footer`` 有「添加」按钮(勾选行后需点击生效)
- 剧信息(结构1): ``.drama-cover`` + ``.drama-title`` + ``.extinfo`` + ``.source-cell .source-name``×2
- 剧信息(结构2): 从 td 单元格文本兜底提取(title=第一个非空单元格,小程序/ID=后续列)
- 禁用行: ``tr.drama-row.drama-row--disabled`` 或行 class 含 disabled
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
    """从一个 tr 抓取剧集信息(在浏览器内一次性 evaluate 读全字段)。

    结构1(小程序剧集 tr.drama-row)有专用 class;结构2(视频号剧集
    tr.ant-table-row,列: 剧集|小程序|ID|操作)用 td 单元格文本兜底。
    """
    return await row_locator.evaluate(
        """(el) => {
            const q = (sel) => el.querySelector(sel);
            const cover = q('.drama-cover') || q('img');
            const extinfoEl = q('.extinfo');
            const sources = Array.from(el.querySelectorAll('.source-cell .source-name'))
                .map(n => (n.textContent || '').trim());
            // ant-table 结构兜底: 按序列出非空单元格文本
            const tdText = Array.from(el.querySelectorAll(':scope > td'))
                .map(td => (td.textContent || '').trim().replace(/\\s+/g, ' '))
                .filter(Boolean);
            const dramaTitle = q('.drama-title');
            let title = dramaTitle ? (dramaTitle.textContent || '').trim() : '';
            if (!title && tdText.length) title = tdText[0];
            let sourceLeft = sources[0] || '';
            let sourceRight = sources[1] || '';
            if (!sources.length && tdText.length >= 2) {
                sourceLeft = tdText[1] || '';
                sourceRight = tdText[2] || '';
            }
            const cls = el.className || '';
            return {
                key: el.getAttribute('data-row-key') || '',
                title,
                cover: cover ? (cover.getAttribute('src') || '') : '',
                extinfo: extinfoEl ? (extinfoEl.textContent || '').trim() : '',
                sourceLeft,
                sourceRight,
                unusable: !!q('.drama-unusable_reason') || cls.indexOf('disabled') !== -1,
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


async def _wait_link_section_ready(page, timeout_s: int = 30) -> None:
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


async def _open_link_dropdown(page, timeout_s: int = 30) -> None:
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
        await option.wait_for(state="visible", timeout=30_000)
    except Exception as exc:
        raise RuntimeError(
            f"[DramaPicker] 找不到下拉项「{label}」({link_type}): {exc}"
        ) from exc
    await option.click()
    await asyncio.sleep(0.4)


async def _wait_drama_entry(page, link_type: str, timeout_s: int = 30) -> None:
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
        await entry.wait_for(state="visible", timeout=30_000)
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


async def wait_panel_ready(page, timeout_s: int = 30) -> None:
    """等弹窗内「可见」内容表就绪:有行,或明确渲染了空态(暂无内容)。"""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            wrap = await _visible_drama_wrap(page)
            if wrap is not None:
                if await wrap.locator(_ROW_SEL).count() > 0:
                    return
                # 空态(账号没有可关联内容)也算就绪,让前端拿到 items=[]
                empty = wrap.locator(".ant-table-placeholder, .empty-wrap").first
                if await empty.count() > 0 and await empty.is_visible():
                    return
        except Exception:
            pass
        await asyncio.sleep(0.4)
    diag = "?"
    try:
        diag = "弹窗已开" if await _active_dialog(page) is not None else "弹窗未开"
    except Exception:
        pass
    raise RuntimeError(
        f"[ChannelsDrama] 等不到剧集表格行(超时 {timeout_s}s, {diag})"
    )


async def close_panel(page) -> None:
    """点弹窗关闭按钮(X)。按可见弹窗定位(标题两入口不一致)。"""
    try:
        dialog = await _active_dialog(page)
        if dialog is None:
            dialog = page.locator(".weui-desktop-dialog").filter(
                has_text=DIALOG_TITLE
            ).first
        close_btn = dialog.locator(".weui-desktop-dialog__close-btn").first
        if await close_btn.count() > 0 and await close_btn.is_visible():
            await close_btn.click()
            await asyncio.sleep(0.4)
    except Exception as exc:
        logger.info("[ChannelsDrama] 关闭弹窗异常(忽略): %s", exc)


# ---------- 可见剧集区定位 ----------

# 弹窗内容 wrap 的两种结构:小程序剧集(.drama-table-wrap + tr.drama-row)/
# 视频号剧集(.common-table-wrap 的 ant-table + tr.ant-table-row)
_CONTENT_WRAP_SEL = (
    ".dialog-wrap:has(.drama-table-wrap), .dialog-wrap:has(.common-table-wrap)"
)

# 两种结构的表格行
_ROW_SEL = "tr.drama-row, tr.ant-table-row"


async def _active_dialog(page):
    """返回当前「可见且带剧集内容表」的 .weui-desktop-dialog,没有则 None。

    发布页预渲染了 30+ 个隐藏弹窗模板;且视频号剧集/小程序剧集两个入口
    的弹窗标题不一致,所以不能按标题过滤 —— 按「可见 + 内含内容 wrap」定位。
    表单在 iframe 里,locator 查询可穿透,无需显式切 frame。
    """
    dlgs = page.locator(".weui-desktop-dialog")
    try:
        n = await dlgs.count()
    except Exception:
        return None
    for i in range(n):
        d = dlgs.nth(i)
        try:
            if not await d.is_visible():
                continue
            if await d.locator(_CONTENT_WRAP_SEL).count() > 0:
                return d
        except Exception:
            continue
    return None


async def _visible_drama_wrap(page):
    """返回弹窗里当前「可见」的内容 wrap,没有则 None。

    弹窗 DOM 同时挂着多个内容 wrap(视频号剧集 ant-table + 两个剧集表,
    一个可见其余 display:none)。读行/读分页/搜索/翻页必须限定在可见的
    那个,否则会把隐藏 wrap 的残留数据一起抓回来(行重复、分页读到旧值)。
    """
    dialog = await _active_dialog(page)
    if dialog is None:
        return None
    wraps = dialog.locator(_CONTENT_WRAP_SEL)
    try:
        n = await wraps.count()
    except Exception:
        return None
    for i in range(n):
        w = wraps.nth(i)
        try:
            if await w.is_visible():
                return w
        except Exception:
            continue
    return None


# ---------- 搜索 + 翻页 + 抓取 ----------

async def search(page, keyword: str) -> None:
    """在弹窗内搜索框输入 keyword 并回车。

    两个入口的搜索框 placeholder 不同(请输入短剧名称 / 搜索内容),
    所以不按 placeholder 定位,取可见 wrap 里 .search-wrap 的 input。
    """
    wrap = await _visible_drama_wrap(page)
    if wrap is None:
        raise RuntimeError("[ChannelsDrama] 找不到可见的剧集表格(无法搜索)")
    inp = None
    for sel in (".search-wrap input", ".filter-wrap input", "input.weui-desktop-form__input"):
        try:
            cand = wrap.locator(sel).first
            if await cand.count() > 0 and await cand.is_visible():
                inp = cand
                break
        except Exception:
            continue
    if inp is None:
        raise RuntimeError("[ChannelsDrama] 弹窗内找不到搜索输入框")
    await inp.click()
    await inp.fill("")
    if keyword:
        await inp.fill(keyword)
    await asyncio.sleep(0.3)
    await inp.press("Enter")
    await asyncio.sleep(1.2)


async def scrape_rows(page) -> list[dict]:
    """抓当前弹窗「可见」内容表的所有行(不含隐藏 wrap 的残留行)。

    兼容两种结构:小程序剧集 tr.drama-row / 视频号剧集 tr.ant-table-row。
    """
    wrap = await _visible_drama_wrap(page)
    if wrap is None:
        return []
    rows = wrap.locator(_ROW_SEL)
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
    """抓当前页码 + 总页数 + 总条数(从分页器读)。

    分页器 DOM 在不同版本里 class 名有差异,所以用多组选择器兜底:
    - 容器: .weui-desktop-pagination / .weui-desktop-pagination__nav
    - 当前页: .weui-desktop-pagination__num_current / .num.current /
              [aria-current] / .weui-desktop-pagination__item--active
    - 页码按钮: .weui-desktop-pagination__num / .weui-desktop-pagination__item
    - 总条数: 「共 N 条」文本(分页器任意子节点)
    兜底: 只要存在可点的「下一页」按钮,至少返回 totalPages=当前页+1,
    保证前端分页控件能显示出来(total 按 totalPages*10 估算)。
    只读「可见」wrap 里的分页器 —— 弹窗里另一个隐藏 wrap 的分页器
    是残留旧值,不能拿来做当前状态。
    """
    wrap = await _visible_drama_wrap(page)
    if wrap is None:
        logger.info("[ChannelsDrama][诊断] 未找到可见剧集表,分页按第 1 页处理")
        return {"page": 1, "total": 0, "totalPages": 1}
    info = await wrap.evaluate(
        """(root) => {
            // 分页容器(多组选择器兜底)
            let pager = root.querySelector('.weui-desktop-pagination__nav')
                     || root.querySelector('.weui-desktop-pagination')
                     || root.querySelector('.pagination-wrap')
                     || null;
            // 诊断:dump 分页器 HTML 前 400 字符(第一次排查用)
            const pagerHtml = pager ? (pager.outerHTML || '').slice(0, 400) : '(未找到分页容器)';

            if (!pager) return {page: 1, total: 0, totalPages: 1, pagerHtml};

            // 当前页: 多组选择器
            const curSel = [
                '.weui-desktop-pagination__num_current',
                '.weui-desktop-pagination__num.current',
                '.weui-desktop-pagination__item--active',
                '[aria-current="page"]',
                '.current',
            ];
            let page = 1;
            for (const s of curSel) {
                const el = pager.querySelector(s);
                if (el) {
                    const x = parseInt((el.textContent || '1').trim());
                    if (!isNaN(x) && x > 0) { page = x; break; }
                }
            }

            // 所有页码按钮数字,取最大值作为总页数下限
            const numSel = [
                '.weui-desktop-pagination__num',
                '.weui-desktop-pagination__item',
                'li',
            ];
            let totalPages = page;
            for (const s of numSel) {
                pager.querySelectorAll(s).forEach(el => {
                    const t = (el.textContent || '').trim();
                    const x = parseInt(t);
                    if (!isNaN(x) && x > totalPages) totalPages = x;
                });
            }

            // 总条数:「共 N 条」文本(分页器或其父级范围内搜)
            let total = 0;
            const scope = pager.parentElement || pager;
            const m = ((scope && scope.textContent) || '').match(/共\\s*(\\d+)\\s*条/);
            if (m) total = parseInt(m[1]);

            // 「下一页」按钮是否可点(兜底:可点说明还有下一页)
            const nextBtns = Array.from(pager.querySelectorAll('a, button, li, span'))
                .filter(el => ((el.textContent || '').trim().indexOf('下一页') !== -1));
            const hasNext = nextBtns.length > 0 && nextBtns.every(el => {
                const cls = el.className || '';
                return cls.indexOf('disabled') === -1;
            });

            return {page, total, totalPages, hasNext, pagerHtml};
        }"""
    )

    # ---- Python 侧兜底:保证分页控件至少能显示 ----
    has_next = bool(info.get("hasNext"))
    total = int(info.get("total") or 0)
    total_pages = int(info.get("totalPages") or 1)
    cur_page = int(info.get("page") or 1)

    # 有下一页可点 → 至少还有一页
    if has_next and total_pages <= cur_page:
        total_pages = cur_page + 1
    # 有总条数但没读出总页数 → 用 total/10 估算(每页 10 条)
    if total > 0 and total_pages <= 1:
        total_pages = max(1, -(-total // 10))  # ceil
    # 没读到 total 但有多页 → 反推
    if total <= 0 and total_pages > 1:
        total = total_pages * 10

    result = {
        "page": cur_page,
        "total": total,
        "totalPages": total_pages,
    }
    # 诊断日志:分页器原始 HTML(只打前 300 字符,方便对照选择器)
    pager_html = str(info.get("pagerHtml") or "")[:300]
    logger.info(
        "[ChannelsDrama][诊断] 分页信息: %s | pagerHtml=%s",
        result, pager_html,
    )
    return result


async def go_page(page, target_page: int) -> None:
    """跳到指定页码(从 1 开始)。点击页码按钮 / 跳页输入 / 连点「下一页」。

    分页器 class 在不同版本有差异,所以每组操作都用多组选择器兜底。
    只操作「可见」wrap 里的分页器(弹窗里另一个隐藏 wrap 也有一个)。
    """
    wrap = await _visible_drama_wrap(page)
    if wrap is None:
        raise RuntimeError("[ChannelsDrama] 找不到可见的剧集表格(无法翻页)")
    dialog = wrap

    # 1) 优先点页码按钮(多组选择器:精确文本匹配,避免 1 匹配到 10)
    num_sels = [
        ".weui-desktop-pagination__num",
        ".weui-desktop-pagination__item",
        ".pagination-wrap li",
    ]
    for ns in num_sels:
        try:
            btns = dialog.locator(ns)
            n = await btns.count()
        except Exception:
            continue
        for i in range(n):
            try:
                b = btns.nth(i)
                txt = ((await b.text_content()) or "").strip()
                if txt == str(target_page):
                    if await b.is_visible():
                        await b.click()
                        await asyncio.sleep(1.2)
                        return
            except Exception:
                continue

    # 2) 跳页输入框(多组选择器)
    jump_sels = [
        ".weui-desktop-pagination__input input",
        ".weui-desktop-pagination__jump input",
        "input.weui-desktop-pagination__input",
    ]
    for js in jump_sels:
        try:
            jump_input = dialog.locator(js).first
            if await jump_input.count() > 0 and await jump_input.is_visible():
                await jump_input.fill(str(target_page))
                # 点「跳转」(可能是 a / button / span)
                jump_link = dialog.locator(
                    ".weui-desktop-pagination :text('跳转')"
                ).first
                if await jump_link.count() > 0:
                    await jump_link.click()
                else:
                    await jump_input.press("Enter")
                await asyncio.sleep(1.2)
                return
        except Exception:
            continue

    # 3) 连续点「下一页」(多组选择器)
    next_sels = [
        ".weui-desktop-btn:has-text('下一页')",
        ".weui-desktop-pagination a:has-text('下一页')",
        ".weui-desktop-pagination li:has-text('下一页')",
        ":text('下一页')",
    ]
    nxt = None
    for ns in next_sels:
        try:
            cand = dialog.locator(ns).first
            if await cand.count() > 0 and await cand.is_visible():
                nxt = cand
                break
        except Exception:
            continue
    if nxt is not None:
        # 从当前页翻到目标页,最多点 target_page 次(防死循环)
        for _ in range(target_page):
            try:
                if not (await nxt.is_visible() and await nxt.is_enabled()):
                    break
            except Exception:
                break
            await nxt.click()
            await asyncio.sleep(1.2)
        return

    raise RuntimeError(
        "[ChannelsDrama] 无法翻到第 " + str(target_page)
        + " 页(找不到页码按钮/跳页输入/下一页按钮,看诊断日志里的 pagerHtml)"
    )


# ---------- 选中 + 确认 ----------

async def select_drama_by_id(page, drama_id: str) -> dict:
    """点指定 row(已在当前页),返回该 row 完整信息。

    视频号剧集弹窗(ant-table)点行只是勾选,还需点底部「添加」才生效;
    小程序剧集弹窗点行即选中。统一在这里兜底处理。
    """
    wrap = await _visible_drama_wrap(page)
    if wrap is None:
        raise RuntimeError("[ChannelsDrama] 找不到可见的剧集表格(无法选 row)")
    row = wrap.locator(
        'tr.drama-row[data-row-key="' + str(drama_id) + '"], '
        'tr.ant-table-row[data-row-key="' + str(drama_id) + '"]'
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
    # 视频号剧集弹窗: 勾选后点 footer「添加」确认(小程序剧集无此按钮,自动跳过)
    try:
        footer_btn = wrap.locator(
            ".dialog-footer .weui-desktop-btn_primary, "
            ".dialog-footer .weui-desktop-btn:has-text('添加'), "
            ".dialog-footer .weui-desktop-btn:has-text('确定')"
        ).first
        if await footer_btn.count() > 0 and await footer_btn.is_visible():
            btn_cls = (await footer_btn.get_attribute("class")) or ""
            if "disabled" not in btn_cls:
                await footer_btn.click()
                await asyncio.sleep(0.6)
    except Exception as exc:
        logger.info("[ChannelsDrama] 点 footer 添加/确定 异常(忽略): %s", exc)
    return info


async def confirm_selection(page) -> None:
    """点弹窗底部「确定/添加」按钮(如无则 Esc 关弹窗)。"""
    dialog = await _active_dialog(page)
    if dialog is None:
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
