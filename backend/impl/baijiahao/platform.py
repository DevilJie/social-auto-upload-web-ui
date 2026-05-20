"""
Baijiahao (Bai Jia Hao) platform implementation.

Wraps existing legacy functions from ``vendor/upstream/uploader/baijiahao_uploader/``
and ``vendor/upstream/myUtils/postVideo.py`` into the ``BasePlatform`` interface.
"""

import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from ..base_platform import BasePlatform
from myUtils.postVideo import post_video_baijiahao
from uploader.baijiahao_uploader.main import cookie_auth as baijiahao_cookie_auth
from uploader.baijiahao_uploader.main import baijiahao_cookie_gen_wrapper as baijiahao_cookie_gen
from uploader.baijiahao_uploader.main import _scrape_baijiahao_profile


class BaijiahaoPlatform(BasePlatform):
    platform_id = 6
    platform_key = "baijiahao"
    platform_name = "百家号"

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform Baijiahao login via QR code scan."""
        await baijiahao_cookie_gen(id, status_queue)

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        return await baijiahao_cookie_auth(cookie_path)

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Baijiahao account settings page.

        Uses ``_scrape_baijiahao_profile`` to scrape the rendered account
        settings page.
        """
        from patchright.async_api import async_playwright
        from myUtils.browser import create_browser, create_context

        async with async_playwright() as p:
            browser = await create_browser(p, headless=True)
            context = await create_context(
                browser,
                storage_state=str(Path(BASE_DIR / "cookiesFile" / cookie_file)),
            )
            page = await context.new_page()
            await page.goto("https://baijiahao.baidu.com/builder/rc/home")
            name, avatar = await _scrape_baijiahao_profile(page)
            await page.close()
            await context.close()
            await browser.close()
            return name, avatar

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Baijiahao creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://baijiahao.baidu.com/"

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
        """Publish a video to Baijiahao.

        Accepted keyword arguments (passed through to ``post_video_baijiahao``):

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video file names (relative to videoFile/)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_landscape_path`` (*str*, optional)
        - ``thumbnail_portrait_path`` (*str*, optional)
        - ``desc`` (*str*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``creation_declaration`` (*str*, optional)
        - ``supplementary_declaration`` (*str*, optional)
        - ``ai_content`` (*bool*, optional)
        """
        post_video_baijiahao(
            title=kwargs.get("title", ""),
            files=kwargs.get("files", []),
            tags=kwargs.get("tags", []),
            account_file=kwargs.get("account_file", []),
            enableTimer=kwargs.get("enableTimer", False),
            videos_per_day=kwargs.get("videos_per_day", 1),
            daily_times=kwargs.get("daily_times"),
            start_days=kwargs.get("start_days", 0),
            thumbnail_landscape_path=kwargs.get("thumbnail_landscape_path"),
            thumbnail_portrait_path=kwargs.get("thumbnail_portrait_path"),
            desc=kwargs.get("desc", ""),
            schedule_time_str=kwargs.get("schedule_time_str", ""),
            creation_declaration=kwargs.get("creation_declaration", ""),
            supplementary_declaration=kwargs.get("supplementary_declaration", ""),
            ai_content=kwargs.get("ai_content", False),
        )
        return True
