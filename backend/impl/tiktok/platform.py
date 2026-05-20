"""
TikTok platform implementation.

Wraps existing legacy functions from ``vendor/upstream/uploader/tk_uploader/`` and
``vendor/upstream/myUtils/postVideo.py`` into the ``BasePlatform`` interface.
"""

import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from ..base_platform import BasePlatform
from myUtils.postVideo import post_video_tiktok
from uploader.tk_uploader.main_chrome import get_tiktok_cookie_wrapper as get_tiktok_cookie
from uploader.tk_uploader.main_chrome import cookie_auth as tiktok_cookie_auth
from myUtils.login import sync_account_profile


class TiktokPlatform(BasePlatform):
    platform_id = 7
    platform_key = "tiktok"
    platform_name = "TikTok"

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform TikTok login via browser."""
        await get_tiktok_cookie(id, status_queue)

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        return await tiktok_cookie_auth(cookie_path)

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from TikTok creator centre."""
        return await sync_account_profile(7, cookie_file)

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the TikTok creator centre in a visible browser window.

        Uses the same synchronous Playwright pattern as the Douyin
        ``open_creator_center`` implementation.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://www.tiktok.com/tiktokstudio/upload?lang=en"

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
        """Publish a video to TikTok.

        Accepted keyword arguments (passed through to ``post_video_tiktok``):

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video file names (relative to videoFile/)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``desc`` (*str*, optional)
        - ``schedule_time_str`` (*str*, optional)
        """
        post_video_tiktok(
            title=kwargs.get("title", ""),
            files=kwargs.get("files", []),
            tags=kwargs.get("tags", []),
            account_file=kwargs.get("account_file", []),
            enableTimer=kwargs.get("enableTimer", False),
            videos_per_day=kwargs.get("videos_per_day", 1),
            daily_times=kwargs.get("daily_times"),
            start_days=kwargs.get("start_days", 0),
            desc=kwargs.get("desc", ""),
            schedule_time_str=kwargs.get("schedule_time_str", ""),
        )
        return True
