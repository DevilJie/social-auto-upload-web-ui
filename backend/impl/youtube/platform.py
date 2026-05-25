"""
YouTube platform implementation.

Uses 100 % CloakBrowser via ``BasePlatform`` browser entry points.
YouTube Studio uses Polymer Shadow DOM; all element interactions go through
Playwright locators with ``force=True`` to pierce shadow boundaries.
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from queue import Queue

logger = logging.getLogger(__name__)

from conf import BASE_DIR, _load_proxy_url

from .._browser import create_browser_sync
from .._utils import parse_schedule_time, scrape_youtube_profile
from ..base_platform import BasePlatform

YOUTUBE_STUDIO_URL = "https://studio.youtube.com"


def _msg(text: str) -> str:
    return f"[youtube] {text}"


class YoutubePlatform(BasePlatform):
    platform_id = 8
    platform_key = "youtube"
    platform_name = "YouTube"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_proxy(self) -> dict | None:
        """Return proxy dict for CloakBrowser, or None."""
        url = _load_proxy_url()
        return {"server": url} if url else None

    # ------------------------------------------------------------------
    # login — UNIQUE: uses persistent_context (Google requires persistent
    # profile for proxy to work in headed mode)
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform YouTube login via persistent browser context.

        Opens accounts.google.com, waits for the user to complete sign-in,
        then verifies by navigating to YouTube Studio, scrapes the profile,
        and saves storage state + DB record.
        """
        user_data_dir = str(Path(BASE_DIR / "cookiesFile" / "yt_profiles" / id))
        os.makedirs(user_data_dir, exist_ok=True)

        context = None
        try:
            context = await self.create_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                proxy=self._get_proxy(),
            )
            page = context.pages[0] if context.pages else await context.new_page()

            logger.info(_msg("navigating to accounts.google.com"))
            await page.goto("https://accounts.google.com/", timeout=30000)
            logger.info(_msg(f"page loaded, title: {await page.title()}"))

            # Poll URL until it leaves accounts.google.com
            try:
                while True:
                    current_url = page.url
                    if (
                        "accounts.google.com" in current_url
                        and (
                            "signin" in current_url
                            or current_url.endswith("accounts.google.com/")
                        )
                    ):
                        await asyncio.sleep(1)
                        continue
                    logger.info(_msg(f"login detected, current page: {current_url}"))
                    break
            except Exception:
                logger.info(_msg("login poll exception (ignored)"))

            # Verify by navigating to YouTube Studio
            try:
                await page.goto(YOUTUBE_STUDIO_URL, timeout=15000)
                logger.info(_msg("YouTube Studio page opened"))
            except Exception:
                logger.info(_msg("navigation to YouTube Studio failed, cookie may still be saved"))

            # Scrape profile
            user_name, avatar_url = await scrape_youtube_profile(page)
            if not user_name:
                user_name = f"YouTube{int(asyncio.get_event_loop().time())}"

            # Save storage state manually (persistent context)
            uuid_v1 = uuid.uuid1()
            cookies_dir = Path(BASE_DIR / "cookiesFile")
            cookies_dir.mkdir(exist_ok=True)
            cookie_filename = f"{uuid_v1}.json"
            await context.storage_state(path=cookies_dir / cookie_filename)
            logger.info(_msg(f"cookie saved as {cookie_filename}"))

            # Write to database
            with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO user_info (type, filePath, userName, status, avatar)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (8, cookie_filename, user_name, 1, avatar_url),
                )
                conn.commit()
            logger.info(_msg("user record saved to DB"))

            # Send SSE status
            status_queue.put(json.dumps({
                "status": "200",
                "name": user_name,
                "avatar": avatar_url,
            }))

        except Exception as e:
            logger.info(_msg(f"login failed: {type(e).__name__}: {e}"))
            status_queue.put(json.dumps({
                "status": "500",
                "msg": f"YouTube login failed: {e}",
            }))
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # check_cookie
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid.

        Opens YouTube Studio with cookies + proxy.  If the page redirects to
        accounts.google.com or contains ``signin`` in the URL, the cookie
        is invalid.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = None
        try:
            browser = await self.create_browser(headless=True, proxy=self._get_proxy())
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(YOUTUBE_STUDIO_URL, timeout=20000)

            current_url = page.url.lower()
            if "accounts.google.com" in current_url or "signin" in current_url:
                logger.info(_msg("cookie expired"))
                return False

            logger.info(_msg("cookie valid"))
            return True

        except Exception as exc:
            logger.info(_msg(f"cookie check error: {exc}"))
            return False
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # sync_profile
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from YouTube Studio."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = None
        try:
            browser = await self.create_browser(
                headless=True, proxy=self._get_proxy(),
            )
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(YOUTUBE_STUDIO_URL, timeout=30000)
            user_name, avatar_url = await scrape_youtube_profile(page)
            return user_name, avatar_url

        except Exception as e:
            logger.info(_msg(f"sync_profile error: {e}"))
            return "", ""
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # open_creator_center — KEEP AS-IS (synchronous browser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open YouTube Studio in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = YOUTUBE_STUDIO_URL + "/"

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
    # publish_video — CloakBrowser implementation with Polymer Shadow DOM
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to YouTube using CloakBrowser.

        YouTube Studio uses Polymer Shadow DOM.  All element interactions
        use ``force=True`` to pierce shadow boundaries.  The upload flow
        has 4 steps in the UI:

          1. Details — title, description, thumbnail, audience, tags
          2. Video elements — skipped
          3. Checks — skipped
          4. Visibility — public or scheduled

        Accepted keyword arguments:

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
        - ``altered_content`` (*bool*, optional)
        """
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", [])
        account_files = kwargs.get("account_file", [])
        enable_timer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        thumbnail_path = kwargs.get("thumbnail_path", "")
        desc = kwargs.get("desc", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        audience = kwargs.get("audience", "not_kids")
        altered_content = kwargs.get("altered_content", False)

        # Resolve paths
        video_files = [str(Path(BASE_DIR / "videoFile" / f)) for f in files]
        cookie_files = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_files]
        if thumbnail_path:
            thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))

        # Parse schedule times (one per file)
        publish_datetimes = parse_schedule_time(
            schedule_time_str, len(video_files), enable_timer,
            videos_per_day, daily_times, start_days,
        )

        # Upload each file under each account
        for index, video_file in enumerate(video_files):
            publish_dt = publish_datetimes[index] if isinstance(publish_datetimes, list) else publish_datetimes
            for cookie_file in cookie_files:
                await self._upload_one(
                    title=title,
                    file_path=video_file,
                    tags=tags,
                    publish_date=publish_dt,
                    account_file=cookie_file,
                    desc=desc,
                    thumbnail_path=thumbnail_path,
                    audience=audience,
                    altered_content=altered_content,
                )

        return True

    # ------------------------------------------------------------------
    # Internal upload helpers
    # ------------------------------------------------------------------

    async def _upload_one(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        desc: str = "",
        thumbnail_path: str = "",
        audience: str = "not_kids",
        altered_content: bool = False,
    ):
        """Upload a single video to YouTube via CloakBrowser."""
        logger.info(_msg(f"starting upload: {title[:50]}"))

        # Parse tags
        if isinstance(tags, str) and tags.strip():
            parsed_tags = [t.strip() for t in re.split(r'[,，#]', tags) if t.strip()]
        elif isinstance(tags, list):
            parsed_tags = tags
        else:
            parsed_tags = []

        browser = None
        try:
            browser = await self.create_browser(
                headless=False, proxy=self._get_proxy(),
            )
            context = await self.create_context(browser, storage_state=account_file)
            page = await context.new_page()

            # Navigate to YouTube Studio — use domcontentloaded, NOT networkidle
            # (YouTube Studio has persistent network requests that never settle)
            await page.goto(
                YOUTUBE_STUDIO_URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            logger.info(_msg("studio page loading, waiting for Polymer render"))
            await asyncio.sleep(5)

            # ---- Step 1: Open upload dialog ----
            await self._open_upload_dialog(page)

            # ---- Step 2: Upload video file ----
            logger.info(_msg("uploading video file"))
            file_input = page.locator('input[name="Filedata"]').first
            await file_input.wait_for(state="attached", timeout=10000)
            await file_input.set_input_files(file_path)
            logger.info(_msg("video file selected"))

            # ---- Step 3: Wait for upload complete ----
            logger.info(_msg("waiting for upload to finish"))
            title_box = page.locator("#title-textarea #textbox").first
            await title_box.wait_for(state="visible", timeout=300000)  # up to 5 min
            logger.info(_msg("title textarea appeared — upload complete"))

            # Wait for thumbnail uploader to be ready
            try:
                thumb_input = page.locator("ytcp-thumbnail-uploader input#file-loader").first
                await thumb_input.wait_for(state="attached", timeout=60000)
            except Exception:
                logger.info(_msg("thumbnail uploader not found, continuing"))

            # Check for upload failure
            fail_text = page.locator("text=upload failed")
            if await fail_text.count() > 0:
                raise RuntimeError("video upload failed")

            await asyncio.sleep(2)

            # ---- Step 4: Fill details ----
            await self._clear_and_type(page, "#title-textarea #textbox", title[:100])
            if desc:
                await self._clear_and_type(page, "#description-textarea #textbox", desc)

            # Set thumbnail
            if thumbnail_path and os.path.exists(thumbnail_path):
                logger.info(_msg("setting thumbnail"))
                thumb_in = page.locator("ytcp-thumbnail-uploader input#file-loader").first
                await thumb_in.wait_for(state="attached", timeout=10000)
                await thumb_in.set_input_files(thumbnail_path)
                await asyncio.sleep(3)

            # Set audience (kids / not kids)
            await self._click_radio(
                page,
                "VIDEO_MADE_FOR_KIDS_MFK" if audience == "kids" else "VIDEO_MADE_FOR_KIDS_NOT_MFK",
                "audience",
            )

            # Expand advanced settings
            logger.info(_msg("expanding advanced settings"))
            toggle_btn = page.locator("#toggle-button").first
            await toggle_btn.wait_for(state="visible", timeout=10000)
            aria_label = await toggle_btn.get_attribute("aria-label") or ""
            if "hide" not in aria_label.lower() and "collapse" not in aria_label.lower() and "隐藏" not in aria_label:
                await toggle_btn.click(force=True)
                await asyncio.sleep(2)

            # Set altered content
            await self._click_radio(
                page,
                "VIDEO_HAS_ALTERED_CONTENT_YES" if altered_content else "VIDEO_HAS_ALTERED_CONTENT_NO",
                "altered content",
            )

            # Fill tags
            if parsed_tags:
                logger.info(_msg(f"adding {len(parsed_tags)} tags"))
                try:
                    tag_input = page.locator("#tags-container input#text-input").first
                    await tag_input.wait_for(state="visible", timeout=10000)
                    for tag in parsed_tags[:15]:
                        try:
                            await tag_input.click()
                            await asyncio.sleep(0.2)
                            await tag_input.press_sequentially(str(tag), delay=30)
                            await asyncio.sleep(0.3)
                            await tag_input.press("Enter")
                            await asyncio.sleep(0.3)
                        except Exception as exc:
                            logger.info(_msg(f"tag '{tag}' failed: {exc}"))
                except Exception as exc:
                    logger.info(_msg(f"tag input not found: {exc}"))

            # ---- Step 5-7: Click Next 3 times (video elements, checks, visibility) ----
            for step_name in ("video elements", "checks", "visibility"):
                logger.info(_msg(f"clicking next -> {step_name}"))
                next_btn = page.locator("#next-button").first
                await next_btn.wait_for(state="visible", timeout=10000)
                await next_btn.click()
                await asyncio.sleep(2)

            # ---- Step 8: Set visibility ----
            await self._set_visibility(page, publish_date)

            await asyncio.sleep(1)

            # ---- Step 9: Click Done ----
            logger.info(_msg("clicking done"))
            done_btn = page.locator("#done-button").first
            await done_btn.wait_for(state="visible", timeout=10000)
            await done_btn.click()
            await asyncio.sleep(5)

            logger.info(_msg("video published successfully"))

            # Update saved cookie
            try:
                await context.storage_state(path=account_file)
                logger.info(_msg("cookie updated"))
            except Exception:
                pass

        except Exception as exc:
            logger.info(_msg(f"upload failed: {exc}"))
            raise
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Shadow DOM interaction helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _clear_and_type(page, selector: str, text: str):
        """Clear a contenteditable div and type new text."""
        el = page.locator(selector).first
        await el.wait_for(state="visible", timeout=10000)
        await el.click()
        await asyncio.sleep(0.3)
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.2)
        await el.press_sequentially(text, delay=30)

    @staticmethod
    async def _click_radio(page, name: str, label: str):
        """Click a Polymer radio button by name, with verification."""
        try:
            radio = page.locator(f'tp-yt-paper-radio-button[name="{name}"]').first
            await radio.wait_for(state="visible", timeout=10000)
            is_checked = await radio.get_attribute("aria-checked")
            if is_checked == "true":
                logger.info(_msg(f"{label} already set"))
                return
            await radio.click(force=True)
            await asyncio.sleep(1)
            is_checked_after = await radio.get_attribute("aria-checked")
            if is_checked_after == "true":
                logger.info(_msg(f"{label} set"))
            else:
                logger.info(_msg(f"{label} retry"))
                await radio.click(force=True)
                await asyncio.sleep(0.5)
        except Exception as exc:
            logger.info(_msg(f"{label} setting failed: {exc}"))

    async def _open_upload_dialog(self, page):
        """Click the upload button on YouTube Studio home page."""
        logger.info(_msg("opening upload dialog"))
        await asyncio.sleep(5)  # wait for Polymer rendering

        upload_btn = page.locator(
            '#upload-icon, [aria-label="Upload videos"], '
            'ytcp-icon-button[aria-label="Upload videos"]'
        ).first
        await upload_btn.wait_for(state="visible", timeout=20000)
        await upload_btn.click(force=True)
        logger.info(_msg("upload button clicked"))

        file_picker = page.locator("#select-files-button, ytcp-uploads-file-picker").first
        await file_picker.wait_for(state="visible", timeout=15000)
        logger.info(_msg("upload dialog opened"))

    async def _set_visibility(self, page, publish_date):
        """Set video visibility — PUBLIC or scheduled."""
        await asyncio.sleep(2)

        # Click PUBLIC radio button with multiple fallback strategies
        logger.info(_msg("selecting PUBLIC visibility"))
        privacy_radios = page.locator("#privacy-radios").first
        await privacy_radios.wait_for(state="visible", timeout=15000)

        public_radio = page.locator('tp-yt-paper-radio-button[name="PUBLIC"]').first
        await public_radio.wait_for(state="visible", timeout=10000)
        is_checked = await public_radio.get_attribute("aria-checked")
        if is_checked != "true":
            # Strategy 1: evaluate click
            await public_radio.evaluate("el => el.click()")
            await asyncio.sleep(1.5)
            is_checked = await public_radio.get_attribute("aria-checked")
            if is_checked != "true":
                # Strategy 2: force click
                await public_radio.click(force=True)
                await asyncio.sleep(1.5)
                is_checked = await public_radio.get_attribute("aria-checked")
                if is_checked != "true":
                    # Strategy 3: click offRadio
                    try:
                        off_radio = public_radio.locator("#offRadio").first
                        await off_radio.click(force=True)
                        await asyncio.sleep(1)
                    except Exception:
                        pass
        logger.info(_msg("PUBLIC radio selected"))

        # Schedule if needed
        is_scheduled = publish_date != 0 and publish_date is not None
        if is_scheduled:
            await self._set_scheduled_publish(page, publish_date)

    async def _set_scheduled_publish(self, page, publish_date):
        """Set scheduled publish date, time, and timezone."""
        try:
            await asyncio.sleep(2)

            # Format date/time
            if isinstance(publish_date, datetime):
                dt = publish_date
            else:
                dt = datetime.fromtimestamp(int(publish_date))
            date_str = f"{dt.year}年{dt.month}月{dt.day}日"
            time_str = f"{dt.hour:02d}:{dt.minute:02d}"

            logger.info(_msg(f"scheduling: {date_str} {time_str}"))

            # Click second-container to expand schedule option
            second_container = page.locator("#second-container").first
            await second_container.wait_for(state="visible", timeout=10000)
            await second_container.click(force=True)
            await asyncio.sleep(1)

            # Expand schedule details
            try:
                expand_btn = page.locator("#second-container-expand-button").first
                if await expand_btn.is_visible():
                    await expand_btn.click(force=True)
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Set date
            logger.info(_msg(f"setting date: {date_str}"))
            date_trigger = page.locator("#datepicker-trigger").first
            await date_trigger.wait_for(state="visible", timeout=10000)
            await date_trigger.click(force=True)
            await asyncio.sleep(1)

            date_input = page.locator(
                "#datepicker-trigger tp-yt-iron-input input, "
                "tp-yt-paper-dialog.ytcp-datepicker tp-yt-iron-input input"
            ).first
            try:
                await date_input.wait_for(state="visible", timeout=5000)
                await date_input.click()
                await asyncio.sleep(0.3)
                await page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
                await date_input.press_sequentially(date_str, delay=30)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)
            except Exception:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                dropdown_text = date_trigger.locator(".dropdown-trigger-text").first
                await dropdown_text.click(force=True)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
                await dropdown_text.press_sequentially(date_str, delay=30)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)

            # Set time
            logger.info(_msg(f"setting time: {time_str}"))
            time_input = page.locator(
                "#time-of-day-container tp-yt-iron-input input, "
                "#time-of-day-container input"
            ).first
            await time_input.wait_for(state="visible", timeout=10000)
            await time_input.click()
            await asyncio.sleep(0.3)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await time_input.press_sequentially(time_str, delay=30)
            await asyncio.sleep(0.3)
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.5)

            # Set timezone to GMT+8 (Hong Kong)
            logger.info(_msg("setting timezone GMT+8"))
            try:
                tz_btn = page.locator('button[aria-label="时区"], #timezone-select-button').first
                await tz_btn.wait_for(state="visible", timeout=5000)
                await tz_btn.click(force=True)
                await asyncio.sleep(1)

                tz_option = page.locator(
                    'tp-yt-paper-item:has-text("（GMT+08:00）香港"), '
                    'tp-yt-paper-item:has-text("(GMT+08:00) Hong Kong"), '
                    'tp-yt-paper-item:has-text("GMT+08:00")'
                ).first
                await tz_option.wait_for(state="visible", timeout=5000)
                await tz_option.click()
                logger.info(_msg("timezone set to GMT+8"))
            except Exception as exc:
                logger.info(_msg(f"timezone setting failed, using default: {exc}"))
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass

            await asyncio.sleep(1)
            logger.info(_msg("scheduled publish configured"))

        except Exception as exc:
            logger.info(_msg(f"scheduled publish failed: {exc}"))
