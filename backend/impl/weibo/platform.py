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

_WEIBO_CREATOR_URL = "https://weibo.com/set/index"
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
        """Perform Weibo login by navigating to creator centre and waiting for the
        user to complete the SSO popup.

        Flow:
        1. Open ``weibo.com/set/index``. If unauthenticated, the server redirects
           to ``passport.weibo.com/sso/signin``.
        2. Watch ``main_frame``'s ``framenavigated`` event with two flags:
           ``enter_login`` and ``exit_login``. ``exit_login`` fires when the URL
           leaves passport.weibo.com back to weibo.com/xxx.
        3. Delegate to ``save_login_result`` to scrape profile, save cookie, write DB.
        4. The browser is left open on failure (login_mode=True) so the user can
           see what went wrong.
        """
        enter_login = asyncio.Event()
        exit_login = asyncio.Event()

        async def _on_nav(frame):
            if frame != page.main_frame:
                return
            url = frame.url
            is_login_page = _WEIBO_LOGIN_HOST in url and _WEIBO_LOGIN_PATH in url
            if is_login_page:
                enter_login.set()
            elif enter_login.is_set():
                exit_login.set()

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                page.on(
                    "framenavigated",
                    lambda f: asyncio.create_task(_on_nav(f)),
                )
                await page.goto(_WEIBO_CREATOR_URL)

                # Wait for the user to complete login
                await exit_login.wait()
                logger.info("[weibo] login completion detected")

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
                await asyncio.sleep(2)

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
