"""
Douyin platform implementation.

Wraps existing legacy functions from ``vendor/upstream/myUtils/`` and
``vendor/upstream/postVideo.py`` into the ``BasePlatform`` interface.
"""

import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from ..base_platform import BasePlatform
from myUtils.auth import cookie_auth_douyin
from myUtils.login import douyin_cookie_gen, sync_account_profile
from myUtils.postVideo import post_video_DouYin


class DouyinPlatform(BasePlatform):
    platform_id = 3
    platform_key = "douyin"
    platform_name = "抖音"

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform Douyin login via QR code scan."""
        await douyin_cookie_gen(id, status_queue)

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid."""
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)
        return await cookie_auth_douyin(cookie_path)

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Douyin creator centre."""
        return await sync_account_profile(3, cookie_file)

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Douyin creator centre in a visible browser window.

        Uses the same synchronous Playwright pattern as the legacy
        ``sau_backend.py`` ``open_creator_center`` route.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://creator.douyin.com/"

        def _launch():
            from patchright.sync_api import sync_playwright
            from myUtils.browser import create_browser_sync, create_context_sync

            pw = sync_playwright().start()
            try:
                browser = create_browser_sync(pw, headless=False)
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
                pw.stop()

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Douyin.

        Accepted keyword arguments (passed through to ``post_video_DouYin``):

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video file names (relative to videoFile/)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``category`` (*int*, optional)
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_landscape_path`` (*str*, optional)
        - ``thumbnail_portrait_path`` (*str*, optional)
        - ``productLink`` (*str*, optional)
        - ``productTitle`` (*str*, optional)
        - ``desc`` (*str*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``ai_content`` (*str*, optional)
        """
        post_video_DouYin(
            title=kwargs.get("title", ""),
            files=kwargs.get("files", []),
            tags=kwargs.get("tags", []),
            account_file=kwargs.get("account_file", []),
            category=kwargs.get("category"),
            enableTimer=kwargs.get("enableTimer", False),
            videos_per_day=kwargs.get("videos_per_day", 1),
            daily_times=kwargs.get("daily_times"),
            start_days=kwargs.get("start_days", 0),
            thumbnail_landscape_path=kwargs.get("thumbnail_landscape_path", ""),
            thumbnail_portrait_path=kwargs.get("thumbnail_portrait_path", ""),
            productLink=kwargs.get("productLink", ""),
            productTitle=kwargs.get("productTitle", ""),
            desc=kwargs.get("desc", ""),
            schedule_time_str=kwargs.get("schedule_time_str", ""),
            ai_content=kwargs.get("ai_content", ""),
        )
        return True
