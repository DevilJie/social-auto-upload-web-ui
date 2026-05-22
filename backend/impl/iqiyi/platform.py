"""
iQiyi (爱奇艺) platform implementation — CloakBrowser.

Login URL: https://creator.iqiyi.com/
Publish URL: https://creator.iqiyi.com/publish/video/wemedia
"""

import asyncio
import logging
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._utils import parse_schedule_time, save_login_result
from ..base_platform import BasePlatform

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://creator.iqiyi.com/"
_PUBLISH_URL = "https://creator.iqiyi.com/publish/video/wemedia"

# ---------------------------------------------------------------------------
# Creation declaration mapping (radio values → human-readable labels)
# ---------------------------------------------------------------------------
CREATION_DECLARATION_MAP = {
    "含AI生成内容": "1",
    "含虚构演绎内容": "2",
    "内容含营销信息": "4",
    "内容为转载": "6",
    "个人观点，仅供参考": "5",
    "内容无需标注": "0",
}

# Reverse: value → label
CREATION_DECLARATION_REVERSE = {v: k for k, v in CREATION_DECLARATION_MAP.items()}

# ---------------------------------------------------------------------------
# Risk warning options
# ---------------------------------------------------------------------------
RISK_WARNING_OPTIONS = [
    "内容可能引人不适，请谨慎观看",
    "内容含有高危险行为，请勿模仿",
    "请理性适度消费",
    "未成年人请在监护人指导下浏览",
]


async def _scrape_iqiyi_profile(page) -> tuple[str, str]:
    """Scrape nickname and avatar from creator.iqiyi.com.

    DOM structure:
      - Avatar: div[class*="user-info"] img  → src
      - Nickname: span[class*="emoji-wrap"]  → text
    """
    name = ""
    avatar = ""

    try:
        await page.wait_for_selector('[class*="user-info"]', timeout=10000)
    except Exception:
        logger.warning("user-info section not found")

    try:
        name_el = page.locator('span[class*="emoji-wrap"]').first
        if await name_el.count() > 0:
            name = (await name_el.text_content() or "").strip()
    except Exception as e:
        logger.warning("Failed to scrape nickname: %s", e)

    try:
        avatar_el = page.locator('[class*="user-info"] img').first
        if await avatar_el.count() > 0:
            avatar = (await avatar_el.get_attribute("src") or "").strip()
    except Exception as e:
        logger.warning("Failed to scrape avatar: %s", e)

    return name, avatar


class IqiyiPlatform(BasePlatform):
    platform_id = 10
    platform_key = "iqiyi"
    platform_name = "爱奇艺"

    # ------------------------------------------------------------------
    # login — open browser, wait for user to log in manually
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue) -> None:
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if page.url.strip("/") == _LOGIN_URL.strip("/"):
                # After login, the page reloads at the same URL with auth
                # Check for user-info to confirm
                try:
                    await page.wait_for_selector(
                        '[class*="user-info"]', timeout=5000
                    )
                    url_changed_event.set()
                except Exception:
                    pass

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

                # Wait up to 300 s for login
                try:
                    await asyncio.wait_for(url_changed_event.wait(), timeout=300)
                    logger.info("Login detected — user-info found")
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
                    scrape_fn=_scrape_iqiyi_profile,
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
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle")

                try:
                    await page.wait_for_selector(
                        '[class*="user-info"]', timeout=5000
                    )
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
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle")
                return await _scrape_iqiyi_profile(page)
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
            await page.goto(_LOGIN_URL)
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
    # publish_video — full iQiyi upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to iQiyi via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video file names (relative to videoFile/)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``desc`` (*str*, optional)
        - ``thumbnail_path`` (*str*, optional) -- cover image path
        - ``thumbnail_landscape_path`` (*str*, optional) -- landscape cover
        - ``thumbnail_portrait_path`` (*str*, optional) -- portrait cover
        - ``creation_declaration`` (*str*) -- creation declaration label
        - ``risk_warning`` (*str*, optional) -- risk warning label
        - ``enable_cash_activity`` (*bool*, optional) -- participate in cash activity
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
        thumbnail_path = kwargs.get("thumbnail_path", "")
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        creation_declaration = kwargs.get("creation_declaration", "")
        risk_warning = kwargs.get("risk_warning", "")
        enable_cash_activity = kwargs.get("enable_cash_activity", False)
        desc = kwargs.get("desc", "")

        # Resolve full paths
        account_paths = [
            str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file
        ]
        file_paths = [str(Path(BASE_DIR / "videoFile" / f)) for f in files]

        cover_path = ""
        for p in [thumbnail_portrait_path, thumbnail_path, thumbnail_landscape_path]:
            if p:
                cover_path = str(Path(BASE_DIR / "videoFile" / p))
                break

        landscape_cover = ""
        if thumbnail_landscape_path:
            landscape_cover = str(
                Path(BASE_DIR / "videoFile" / thumbnail_landscape_path)
            )

        portrait_cover = ""
        if thumbnail_portrait_path:
            portrait_cover = str(
                Path(BASE_DIR / "videoFile" / thumbnail_portrait_path)
            )

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
                    cover_path=portrait_cover or cover_path or None,
                    landscape_cover=landscape_cover or None,
                    creation_declaration=creation_declaration,
                    risk_warning=risk_warning,
                    enable_cash_activity=enable_cash_activity,
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
        cover_path=None,
        landscape_cover=None,
        creation_declaration="",
        risk_warning="",
        enable_cash_activity=False,
        desc="",
    ):
        """Upload a single video to one iQiyi account."""
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
                await page.wait_for_selector(
                    '[class*="wemedia-catalog-form"]',
                    timeout=120000,
                )
                logger.info("Video upload complete, publish form ready")
                await asyncio.sleep(3)

                # Step 3: Fill title
                await self._fill_title(page, title or desc)

                # Step 4: Fill description
                await self._fill_description(page, desc)

                # Step 5: Click cash activity if enabled
                if enable_cash_activity:
                    await self._click_cash_activity(page)

                # Step 6: Set creation declaration (required — radio)
                if creation_declaration:
                    await self._set_creation_declaration(
                        page, creation_declaration
                    )

                # Step 7: Set risk warning (optional — select)
                if risk_warning:
                    await self._set_risk_warning(page, risk_warning)

                # Step 8: Upload cover image(s)
                logger.info("Step 8: cover_path=%s, landscape_cover=%s", cover_path, landscape_cover)
                if cover_path or landscape_cover:
                    logger.info(">>> Calling _upload_cover <<<")
                    await self._upload_cover(
                        page,
                        portrait_path=cover_path,
                        landscape_path=landscape_cover,
                    )
                else:
                    logger.warning("Step 8: SKIPPED — no cover paths provided")

                # Step 9: Handle scheduled publishing
                if enableTimer and publish_date != 0:
                    await self._set_schedule_time(page, publish_date)

                # Step 10: Click publish / submit
                await self._click_publish(page)

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("Cookie state updated after publish")
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Form field helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _fill_title(page, title: str):
        """Fill the video title."""
        if not title:
            return

        # Target: input.catalog-desc-title-input input[type="text"]
        # or just find by placeholder
        title_input = page.locator(
            'input[placeholder*="标题字数"]'
        ).first
        if await title_input.count() == 0:
            # Fallback: any title-related input
            title_input = page.locator(
                '.catalog-desc-title-input input[type="text"]'
            ).first
        if await title_input.count() == 0:
            logger.warning("Title input not found")
            return

        await title_input.wait_for(state="visible", timeout=10000)
        await title_input.click()
        await asyncio.sleep(0.3)

        # Clear existing content
        await page.keyboard.press("Control+KeyA")
        await asyncio.sleep(0.2)
        await page.keyboard.press("Delete")
        await asyncio.sleep(0.2)

        # iQiyi title max 30 chars
        await page.keyboard.type(title[:30])
        logger.info("Title filled: %s", title[:30])

    @staticmethod
    async def _fill_description(page, desc: str):
        """Fill the video description."""
        if not desc:
            return

        desc_textarea = page.locator(
            'textarea[placeholder*="作品简介"]'
        ).first
        if await desc_textarea.count() == 0:
            logger.warning("Description textarea not found")
            return

        await desc_textarea.wait_for(state="visible", timeout=5000)
        await desc_textarea.click()
        await asyncio.sleep(0.3)

        # Clear
        await page.keyboard.press("Control+KeyA")
        await asyncio.sleep(0.2)
        await page.keyboard.press("Delete")
        await asyncio.sleep(0.2)

        # iQiyi description max 450 chars
        await page.keyboard.type(desc[:450])
        logger.info("Description filled: %s", desc[:50])

    @staticmethod
    async def _set_creation_declaration(page, declaration: str):
        """Set the creation declaration (required — radio button).

        ``declaration`` can be a label (e.g. "含AI生成内容") or a value ("1").
        """
        # Determine the radio value to click
        value = CREATION_DECLARATION_MAP.get(declaration, declaration)

        logger.info("Setting creation declaration to value=%s", value)

        try:
            # Click the <label class="el-radio"> that wraps the matching radio input
            label = page.locator(
                f'.form-declare-group label.el-radio '
                f'input[type="radio"][value="{value}"] '
                f'>> xpath=ancestor::label'
            ).first
            if await label.count() == 0:
                # Fallback: find by text content
                decl_label = CREATION_DECLARATION_REVERSE.get(value, declaration)
                label = page.locator(
                    f'.form-declare-group label.el-radio:has-text("{decl_label}")'
                ).first

            if await label.count() > 0:
                await label.wait_for(state="visible", timeout=5000)
                await label.click()
                logger.info(
                    "Creation declaration set to: %s", declaration
                )
                await asyncio.sleep(0.5)
            else:
                logger.warning(
                    "Creation declaration label not found for value=%s", value
                )
        except Exception as e:
            logger.warning(
                "Failed to set creation declaration (non-blocking): %s", e
            )

    @staticmethod
    async def _set_risk_warning(page, warning: str):
        """Set the risk warning (optional — select dropdown)."""
        if warning not in RISK_WARNING_OPTIONS:
            logger.warning("Unknown risk warning: %s", warning)
            return

        logger.info("Setting risk warning: %s", warning)

        try:
            # Click the select trigger to open the dropdown
            select_trigger = page.locator(
                '.form-select-full .el-input__inner'
            ).first
            if await select_trigger.count() == 0:
                logger.warning("Risk warning select not found")
                return

            await select_trigger.click()
            await asyncio.sleep(1)

            # Wait for the dropdown to appear and click the option
            option = page.locator(
                f'.el-select-dropdown__item:has-text("{warning}")'
            ).first
            if await option.count() > 0:
                await option.wait_for(state="visible", timeout=5000)
                await option.click()
                logger.info("Risk warning set to: %s", warning)
                await asyncio.sleep(0.5)
            else:
                logger.warning("Risk warning option not found: %s", warning)
        except Exception as e:
            logger.warning(
                "Failed to set risk warning (non-blocking): %s", e
            )

    @staticmethod
    async def _click_cash_activity(page):
        """Click the cash activity (打卡挑战赛) radio to enable it."""
        logger.info("Clicking cash activity")
        try:
            activity = page.locator(
                '.activity-radio-option:not(.is-checked)'
            ).first
            if await activity.count() > 0:
                await activity.click()
                logger.info("Cash activity clicked")
                await asyncio.sleep(0.5)
            else:
                logger.info("Cash activity already checked or not found")
        except Exception as e:
            logger.warning("Failed to click cash activity (non-blocking): %s", e)

    @staticmethod
    async def _upload_cover(
        page,
        portrait_path=None,
        landscape_path=None,
        **kwargs,
    ):
        """Upload cover image on the publish page.

        iQiyi cover dialog flow (Plupload/moxie):
        1. Click "选择封面" → opens crop dialog, default portrait tab active
        2. Click ".upload-btn-wrap" → triggers Plupload file chooser → upload portrait
        3. Wait for portrait upload to fully complete on server
        4. Click "设置横封面" button to switch to landscape tab
        5. Click ".upload-btn-wrap" → triggers Plupload file chooser → upload landscape
        6. Wait for landscape upload to fully complete
        7. Click "完成" to confirm
        """
        portrait_path = portrait_path or kwargs.get("cover_path")
        landscape_path = landscape_path or kwargs.get("landscape_path")

        print(f"[COVER] START — portrait={portrait_path}, landscape={landscape_path}", flush=True)

        try:
            # Step 1: Click "选择封面" to open the cover selection dialog
            print("[COVER] Step 1: Clicking '选择封面'...", flush=True)
            trigger = page.locator('div.main-edit-bar').first
            if await trigger.count() == 0:
                print("[COVER] Step 1: '选择封面' not found, abort", flush=True)
                return

            await trigger.scroll_into_view_if_needed()
            await trigger.wait_for(state="visible", timeout=10000)
            await trigger.evaluate("el => el.click()")
            print("[COVER] Step 1: Clicked OK", flush=True)

            # Wait for crop dialog
            dialog_body = page.locator('.el-dialog__body').first
            await dialog_body.wait_for(state="visible", timeout=10000)
            print("[COVER] Step 1: Dialog opened", flush=True)
            await asyncio.sleep(2)

            # Step 2: Upload portrait cover via file chooser
            if portrait_path:
                print(f"[COVER] Step 2: Uploading portrait via file chooser: {portrait_path}", flush=True)
                upload_btn = dialog_body.locator('.upload-btn-wrap').first
                await upload_btn.wait_for(state="visible", timeout=10000)
                async with page.expect_file_chooser() as fc_info:
                    await upload_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(portrait_path)
                print("[COVER] Step 2: File chosen, waiting 10s for server upload...", flush=True)
                await asyncio.sleep(10)
                print("[COVER] Step 2: Portrait upload wait done", flush=True)
            else:
                print("[COVER] Step 2: SKIPPED (no portrait_path)", flush=True)

            # Step 3: Click "设置横封面" to switch to landscape tab
            if landscape_path:
                print("[COVER] Step 3: Clicking '设置横封面'...", flush=True)
                set_landscape_btn = page.locator('button:has-text("设置横封面")').first
                if await set_landscape_btn.count() > 0:
                    await set_landscape_btn.wait_for(state="visible", timeout=10000)
                    await set_landscape_btn.click()
                    print("[COVER] Step 3: Clicked OK, waiting 3s...", flush=True)
                    await asyncio.sleep(3)

                    # Upload landscape cover via file chooser
                    print(f"[COVER] Step 3: Uploading landscape: {landscape_path}", flush=True)
                    upload_btn = dialog_body.locator('.upload-btn-wrap').first
                    await upload_btn.wait_for(state="visible", timeout=10000)
                    async with page.expect_file_chooser() as fc_info:
                        await upload_btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(landscape_path)
                    print("[COVER] Step 3: File chosen, waiting 10s for server upload...", flush=True)
                    await asyncio.sleep(10)
                    print("[COVER] Step 3: Landscape upload wait done", flush=True)
                else:
                    print("[COVER] Step 3: '设置横封面' button NOT found", flush=True)
            else:
                print("[COVER] Step 3: SKIPPED (no landscape_path)", flush=True)

            # Step 4: Click "完成" to confirm
            print("[COVER] Step 4: Clicking '完成'...", flush=True)
            done_btn = page.locator('button:has-text("完成")').first
            if await done_btn.count() > 0:
                await done_btn.wait_for(state="visible", timeout=10000)
                await done_btn.click()
                print("[COVER] Step 4: Clicked '完成' — cover done", flush=True)
                await asyncio.sleep(2)
            else:
                print("[COVER] Step 4: '完成' button NOT found", flush=True)
        except Exception as e:
            print(f"[COVER] EXCEPTION: {e}", flush=True)
            logger.warning("Cover upload failed: %s", e, exc_info=True)

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Enable scheduled publishing and set the date/time."""
        logger.info("Setting schedule time: %s", publish_date)
        try:
            # Click "定时发布" radio
            schedule_radio = page.locator(
                '.form-publish-block .el-radio-group '
                'label:has-text("定时发布")'
            ).first
            if await schedule_radio.count() > 0:
                await schedule_radio.click()
                logger.info("Schedule radio selected")
                await asyncio.sleep(1)

            # The date picker should appear — find the date input
            date_input = page.locator(
                '.form-publish-block input[placeholder*="选择日期"], '
                '.form-publish-block input[placeholder*="时间"]'
            ).first
            if await date_input.count() > 0:
                await date_input.click()
                await asyncio.sleep(1)

                # Format datetime
                date_str = publish_date.strftime("%Y-%m-%d")
                time_str = publish_date.strftime("%H:%M")

                # Type the date directly
                await date_input.fill(f"{date_str} {time_str}")
                logger.info(
                    "Schedule date set to: %s %s", date_str, time_str
                )
                await asyncio.sleep(1)

                # Press Enter to confirm
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)
            else:
                logger.warning("Schedule date input not found")
        except Exception as e:
            logger.warning(
                "Schedule time setup failed (non-blocking): %s", e
            )

    @staticmethod
    async def _click_publish(page):
        """Click the publish button and wait for navigation to the success page.

        iQiyi redirects away from ``/publish/video/wemedia`` on success.
        """
        logger.info("Clicking publish button")
        try:
            publish_btn = page.locator(
                'button:has-text("发布"), '
                'button:has-text("提交"), '
                'button[type="submit"]'
            ).first

            await publish_btn.wait_for(state="visible", timeout=10000)
            await publish_btn.click()
            logger.info("Publish button clicked, waiting for navigation")

            # Wait for navigation away from the publish URL
            success = False
            try:
                await page.wait_for_url(
                    lambda url: "creator.iqiyi.com/publish/video/wemedia"
                    not in url,
                    timeout=60000,
                )
                logger.info(
                    "Navigated to success page: %s", page.url
                )
                success = True
            except Exception:
                logger.warning(
                    "Navigation timeout — still on publish page, "
                    "may still succeed"
                )

            await asyncio.sleep(2)

            if success:
                logger.info("Video published successfully")
        except Exception as e:
            logger.warning("Publish click failed: %s", e)
            raise
