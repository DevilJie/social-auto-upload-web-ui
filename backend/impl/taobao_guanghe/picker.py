"""淘宝光合「关联商品/店铺」选择面板 —— 浏览器会话池。

用户在前端弹窗操作时,后端同步驱动一个常驻无头浏览器:
进入光合首页 → 进入视频发布页 → 切换商品/店铺 radio → 点添加卡片 → 弹出选择面板。
搜索/筛选/加载更多等操作都在该浏览器内同步执行,然后抓取 DOM 数据回传前端。

生命周期:
- 前端打开弹窗 → ``open`` 创建会话并初始化到选择面板
- 用户操作 → ``switch_type``/``switch_tab``/``apply_filter``/``search``/``load_more``
- 前端关闭弹窗 → ``close`` 释放浏览器

DOM 选择器策略(避免 CSS Modules 哈希 class 模糊匹配):
- Next UI 稳定 class: ``.next-tabs-tab`` / ``.next-checkbox-wrapper`` / ``.next-radio-wrapper`` / ``.next-icon-plus`` / ``.next-btn-primary``
- ARIA 属性: ``role="tabpanel"[aria-hidden="false"]`` / ``input[role="searchbox"]``
- 稳定属性: ``href*="item.taobao.com"`` / ``span[title]`` / ``placeholder*="店铺"``
- 文本锚点: ``get_by_text("添加商品", exact=True)`` / ``get_by_text("加载更多")``
- 复杂关系(卡片定位) 用 ``frame.evaluate(JS)`` 以稳定锚点向上找祖先
"""

import asyncio
import sqlite3
import threading
import urllib.parse
from pathlib import Path

from conf import BASE_DIR
from util._logger import get_channel_logger

from .._browser import create_browser, create_context
from . import _link_ops
from ._link_ops import GUANGHE_PUBLISH_URL as _GUANGHE_PUBLISH_URL
from ._link_ops import TYPE_PRODUCT as _TYPE_PRODUCT
from ._link_ops import TYPE_SHOP as _TYPE_SHOP

logger = get_channel_logger("taobao_guanghe")

_GUANGHE_HOME_URL = "https://creator.guanghe.taobao.com/"
_COOKIE_INVALID_MARKERS = ("login.taobao.com",)


# ----------------------------------------------------------------------
# Cookie 路径解析
# ----------------------------------------------------------------------

def _get_cookie_path_by_account_id(account_id: str) -> str | None:
    """根据 user_info.id 取 cookiesFile 路径。"""
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


def _resolve_cookie_path(cookie_filename: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile") / cookie_filename)


# ----------------------------------------------------------------------
# 单个会话
# ----------------------------------------------------------------------

class GuanghePickerSession:
    """一个账号 + 一个常驻无头浏览器,负责 picker 全流程操作。"""

    def __init__(self, session_id: str, cookie_path: str):
        self.session_id = session_id
        self.cookie_path = cookie_path
        self.browser = None
        self.context = None
        self.page = None
        self.frame = None  # 发布页 iframe
        self.current_type: str | None = None  # 'product' / 'shop'

    # ---- 生命周期 ----

    async def open(self, type_: str) -> dict:
        """启动浏览器并初始化到选择面板。

        Args:
            type_: 'product' 或 'shop'

        Returns:
            ``{"items": [...], "has_more": bool, "type": ...}``
        """
        if type_ not in ("product", "shop"):
            raise ValueError(f"unknown type: {type_}")

        logger.info(f"[Picker][{self.session_id}] open type={type_}")
        self.browser = await create_browser(headless=False)
        try:
            self.context = await create_context(self.browser, storage_state=self.cookie_path)
            self.page = await self.context.new_page()

            # 直接带 cookie goto 发布页 URL(跳过先访问首页)
            # 失效 cookie 会被淘宝重定向到 login.taobao.com,据此判断登录状态
            logger.info(f"[Picker] goto 发布页: {_GUANGHE_PUBLISH_URL[:80]}...")
            await self.page.goto(_GUANGHE_PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            current_url = self.page.url or ""
            if any(m in current_url for m in _COOKIE_INVALID_MARKERS):
                raise RuntimeError("cookie 失效,请重新登录淘宝光合")

            # 找到发布页 iframe
            self.frame = await self._find_publish_frame()

            # 提前设置 current_type,让 _open_picker_panel 内部能调 switch_tab
            # (switch_tab 会校验 self.current_type,提前设置才能正确切换到「平台优选」)
            self.current_type = type_

            # 点对应 radio + 点添加卡片,打开选择弹窗
            await self._open_picker_panel(type_)

            # 抓取初始数据 + 筛选选项
            items, has_more = await self._scrape()
            filters = await self._scrape_filters() if type_ == "product" else {}
            return {"items": items, "has_more": has_more, "filters": filters, "type": type_}
        except Exception:
            # 初始化失败立即释放浏览器
            await self._teardown()
            raise

    async def switch_type(self, type_: str) -> dict:
        """切换商品↔店铺(关闭当前选择面板 → 切 radio → 重开面板)。"""
        if type_ not in ("product", "shop"):
            raise ValueError(f"unknown type: {type_}")
        if type_ == self.current_type:
            # 已是该类型,直接返回当前快照
            items, has_more = await self._scrape()
            return {"items": items, "has_more": has_more, "type": type_}

        logger.info(f"[Picker][{self.session_id}] switch {self.current_type}→{type_}")
        # 关闭当前弹窗(Esc)
        try:
            await self.frame.page.keyboard.press("Escape")
            await asyncio.sleep(0.8)
        except Exception:
            pass

        await self._open_picker_panel(type_)
        self.current_type = type_

        items, has_more = await self._scrape()
        return {"items": items, "has_more": has_more, "type": type_}

    async def switch_tab(self, tab: str) -> dict:
        """商品模式:切换「已购商品」/「平台优选」。"""
        if self.current_type != "product":
            raise RuntimeError("tab 切换仅商品模式支持")
        if tab not in ("bought", "preferred"):
            raise ValueError(f"unknown tab: {tab}")
        target_text = "已购商品" if tab == "bought" else "平台优选"
        logger.info(f"[Picker][{self.session_id}] switch_tab → {target_text}")
        await _link_ops.switch_tab(self.frame, tab)
        items, has_more = await self._scrape()
        return {"items": items, "has_more": has_more}

    async def apply_filter(self, rule: str | None = None, category: str | None = None) -> dict:
        """切换推荐规则/品类筛选(仅平台优选 tab 有效)。"""
        if self.current_type != "product":
            raise RuntimeError("筛选仅商品模式支持")
        if rule:
            await _link_ops.click_filter(self.frame, "推荐规则", rule)
        if category:
            await _link_ops.click_filter(self.frame, "品类筛选", category)
        await asyncio.sleep(1.2)
        items, has_more = await self._scrape()
        filters = await self._scrape_filters()
        return {"items": items, "has_more": has_more, "filters": filters}

    async def search(self, keyword: str) -> dict:
        """搜索。"""
        keyword = (keyword or "").strip()
        logger.info(f"[Picker][{self.session_id}] search: {keyword!r}")
        await _link_ops.search(self.frame, keyword)
        items, has_more = await self._scrape()
        filters = await self._scrape_filters() if self.current_type == "product" else {}
        return {"items": items, "has_more": has_more, "filters": filters}

    async def load_more(self) -> dict:
        """点击「加载更多」按钮。"""
        logger.info(f"[Picker][{self.session_id}] load_more")
        await _link_ops.load_more(self.frame)
        items, has_more = await self._scrape()
        return {"items": items, "has_more": has_more}

    async def close(self) -> None:
        """关闭浏览器,释放所有资源。"""
        logger.info(f"[Picker][{self.session_id}] close")
        await self._teardown()

    # ---- 内部辅助 ----

    async def _find_publish_frame(self):
        """找含上传元素的 iframe(发布页内容由跨域 iframe 嵌入)。"""
        page = self.page
        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    # 发布页 iframe 内会有 file input(上传视频用);用它判定 iframe 已就绪
                    inp_count = await frame.locator(
                        'input[type="file"]'
                    ).count()
                    if inp_count > 0:
                        return frame
                except Exception:
                    pass
            await asyncio.sleep(1)
        return page.main_frame

    async def _open_picker_panel(self, type_: str) -> None:
        """在发布页 iframe 内:点对应 radio → 点添加卡片 → 等选择面板出现。"""
        frame = self.frame
        try:
            await _link_ops.switch_radio(frame, type_)
            logger.info(f"[Picker] ✓ 已选 radio={'商品' if type_ == 'product' else '店铺'}")
        except Exception as e:
            logger.info(f"[Picker] radio 点击失败: {e}")

        try:
            await _link_ops.click_add_card(frame, type_)
            trigger_text = "添加商品" if type_ == "product" else "添加店铺"
            logger.info(f"[Picker] ✓ 已点击 {trigger_text}")
        except Exception as e:
            logger.info(f"[Picker] 添加卡片点击失败: {e}")

        try:
            await _link_ops.wait_panel_ready(frame, type_)
            if type_ == "product":
                await self.switch_tab("preferred")
        except Exception as e:
            logger.info(f"[Picker] 面板等待失败: {e}")

    async def _scrape(self) -> tuple[list, bool]:
        """抓取当前面板所有商品/店铺。"""
        return await _link_ops.scrape(self.frame, self.current_type)

    async def _scrape_filters(self) -> dict:
        """抓取筛选选项。"""
        return await _link_ops.scrape_filters(self.frame)

    async def _teardown(self) -> None:
        """关闭浏览器,清空所有引用。"""
        for attr in ("context", "browser"):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                await obj.close()
            except Exception:
                pass
            setattr(self, attr, None)
        self.page = None
        self.frame = None
        self.current_type = None


# ----------------------------------------------------------------------
# 全局会话池
# ----------------------------------------------------------------------

class _SessionPool:
    """按 session_id 管理 GuanghePickerSession。

    session_id 命名: ``f"{account_id}"`` —— 同一账号同时只能开一个 picker。
    切换账号 = 关闭旧 session + 开新 session。
    """

    def __init__(self):
        self._sessions: dict[str, GuanghePickerSession] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> GuanghePickerSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def create(self, session_id: str, cookie_path: str) -> GuanghePickerSession:
        with self._lock:
            # 如果已存在,先标记需要替换;实际关闭在锁外做(避免阻塞)
            old = self._sessions.get(session_id)
            session = GuanghePickerSession(session_id, cookie_path)
            self._sessions[session_id] = session
        # 关旧会话(锁外,async)
        if old:
            asyncio.ensure_future(old._teardown())
        return session

    def remove(self, session_id: str) -> GuanghePickerSession | None:
        with self._lock:
            return self._sessions.pop(session_id, None)


pool = _SessionPool()
