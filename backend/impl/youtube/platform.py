"""
YouTube platform implementation.

Wraps existing legacy functions from ``vendor/upstream/uploader/youtube_uploader/``
and ``vendor/upstream/myUtils/postVideo.py`` into the ``BasePlatform`` interface.
"""

import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from ..base_platform import BasePlatform
from myUtils.postVideo import post_video_youtube
from myUtils.login import sync_account_profile
from uploader.youtube_uploader.main import youtube_cookie_gen
from uploader.youtube_uploader.main import cookie_auth as youtube_cookie_auth


class YoutubePlatform(BasePlatform):
    platform_id = 8
    platform_key = "youtube"
    platform_name = "YouTube"

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform YouTube login via browser cookie auth."""
        await youtube_cookie_gen(id, status_queue)

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid.

        YouTube's ``cookie_auth`` takes a plain string path, not a ``Path`` object.
        """
        return await youtube_cookie_auth(str(Path(BASE_DIR / "cookiesFile" / cookie_file)))

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from YouTube Studio.

        Delegates to ``sync_account_profile(8, ...)`` which internally imports
        ``_scrape_youtube_profile`` from the legacy YouTube uploader.
        """
        return await sync_account_profile(8, cookie_file)

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open YouTube Studio in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://studio.youtube.com/"

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
        """Publish a video to YouTube.

        Accepted keyword arguments (passed through to ``post_video_youtube``):

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video file names (relative to videoFile/)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_path`` (*str*, optional)
        - ``desc`` (*str*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``audience`` (*str*, optional) -- ``"not_kids"`` (default) or ``"kids"``
        - ``altered_content`` (*bool*, optional) -- whether video contains altered/adjusted content
        """
        post_video_youtube(
            title=kwargs.get("title", ""),
            files=kwargs.get("files", []),
            tags=kwargs.get("tags", []),
            account_file=kwargs.get("account_file", []),
            enableTimer=kwargs.get("enableTimer", False),
            videos_per_day=kwargs.get("videos_per_day", 1),
            daily_times=kwargs.get("daily_times"),
            start_days=kwargs.get("start_days", 0),
            thumbnail_path=kwargs.get("thumbnail_path", ""),
            desc=kwargs.get("desc", ""),
            schedule_time_str=kwargs.get("schedule_time_str", ""),
            audience=kwargs.get("audience", "not_kids"),
            altered_content=kwargs.get("altered_content", False),
        )
        return True
