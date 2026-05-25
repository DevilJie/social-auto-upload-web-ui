"""
Douyin platform implementation — 100% CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser (stealth
Chromium) with automatic Playwright fallback.
"""

import asyncio
import logging
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._browser import create_browser_sync
from .._utils import parse_schedule_time, save_login_result, scrape_user_profile
from ..base_platform import BasePlatform

logger = logging.getLogger(__name__)

DOUYIN_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
DOUYIN_PUBLISH_STRATEGY_SCHEDULED = "scheduled"


class DouyinPlatform(BasePlatform):
    platform_id = 3
    platform_key = "douyin"
    platform_name = "抖音"

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform Douyin login via QR code scan.

        Opens ``https://creator.douyin.com/``, extracts the QR image from
        ``get_by_role("img", name="二维码")``, sends the image URL to
        *status_queue*, then waits for the page to navigate away (indicating
        the user scanned the code).  On success, scrapes the user profile and
        saves the login result.
        """
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if page.url != original_url:
                url_changed_event.set()

        browser = await self.create_browser(login_mode=True)
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto("https://creator.douyin.com/")
                original_url = page.url

                # Extract QR code image
                img_locator = page.get_by_role("img", name="二维码")
                src = await img_locator.get_attribute("src")
                logger.info("QR image src: %s", src)
                status_queue.put(src)

                # Monitor URL change via framenavigated
                page.on(
                    "framenavigated",
                    lambda frame: asyncio.create_task(_on_url_change())
                    if frame == page.main_frame
                    else None,
                )

                try:
                    await asyncio.wait_for(url_changed_event.wait(), timeout=200)
                    logger.info("Page navigation detected — login successful")
                except asyncio.TimeoutError:
                    logger.warning("Login monitoring timed out (200 s)")
                    status_queue.put("500")
                    return

                # Scrape profile & save via shared utility
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_user_profile,
                )
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        Opens ``https://creator.douyin.com/creator-micro/content/upload`` with
        the stored cookies.  If the page shows "扫码登录" within 5 seconds the
        cookie is considered invalid.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )
                try:
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/upload",
                        timeout=5000,
                    )
                except Exception:
                    logger.info("cookie check: page did not reach target URL")
                    return False

                # If "扫码登录" is visible the cookie has expired
                try:
                    await page.get_by_text("扫码登录").wait_for(timeout=5000)
                    logger.info("cookie check: 扫码登录 visible — cookie invalid")
                    return False
                except Exception:
                    logger.info("cookie check: no login prompt — cookie valid")
                    return True
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — refresh user name / avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Douyin creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                try:
                    await page.goto(
                        "https://creator.douyin.com/",
                        wait_until="networkidle",
                        timeout=30000,
                    )
                except Exception:
                    # networkidle can timeout; page content may still be usable
                    pass
                name, avatar = await scrape_user_profile(page)
                return name, avatar
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window (sync CloakBrowser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Douyin creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://creator.douyin.com/"

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
    # publish_video — full Douyin upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Douyin via CloakBrowser.

        Accepted keyword arguments:

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
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", [])
        enableTimer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        product_link = kwargs.get("productLink", "")
        product_title = kwargs.get("productTitle", "")
        desc = kwargs.get("desc", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        ai_content = kwargs.get("ai_content", "")

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(Path(BASE_DIR / "videoFile" / f)) for f in files]
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(
                Path(BASE_DIR / "videoFile" / thumbnail_landscape_path)
            )
        if thumbnail_portrait_path:
            thumbnail_portrait_path = str(
                Path(BASE_DIR / "videoFile" / thumbnail_portrait_path)
            )

        # Determine publish strategy and schedule times
        publish_strategy = (
            DOUYIN_PUBLISH_STRATEGY_SCHEDULED
            if enableTimer and schedule_time_str
            else DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
        )
        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(file_paths),
            enableTimer,
            videos_per_day,
            daily_times,
            start_days,
        )

        for file_index, file_path in enumerate(file_paths):
            for cookie_path in account_paths:
                await self._upload_one_video(
                    title=title,
                    file_path=file_path,
                    tags=tags,
                    publish_date=publish_datetimes[file_index],
                    account_file=cookie_path,
                    publish_strategy=publish_strategy,
                    thumbnail_landscape_path=thumbnail_landscape_path or None,
                    thumbnail_portrait_path=thumbnail_portrait_path or None,
                    product_link=product_link,
                    product_title=product_title,
                    desc=desc,
                    ai_content=ai_content,
                )
        return True

    # ------------------------------------------------------------------
    # Internal helpers (ported from DouYinVideo / DouYinBaseUploader)
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        publish_strategy: str,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        product_link="",
        product_title="",
        desc="",
        ai_content="",
    ):
        """Upload a single video to one Douyin account."""
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser, storage_state=account_file
            )
            try:
                await context.grant_permissions(["geolocation"])
                page = await context.new_page()
                await page.goto(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )

                # Upload video file
                logger.info("Uploading video file: %s", file_path)
                await page.locator(
                    "div[class^='container'] input"
                ).set_input_files(file_path)

                # Wait for redirect to publish page (version 1 or version 2)
                while True:
                    try:
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page",
                            timeout=3000,
                        )
                        break
                    except Exception:
                        try:
                            await page.wait_for_url(
                                "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                                timeout=3000,
                            )
                            break
                        except Exception:
                            await asyncio.sleep(0.5)

                await asyncio.sleep(1)

                # Fill title, description, tags
                await self._fill_title_and_description(
                    page, title, desc or title, tags
                )

                # Wait for upload to complete
                while True:
                    try:
                        number = await page.locator(
                            '[class^="long-card"] div:has-text("重新上传")'
                        ).count()
                        if number > 0:
                            break
                        await asyncio.sleep(2)
                        if await page.locator(
                            'div.progress-div > div:has-text("上传失败")'
                        ).count():
                            logger.warning("Upload failed, retrying")
                            await page.locator(
                                "div.progress-div [class^='upload-btn-input']"
                            ).set_input_files(file_path)
                    except Exception:
                        await asyncio.sleep(2)

                # Set product link
                if product_link and product_title:
                    await self._set_product_link(page, product_link, product_title)

                # Set thumbnail / cover
                await self._set_thumbnail(
                    page, thumbnail_landscape_path, thumbnail_portrait_path
                )

                # Toggle third-party content switch
                third_part_element = (
                    '[class^="info"] > [class^="first-part"] div div.semi-switch'
                )
                if await page.locator(third_part_element).count():
                    if "semi-switch-checked" not in await page.eval_on_selector(
                        third_part_element, "div => div.className"
                    ):
                        await page.locator(
                            third_part_element
                        ).locator("input.semi-switch-native-control").click()

                # Schedule if needed
                if (
                    publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED
                    and publish_date != 0
                ):
                    await self._set_schedule_time(page, publish_date)

                # Set AI content declaration
                if ai_content:
                    await self._set_declaration(page, ai_content)

                # Click publish and wait for redirect
                while True:
                    try:
                        publish_button = page.get_by_role(
                            "button", name="发布", exact=True
                        )
                        if await publish_button.count():
                            await publish_button.click()
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/manage**",
                            timeout=3000,
                        )
                        logger.info("Video published successfully")
                        break
                    except Exception:
                        # Maybe a cover selection is required
                        await self._handle_auto_video_cover(page)
                        await asyncio.sleep(0.5)

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("Cookie state updated after publish")
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper: fill title, description, tags
    # ------------------------------------------------------------------

    @staticmethod
    async def _fill_title_and_description(
        page, title: str, description: str, tags: list | None = None
    ):
        description_section = (
            page.get_by_text("作品描述", exact=True)
            .locator("xpath=ancestor::div[2]")
            .locator("xpath=following-sibling::div[1]")
        )

        title_input = description_section.locator('input[type="text"]').first
        await title_input.wait_for(state="visible", timeout=10000)
        await title_input.fill(title[:30])

        description_editor = description_section.locator(
            '.zone-container[contenteditable="true"]'
        ).first
        await description_editor.wait_for(state="visible", timeout=10000)
        await description_editor.click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")
        await page.keyboard.type(description)

        for tag in tags or []:
            await page.keyboard.type(" #" + tag)
            await page.keyboard.press("Space")

    # ------------------------------------------------------------------
    # Helper: set schedule time
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        await label_element.click()
        await asyncio.sleep(1)

        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")
        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="日期和时间"]').click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Helper: set product link (购物车)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_product_link(page, product_link: str, product_title: str):
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_selector("text=添加标签", timeout=10000)
            dropdown = (
                page.get_by_text("添加标签")
                .locator("..")
                .locator("..")
                .locator("..")
                .locator(".semi-select")
                .first
            )
            if not await dropdown.count():
                logger.warning("Product link: tag dropdown not found")
                return False

            await dropdown.click()
            await page.wait_for_selector('[role="listbox"]', timeout=5000)
            await page.locator('[role="option"]:has-text("购物车")').click()

            await page.wait_for_selector(
                'input[placeholder="粘贴商品链接"]', timeout=5000
            )
            input_field = page.locator('input[placeholder="粘贴商品链接"]')
            await input_field.fill(product_link)

            add_button = page.locator('span:has-text("添加链接")')
            button_class = await add_button.get_attribute("class")
            if "disable" in button_class:
                logger.warning("Product link: add-link button disabled")
                return False
            await add_button.click()

            await page.wait_for_timeout(2000)
            error_modal = page.locator("text=未搜索到对应商品")
            if await error_modal.count():
                confirm_button = page.locator('button:has-text("确定")')
                await confirm_button.click()
                logger.warning("Product link: invalid product link")
                return False

            # Fill product short title
            await page.wait_for_timeout(2000)
            await page.wait_for_selector(
                'input[placeholder="请输入商品短标题"]', timeout=10000
            )
            short_title_input = page.locator(
                'input[placeholder="请输入商品短标题"]'
            )
            if not await short_title_input.count():
                logger.warning("Product link: short-title input not found")
                return False

            await short_title_input.fill(product_title[:10])
            await page.wait_for_timeout(1000)

            finish_button = page.locator('button:has-text("完成编辑")')
            if "disabled" not in await finish_button.get_attribute("class"):
                await finish_button.click()
                await page.wait_for_selector(
                    ".semi-modal-content", state="hidden", timeout=5000
                )
                return True

            # Button is disabled — close dialog
            cancel_button = page.locator('button:has-text("取消")')
            if await cancel_button.count():
                await cancel_button.click()
            else:
                close_button = page.locator(".semi-modal-close")
                await close_button.click()
            await page.wait_for_selector(
                ".semi-modal-content", state="hidden", timeout=5000
            )
            return False
        except Exception as e:
            logger.warning("Product link error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Helper: set thumbnail (cover images)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_thumbnail(
        page, thumbnail_landscape_path=None, thumbnail_portrait_path=None
    ):
        if not thumbnail_landscape_path and not thumbnail_portrait_path:
            return

        logger.info("Setting video cover")
        await page.click('text="选择封面"')
        cover_locator_str = 'div[id*="creator-content-modal"]'
        cover_locator = page.locator(cover_locator_str)
        await page.wait_for_selector(cover_locator_str)

        upload_input = cover_locator.locator(
            "div[class^='semi-upload upload'] >> input.semi-upload-hidden-input"
        )

        if thumbnail_landscape_path:
            await page.wait_for_timeout(1000)
            await upload_input.set_input_files(thumbnail_landscape_path)
            await page.wait_for_timeout(2000)
            logger.info("Landscape cover uploaded")

        if thumbnail_portrait_path:
            await cover_locator.locator("div[class*='steps'] div").nth(1).click()
            await page.wait_for_timeout(1000)
            await upload_input.set_input_files(thumbnail_portrait_path)
            await page.wait_for_timeout(2000)
            logger.info("Portrait cover uploaded")

        await cover_locator.locator('button:visible:has-text("完成")').click()
        logger.info("Cover selection completed")
        await page.wait_for_selector("div.extractFooter", state="detached")

    # ------------------------------------------------------------------
    # Helper: handle auto video cover prompt
    # ------------------------------------------------------------------

    @staticmethod
    async def _handle_auto_video_cover(page):
        try:
            if await page.get_by_text("请设置封面后再发布").first.is_visible():
                recommend_cover = page.locator(
                    '[class^="recommendCover-"]'
                ).first
                if await recommend_cover.count():
                    try:
                        await recommend_cover.click()
                        await asyncio.sleep(1)
                        confirm_text = "是否确认应用此封面？"
                        if await page.get_by_text(
                            confirm_text
                        ).first.is_visible():
                            await page.get_by_role(
                                "button", name="确定"
                            ).click()
                            await asyncio.sleep(1)
                        return True
                    except Exception as e:
                        logger.warning("Auto cover selection failed: %s", e)
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Helper: set AI content declaration
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_declaration(page, ai_content: str):
        logger.info("Setting declaration: %s", ai_content)
        try:
            select_box = page.locator(".selectBox-buZRzi").first
            await select_box.wait_for(state="visible", timeout=10000)
            await select_box.click()
            await asyncio.sleep(2)

            clicked = await page.evaluate(
                """(targetText) => {
                const addons = document.querySelectorAll('.semi-radio-addon');
                for (const addon of addons) {
                    if (addon.textContent.trim() === targetText) {
                        addon.closest('label').click();
                        return addon.textContent.trim();
                    }
                }
                return null;
            }""",
                ai_content,
            )

            if clicked:
                logger.info("Declaration selected: %s", clicked)
                await asyncio.sleep(1)

                await page.evaluate(
                    """() => {
                    const btns = document.querySelectorAll('.btnWrapper-LtGF4z button');
                    for (const btn of btns) {
                        if (btn.textContent.trim() === '确定') {
                            btn.disabled = false;
                            btn.className = btn.className.replace('semi-button-disabled', '');
                            btn.click();
                        }
                    }
                }"""
                )
                logger.info("Declaration confirmed")
            else:
                logger.warning("Declaration option not found: %s", ai_content)
                close_btn = page.locator(".semi-modal-close")
                if await close_btn.count() > 0:
                    await close_btn.first.click()

            await asyncio.sleep(1)
        except Exception as exc:
            logger.warning(
                "Declaration setup failed (non-blocking): %s", exc
            )
