"""京东关联商品 picker session — 后台 headless browser。

按 account_id 单例复用:
- 同账号同时只能开一个 picker(避免资源竞争)
- picker 与 platform 共享 _jd_link_ops(同一份 DOM 操作)

浏览器策略:headless=False(调试期,用户能看到浏览器自动化操作)
"""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from .._browser import create_browser, create_context, close_browser
from . import _jd_link_ops as link_ops
from conf import BASE_DIR

logger = logging.getLogger(__name__)


def _get_cookie_path_by_account_id(account_id: str) -> str | None:
    """根据 user_info.id 取 cookiesFile 路径(参考淘宝光合 picker)。"""
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


class JdPickerSession:
    """单账号单 headless browser session。"""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.browser = None
        self.page = None

    async def open(self) -> list[dict]:
        """启动浏览器进入选择面板,返回首屏商品列表。"""
        if self.browser is not None:
            raise RuntimeError(f"picker session 已存在: {self.account_id}")

        cookie_filename = _get_cookie_path_by_account_id(self.account_id)
        cookie_path = _resolve_cookie_path(cookie_filename) if cookie_filename else None
        storage_state = str(cookie_path) if cookie_path and cookie_path.exists() else None

        # 后台 headless(与淘宝光合 picker ad3b8d8 一致)
        self.browser = await create_browser(headless=False)
        if storage_state:
            ctx = await create_context(self.browser, storage_state=storage_state)
            self.page = await ctx.new_page()
        else:
            ctx = await self.browser.new_context()
            self.page = await ctx.new_page()

        # goto 发布页
        await self.page.goto(
            "https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop",
            wait_until="domcontentloaded",
        )
        # 等 SPA 路由 + 发布表单渲染
        await asyncio.sleep(2)
        await self.page.wait_for_selector(
            ".video-upload-wrapper",
            timeout=15_000,
            state="visible",
        )

        # 切商品 radio(默认已是商品,但保险起见)
        await link_ops.switch_radio(self.page, "product")
        await link_ops.click_add_card(self.page)
        await link_ops.wait_panel_ready(self.page)

        # 返回首屏商品
        return await link_ops.scrape_products(self.page)

    async def search(self, keyword: str) -> list[dict]:
        """搜索并返回商品列表。"""
        if self.page is None:
            raise RuntimeError("picker 未打开,请先调用 open()")
        await link_ops.clear_search(self.page)
        if keyword:
            await link_ops.search(self.page, keyword)
            await link_ops.wait_search_results(self.page)
        return await link_ops.scrape_products(self.page)

    async def go_page(self, page: int) -> list[dict]:
        """翻页并返回商品列表。"""
        if self.page is None:
            raise RuntimeError("picker 未打开")
        await link_ops.go_page(self.page, page)
        return await link_ops.scrape_products(self.page)

    async def close(self):
        """释放浏览器资源(必须在 finally 中调用)。"""
        try:
            if self.browser is not None:
                await close_browser(self.browser, is_close_by_code=True)
        except Exception as e:
            logger.warning(f"关闭 picker 浏览器失败: {e}")
        finally:
            self.browser = None
            self.page = None


# ---------- session 池 ----------


class _SessionPool:
    """按 account_id 管理 picker session,同账号同时只能开一个。"""

    def __init__(self):
        self._sessions: dict[str, JdPickerSession] = {}

    def get_or_create(self, account_id: str) -> JdPickerSession:
        existing = self._sessions.get(account_id)
        if existing is not None:
            return existing
        new_session = JdPickerSession(account_id)
        self._sessions[account_id] = new_session
        return new_session

    def get(self, account_id: str) -> Optional[JdPickerSession]:
        return self._sessions.get(account_id)

    def release(self, account_id: str):
        """释放 session 并关闭浏览器。"""
        session = self._sessions.pop(account_id, None)
        if session is not None:
            # 异步关闭:跨线程调用
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(session.close())
                else:
                    loop.run_until_complete(session.close())
            except RuntimeError:
                # 没有运行中的 loop,直接同步关闭
                pass

    def has(self, account_id: str) -> bool:
        return account_id in self._sessions


pool = _SessionPool()