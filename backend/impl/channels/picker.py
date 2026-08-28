"""视频号(channels)剧集 picker session — 后台 headless browser。

按 account_id 单例复用,流程:
1. 启动浏览器 → 访问视频号创作中心拿 cookie/session
2. 打开剧集选择弹窗(直接走 channels 发布页 URL)
3. 提供 search/go_page/select/close API 给前端调

不真实发布 — 关闭 picker session 时直接 close_browser。
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

from .._browser import create_browser, create_context, close_browser
from . import _drama_link_ops as link_ops
from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("channels")


# 视频号发布页 URL(与 platform.py TENCENT_UPLOAD_URL 一致)
_UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"


def _get_cookie_path_by_account_id(account_id: str) -> str | None:
    if not account_id:
        return None
    db_path = str(Path(BASE_DIR / "db" / "database.db"))
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _resolve_cookie_path(cookie_filename: str) -> Path:
    return Path(BASE_DIR / "cookiesFile") / cookie_filename


class ChannelsDramaPickerSession:
    """单账号单 headless browser session,管剧集选择弹窗。"""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.browser = None
        self.context = None
        self.page = None  # 视频号发布页

    async def _init_browser_and_page(self) -> None:
        if self.browser is not None:
            raise RuntimeError(f"picker session 已存在: {self.account_id}")

        cookie_filename = _get_cookie_path_by_account_id(self.account_id)
        cookie_path = _resolve_cookie_path(cookie_filename) if cookie_filename else None
        storage_state = str(cookie_path) if cookie_path and cookie_path.exists() else None
        logger.info(
            "[ChannelsDramaPicker][%s] init cookie=%s",
            self.account_id,
            "有" if storage_state else "无",
        )

        # 无头模式:picker 只读数据不发布,不需要可见窗口(发布流程仍为有头)
        self.browser = await create_browser(headless=True)
        if storage_state:
            self.context = await create_context(
                self.browser, storage_state=storage_state
            )
        else:
            self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

    async def open(
        self, link_type: str = "drama"
    ) -> dict:
        """启动浏览器 → 打开视频号发布页 → 走真实 DOM 流程打开剧集弹窗 → 返回首屏。

        Args:
            link_type: 'drama'(视频号剧集) / 'mini_drama'(小程序短剧)。
                决定点哪个 .link-option-item + 子区 placeholder 文本。
        """
        await self._init_browser_and_page()
        logger.info(
            "[ChannelsDramaPicker] goto 视频号发布页: %s", _UPLOAD_URL
        )
        await self.page.goto(_UPLOAD_URL, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)

        # 点链接下拉 → 选剧集类型 → 点子区入口 → 打开剧集弹窗
        await link_ops.open_drama_panel(self.page, link_type)
        await self._wait_ready_or_empty("open", timeout_s=15, require_dialog=True)
        items, page_info = await self._scrape()
        return {
            "items": items,
            "page": page_info.get("page", 1),
            "total": page_info.get("total", 0),
            "total_pages": page_info.get("totalPages", 1),
            "entry": link_type,
        }

    async def _wait_ready_or_empty(self, what: str, timeout_s: int = 8, require_dialog: bool = False) -> None:
        """等表格就绪;超时不抛错(可能搜索无结果),由调用方 scrape 出空列表。

        require_dialog=True 时(open 场景)超时后确认弹窗是否真的打开了,
        没打开才算失败抛错 —— 避免「弹窗没开」被误报成「无结果」。
        """
        try:
            await link_ops.wait_panel_ready(self.page, timeout_s=timeout_s)
            return
        except Exception as exc:
            logger.info(
                "[ChannelsDramaPicker] %s 等待就绪超时(按空结果兜底): %s", what, exc
            )
        if require_dialog:
            dialog = await link_ops._active_dialog(self.page)
            if dialog is None:
                raise RuntimeError(f"[ChannelsDramaPicker] {what}: 剧集弹窗未打开")

    async def search(self, keyword: str) -> dict:
        await link_ops.search(self.page, keyword)
        await self._wait_ready_or_empty("search", timeout_s=8)
        items, page_info = await self._scrape()
        return {
            "items": items,
            "page": page_info.get("page", 1),
            "total": page_info.get("total", 0),
            "total_pages": page_info.get("totalPages", 1),
        }

    async def go_page(self, page: int) -> dict:
        await link_ops.go_page(self.page, page)
        await self._wait_ready_or_empty("go_page", timeout_s=8)
        items, page_info = await self._scrape()
        return {
            "items": items,
            "page": page_info.get("page", 1),
            "total": page_info.get("total", 0),
            "total_pages": page_info.get("totalPages", 1),
        }

    async def select_drama(self, drama_id: str) -> dict:
        """按 id 选剧集(先翻到该 row 所在页,再点 row)。返回完整信息。"""
        # 先遍历已有页(限定 1-10 页)找 row,找不到再 raise
        for p in range(1, 11):
            try:
                await link_ops.go_page(self.page, p)
                await link_ops.wait_panel_ready(self.page)
                items, _ = await self._scrape()
                if any(it.get("key") == drama_id for it in items):
                    info = await link_ops.select_drama_by_id(self.page, drama_id)
                    return info
            except Exception as exc:
                logger.info(
                    "[ChannelsDramaPicker] 翻第 %d 页找 drama=%s 异常: %s",
                    p, drama_id, exc,
                )
        raise RuntimeError(
            f"[ChannelsDramaPicker] 前 10 页内未找到 drama_id={drama_id!r}"
        )

    async def select_drama_by_trace(self, trace: dict) -> dict:
        """按 trace (keyword, page) 复现,选中对应 row。"""
        kw = (trace or {}).get("keyword", "")
        page = int((trace or {}).get("page", 1))
        if kw:
            await link_ops.search(self.page, kw)
            await link_ops.wait_panel_ready(self.page)
        if page > 1:
            await link_ops.go_page(self.page, page)
            await link_ops.wait_panel_ready(self.page)
        items, _ = await self._scrape()
        # 在当前页找选中的 drama(由 picker 传 drama_id)
        if items:
            return items[0]
        raise RuntimeError(
            f"[ChannelsDramaPicker] 按 trace 复现后页面无剧集(trace={trace})"
        )

    async def _scrape(self) -> tuple[list, dict]:
        items = await link_ops.scrape_rows(self.page)
        page_info = await link_ops.scrape_page_info(self.page)
        return items, page_info

    async def close(self) -> None:
        if self.browser is None:
            return
        try:
            await link_ops.close_panel(self.page) if self.page else None
        except Exception:
            pass
        try:
            await self.browser.close()
        except Exception:
            pass
        self.browser = None
        self.context = None
        self.page = None
        logger.info("[ChannelsDramaPicker][%s] closed", self.account_id)
