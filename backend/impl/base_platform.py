"""
Abstract base class for all social media platform implementations.

Each platform (Douyin, Xiaohongshu, Bilibili, etc.) must subclass BasePlatform
and implement the abstract methods. Browser entry points delegate to
``_browser.py`` (CloakBrowser stealth layer).
"""

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import get_channel_logger

from ._browser import (
    create_browser as _create_browser,
    create_context as _create_context,
    create_persistent_context as _create_persistent_context,
)

_base_logger = get_channel_logger("base_platform")


class BasePlatform(ABC):
    """Abstract base for platform-specific automation logic."""

    platform_id: int = 0
    platform_key: str = ""
    platform_name: str = ""

    # ------------------------------------------------------------------
    # Cookie import capability
    # ------------------------------------------------------------------

    #: True if this platform supports importing accounts from a raw cookie
    #: string (e.g. pasted from browser DevTools).  Subclasses override.
    supports_cookie_import: bool = False

    #: The wildcard domain to attach imported cookies to, e.g. ``".baidu.com"``
    #: for Baijiahao (cookie issued by passport.baidu.com also applies to
    #: baijiahao.baidu.com).  Subclasses override; most platforms can simply
    #: set this to ``f".{platform_key}.com"`` or similar.
    platform_cookie_domain: str = ""

    # ------------------------------------------------------------------
    # Unified browser entry points (delegate to _browser.py / CloakBrowser)
    # ------------------------------------------------------------------

    async def create_browser(
        self,
        headless: bool | None = None,
        login_mode: bool = False,
        humanize: bool = False,
        human_preset: str = "default",
    ):
        """Create a stealth Chromium browser via CloakBrowser.

        humanize=True 启用 CloakBrowser 拟人化操作层，仅建议在发布动作
        开启（会让操作明显变慢，login/cookie 校验等场景保持默认关闭）。
        """
        return await _create_browser(
            headless=headless,
            login_mode=login_mode,
            humanize=humanize,
            human_preset=human_preset,
        )

    async def create_context(
        self,
        browser,
        storage_state: str | None = None,
        user_agent: str | None = None,
    ):
        """Create a browser context (optionally with stored auth state)."""
        return await _create_context(
            browser,
            storage_state=storage_state,
            user_agent=user_agent,
        )

    async def create_persistent_context(
        self,
        user_data_dir: str,
        headless: bool = False,
    ):
        """Create a persistent browser context with a local user data dir."""
        return await _create_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
        )

    # ------------------------------------------------------------------
    # Abstract operations (every platform must implement)
    # ------------------------------------------------------------------

    @abstractmethod
    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform platform login, pushing progress updates to *status_queue*."""
        ...

    @abstractmethod
    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid."""
        ...

    @abstractmethod
    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the platform creator / upload centre page."""
        ...

    @abstractmethod
    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile information from the platform.

        Returns a ``(display_name, avatar_url)`` tuple, or ``("", "")``
        on failure.
        """
        ...

    @abstractmethod
    def publish_video(self, **kwargs) -> bool:
        """Publish a video to the platform.  Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Cookie import (default skeleton + per-platform hook)
    # ------------------------------------------------------------------

    # 注意：_parse_cookie_to_storage_state 不是 @abstractmethod，否则会强制
    # 所有平台实现它。仅当 supports_cookie_import=True 时由子类重写。

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        只有 ``supports_cookie_import=True`` 的平台需要重写。基类的默认实现
        直接抛错，由 :meth:`import_cookie` 触发并通过 status_queue 上报。
        子类的典型实现参考 BaijiahaoPlatform。

        Returns:
            ``(cookies, origins)`` —— ``import_cookie`` 会原样写入 storage_state。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support cookie import"
        )

    # Cookie import expires 保守占位（7 天）: 手工导入的 cookie 没有真实 expires，
    # Chromium 对 expires=-1（session）部分平台不收；sync_profile 跑完后会
    # 把 storage_state 回写刷新成真实 expires。
    _IMPORT_COOKIE_EXPIRES_SECONDS = 7 * 24 * 3600

    async def import_cookie(
        self,
        cookie_str: str,
        status_queue: Queue,
        account_id: int | None = None,
    ) -> dict:
        """Default cookie-import flow (4-step progress).

        Subclasses do NOT override this; they only set
        ``supports_cookie_import = True`` and implement
        :meth:`_parse_cookie_to_storage_state`.

        status_queue contract (JSON-per-line):
            ``{"step": 1|2|3, "status": "running", "msg": "..."}``
            ``{"step": 4, "status": "done", "msg": "...", "account_id": int,
              "userName": str, "avatar": str}``
            ``{"status": "error", "step": int, "msg": str}``

        Returns:
            ``{"account_id": int, "userName": str, "avatar": str}`` on success.
        """
        # ---- Step 1: parse cookie string ----
        try:
            status_queue.put(json.dumps({
                "step": 1, "status": "running", "msg": "解析 cookie 字符串",
            }))
            cookies, origins = self._parse_cookie_to_storage_state(cookie_str)
            if not cookies:
                raise ValueError("未解析到任何 cookie")
            _base_logger.info(
                "[import_cookie] %s 解析到 %d 个 cookie",
                self.platform_name, len(cookies),
            )
        except Exception as e:
            status_queue.put(json.dumps({
                "status": "error", "step": 1, "msg": f"解析失败: {e}",
            }))
            raise

        # ---- Step 2: 写入临时 cookie 文件（不写 user_info，先验证有效性）----
        cookie_filename: str = ""
        cookie_path: Path | None = None
        try:
            status_queue.put(json.dumps({
                "step": 2, "status": "running", "msg": "生成 cookie 文件",
            }))
            cookies_dir = Path(BASE_DIR / "cookiesFile")
            cookies_dir.mkdir(parents=True, exist_ok=True)
            cookie_filename = f"{uuid.uuid1()}.json"
            storage = {"cookies": cookies, "origins": origins}
            cookie_path = cookies_dir / cookie_filename
            cookie_path.write_text(
                json.dumps(storage, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            status_queue.put(json.dumps({
                "status": "error", "step": 2, "msg": f"生成失败: {e}",
            }))
            raise

        # ---- Step 3: sync_profile（与账号列表「同步」按钮完全一致的调用）----
        # 复用 platform.sync_profile —— 就是 /syncProfile 路由里调的同一个方法，
        # 同一套 scrape 逻辑、同样的 headless 配置，不做任何特殊处理。
        name, avatar = "", ""
        sync_failed = False
        try:
            status_queue.put(json.dumps({
                "step": 3, "status": "running", "msg": "同步用户资料",
            }))
            name, avatar = await self.sync_profile(cookie_filename)
        except Exception as e:
            sync_failed = True
            _base_logger.info(
                "[import_cookie] %s sync_profile 失败: %s",
                self.platform_name, e,
            )
            status_queue.put(json.dumps({
                "step": 3, "status": "running",
                "msg": f"同步失败: {e}",
            }))

        # ---- Step 4: 创建账号记录 ----
        # 策略:
        #   a) account_id 已存在 (re-import) → 直接 UPDATE, 任何结果都接受
        #   b) account_id 不存在:
        #      - sync 抓到 name/avatar → INSERT 真账号
        #      - sync 拿到空 (cookie 失效) → 删临时 cookie 文件, 报错让用户重试
        if not name and not avatar and not account_id:
            # cookie 验证失败,清理临时文件
            if cookie_path and cookie_path.exists():
                try:
                    cookie_path.unlink()
                except Exception:
                    pass
            status_queue.put(json.dumps({
                "status": "error", "step": 4,
                "msg": "cookie 已失效,无法同步到用户资料。请确认 cookie 是否过期后重试。",
            }))
            raise RuntimeError("cookie 同步失败: 抓取到空的昵称/头像")

        status_queue.put(json.dumps({
            "step": 4, "status": "running", "msg": "创建账号记录",
        }))
        account_id_saved: int = 0
        try:
            db_path = Path(BASE_DIR) / "db" / "database.db"
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()
                if account_id:
                    cursor.execute(
                        "UPDATE user_info SET filePath=?, status=1, userName=?, avatar=? "
                        "WHERE id=?",
                        (cookie_filename, name, avatar, account_id),
                    )
                    account_id_saved = int(account_id)
                    _base_logger.info(
                        "[import_cookie] %s re-import 更新 id=%s",
                        self.platform_name, account_id,
                    )
                else:
                    cursor.execute(
                        "INSERT INTO user_info (type, filePath, userName, status, avatar) "
                        "VALUES (?, ?, ?, 1, ?)",
                        (self.platform_id, cookie_filename, name, avatar),
                    )
                    account_id_saved = cursor.lastrowid
                    _base_logger.info(
                        "[import_cookie] %s 新建账号 id=%s, name=%r",
                        self.platform_name, account_id_saved, name,
                    )
                conn.commit()
        except Exception as e:
            status_queue.put(json.dumps({
                "status": "error", "step": 4, "msg": f"写入数据库失败: {e}",
            }))
            raise

        status_queue.put(json.dumps({
            "step": 4, "status": "done", "msg": "导入完成",
            "account_id": account_id_saved,
            "userName": name, "avatar": avatar,
        }))
        return {
            "account_id": account_id_saved,
            "userName": name, "avatar": avatar,
            "cookie_filename": cookie_filename,
        }

    # ------------------------------------------------------------------
    # Optional stubs (override if the platform supports these)
    # ------------------------------------------------------------------

    async def publish_note(self, **kwargs) -> bool:
        """Publish an image note (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support note publishing"
        )

    async def publish_image(self, **kwargs) -> bool:
        """Publish an image post (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support image publishing"
        )

    async def get_statistics(self, **kwargs) -> dict:
        """Fetch account statistics (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support statistics"
        )
