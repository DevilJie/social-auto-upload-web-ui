"""
Tencent Video (腾讯视频) platform implementation — CloakBrowser.

Login URL: https://mp.v.qq.com/
Profile page: https://mp.v.qq.com/homepage
Publish URL: https://mp.v.qq.com/publishVideo/video
"""

import asyncio
import json
import logging
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._utils import parse_schedule_time, save_login_result
from ..base_platform import BasePlatform

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://mp.v.qq.com/"
_HOME_URL = "https://mp.v.qq.com/homepage"
_PUBLISH_URL = "https://mp.v.qq.com/publishVideo/video"

# ---------------------------------------------------------------------------
# Creation declaration options (matches the platform checkboxes)
# ---------------------------------------------------------------------------
CREATION_DECLARATIONS = [
    "剧情演绎，仅供娱乐",
    "取材网络，谨慎甄别",
    "个人观点，仅供参考",
    "未成年人请勿学习模仿",
    "内容由AI生成",
]


async def _scrape_tencent_video_profile(page) -> tuple[str, str]:
    """Scrape nickname and avatar from mp.v.qq.com/homepage.

    DOM structure (CSS Module classes with hash suffixes — use partial matches):
      - Avatar:  div[class*="userAvatar"] img  → src
      - Nickname: a[href*="videoplus"][class*="name"]  → text
    """
    name = ""
    avatar = ""

    try:
        # Wait for the user info section to render
        await page.wait_for_selector('div[class*="userInfo"]', timeout=10000)
    except Exception:
        logger.warning("userInfo section not found")

    try:
        name_el = page.locator('a[href*="videoplus"][class*="name"]').first
        if await name_el.count() > 0:
            name = (await name_el.text_content() or "").strip()
    except Exception as e:
        logger.warning("Failed to scrape nickname: %s", e)

    try:
        avatar_el = page.locator('div[class*="userAvatar"] img').first
        if await avatar_el.count() > 0:
            avatar = (await avatar_el.get_attribute("src") or "").strip()
    except Exception as e:
        logger.warning("Failed to scrape avatar: %s", e)

    return name, avatar


class TencentVideoPlatform(BasePlatform):
    platform_id = 9
    platform_key = "tencent_video"
    platform_name = "腾讯视频"

    # ------------------------------------------------------------------
    # login — open browser, wait for user to log in manually
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue) -> None:
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if "homepage" in page.url:
                url_changed_event.set()

        browser = await self.create_browser(login_mode=True)
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(_LOGIN_URL)

                page.on(
                    "framenavigated",
                    lambda frame: asyncio.create_task(_on_url_change())
                    if frame == page.main_frame
                    else None,
                )

                # Wait up to 300s for the user to complete login and land on homepage
                try:
                    await asyncio.wait_for(url_changed_event.wait(), timeout=300)
                    logger.info("Homepage detected — login successful")
                except asyncio.TimeoutError:
                    logger.warning("Login timed out (300 s)")
                    status_queue.put("500")
                    return

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=_scrape_tencent_video_profile,
                )
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(_HOME_URL, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle")

                try:
                    await page.wait_for_selector('div[class*="userInfo"]', timeout=5000)
                    return True
                except Exception:
                    return False
            finally:
                await context.close()
        except Exception as e:
            logger.warning("check_cookie failed: %s", e)
            return False
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — scrape user name and avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple[str, str]:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(_HOME_URL, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle")
                return await _scrape_tencent_video_profile(page)
            finally:
                await context.close()
        except Exception as e:
            logger.warning("sync_profile failed: %s", e)
            return "", ""
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center — open visible browser with stored cookies
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(login_mode=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(_HOME_URL)
            try:
                await page.wait_for_event("close", timeout=0)
            except Exception:
                pass
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # publish_video — full Tencent Video upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Tencent Video via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video file names (relative to videoFile/)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``desc`` (*str*, optional)
        - ``thumbnail_landscape_path`` (*str*, optional) -- cover image path
        - ``creation_declaration`` (*str|list*) -- creation declaration(s)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        """
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", [])
        enableTimer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        creation_declaration = kwargs.get("creation_declaration", "")
        desc = kwargs.get("desc", "")

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(Path(BASE_DIR / "videoFile" / f)) for f in files]
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(
                Path(BASE_DIR / "videoFile" / thumbnail_landscape_path)
            )

        # Parse creation declaration(s)
        declarations = []
        if creation_declaration:
            if isinstance(creation_declaration, list):
                declarations = creation_declaration
            elif isinstance(creation_declaration, str):
                declarations = [
                    d.strip() for d in creation_declaration.split(",") if d.strip()
                ]

        # Parse schedule times
        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(file_paths),
            enableTimer,
            kwargs.get("videos_per_day", 1),
            kwargs.get("daily_times"),
            kwargs.get("start_days", 0),
        )

        for file_index, file_path in enumerate(file_paths):
            for cookie_path in account_paths:
                await self._upload_one_video(
                    title=title,
                    file_path=file_path,
                    tags=tags,
                    publish_date=publish_datetimes[file_index],
                    account_file=cookie_path,
                    enableTimer=enableTimer,
                    thumbnail_landscape_path=thumbnail_landscape_path or None,
                    creation_declarations=declarations,
                    desc=desc,
                )
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        enableTimer: bool = False,
        thumbnail_landscape_path=None,
        creation_declarations=None,
        desc="",
    ):
        """Upload a single video to one Tencent Video account."""
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()
                await page.goto(_PUBLISH_URL)
                await page.wait_for_load_state("networkidle")

                # Step 1: Upload video file via input[type=file]
                logger.info("Uploading video file: %s", file_path)
                file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(file_path)
                logger.info("Video file set, waiting for upload to complete...")

                # Step 2: Wait for the publish form to appear after upload
                # The form title "视频1" signals upload is done
                await page.wait_for_selector(
                    'div[class*="formTitle"]:has-text("视频")',
                    timeout=120000,
                )
                logger.info("Video upload complete, publish form ready")
                await asyncio.sleep(2)

                # Step 3: Fill title
                await self._fill_title(page, title or desc)

                # Step 4: Upload cover image if provided
                if thumbnail_landscape_path:
                    await self._upload_cover(page, thumbnail_landscape_path)

                # Step 5: Set creation declarations (checkboxes)
                if creation_declarations:
                    await self._set_creation_declarations(
                        page, creation_declarations
                    )

                # Step 6: Handle scheduled publishing
                if enableTimer and publish_date != 0:
                    await self._set_schedule_time(page, publish_date)

                # Step 7: Click publish
                await self._click_publish(page)

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("Cookie state updated after publish")
            finally:
                await context.close()
        finally:
            await browser.close()

    @staticmethod
    async def _fill_title(page, title: str):
        """Fill the video title in the contenteditable div."""
        if not title:
            return
        title_container = page.locator(
            'div[data-field-name="videos.0.title"]'
        ).first
        if await title_container.count() == 0:
            logger.warning("Title field not found")
            return

        title_div = title_container.locator(
            'div.ProseMirror.ExEditor-cc-title-input'
        ).first
        if await title_div.count() == 0:
            logger.warning("Title contenteditable div not found")
            return

        await title_div.wait_for(state="visible", timeout=10000)
        await title_div.click()
        # Clear existing content
        await page.keyboard.press("Control+KeyA")
        await asyncio.sleep(0.2)
        await page.keyboard.press("Delete")
        await asyncio.sleep(0.2)
        # Type the title (max 80 chars per the platform)
        await page.keyboard.type(title[:80])
        logger.info("Title filled: %s", title[:80])

    @staticmethod
    async def _upload_cover(page, cover_path: str):
        """Upload cover image via the cover modal."""
        logger.info("Uploading cover image: %s", cover_path)
        try:
            # Click the "上传横版封面" button area to open the modal
            upload_area = page.locator(
                'div[class*="uploadAddArea"]:has-text("上传横版封面")'
            ).first
            if await upload_area.count() == 0:
                logger.warning("Cover upload area not found")
                return

            await upload_area.wait_for(state="visible", timeout=10000)
            await upload_area.click()
            await asyncio.sleep(1)

            # Wait for the ReactModal to appear
            modal = page.locator('div.ReactModal__Content').first
            await modal.wait_for(state="visible", timeout=10000)
            logger.info("Cover upload modal opened")

            # Find the hidden file input inside the modal by id
            # The input is: <input accept=".jpg,.jpeg,.png,.webp" id="uploadCoverBtn" type="file">
            cover_input = modal.locator('input#uploadCoverBtn')
            await cover_input.wait_for(state="attached", timeout=10000)

            # Use evaluate to set the file since input is display:none
            await cover_input.evaluate(
                "el => el.style.display = 'block'"
            )
            await cover_input.set_input_files(cover_path)
            logger.info("Cover image uploaded to modal")
            await asyncio.sleep(3)

            # Click the "使用" button to confirm the cover
            # From the DOM: button with dt-mpid="上传封面确定"
            use_btn = modal.locator(
                'button[dt-mpid="上传封面确定"]'
            ).first
            if await use_btn.count() > 0:
                await use_btn.click()
                logger.info("Cover confirmed with '上传封面确定' button")
                await asyncio.sleep(1)
            else:
                # Fallback: try any "使用" button
                use_btn_fallback = modal.locator(
                    'button:has-text("使用")'
                ).first
                if await use_btn_fallback.count() > 0:
                    await use_btn_fallback.click()
                    logger.info("Cover confirmed with '使用' button")
                    await asyncio.sleep(1)
                else:
                    logger.warning("Cover '使用' button not found in modal")
        except Exception as e:
            logger.warning("Cover upload failed (non-blocking): %s", e)

    @staticmethod
    async def _set_creation_declarations(page, declarations: list):
        """Check the specified creation declaration checkboxes."""
        logger.info("Setting creation declarations: %s", declarations)
        for decl in declarations:
            if decl not in CREATION_DECLARATIONS:
                logger.warning("Unknown declaration: %s", decl)
                continue
            try:
                # Find the checkbox by its label text
                checkbox = page.locator(
                    f'label[class*="checkboxItem"]:has-text("{decl}")'
                ).first
                if await checkbox.count() == 0:
                    logger.warning("Declaration checkbox not found: %s", decl)
                    continue

                await checkbox.wait_for(state="visible", timeout=5000)
                # Check if already checked
                chk_input = checkbox.locator('input[type="checkbox"]')
                if await chk_input.is_checked():
                    logger.info("Declaration already checked: %s", decl)
                    continue

                await checkbox.click()
                logger.info("Declaration checked: %s", decl)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(
                    "Failed to set declaration '%s' (non-blocking): %s",
                    decl, e,
                )

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Enable scheduled publishing and set the date/time."""
        logger.info("Setting schedule time: %s", publish_date)
        try:
            # Find the toggle switch - check if already enabled
            switch = page.locator('button[role="switch"]').first
            if await switch.count() > 0:
                is_checked = await switch.get_attribute("aria-checked")
                if is_checked != "true":
                    await switch.click()
                    logger.info("Scheduled publish toggled ON")
                    await asyncio.sleep(1)

            # Click the datetime trigger to open the picker
            datetime_trigger = page.locator(
                'div[class*="dateTimeSelect"]'
            ).first
            if await datetime_trigger.count() == 0:
                logger.warning("Datetime trigger not found")
                return

            await datetime_trigger.click()
            await asyncio.sleep(1)

            # Wait for the popup to appear
            popup = page.locator('div[class*="popupWrap"]').first
            if await popup.count() == 0:
                logger.warning("Datetime popup not found")
                return

            # Format date components as they appear in the popup
            date_str = publish_date.strftime("%Y-%m-%d")
            hour_str = f"{publish_date.hour}时"
            minute_str = f"{publish_date.minute}分"

            # Select date in the first list
            date_item = popup.locator(
                f'div[class*="itemWrap"]:has-text("{date_str}")'
            ).first
            if await date_item.count() > 0:
                await date_item.click()
                await asyncio.sleep(0.3)

            # Select hour in the second list
            hour_item = popup.locator(
                f'div[class*="itemWrap"]:has-text("{hour_str}")'
            ).first
            if await hour_item.count() > 0:
                await hour_item.click()
                await asyncio.sleep(0.3)

            # Select minute in the third list
            minute_item = popup.locator(
                f'div[class*="itemWrap"]:has-text("{minute_str}")'
            ).first
            if await minute_item.count() > 0:
                await minute_item.click()
                await asyncio.sleep(0.3)

            # Click "确定" (confirm) button in the popup footer
            confirm_btn = popup.locator('button:has-text("确定")').first
            if await confirm_btn.count() > 0:
                await confirm_btn.click()
                logger.info("Schedule time confirmed: %s", publish_date)
                await asyncio.sleep(1)
        except Exception as e:
            logger.warning(
                "Schedule time setup failed (non-blocking): %s", e
            )

    @staticmethod
    async def _click_publish(page):
        """Click the publish button and wait for completion.

        Waits for either:
        1. URL change to a different mp.v.qq.com page (success redirect)
        2. "提交成功" / "发布成功" text appearing on the page
        """
        logger.info("Clicking publish button")
        try:
            publish_btn = page.locator(
                'button[dt-mpid="video_submit_click"]'
            ).first
            await publish_btn.wait_for(state="visible", timeout=10000)
            await publish_btn.click()
            logger.info("Publish button clicked, waiting for publish result")

            # Wait up to 60s for success indicators
            success = False
            for _ in range(60):
                try:
                    # Check for success text on the page
                    success_text = page.locator(
                        'text=提交成功, text=发布成功, text=投稿成功'
                    ).first
                    if await success_text.count() > 0 and await success_text.is_visible():
                        logger.info("Publish success text detected!")
                        success = True
                        break
                except Exception:
                    pass

                # Also check if URL changed away from publish page
                try:
                    current_url = page.url
                    if "publishVideo" not in current_url:
                        logger.info(
                            "Navigated away from publish page: %s", current_url
                        )
                        success = True
                        break
                except Exception:
                    pass

                await asyncio.sleep(1)

            if success:
                logger.info("Video published successfully")
            else:
                logger.warning(
                    "Publish indicator not found within timeout, "
                    "may still succeed"
                )

            await asyncio.sleep(2)
        except Exception as e:
            logger.warning("Publish click failed: %s", e)
            raise
