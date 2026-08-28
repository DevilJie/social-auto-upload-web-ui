"""视频号剧集 picker session — 后台 headless browser。

流程:
1. 启动浏览器 → 公众号首页拿 token(复用 platform._resolve_token)
2. goto appmsg_edit_v2 编辑页(空的新建,无需上传视频)
3. 等「关联视频号剧集」入口出现
4. 提供 search/go_page/select/close API

不真实发布 —— 浏览器停在编辑页供用户操作 picker,close 时关闭浏览器。
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

logger = get_channel_logger("weixin_gzh")


# appmsg_edit_v2 发布编辑页(空新建,无需素材)。
# platform.py 走的是先 videomsg_edit 上传 → 点保存并发表 → 跳新 tab 到 appmsg_edit_v2;
# picker 跳过上传,直接打开 appmsg_edit_v2(isNew=1 type=10)看空白编辑器。
_PUBLISH_V2_URL = (
    "https://mp.weixin.qq.com/cgi-bin/appmsg"
    "?t=media/appmsg_edit_v2&action=edit&isNew=1&type=10"
    "&token={token}&lang=zh_CN"
)


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


class WeixinGzhDramaPickerSession:
    """单账号单 headless browser session,管剧集选择弹窗。"""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.browser = None
        self.context = None
        self.page = None  # appmsg_edit_v2 编辑页

    async def _init_browser_and_page(self) -> None:
        if self.browser is not None:
            raise RuntimeError(f"picker session 已存在: {self.account_id}")

        cookie_filename = _get_cookie_path_by_account_id(self.account_id)
        cookie_path = _resolve_cookie_path(cookie_filename) if cookie_filename else None
        storage_state = str(cookie_path) if cookie_path and cookie_path.exists() else None
        logger.info(f"[DramaPicker][{self.account_id}] init cookie={'有' if storage_state else '无'}")

        self.browser = await create_browser(headless=False)
        if storage_state:
            self.context = await create_context(self.browser, storage_state=storage_state)
        else:
            self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

    async def _resolve_token(self) -> str:
        from .platform import WeixinGzhPlatform
        return await WeixinGzhPlatform._resolve_token(self.page)

    async def _wait_drama_entry(self, timeout_s: int = 30) -> None:
        """等「选择需要添加的视频号剧集」placeholder 出现,确认编辑页就绪。"""
        entry = self.page.locator(
            '.content-wrap:has-text("选择需要添加的视频号剧集")'
        ).first
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                if await entry.count() > 0 and await entry.is_visible():
                    return
            except Exception:
                pass
            await asyncio.sleep(0.8)
        # 兜底:页面可能还在加载,等长一点
        try:
            await entry.wait_for(state="visible", timeout=5_000)
        except Exception as exc:
            raise RuntimeError(
                f"[DramaPicker] 等不到「关联视频号剧集」入口(可能 cookie 失效或页面改版): {exc}"
            )

    async def open(self) -> dict:
        """启动浏览器 → 进 appmsg_edit_v2 编辑页 → 打开剧集弹窗 → 返回首屏。"""
        await self._init_browser_and_page()
        token = await self._resolve_token()
        url = _PUBLISH_V2_URL.format(token=token)
        logger.info(f"[DramaPicker] goto appmsg_edit_v2: {url[:80]}...")
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)

        # 关掉可能出现的教育弹窗(同 platform._dismiss_education_dialog)
        try:
            from .platform import WeixinGzhPlatform
            await WeixinGzhPlatform._dismiss_education_dialog(self.page)
        except Exception:
            pass

        # 等「关联视频号剧集」入口出现
        await self._wait_drama_entry()

        # 点开剧集弹窗
        await link_ops.open_drama_panel(self.page)
        await link_ops.wait_panel_ready(self.page)
        items, page_info = await self._scrape()
        return {
            "items": items,
            "page": page_info.get("page", 1),
            "total_pages": page_info.get("totalPages", 1),
            "total": page_info.get("total", 0),
        }

    async def search(self, keyword: str) -> dict:
        await link_ops.search(self.page, keyword)
        await link_ops.wait_panel_ready(self.page)
        items, page_info = await self._scrape()
        return {
            "items": items,
            "page": page_info.get("page", 1),
            "total_pages": page_info.get("totalPages", 1),
            "total": page_info.get("total", 0),
        }

    async def go_page(self, page: int) -> dict:
        await link_ops.go_page(self.page, page)
        await link_ops.wait_panel_ready(self.page)
        items, page_info = await self._scrape()
        return {
            "items": items,
            "page": page_info.get("page", 1),
            "total_pages": page_info.get("totalPages", 1),
            "total": page_info.get("total", 0),
        }

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
        logger.info(f"[DramaPicker][{self.account_id}] closed")
