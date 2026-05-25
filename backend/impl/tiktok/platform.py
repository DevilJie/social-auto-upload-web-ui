"""
TikTok platform implementation — CloakBrowser automation.

All browser operations go through BasePlatform's CloakBrowser entry points.
"""

import asyncio
import re
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue

from conf import BASE_DIR, LOCAL_CHROME_HEADLESS, _load_proxy_url

from .._browser import create_browser_sync
from .._utils import (
    parse_schedule_time,
    save_login_result,
    scrape_user_profile,
)
from ..base_platform import BasePlatform

import logging

logger = logging.getLogger(__name__)

# TikTok upload page uses an iframe; these locators select the correct DOM root.
TK_IFRAME = '[data-tt="Upload_index_iframe"]'
TK_DEFAULT = 'body'


class TiktokPlatform(BasePlatform):
    platform_id = 7
    platform_key = "tiktok"
    platform_name = "TikTok"

    # ------------------------------------------------------------------
    # Proxy helper
    # ------------------------------------------------------------------

    @staticmethod
    def _get_proxy():
        """Return a proxy dict suitable for CloakBrowser / Playwright, or None."""
        url = _load_proxy_url()
        return {"server": url} if url else None

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform TikTok login via browser.

        Opens ``https://www.tiktok.com/login?lang=en`` with proxy and
        ``--lang en-GB``.  Waits up to 120 s for a URL matching
        ``/(foryou|following|upload|@)/``, then scrapes the user profile
        and saves the result via :func:`save_login_result`.
        """
        proxy = self._get_proxy()
        browser = await self.create_browser(
            headless=False,
            login_mode=True,
            proxy=proxy,
            extra_args=["--lang en-GB"],
        )
        try:
            context = await self.create_context(browser)
            page = await context.new_page()
            await page.goto("https://www.tiktok.com/login?lang=en")

            # Wait for post-login redirect (foryou, following, upload, or @profile)
            try:
                await page.wait_for_url(
                    re.compile(r"/(foryou|following|upload|@)"),
                    timeout=120_000,
                )
            except Exception:
                # Timed out — still save whatever state we have
                await asyncio.sleep(3)

            await save_login_result(
                context,
                page,
                platform_id=self.platform_id,
                platform_name=self.platform_name,
                status_queue=status_queue,
                scrape_fn=scrape_user_profile,
            )
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Cookie validation
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid.

        Opens the TikTok Studio upload page and inspects ``<select>``
        elements for a class matching ``tiktok-.*-SelectFormContainer.*``,
        which indicates an expired / unauthenticated session.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        proxy = self._get_proxy()
        browser = await self.create_browser(
            headless=True,
            proxy=proxy,
            extra_args=["--lang en-GB"],
        )
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto("https://www.tiktok.com/tiktokstudio/upload?lang=en")
            await page.wait_for_load_state("networkidle")
            try:
                select_elements = await page.query_selector_all("select")
                for element in select_elements:
                    class_name = await element.get_attribute("class")
                    if class_name and re.match(
                        r"tiktok-.*-SelectFormContainer.*", class_name
                    ):
                        return False
                return True
            except Exception:
                return True
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Profile sync
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from TikTok.

        Opens the TikTok Studio upload page with saved cookies and runs
        the generic :func:`scrape_user_profile` JS scraper.

        Returns:
            tuple[str, str]: ``(display_name, avatar_url)``
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        proxy = self._get_proxy()
        browser = await self.create_browser(
            headless=True,
            proxy=proxy,
            extra_args=["--lang en-GB"],
        )
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(
                "https://www.tiktok.com/tiktokstudio/upload?lang=en",
                wait_until="domcontentloaded",
            )
            return await scrape_user_profile(page)
        except Exception as e:
            logger.info(f"[tiktok] sync_profile error: {e}")
            return ("", "")
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Open creator centre (unchanged — uses sync CloakBrowser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the TikTok creator centre in a visible browser window.

        Uses the same synchronous Playwright pattern as the Douyin
        ``open_creator_center`` implementation.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://www.tiktok.com/tiktokstudio/upload?lang=en"

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = browser.new_context(storage_state=cookie_path)
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
    # Publish video — main entry point (sync)
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to TikTok.

        Accepted keyword arguments:

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
        - ``thumbnail_path`` (*str*, optional) -- thumbnail image file name
        """
        asyncio.run(self._upload_all(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Publish video — async orchestrator
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs) -> None:
        """Iterate over (file, account) combinations and upload each."""
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", [])
        account_files = kwargs.get("account_file", [])
        enable_timer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        thumbnail_path = kwargs.get("thumbnail_path")

        # Resolve paths
        file_paths = [str(Path(BASE_DIR / "videoFile" / f)) for f in files]
        cookie_paths = [
            str(Path(BASE_DIR / "cookiesFile" / c)) for c in account_files
        ]
        thumb = (
            str(Path(BASE_DIR / "videoFile" / thumbnail_path))
            if thumbnail_path
            else None
        )

        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(file_paths),
            enable_timer,
            videos_per_day,
            daily_times,
            start_days,
        )

        for idx, file_path in enumerate(file_paths):
            pub_dt = (
                publish_datetimes[idx]
                if isinstance(publish_datetimes, list)
                else publish_datetimes
            )
            for cookie_path in cookie_paths:
                await self._upload_single(
                    title=title,
                    file_path=file_path,
                    tags=tags,
                    publish_date=pub_dt,
                    account_file=cookie_path,
                    thumbnail_path=thumb,
                )

    # ------------------------------------------------------------------
    # Publish video — single upload
    # ------------------------------------------------------------------

    async def _upload_single(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        thumbnail_path: str | None = None,
    ) -> None:
        """Upload one video to one TikTok account using CloakBrowser.
        """
        proxy = self._get_proxy()
        browser = await self.create_browser(
            headless=LOCAL_CHROME_HEADLESS,
            proxy=proxy,
            extra_args=["--lang en-GB"],
        )
        locator_base = None

        try:
            context = await self.create_context(
                browser, storage_state=account_file
            )
            page = await context.new_page()

            # 1. Change language to English
            await self._change_language(page)

            # 2. Navigate to upload page
            await page.goto("https://www.tiktok.com/tiktokstudio/upload")
            logger.info(f"[tiktok] Uploading — {title}")

            await page.wait_for_url(
                "https://www.tiktok.com/tiktokstudio/upload", timeout=10_000
            )

            # 3. Wait for iframe or direct upload container
            try:
                await page.wait_for_selector(
                    'iframe[data-tt="Upload_index_iframe"], div.upload-container',
                    timeout=10_000,
                )
            except Exception:
                logger.info("[tiktok] Neither iframe nor div appeared within timeout")

            # 4. Choose base locator (iframe or body)
            if await page.locator(
                'iframe[data-tt="Upload_index_iframe"]'
            ).count():
                locator_base = page.frame_locator(TK_IFRAME)
            else:
                locator_base = page.locator(TK_DEFAULT)

            # 5. Upload video via file chooser
            upload_button = locator_base.locator(
                'button:has-text("Select video"):visible'
            )
            await upload_button.wait_for(state="visible")
            async with page.expect_file_chooser() as fc_info:
                await upload_button.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(file_path)

            # 6. Fill title + tags
            await self._add_title_tags(page, locator_base, title, tags)

            # 7. Wait for upload to finish
            await self._detect_upload_status(page, locator_base, file_path)

            # 8. Upload thumbnail if provided
            if thumbnail_path:
                logger.info(f"[tiktok] Uploading thumbnail — {title}")
                await self._upload_thumbnail(page, locator_base, thumbnail_path)

            # 9. Schedule if needed
            if publish_date != 0:
                await self._set_schedule_time(page, locator_base, publish_date)

            # 10. Click publish
            await self._click_publish(page, locator_base)

            # 11. Log video ID
            video_id = await self._get_last_video_id(page, locator_base)
            logger.info(f"[tiktok] video_id: {video_id}")

            # 12. Update cookie
            await context.storage_state(path=account_file)
            logger.info("[tiktok] Cookie updated")

            await asyncio.sleep(2)

        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Upload sub-operations (private helpers)
    # ------------------------------------------------------------------

    @staticmethod
    async def _change_language(page) -> None:
        """Switch TikTok UI language to English if not already set."""
        await page.goto("https://www.tiktok.com")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_selector('[data-e2e="nav-more-menu"]')
        text = await page.locator('[data-e2e="nav-more-menu"]').text_content()
        if text == "More":
            return
        await page.locator('[data-e2e="nav-more-menu"]').click()
        await page.locator('[data-e2e="language-select"]').click()
        await page.locator(
            '#creator-tools-selection-menu-header >> text=English (US)'
        ).click()

    @staticmethod
    async def _add_title_tags(page, locator_base, title: str, tags: list) -> None:
        """Enter video title and hashtags into the DraftEditor."""
        editor = locator_base.locator("div.public-DraftEditor-content")
        await editor.click()

        await page.keyboard.press("End")
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Delete")
        await page.keyboard.press("End")

        await page.wait_for_timeout(1000)

        await page.keyboard.insert_text(title)
        await page.wait_for_timeout(1000)
        await page.keyboard.press("End")
        await page.keyboard.press("Enter")

        # Tags
        for index, tag in enumerate(tags, start=1):
            logger.info(f"[tiktok] Setting tag {index}: #{tag}")
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
            await page.keyboard.insert_text(f"#{tag} ")
            await page.keyboard.press("Space")
            await page.wait_for_timeout(1000)
            await page.keyboard.press("Backspace")
            await page.keyboard.press("End")

    @staticmethod
    async def _detect_upload_status(page, locator_base, file_path: str) -> None:
        """Poll until the video has finished uploading (Post button enabled)."""
        while True:
            try:
                post_btn = locator_base.locator(
                    'div.button-group > button >> text=Post'
                )
                disabled = await post_btn.get_attribute("disabled")
                if disabled is None:
                    logger.info("[tiktok] Video uploaded")
                    break
                logger.info("[tiktok] Video uploading...")
                await asyncio.sleep(2)
                # Check for upload error — retry if needed
                if await locator_base.locator(
                    'button[aria-label="Select file"]'
                ).count():
                    logger.info("[tiktok] Upload error detected, retrying...")
                    select_file_btn = locator_base.locator(
                        'button[aria-label="Select file"]'
                    )
                    async with page.expect_file_chooser() as fc_info:
                        await select_file_btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(file_path)
            except Exception:
                logger.info("[tiktok] Video uploading...")
                await asyncio.sleep(2)

    @staticmethod
    async def _upload_thumbnail(page, locator_base, thumbnail_path: str) -> None:
        """Upload a custom video thumbnail."""
        await locator_base.locator(".cover-container").click()
        await locator_base.locator(
            ".cover-edit-container >> text=Upload cover"
        ).click()
        async with page.expect_file_chooser() as fc_info:
            await locator_base.locator(".upload-image-upload-area").click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(thumbnail_path)
        await locator_base.locator(
            'div.cover-edit-panel:not(.hide-panel)'
        ).get_by_role("button", name="Confirm").click()
        await page.wait_for_timeout(3000)

    @staticmethod
    async def _set_schedule_time(page, locator_base, publish_date) -> None:
        """Set a scheduled publish date/time in the TikTok upload form."""
        schedule_input = locator_base.get_by_label("Schedule")
        await schedule_input.wait_for(state="visible")
        await schedule_input.click(force=True)

        # Dismiss "Allow" dialog if present
        if await locator_base.locator(
            'div.TUXButton-content >> text=Allow'
        ).count():
            await locator_base.locator(
                'div.TUXButton-content >> text=Allow'
            ).click()

        scheduled_picker = locator_base.locator("div.scheduled-picker")

        # --- Month navigation ---
        await scheduled_picker.locator("div.TUXInputBox").nth(1).click()
        calendar_month_text = await locator_base.locator(
            "div.calendar-wrapper span.month-title"
        ).inner_text()
        current_month = datetime.strptime(calendar_month_text, "%B").month
        target_month = publish_date.month

        if current_month != target_month:
            if current_month < target_month:
                arrow = locator_base.locator(
                    "div.calendar-wrapper span.arrow"
                ).nth(-1)
            else:
                arrow = locator_base.locator(
                    "div.calendar-wrapper span.arrow"
                ).nth(0)
            await arrow.click()

        # --- Day selection ---
        valid_days = locator_base.locator(
            "div.calendar-wrapper span.day.valid"
        )
        day_count = await valid_days.count()
        for i in range(day_count):
            day_el = valid_days.nth(i)
            text = await day_el.inner_text()
            if text.strip() == str(publish_date.day):
                await day_el.click()
                break

        # --- Time selection ---
        await scheduled_picker.locator("div.TUXInputBox").nth(0).click()

        hour_str = publish_date.strftime("%H")
        correct_minute = int(publish_date.minute / 5)
        minute_str = f"{correct_minute:02d}"

        hour_sel = f"span.tiktok-timepicker-left:has-text('{hour_str}')"
        minute_sel = f"span.tiktok-timepicker-right:has-text('{minute_str}')"

        await page.wait_for_timeout(1000)
        await locator_base.locator(hour_sel).click()
        await page.wait_for_timeout(1000)
        await locator_base.locator(minute_sel).click()

    @staticmethod
    async def _click_publish(page, locator_base) -> None:
        """Click the Post button and wait for redirect to content page."""
        while True:
            try:
                publish_btn = locator_base.locator(
                    "div.button-group button"
                ).nth(0)
                if await publish_btn.count():
                    await publish_btn.click()

                await page.wait_for_url(
                    "https://www.tiktok.com/tiktokstudio/content",
                    timeout=3000,
                )
                logger.info("[tiktok] Video published successfully")
                break
            except Exception:
                logger.info("[tiktok] Video publishing...")
                await asyncio.sleep(0.5)

    @staticmethod
    async def _get_last_video_id(page, locator_base):
        """Extract the video ID of the most recently uploaded video."""
        try:
            await page.wait_for_selector(
                'div[data-tt="components_PostTable_Container"]'
            )
            video_list = locator_base.locator(
                'div[data-tt="components_PostTable_Container"] '
                'div[data-tt="components_PostInfoCell_Container"] a'
            )
            if await video_list.count():
                href = await video_list.nth(0).get_attribute("href")
                if href:
                    match = re.search(r"video/(\d+)", href)
                    return match.group(1) if match else None
        except Exception:
            pass
        return None
