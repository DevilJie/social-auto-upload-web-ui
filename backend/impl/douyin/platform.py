"""
Douyin platform implementation — 100% CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser (stealth
Chromium) with automatic Playwright fallback.
"""

import asyncio
import threading
from pathlib import Path
from queue import Queue

from util._logger import get_channel_logger

from conf import BASE_DIR

from .._browser import create_browser_sync
from .._utils import parse_schedule_time, save_login_result, scrape_user_profile
from ..base_platform import BasePlatform

logger = get_channel_logger("douyin")

DOUYIN_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
DOUYIN_PUBLISH_STRATEGY_SCHEDULED = "scheduled"


class DouyinPlatform(BasePlatform):
    platform_id = 3
    platform_key = "douyin"
    platform_name = "抖音"

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
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
                    account_id=account_id,
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
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
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
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            # thumbnail_landscape_path 已是绝对路径
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            # thumbnail_portrait_path 已是绝对路径
            thumbnail_portrait_path = str(thumbnail_portrait_path)

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

        # Douyin is a portrait-first platform: the default (first visible)
        # tab in the cover dialog is for 竖版 (9:16 portrait) covers.
        # The tab at index 1 (nth 1) is for 横版 (16:9 landscape) covers.
        if thumbnail_portrait_path:
            await page.wait_for_timeout(1000)
            await upload_input.set_input_files(thumbnail_portrait_path)
            await page.wait_for_timeout(2000)
            logger.info("Portrait cover uploaded (default tab)")

        if thumbnail_landscape_path:
            await cover_locator.locator("div[class*='steps'] div").nth(1).click()
            await page.wait_for_timeout(1000)
            await upload_input.set_input_files(thumbnail_landscape_path)
            await page.wait_for_timeout(2000)
            logger.info("Landscape cover uploaded (tab 1)")

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
    # publish_image — Douyin image note upload pipeline
    # ------------------------------------------------------------------

    async def publish_image(self, **kwargs) -> bool:
        """Publish an image note to Douyin via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- note title (max 20 chars)
        - ``files`` (*list[str]*) -- image absolute file paths (resolved by image_publish_bp)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``desc`` (*str*, optional) -- description (max 1000 chars)
        - ``cover_path`` (*str*, optional) -- cover image file name
        - ``mix_id`` (*str*, optional) -- mix/collection ID
        - ``music_name`` (*str*, optional) -- music name to search and select
        - ``hotspot`` (*str*, optional) -- hotspot keyword to search and select
        - ``tag_type`` (*str*, optional) -- tag type: 'location' | 'miniapp' | 'gamepad' | 'mark'
        - ``tag_value`` (*str*, optional) -- tag value (keyword or link)
        - ``mini_link`` (*str*, optional) -- mini app link (for miniapp type)
        - ``enableTimer`` (*bool*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``ai_content`` (*str*, optional) -- AI content declaration
        - ``activities`` (*list[str]*, optional) -- official activities (appended as #tags)
        - ``dry_run`` (*bool*, optional) -- if True, skip publish button click (default True)
        """
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", [])
        desc = kwargs.get("desc", "")
        cover_path = kwargs.get("cover_path", "")
        mix_id = kwargs.get("mix_id", "")
        music_name = kwargs.get("music_name", "")
        hotspot = kwargs.get("hotspot", "")
        tag_type = kwargs.get("tag_type", "")
        tag_value = kwargs.get("tag_value", "")
        mini_link = kwargs.get("mini_link", "")
        enable_timer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        ai_content = kwargs.get("ai_content", "")
        activities = kwargs.get("activities", []) or []
        dry_run = kwargs.get("dry_run", True)  # Default to dry run for safety

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        # files 已是绝对路径（image_publish_bp 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]

        # cover_path 已是绝对路径，无需拼接
        if cover_path and not Path(cover_path).is_file():
            logger.warning("Cover file not found: %s", cover_path)
            cover_path = ""

        # Append activities as hashtags to description
        if activities:
            activity_tags = " ".join([f"#{act}" for act in activities])
            desc = f"{desc} {activity_tags}".strip()

        for cookie_path in account_paths:
            await self._upload_image_note(
                title=title,
                file_paths=file_paths,
                tags=tags,
                account_file=cookie_path,
                desc=desc,
                cover_path=cover_path,
                mix_id=mix_id,
                music_name=music_name,
                hotspot=hotspot,
                tag_type=tag_type,
                tag_value=tag_value,
                mini_link=mini_link,
                enable_timer=enable_timer,
                schedule_time_str=schedule_time_str,
                ai_content=ai_content,
                dry_run=dry_run,
            )
        return True

    async def _upload_image_note(
        self,
        title: str,
        file_paths: list,
        tags: list,
        account_file: str,
        desc: str = "",
        cover_path: str = "",
        mix_id: str = "",
        music_name: str = "",
        hotspot: str = "",
        tag_type: str = "",
        tag_value: str = "",
        mini_link: str = "",
        enable_timer: bool = False,
        schedule_time_str: str = "",
        ai_content: str = "",
        dry_run: bool = True,
    ):
        """Upload image note to one Douyin account."""
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                await context.grant_permissions(["geolocation"])
                page = await context.new_page()

                # Navigate to image upload page
                # 抖音创作者中心是 SPA，永远不会触发 load 事件。
                # 用 domcontentloaded + URL 匹配即可，避免 30s 等待
                logger.info("Navigating to Douyin image upload page")
                await page.goto(
                    "https://creator.douyin.com/creator-micro/content/upload?default-tab=3",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/upload?default-tab=3",
                    timeout=60000,
                )
                await asyncio.sleep(2)

                # Upload images via hidden input
                logger.info("Uploading %d images", len(file_paths))
                file_input = page.locator("div[class^='container'] input[type='file']")
                await file_input.set_input_files(file_paths)

                # Wait for redirect to image publish page
                logger.info("Waiting for redirect to publish page...")
                max_wait = 120  # seconds - longer timeout for many images
                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    current_url = page.url
                    if "content/upload" not in current_url:
                        logger.info("Redirected to: %s", current_url)
                        break
                    await asyncio.sleep(1)
                else:
                    logger.warning("Timeout waiting for redirect")

                # Wait for all images to upload successfully
                # Calculate timeout based on image count: 30s per image, min 120s, max 600s
                upload_timeout_per_image = 30
                max_upload_wait = max(120, min(len(file_paths) * upload_timeout_per_image, 600))
                logger.info("Waiting for all %d images to upload (timeout: %ds)...", len(file_paths), max_upload_wait)
                uploaded_count = 0
                upload_start = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - upload_start) < max_upload_wait:
                    # Check for uploaded image count in the UI
                    image_items = page.locator('div[class*="img-"][draggable="true"]')
                    uploaded_count = await image_items.count()
                    logger.info("Uploaded images: %d/%d", uploaded_count, len(file_paths))
                    if uploaded_count >= len(file_paths):
                        logger.info("All %d images uploaded successfully!", len(file_paths))
                        break
                    await asyncio.sleep(3)
                else:
                    logger.warning("Timeout waiting for image upload. Uploaded: %d/%d", uploaded_count, len(file_paths))

                await asyncio.sleep(5)  # 等待更长时间确保页面加载完成

                # Fill title
                logger.info("Filling title: %s", title[:20])
                title_input = page.locator(
                    'div[class^="container-sGoJ9f"] input[type="text"]'
                ).first
                await title_input.wait_for(state="visible", timeout=10000)
                await title_input.fill(title[:20])

                # Fill description with tags
                logger.info("Filling description with tags")
                desc_editor = page.locator(
                    'div[data-zone-container="*"][contenteditable="true"]'
                ).first
                await desc_editor.wait_for(state="visible", timeout=10000)
                await desc_editor.click()
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")

                # 构建完整的描述文本（包含标签），每个标签后加空格触发抖音识别
                full_desc = desc[:1000]
                for tag in tags:
                    if ' ' in tag or any(c in tag for c in '！？，。、；：""''（）【】《》'):
                        full_desc += f" #[{tag}] "
                    else:
                        full_desc += f" #{tag} "

                # 使用 JavaScript 直接设置内容，避免键盘输入触发标签激活
                await page.evaluate("""(text) => {
                    const editor = document.querySelector('div[data-zone-container="*"][contenteditable="true"]');
                    if (editor) {
                        editor.focus();
                        // 清空现有内容
                        editor.innerHTML = '';
                        // 使用 insertText 命令设置新内容
                        document.execCommand('insertText', false, text);
                    }
                }""", full_desc)
                await asyncio.sleep(0.3)
                # 触发一次键盘输入事件，让抖音前端识别 #标签
                await page.keyboard.press('Space')
                await page.keyboard.press('Backspace')
                await asyncio.sleep(0.3)

                # Set cover if provided
                if cover_path:
                    logger.info("Setting cover image")
                    await self._set_image_cover(page, cover_path)

                # Set mix/collection if provided
                if mix_id:
                    logger.info("Setting mix/collection: %s", mix_id)
                    await self._set_image_mix(page, mix_id)

                # Set music if provided
                if music_name:
                    logger.info("Selecting music: %s", music_name)
                    await self._select_music(page, music_name)

                # Set hotspot if provided
                if hotspot:
                    logger.info("Setting hotspot: %s", hotspot)
                    await self._set_hotspot(page, hotspot)

                # Set tag (位置/小程序/游戏手柄/标记万物) if provided
                if tag_type and tag_value:
                    logger.info("Setting tag: type=%s, value=%s, mini_link=%s", tag_type, tag_value, mini_link)
                    await self._set_tag(page, tag_type, tag_value, mini_link)

                # Set AI content declaration
                if ai_content:
                    await self._set_declaration(page, ai_content)

                # Set schedule time if needed
                if enable_timer and schedule_time_str:
                    publish_date = parse_schedule_time(
                        schedule_time_str, 1, enable_timer, 1, None, 0
                    )[0]
                    if publish_date != 0:
                        await self._set_schedule_time(page, publish_date)

                logger.info("Form filling completed. dry_run=%s", dry_run)

                if not dry_run:
                    # Click publish button
                    # 使用稳定的文本匹配：精确匹配"发布"按钮，排除"暂存离开"
                    publish_btn = page.get_by_role("button", name="发布", exact=True)
                    await publish_btn.wait_for(state="visible", timeout=10000)
                    await publish_btn.click()
                    logger.info("Publish button clicked, waiting for page redirect...")

                    # 等待页面跳转 - 跳转到 manage 页面才是发布成功
                    try:
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/manage*",
                            timeout=60000
                        )
                        logger.info("Published successfully - redirected to manage page")
                        result = True
                    except Exception:
                        # 检查当前URL
                        current_url = page.url
                        if "content/manage" in current_url:
                            logger.info("Published successfully - already on manage page")
                            result = True
                        else:
                            logger.warning("Publish may have failed - current URL: %s", current_url)
                            result = False

                    # Save cookie state
                    await context.storage_state(path=account_file)
                    logger.info("Cookie state updated")
                else:
                    # Dry run mode - simulate publish
                    logger.info("========================================")
                    logger.info("点击发布！发布成功！")
                    logger.info("========================================")
                    result = True

            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper: set image cover
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_cover(page, cover_path: str):
        """Set cover image for image note."""
        try:
            # Click edit cover button - use text content for stability
            edit_cover_btn = page.get_by_text("编辑封面", exact=True)
            await edit_cover_btn.click()
            await asyncio.sleep(2)

            # Click upload cover tab
            upload_tab = page.get_by_role("tab", name="上传封面")
            await upload_tab.click()
            await asyncio.sleep(1)

            # Find hidden input=file in the upload area
            # Look for input[type="file"] that accepts images
            cover_input = page.locator('input[type="file"][accept*="image"]').first
            if not await cover_input.count():
                # Fallback: find any hidden file input
                cover_input = page.locator('input[type="file"]').first

            await cover_input.set_input_files(cover_path)
            await asyncio.sleep(3)

            # Click confirm in crop dialog - find button with text "确定"
            # Wait for crop dialog to appear
            await page.wait_for_selector('button:has-text("确定")', timeout=5000)
            # Click the confirm button (not the cancel button)
            confirm_buttons = page.locator('button:has-text("确定")')
            count = await confirm_buttons.count()
            logger.info("Found %d confirm buttons", count)
            # Click the last one (should be the crop confirm)
            await confirm_buttons.last.click()
            await asyncio.sleep(2)

            # Click final confirm in cover editor
            final_confirm = page.locator('button:has-text("确定")').last
            await final_confirm.click()
            await asyncio.sleep(2)

            logger.info("Cover image set successfully")
        except Exception as e:
            logger.warning("Failed to set cover: %s", e)

    # ------------------------------------------------------------------
    # Helper: set mix/collection
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_mix(page, mix_id: str):
        """Set mix/collection for image note."""
        try:
            # Click mix dropdown
            mix_dropdown = page.locator(
                'div.semi-select:has-text("不选择合集")'
            ).first
            await mix_dropdown.click()
            await asyncio.sleep(2)

            # Select mix by ID or text
            mix_option = page.locator(
                f'div.semi-select-option:has-text("{mix_id}")'
            ).first
            if await mix_option.count():
                await mix_option.click()
                logger.info("Mix selected: %s", mix_id)
            else:
                logger.warning("Mix not found: %s", mix_id)
                # Close dropdown
                await page.keyboard.press("Escape")

            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("Failed to set mix: %s", e)

    # ------------------------------------------------------------------
    # Helper: select music
    # ------------------------------------------------------------------

    @staticmethod
    async def _select_music(page, music_name: str):
        """Search and select music."""
        try:
            # Click select music button - find the one in the music section
            # Use XPath to find the specific "选择音乐" button
            music_btn = page.locator('xpath=//div[contains(@class, "container-right")]//span[text()="选择音乐"]')
            if not await music_btn.count():
                # Fallback: find by text and click the visible one
                music_btn = page.get_by_text("选择音乐", exact=True).last
            await music_btn.click()
            await asyncio.sleep(3)

            # Search music - use placeholder for stability
            search_input = page.locator('input[placeholder="搜索音乐"]')
            await search_input.wait_for(state="visible", timeout=5000)
            await search_input.fill(music_name)
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)

            # Find matching music card
            music_cards = page.locator('div.card-container-tmocjc')
            count = await music_cards.count()
            logger.info("Found %d music cards", count)

            # Find the card that matches the search text
            target_card = None
            for i in range(count):
                card = music_cards.nth(i)
                card_text = await card.text_content()
                if music_name in card_text:
                    target_card = card
                    logger.info("Found matching music: %s", card_text[:50])
                    break

            if not target_card and count > 0:
                # Fallback: use first card
                target_card = music_cards.first
                logger.info("Using first music card as fallback")

            if target_card:
                # Hover to show "使用" button
                await target_card.hover()
                await asyncio.sleep(1)

                # Click use button within this card
                use_btn = target_card.locator('button:has-text("使用")')
                if await use_btn.count():
                    await use_btn.click(force=True)
                    logger.info("Music selected: %s", music_name)
                else:
                    logger.warning("Use button not found for music: %s", music_name)
            else:
                logger.warning("Music card not found for: %s", music_name)

            await asyncio.sleep(2)
        except Exception as e:
            logger.warning("Failed to select music: %s", e)

    # ------------------------------------------------------------------
    # Helper: set hotspot
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_hotspot(page, hotspot: str):
        """Search and select hotspot."""
        try:
            # Click hotspot - use text for stability (it's a span, not input)
            hotspot_text = page.get_by_text("点击输入热点词", exact=True)
            await hotspot_text.click()
            await asyncio.sleep(1)

            # Type hotspot keyword
            await page.keyboard.type(hotspot)
            await asyncio.sleep(3)

            # Find matching hotspot option in dropdown
            hotspot_options = page.locator('div[role="option"]:not([aria-disabled="true"])')
            count = await hotspot_options.count()
            logger.info("Found %d hotspot options", count)

            # Click the option that matches the search text
            clicked = False
            for i in range(count):
                option = hotspot_options.nth(i)
                option_text = await option.text_content()
                if hotspot in option_text:
                    await option.click()
                    logger.info("Hotspot selected: %s (matched: %s)", hotspot, option_text[:50])
                    clicked = True
                    break

            if not clicked:
                # Fallback: click first option if no exact match
                if count > 0:
                    await hotspot_options.first.click()
                    logger.info("Hotspot selected: %s (first option)", hotspot)
                else:
                    logger.warning("Hotspot not found: %s", hotspot)
                    await page.keyboard.press("Escape")

            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("Failed to set hotspot: %s", e)

    # ------------------------------------------------------------------
    # Helper: set tag (位置/小程序/游戏手柄/标记万物)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_tag(page, tag_type: str, tag_value: str, mini_link: str = ""):
        """Set tag with type and value.

        tag_type: 'location' | 'miniapp' | 'gamepad' | 'mark'
        tag_value: the search keyword or link
        mini_link: mini app link (for miniapp type)
        """
        try:
            # Tag type mapping
            type_map = {
                'location': '位置',
                'miniapp': '小程序',
                'gamepad': '游戏手柄',
                'mark': '标记万物',
            }
            type_text = type_map.get(tag_type, '位置')

            # Click tag type dropdown
            tag_dropdown = page.locator(
                'div.select-GDaqAd'
            ).first
            await tag_dropdown.click()
            await asyncio.sleep(1)

            # Select tag type
            type_option = page.get_by_role("option", name=type_text)
            await type_option.click()
            await asyncio.sleep(1)

            # Helper function to find and click matching option
            async def find_and_click_option(page, tag_value, option_selector='div[role="option"]'):
                options = page.locator(option_selector)
                count = await options.count()
                logger.info("Found %d options", count)

                # Try to find exact match
                for i in range(count):
                    option = options.nth(i)
                    option_text = await option.text_content()
                    if tag_value in option_text:
                        await option.click()
                        logger.info("Tag set: %s (matched: %s)", tag_value, option_text[:50])
                        return True

                # Fallback: click first option
                if count > 0:
                    await options.first.click()
                    logger.info("Tag set: %s (first option)", tag_value)
                    return True
                return False

            # Based on tag type, handle differently
            if tag_type == 'location':
                # Location: click to activate, then input search keyword
                location_select = page.get_by_text("输入相关位置，让更多人看到你的作品", exact=True)
                await location_select.click()
                await asyncio.sleep(1)

                # Use keyboard to type directly since input is already focused
                await page.keyboard.type(tag_value, delay=50)
                logger.info("Typed location keyword: %s", tag_value)
                await asyncio.sleep(5)  # 位置查询可能有延迟，等待更长时间

                # Select matching result
                await find_and_click_option(page, tag_value)

            elif tag_type == 'miniapp':
                # Mini app: click to activate, then paste link
                miniapp_select = page.get_by_text("粘贴抖音小程序链接", exact=True)
                await miniapp_select.click()
                await asyncio.sleep(1)

                # Use mini_link if provided, otherwise use tag_value
                link_to_use = mini_link if mini_link else tag_value
                await page.keyboard.type(link_to_use, delay=50)
                logger.info("Typed miniapp link: %s", link_to_use)
                await asyncio.sleep(2)

                # Select matching result
                await find_and_click_option(page, tag_value, 'div[role="option"]:not([aria-disabled="true"])')

            elif tag_type == 'gamepad':
                # Game: click the semi-select component by placeholder text
                game_select = page.get_by_text("添加作品同款游戏", exact=True)
                await game_select.click()
                await asyncio.sleep(1)

                # Use keyboard to type directly since input is already focused
                await page.keyboard.type(tag_value, delay=50)
                logger.info("Typed game tag value: %s", tag_value)
                await asyncio.sleep(3)

                # Find matching game option in dropdown
                game_options = page.locator('div.semi-popover [class*="anchor-game-option"]')
                count = await game_options.count()
                logger.info("Found %d game options", count)

                # Click the option that matches the search text
                clicked = False
                for i in range(count):
                    option = game_options.nth(i)
                    option_text = await option.text_content()
                    if tag_value in option_text:
                        await option.click()
                        logger.info("Game tag set: %s (matched: %s)", tag_value, option_text[:50])
                        clicked = True
                        break

                if not clicked:
                    # Fallback: click first option if no exact match
                    if count > 0:
                        await game_options.first.click()
                        logger.info("Game tag set: %s (first option)", tag_value)
                    else:
                        logger.warning("Game option not found for: %s", tag_value)

            elif tag_type == 'mark':
                # Mark: input search keyword
                mark_input = page.get_by_placeholder("请输入或选择标记的物品")
                await mark_input.click()
                await page.keyboard.type(tag_value)
                await asyncio.sleep(2)

                # Find matching mark option in dropdown
                mark_options = page.locator('div.semi-popover [class*="option-"]')
                count = await mark_options.count()
                logger.info("Found %d mark options", count)

                # Click the option that matches the search text
                clicked = False
                for i in range(count):
                    option = mark_options.nth(i)
                    option_text = await option.text_content()
                    if tag_value in option_text:
                        await option.click()
                        logger.info("Mark tag set: %s (matched: %s)", tag_value, option_text[:50])
                        clicked = True
                        break

                if not clicked:
                    # Fallback: click first option if no exact match
                    if count > 0:
                        await mark_options.first.click()
                        logger.info("Mark tag set: %s (first option)", tag_value)
                    else:
                        logger.warning("Mark option not found for: %s", tag_value)

            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("Failed to set tag: %s", e)

    @staticmethod
    async def _set_location_tag(page, location: str):
        """Search and select location tag."""
        try:
            # Click location input
            location_input = page.get_by_placeholder("输入相关位置，让更多人看到你的作品")
            await location_input.click()
            await asyncio.sleep(1)

            # Type location keyword
            await page.keyboard.type(location)
            await asyncio.sleep(2)

            # Select first result
            location_option = page.locator(
                'div[role="option"]'
            ).first
            if await location_option.count():
                await location_option.click()
                logger.info("Location selected: %s", location)
            else:
                logger.warning("Location not found: %s", location)
                await page.keyboard.press("Escape")

            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("Failed to set location: %s", e)

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
