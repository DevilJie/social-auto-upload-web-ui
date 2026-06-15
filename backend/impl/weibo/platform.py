"""Weibo platform implementation — CloakBrowser."""

import asyncio
import os
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._utils import save_login_result, scrape_weibo_profile
from ..base_platform import BasePlatform
from util._logger import get_channel_logger

logger = get_channel_logger("weibo")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WEIBO_CREATOR_URL = "https://weibo.com/n/微博创作者中心"
_WEIBO_LOGIN_HOST = "passport.weibo.com"
_WEIBO_LOGIN_PATH = "/sso/signin"


# ======================================================================
# WeiboPlatform
# ======================================================================

class WeiboPlatform(BasePlatform):
    platform_id = 11
    platform_key = "weibo"
    platform_name = "微博"

    # ------------------------------------------------------------------
    # login()
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Weibo login.

        Real flow (per user testing, 2026-06-15):
        1. Goto ``weibo.com/n/微博创作者中心`` (the creator centre home).
        2. The "登录" link is in the top-right of the page; click it.
        3. Clicking triggers a popup / new tab / redirect to
           ``passport.weibo.com/sso/signin``.
        4. User completes login in the popup (QR scan, phone, password, etc.).
        5. After login, the main page auto-refreshes and shows the user's avatar
           and nickname in the top nav (rendered as ``a[href^="/u/"]`` containing
           an ``img[src*="sinaimg.cn"]``).
        6. ``save_login_result`` runs on the now-authenticated main page.

        No timeout: the user may take as long as needed. Browser close → task
        cancel (handled by ``login_mode=True`` in ``_browser.py``).
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()

                await page.goto(_WEIBO_CREATOR_URL)

                # Scroll a small amount (200px) just in case, but rely on text selector
                await page.evaluate("window.scrollTo(0, 200)")
                await asyncio.sleep(0.5)

                # Click the "登录" link by text (robust against hash class changes).
                # NB: <a> 不带 href 在现代浏览器中没有 link role，所以不能用
                # get_by_role("link", ...)。get_by_text 匹配文本节点，不依赖角色。
                login_link = page.get_by_text("登录").first
                await login_link.click(timeout=15000)
                logger.info("[weibo] login link clicked, waiting for user to complete login")

                # Wait indefinitely for the post-login profile link. The user
                # may take as long as needed; browser close → task cancel
                # (handled by login_mode=True in _browser.py).
                # 等待登录成功标志（无限等）：浏览器关闭由 login_mode=True 处理
                # 必须限定到顶部导航栏 .woo-tab-nav，否则未登录态主页面有热门博主
                # 链接（同样 a[href^="/u/"] img[src*="sinaimg.cn"]）会误判已登录
                await page.locator(
                    '.woo-tab-nav a[href^="/u/"] img[src*="sinaimg.cn"]'
                ).first.wait_for(timeout=999999999)
                logger.info("[weibo] login detected (profile link in top nav)")

                # Give the page a moment to render authenticated content
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                await save_login_result(
                    context, page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_weibo_profile,
                    account_id=account_id,
                )
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await browser.close()

    # ------------------------------------------------------------------
    # check_cookie()
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        if not os.path.exists(cookie_path):
            return False

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(_WEIBO_CREATOR_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await page.wait_for_load_state("networkidle", timeout=10000)

                if _WEIBO_LOGIN_HOST in page.url:
                    logger.info("[weibo] cookie expired, needs re-login")
                    return False

                logger.info("[weibo] cookie valid")
                return True
            except Exception as exc:
                logger.info(f"[weibo] cookie check error: {exc}")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center()
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Weibo creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _WEIBO_CREATOR_URL

        from .._browser import create_browser_sync, create_context_sync

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(url)
                try:
                    page.wait_for_event("close", timeout=0)
                except Exception:
                    pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # sync_profile()
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Weibo creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _WEIBO_CREATOR_URL

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                return await scrape_weibo_profile(page)
            except Exception as e:
                logger.info(f"[weibo] sync profile failed: {e}")
                return "", ""
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # publish_video() — not implemented in this round
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Stub: video publishing for Weibo is not implemented yet.

        Raises NotImplementedError so the platform can still be registered
        and used for login / cookie check / profile sync, while clearly
        signalling that ``publish_video`` is out of scope.
        """
        raise NotImplementedError(
            "WeiboPlatform.publish_video is not implemented in this round"
        )
