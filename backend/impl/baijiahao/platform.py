"""
Baijiahao (百家号) platform implementation -- 100% CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser (stealth
Chromium) with automatic Playwright fallback.
"""

import asyncio
import logging
import os
import random
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._browser import create_browser_sync
from .._utils import (
    parse_schedule_time,
    save_login_result,
    scrape_baijiahao_profile,
)
from ..base_platform import BasePlatform

logger = logging.getLogger(__name__)


class BaijiahaoPlatform(BasePlatform):
    platform_id = 6
    platform_key = "baijiahao"
    platform_name = "百家号"

    # ------------------------------------------------------------------
    # login -- QR code / redirect via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform Baijiahao login.

        Opens ``https://baijiahao.baidu.com/builder/theme/bjh/login`` and
        waits for the page to redirect to ``**/builder/rc/home**`` (up to
        120 s).  On success, scrapes the user profile and saves the login
        result via the shared utility.
        """
        browser = await self.create_browser(login_mode=True)
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(
                    "https://baijiahao.baidu.com/builder/theme/bjh/login",
                    timeout=45000,
                )
                logger.info("百家号登录页面已打开，请完成扫码登录...")

                # Wait for redirect after successful login
                try:
                    await page.wait_for_url(
                        "**/builder/rc/home**", timeout=120000
                    )
                    logger.info("检测到登录成功，正在保存 cookie...")
                except Exception:
                    logger.warning("未检测到登录完成，将在 120 秒后保存当前状态")
                    await asyncio.sleep(120)

                # Scrape profile & save via shared utility
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_baijiahao_profile,
                )
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # check_cookie -- verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        Opens ``https://baijiahao.baidu.com/builder/rc/home`` with the
        stored cookies.  If "注册/登录百家号" text appears within 5 seconds
        the cookie is considered invalid.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(
                browser, storage_state=cookie_path
            )
            try:
                page = await context.new_page()
                await page.goto(
                    "https://baijiahao.baidu.com/builder/rc/home"
                )
                await page.wait_for_timeout(5000)

                if await page.get_by_text("注册/登录百家号").count():
                    logger.error("等待5秒 cookie 失效")
                    return False
                else:
                    logger.info("[+] cookie 有效")
                    return True
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile -- refresh user name / avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Baijiahao account settings page.

        Uses ``scrape_baijiahao_profile`` from ``_utils`` to scrape the
        rendered account settings page.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(
                browser, storage_state=cookie_path
            )
            try:
                page = await context.new_page()
                await page.goto(
                    "https://baijiahao.baidu.com/builder/rc/home"
                )
                name, avatar = await scrape_baijiahao_profile(page)
                return name, avatar
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center -- visible browser window (sync CloakBrowser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Baijiahao creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://baijiahao.baidu.com/"

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
    # publish_video -- full Baijiahao upload pipeline (sync entry point)
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Baijiahao (sync wrapper).

        Accepted keyword arguments:

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
        asyncio.run(self._upload_all(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Internal: orchestrate all file x account uploads
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """Create a browser for each file+account combo and upload."""
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", [])
        enableTimer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path")
        desc = kwargs.get("desc", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        creation_declaration = kwargs.get("creation_declaration", "")
        supplementary_declaration = kwargs.get("supplementary_declaration", "")
        ai_content = kwargs.get("ai_content", False)

        # Resolve full paths
        account_paths = [
            str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file
        ]
        file_paths = [
            str(Path(BASE_DIR / "videoFile" / f)) for f in files
        ]
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(
                Path(BASE_DIR / "videoFile" / thumbnail_landscape_path)
            )
        if thumbnail_portrait_path:
            thumbnail_portrait_path = str(
                Path(BASE_DIR / "videoFile" / thumbnail_portrait_path)
            )

        # Determine schedule times
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
                    thumbnail_landscape_path=thumbnail_landscape_path,
                    thumbnail_portrait_path=thumbnail_portrait_path,
                    desc=desc,
                    creation_declaration=creation_declaration,
                    supplementary_declaration=supplementary_declaration,
                    ai_content=ai_content,
                )

    # ------------------------------------------------------------------
    # Internal: upload one video to one account
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        desc="",
        creation_declaration="",
        supplementary_declaration="",
        ai_content=False,
    ):
        """Upload a single video to one Baijiahao account."""
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser,
                storage_state=account_file,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/127.0.4324.150 Safari/537.36"
                ),
            )
            try:
                await context.grant_permissions(["geolocation"])
                page = await context.new_page()
                await page.goto(
                    "https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
                    timeout=60000,
                )
                logger.info("正在上传-------%s", title)

                await page.wait_for_url(
                    "https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
                    timeout=60000,
                )

                # Upload video file
                video_input = page.locator(
                    "input[type='file'][accept*='.mp4']"
                )
                if await video_input.count() == 0:
                    video_input = page.locator("input[type='file']").first
                await video_input.set_input_files(file_path)

                # Wait for the form page to appear
                while True:
                    try:
                        await page.wait_for_selector(
                            "div#formMain:visible"
                        )
                        break
                    except Exception:
                        logger.info("正在等待进入视频发布页面...")
                        await asyncio.sleep(0.1)

                # Fill title and tags
                await asyncio.sleep(1)
                logger.info("正在填充标题和话题...")
                await self._add_title_tags(page, title, desc, tags)

                # Wait for video upload to complete
                upload_status = await self._wait_for_upload(page)
                if not upload_status:
                    logger.error("发现上传出错了... 文件:%s", file_path)
                    raise Exception("Video upload failed")

                # Wait for cover area to be ready
                while True:
                    container_count = await page.locator(
                        "div[class*='coverWrap'] > "
                        "div[class*='cover-container']"
                    ).count()
                    if container_count >= 2:
                        logger.info(
                            "封面区域已就绪（找到 %d 个 cover-container）",
                            container_count,
                        )
                        break
                    else:
                        logger.info(
                            "等待封面区域就绪（当前 %d 个 cover-container）...",
                            container_count,
                        )
                        await asyncio.sleep(3)

                # Set custom covers
                await self._set_cover(
                    page,
                    thumbnail_landscape_path,
                    thumbnail_portrait_path,
                )

                # Set creation declaration
                await self._set_creation_declaration(
                    page,
                    creation_declaration,
                    supplementary_declaration,
                )

                # Publish (immediate or scheduled)
                await self._publish_video(page, publish_date)
                await page.wait_for_timeout(2000)

                # Handle captcha if present
                captcha_dialog = page.locator(
                    "div.passMod_dialog-container:visible"
                )
                if await captcha_dialog.count():
                    logger.warning(
                        "出现人机校验，请在浏览器中手动完成验证..."
                    )
                    try:
                        await captcha_dialog.wait_for(
                            state="hidden", timeout=120000
                        )
                        logger.info("人机校验已完成")
                        await asyncio.sleep(3)
                    except Exception:
                        logger.error("人机校验等待超时（120秒），退出")
                        raise Exception("人机校验等待超时")

                # Wait for publish success redirect
                try:
                    await page.wait_for_url(
                        "https://baijiahao.baidu.com/builder/rc/clue**",
                        timeout=30000,
                    )
                    logger.info("视频发布成功")
                except Exception:
                    current_url = page.url
                    logger.error(
                        "发布后未跳转到成功页面, 当前URL: %s",
                        current_url,
                    )
                    raise Exception(
                        f"视频发布后未成功跳转, 当前URL: {current_url}"
                    )

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("cookie更新完毕！")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper: wait for video upload to complete
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_upload(page) -> bool:
        """Poll until the video upload completes or fails.

        Returns True on success, False on failure.
        """
        while True:
            upload_failed = await page.locator(
                'div .cover-overlay:has-text("上传失败")'
            ).count()
            if upload_failed:
                logger.error("发现上传出错了...")
                return False

            uploading = await page.locator(
                'div .cover-overlay:has-text("上传中")'
            ).count()
            if uploading:
                logger.info("正在上传视频中...")
                await asyncio.sleep(2)
                continue

            if not uploading and not upload_failed:
                logger.info("视频上传完毕")
                return True

    # ------------------------------------------------------------------
    # Helper: fill title and tags (Baijiahao uses description field)
    # ------------------------------------------------------------------

    @staticmethod
    async def _add_title_tags(page, title, desc, tags):
        """Fill the description field (Lexical editor) with title and tags.

        Baijiahao publish page has a "作品描述" field (Lexical editor) rather
        than a separate title input.
        """
        desc_text = (desc or title or "").strip()
        if not desc_text:
            logger.warning("无描述内容，跳过填充")
            return
        desc_text = desc_text[:50]

        # Lexical contenteditable editor
        lexical_editor = page.locator('[data-lexical-editor="true"]')
        if await lexical_editor.count():
            editor = lexical_editor.first
            await editor.click()
            await asyncio.sleep(0.3)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await page.keyboard.type(desc_text, delay=50)
            logger.info("已填充作品描述: %s", desc_text)
            return

        # Fallback: placeholder
        title_container = page.get_by_placeholder("添加标题获得更多推荐")
        if await title_container.count():
            await title_container.fill(desc_text)
            logger.info("已通过 placeholder 填充描述: %s", desc_text)
            return

        logger.warning("未找到描述输入框，跳过填充")

    # ------------------------------------------------------------------
    # Helper: publish (immediate or scheduled)
    # ------------------------------------------------------------------

    async def _publish_video(self, page, publish_date):
        """Click the publish button, with optional scheduling."""
        if publish_date != 0:
            await self._set_schedule_publish(page, publish_date)
        else:
            await self._direct_publish(page)

    @staticmethod
    async def _direct_publish(page):
        """Click the publish button immediately."""
        try:
            publish_button = page.locator(
                "button[data-testid='publish-btn']"
            )
            if await publish_button.count():
                await publish_button.click()
            else:
                publish_button = page.locator(
                    "button.cheetah-btn-primary:has-text('发布')"
                )
                if await publish_button.count():
                    await publish_button.first.click()
        except Exception as e:
            logger.error("直接发布视频失败: %s", e)
            raise

    # ------------------------------------------------------------------
    # Helper: schedule publish
    # ------------------------------------------------------------------

    async def _set_schedule_publish(self, page, publish_date):
        """Open the schedule dialog and set the time."""
        while True:
            schedule_element = (
                page.locator(
                    "div.op-btn-outter-content >> text=定时发布"
                )
                .locator("..")
                .locator("button")
            )
            try:
                await schedule_element.click()
                await page.wait_for_selector(
                    "div.select-wrap:visible", timeout=3000
                )
                await page.wait_for_timeout(2000)
                logger.info("开始点击发布定时...")
                await self._set_schedule_time(page, publish_date)
                break
            except Exception as e:
                logger.error("定时发布失败: %s", e)
                raise

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Set the schedule time in the dropdown selectors.

        Selects the day, then a random hour, then clicks the confirm button.
        """
        publish_date_day = (
            f"{publish_date.month}月{publish_date.day}日"
            if publish_date.day > 9
            else f"{publish_date.month}月0{publish_date.day}日"
        )

        # Open day selector
        await page.wait_for_selector("div.select-wrap", timeout=5000)
        for _ in range(3):
            try:
                await page.locator("div.select-wrap").nth(0).click()
                await page.wait_for_selector(
                    "div.rc-virtual-list  div.cheetah-select-item",
                    timeout=5000,
                )
                break
            except Exception:
                await page.locator("div.select-wrap").nth(0).click()

        await page.wait_for_timeout(2000)
        await page.locator(
            f"div.rc-virtual-list  div.cheetah-select-item >> "
            f"text={publish_date_day}"
        ).click()
        await page.wait_for_timeout(2000)

        # Open hour selector and pick a random hour
        for _ in range(3):
            try:
                await page.locator("div.select-wrap").nth(1).click()
                await page.wait_for_selector(
                    "div.rc-virtual-list "
                    "div.rc-virtual-list-holder-inner:visible",
                    timeout=5000,
                )
                break
            except Exception:
                await page.locator("div.select-wrap").nth(1).click()

        await page.wait_for_timeout(2000)
        current_choice_hour = await page.locator(
            "div.rc-virtual-list:visible "
            "div.cheetah-select-item-option"
        ).count()
        await page.wait_for_timeout(2000)
        await page.locator(
            "div.rc-virtual-list:visible "
            "div.cheetah-select-item-option"
        ).nth(random.randint(1, current_choice_hour - 3)).click()

        await page.wait_for_timeout(2000)
        await page.locator("button >> text=定时发布").click()

    # ------------------------------------------------------------------
    # Helper: set custom cover images (landscape + portrait)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_cover(
        page,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
    ):
        """Upload custom cover images (landscape + portrait).

        Locates cover-container elements inside coverWrap, clicks each one
        to open a modal, uploads the image, and clicks confirm.
        """
        containers = page.locator(
            "div[class*='coverWrap'] > "
            "div[class*='cover-container']"
        )
        total = await containers.count()
        logger.info("[封面] 找到 %d 个 cover-container，开始逐个设置", total)

        for idx, (cover_type, cover_path) in enumerate(
            [
                ("横屏封面", thumbnail_landscape_path),
                ("竖屏封面", thumbnail_portrait_path),
            ]
        ):
            logger.info(
                "[封面] === 处理第 %d 个: %s ===", idx + 1, cover_type
            )

            if not cover_path or not os.path.exists(cover_path):
                logger.info("[封面] %s 无图片文件，跳过", cover_type)
                continue
            if idx >= total:
                logger.warning(
                    "[封面] cover-container 不足（%d），跳过%s",
                    total,
                    cover_type,
                )
                continue

            logger.info(
                "[封面] %s 图片: %s", cover_type, os.path.basename(cover_path)
            )
            try:
                container = containers.nth(idx)

                # 1. Click cover area to open modal
                logger.info(
                    "[封面] 点击第 %d 个 cover-container ...", idx + 1
                )
                await container.click()
                logger.info(
                    "[封面] 已点击%s，等待弹窗打开...", cover_type
                )

                # Wait for modal to appear
                await page.wait_for_selector(
                    "div.cheetah-modal:visible", timeout=10000
                )
                logger.info("[封面] %s弹窗已出现", cover_type)
                await asyncio.sleep(1)

                # 2. Upload image via file input inside the modal
                file_input_count = await page.locator(
                    "div.cheetah-modal:visible input[type='file']"
                ).count()
                logger.info(
                    "[封面] 弹窗中找到 %d 个 file input", file_input_count
                )

                dialog_input = page.locator(
                    "div.cheetah-modal:visible input[type='file']"
                ).first
                await dialog_input.set_input_files(cover_path)
                logger.info("[封面] 已上传%s文件", cover_type)
                await asyncio.sleep(2)

                # 3. Click confirm button in the modal
                confirm_btn = page.locator(
                    "div.cheetah-modal:visible "
                    "button.cheetah-btn-primary:has-text('确定')"
                )
                confirm_count = await confirm_btn.count()
                logger.info(
                    "[封面] 弹窗中找到 %d 个确定按钮", confirm_count
                )

                if confirm_count:
                    await confirm_btn.first.click()
                    logger.info("[封面] 已点击确定提交%s", cover_type)
                else:
                    logger.warning(
                        "[封面] %s弹窗未找到确定按钮", cover_type
                    )

                await asyncio.sleep(2)
                logger.info("[封面] %s设置完成", cover_type)

            except Exception as e:
                logger.error("[封面] 设置%s失败: %s", cover_type, e)

    # ------------------------------------------------------------------
    # Helper: set creation declaration
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_creation_declaration(
        page, creation_declaration="", supplementary_declaration=""
    ):
        """Set the creation declaration (required + supplementary).

        Opens the declaration dialog, selects matching radio options, and
        confirms.
        """
        if not creation_declaration and not supplementary_declaration:
            return

        logger.info(
            "设置创作声明 - 必选: %s, 补充: %s",
            creation_declaration,
            supplementary_declaration,
        )
        try:
            declaration_input = page.locator(
                "input[placeholder='请选择创作声明']"
            )
            if not await declaration_input.count():
                logger.info("未找到创作声明输入框，跳过")
                return

            await declaration_input.click()
            logger.info("已点击创作声明输入框")
            await asyncio.sleep(1)

            # Locate dialog
            modal = page.get_by_role("dialog", name="创作声明")
            await modal.wait_for(state="visible", timeout=5000)
            logger.info("创作声明弹窗已出现")

            # Select required declaration
            if creation_declaration:
                target_text = creation_declaration.strip()
                count = await modal.locator(
                    "div.flex.items-center.cursor-pointer"
                ).count()
                clicked = False
                for i in range(count):
                    row = modal.locator(
                        "div.flex.items-center.cursor-pointer"
                    ).nth(i)
                    row_text = (await row.inner_text() or "").strip()
                    if row_text == target_text:
                        await row.locator(
                            "input.cheetah-radio-input"
                        ).click(force=True)
                        logger.info("已选择必选声明: %s", row_text)
                        clicked = True
                        break
                if not clicked:
                    logger.warning(
                        "未找到匹配的必选声明: %s", target_text
                    )
                await asyncio.sleep(0.5)

            # Select supplementary declaration
            if supplementary_declaration:
                target_text = supplementary_declaration.strip()
                count = await modal.locator(
                    "div.flex.items-center.cursor-pointer"
                ).count()
                clicked = False
                for i in range(count):
                    row = modal.locator(
                        "div.flex.items-center.cursor-pointer"
                    ).nth(i)
                    row_text = (await row.inner_text() or "").strip()
                    if row_text == target_text:
                        await row.locator(
                            "input.cheetah-radio-input"
                        ).click(force=True)
                        logger.info("已选择补充声明: %s", row_text)
                        clicked = True
                        break
                if not clicked:
                    logger.warning(
                        "未找到匹配的补充声明: %s", target_text
                    )
                await asyncio.sleep(0.5)

            # Click confirm
            confirm_btn = modal.locator(
                "button.cheetah-btn-primary:has-text('确定')"
            )
            if await confirm_btn.count():
                await confirm_btn.click()
                logger.info("已点击创作声明确定按钮")
            else:
                logger.warning("未找到创作声明确定按钮")

            await asyncio.sleep(1)
            logger.info("创作声明设置完成")

        except Exception as e:
            logger.warning("设置创作声明失败（不影响上传）: %s", e)
