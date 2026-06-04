"""
Kuaishou platform implementation — 100% CloakBrowser.

Uses ``BasePlatform`` browser entry points and shared utilities from
``backend/impl/_utils.py``.
"""

import asyncio
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import get_channel_logger
logger = get_channel_logger("kuaishou")

from .._browser import create_browser_sync, create_context_sync
from .._utils import parse_schedule_time, save_login_result, scrape_user_profile
from ..base_platform import BasePlatform

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KS_LOGIN_URL = "https://cp.kuaishou.com"
_KS_UPLOAD_URL = "https://cp.kuaishou.com/article/publish/video"
_KS_MANAGE_URL_PATTERN = "**/article/manage/video?status=2&from=publish**"
_KS_UPLOAD_URL_PATTERN = "**/article/publish/video**"
_COOKIE_INVALID_SELECTOR = "div.names div.container div.name:text('机构服务')"


class KuaishouPlatform(BasePlatform):
    platform_id = 4
    platform_key = "kuaishou"
    platform_name = "快手"

    # ------------------------------------------------------------------
    # Login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Kuaishou login via QR code scan.

        Opens the Kuaishou creator platform, clicks through to the QR
        code login view, extracts the QR image, and waits for the user
        to scan.  On success the cookie and profile are saved via
        :func:`save_login_result`.
        """
        browser = await self.create_browser(login_mode=True)
        try:
            context = await self.create_context(browser)
            page = await context.new_page()

            await page.goto(_KS_LOGIN_URL)
            await page.wait_for_load_state("domcontentloaded")

            # Click "立即登录"
            login_btn = page.locator('button:has-text("立即登录"), a:has-text("立即登录")').first
            await login_btn.wait_for(state="visible", timeout=15000)
            await login_btn.click()
            await asyncio.sleep(2)

            # Click "扫码登录" if not already on QR view
            qr_login_tab = page.locator('text="扫码登录"').first
            try:
                if await qr_login_tab.count() and await qr_login_tab.is_visible():
                    await qr_login_tab.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Extract QR code image
            qrcode_img = page.locator('img[name="qrcode"], div.qr-login img[alt="qrcode"]').first
            await qrcode_img.wait_for(state="visible", timeout=30000)
            qrcode_src = await qrcode_img.get_attribute("src")
            logger.info(f"[kuaishou] QR code ready, waiting for scan...")

            # Monitor URL change — login redirects to profile or upload page
            _KS_LOGGED_IN_URLS = (
                _KS_UPLOAD_URL,                          # /article/publish/video
                "https://cp.kuaishou.com/profile",       # personal profile
                "https://cp.kuaishou.com/rest/app",      # app dashboard
                "https://cp.kuaishou.com/article/manage", # manage page
            )
            current_url = page.url
            for _ in range(200):  # ~600 seconds
                if any(page.url.startswith(u) for u in _KS_LOGGED_IN_URLS):
                    break
                # Check for QR expiry and refresh
                expired = page.locator("div.qrcode-status.qrcode-status-timeout:visible").first
                if await expired.count():
                    refresh_btn = page.locator("p.qrcode-refresh").first
                    if await refresh_btn.count():
                        await refresh_btn.click()
                        await asyncio.sleep(1)
                await asyncio.sleep(3)
            else:
                logger.info("[kuaishou] login timed out waiting for scan")
                return

            # Navigate to upload page to ensure profile data is loaded
            if not page.url.startswith(_KS_UPLOAD_URL):
                await page.goto(_KS_UPLOAD_URL)
                await page.wait_for_load_state("domcontentloaded")

            await save_login_result(
                context, page,
                platform_id=self.platform_id,
                platform_name=self.platform_name,
                status_queue=status_queue,
                scrape_fn=scrape_user_profile,
                account_id=account_id,
            )
        except Exception as exc:
            logger.info(f"[kuaishou] login error: {exc}")
            status_queue.put('{"status": "0", "error": "' + str(exc) + '"}')
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Cookie check
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        Opens the upload page and checks for the "机构服务" selector
        within 5 seconds.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(_KS_UPLOAD_URL, timeout=15000)

            try:
                await page.wait_for_selector(
                    _COOKIE_INVALID_SELECTOR, timeout=5000
                )
                # Selector found means the login page appeared → cookie invalid
                logger.info("[kuaishou] cookie invalid — login page shown")
                return False
            except Exception:
                # Selector not found → we stayed on the upload page → valid
                logger.info("[kuaishou] cookie valid")
                return True
        except Exception as exc:
            logger.info(f"[kuaishou] cookie check error: {exc}")
            return False
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Sync profile
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Kuaishou creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(_KS_UPLOAD_URL, timeout=15000)
            await page.wait_for_load_state("domcontentloaded")
            return await scrape_user_profile(page)
        except Exception as exc:
            logger.info(f"[kuaishou] sync_profile error: {exc}")
            return ("", "")
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Open creator centre — KEEP AS-IS (sync CloakBrowser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Kuaishou creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _KS_UPLOAD_URL

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
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

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Publish image — image note upload pipeline
    # ------------------------------------------------------------------

    async def publish_image(self, **kwargs) -> bool:
        """Publish an image note to Kuaishou via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- note title (will be prepended to description)
        - ``files`` (*list[str]*) -- image absolute file paths
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``desc`` (*str*, optional) -- description
        - ``cover_path`` (*str*, optional) -- cover image absolute path
        - ``author_declaration`` (*str*, optional) -- 作者声明 option text
        - ``music_id`` (*str*, optional) -- 音乐 ID
        - ``music_title`` (*str*, optional) -- 音乐标题（用于搜索匹配）
        - ``enableTimer`` (*bool*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``activities`` (*list[str]*, optional) -- official activities
        - ``dry_run`` (*bool*, optional) -- skip publish click (default True)
        """
        title = kwargs.get("title", "")
        files = kwargs.get("files", []) or []
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", []) or []
        desc = kwargs.get("desc", "")
        cover_path = kwargs.get("cover_path", "")
        author_declaration = kwargs.get("author_declaration", "")
        music_id = kwargs.get("music_id", "")
        music_title = kwargs.get("music_title", "")
        enable_timer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        activities = kwargs.get("activities", []) or []
        dry_run = kwargs.get("dry_run", True)

        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(f) for f in files]

        if cover_path and not Path(cover_path).is_file():
            logger.warning("Cover file not found: %s", cover_path)
            cover_path = ""

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
                author_declaration=author_declaration,
                music_id=music_id,
                music_title=music_title,
                enable_timer=enable_timer,
                schedule_time_str=schedule_time_str,
                dry_run=dry_run,
            )
        return True

    async def _upload_image_note(
        self, *, title, file_paths, tags, account_file, desc="", cover_path="",
        author_declaration="", music_id="", music_title="",
        enable_timer=False, schedule_time_str="", dry_run=True,
    ):
        """Upload image note to one Kuaishou account."""
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()

                # 1. 打开图文 tab
                logger.info("Navigating to Kuaishou image upload page")
                await page.goto(
                    "https://cp.kuaishou.com/article/publish/video?tabType=2",
                    wait_until="domcontentloaded", timeout=60000,
                )
                await page.wait_for_url(
                    "**/article/publish/video?tabType=2**", timeout=60000,
                )
                await asyncio.sleep(2)

                # 2. 上传图片（file chooser 多选）
                logger.info("Uploading %d images", len(file_paths))
                upload_btn = page.locator("button[class^='_upload-btn']:visible").first
                await upload_btn.wait_for(state="visible", timeout=10000)
                async with page.expect_file_chooser() as fc_info:
                    await upload_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(file_paths)
                await asyncio.sleep(2)

                # 3. 等编辑页加载（URL 不会变，等描述输入框出现即可）
                logger.info("Waiting for edit page to load...")
                await page.locator("#work-description-edit").wait_for(state="visible", timeout=30000)
                logger.info("Edit page loaded, URL: %s", page.url)
                await asyncio.sleep(1)

                # 4. 关闭引导弹层
                await self._close_guide_overlay(page)

                # 5. 填描述（标题拼首行 + 描述 + 标签）
                full_desc = f"{title}\n\n{desc}" if title else desc
                logger.info("Filling description: %s", full_desc[:50])
                desc_editor = page.locator("#work-description-edit").first
                await desc_editor.wait_for(state="visible", timeout=15000)
                await desc_editor.click()
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")
                await page.keyboard.type(full_desc[:500])
                for tag in (tags or [])[:3]:
                    await page.keyboard.type(f" #{tag}")
                    await page.keyboard.press("Space")
                await asyncio.sleep(0.5)

                logger.info("Description filled. cover_path=%s, music_id=%s", cover_path, music_id)

                # 6. 设置封面
                if cover_path:
                    await self._set_image_cover(page, cover_path)

                # 7. 设置音乐
                if music_id:
                    await self._set_image_music(page, music_id, music_title)

                # 8. 作者声明
                if author_declaration:
                    await self._set_author_declaration(page, author_declaration)

                # 9. 定时发布
                if enable_timer and schedule_time_str:
                    publish_date = parse_schedule_time(
                        schedule_time_str, 1, enable_timer, 1, None, 0
                    )[0]
                    if publish_date != 0:
                        await self._set_schedule_time(page, publish_date)

                logger.info("Form filling completed. dry_run=%s", dry_run)

                if not dry_run:
                    publish_btn = page.get_by_text("发布", exact=True)
                    await publish_btn.first.click()
                    await page.wait_for_url(
                        "**/article/manage/video?status=2&from=publish**",
                        timeout=60000,
                    )
                    logger.info("Published successfully")
                    await context.storage_state(path=account_file)
                else:
                    logger.info("========================================")
                    logger.info("点击发布！发布成功！（dry_run）")
                    logger.info("========================================")
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Publish video
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Kuaishou using CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title / description fallback
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``category`` (*int*, optional)
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_path`` (*str*, optional)
        - ``desc`` (*str*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``author_declaration`` (*str*, optional)
        """
        import asyncio as _aio

        _aio.run(self._publish_video_async(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Internal async implementation
    # ------------------------------------------------------------------

    async def _publish_video_async(self, **kwargs):
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_files = kwargs.get("account_file", [])
        enable_timer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        thumbnail_path = kwargs.get("thumbnail_path", "")
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        desc = kwargs.get("desc", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        author_declaration = kwargs.get("author_declaration", "")

        # 优先使用竖版封面，其次横版，最后通用封面
        cover_path = thumbnail_portrait_path or thumbnail_landscape_path or thumbnail_path

        publish_dates = parse_schedule_time(
            schedule_time_str, len(files), enable_timer,
            videos_per_day, daily_times, start_days,
        )

        # 构建封面完整路径
        if cover_path:
            # cover_path 已是绝对路径
            cover_path = str(cover_path)
            logger.info(f"[kuaishou] cover path: {cover_path}")

        for idx, file_name in enumerate(files):
            # file_name 已是绝对路径
            video_path = str(file_name)
            pub_date = publish_dates[idx] if idx < len(publish_dates) else 0

            for cookie_file in account_files:
                cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
                await self._upload_single(
                    video_path=video_path,
                    cookie_path=cookie_path,
                    title=title,
                    desc=desc,
                    tags=tags,
                    thumbnail_path=cover_path,
                    author_declaration=author_declaration,
                    publish_date=pub_date,
                    enable_timer=enable_timer,
                )

    # ------------------------------------------------------------------
    # Single upload
    # ------------------------------------------------------------------

    async def _upload_single(
        self,
        video_path: str,
        cookie_path: str,
        title: str,
        desc: str,
        tags: list,
        thumbnail_path: str | None,
        author_declaration: str,
        publish_date,
        enable_timer: bool,
    ):
        browser = await self.create_browser(headless=False)
        upload_success = False
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()

            await page.goto(_KS_UPLOAD_URL)
            await page.wait_for_url(_KS_UPLOAD_URL_PATTERN)
            logger.info(f"[kuaishou] uploading: {title}")

            # ------ Upload video via file chooser ------
            upload_button = page.locator("button[class^='_upload-btn']")
            await upload_button.wait_for(state="visible", timeout=10000)

            async with page.expect_file_chooser() as fc_info:
                await upload_button.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(video_path)

            await asyncio.sleep(2)

            # ------ Dismiss "我知道了" ------
            know_btn = page.locator('button[type="button"] span:text("我知道了")').first
            try:
                if await know_btn.count() and await know_btn.is_visible():
                    await know_btn.click()
            except Exception:
                pass

            # ------ Dismiss guide overlay ------
            await self._close_guide_overlay(page)

            # ------ Fill description + tags ------
            logger.info("[kuaishou] filling description and tags")
            await page.get_by_text("描述").locator("xpath=following-sibling::div").click()
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(desc or title)
            await page.keyboard.press("Enter")

            for tag in tags[:3]:
                logger.info(f"[kuaishou] adding tag: #{tag}")
                await page.keyboard.type(f"#{tag} ")
                await asyncio.sleep(2)

            # ------ Wait for upload to complete ------
            retry = 0
            while retry < 60:
                try:
                    if await page.locator("text=上传中").count() == 0:
                        logger.info("[kuaishou] video upload complete")
                        break
                    if retry % 5 == 0:
                        logger.info("[kuaishou] still uploading...")
                    if await page.locator("text=上传失败").count():
                        logger.info("[kuaishou] upload failed, retrying...")
                        await page.locator(
                            'div.progress-div [class^="upload-btn-input"]'
                        ).set_input_files(video_path)
                except Exception:
                    pass
                await asyncio.sleep(2)
                retry += 1

            # ------ Set thumbnail ------
            logger.info(f"[kuaishou] thumbnail_path: {thumbnail_path}")
            if thumbnail_path:
                await self._set_thumbnail(page, thumbnail_path)
            else:
                logger.info("[kuaishou] no thumbnail_path provided, skipping cover setting")

            # ------ Set author declaration ------
            if author_declaration:
                await self._set_author_declaration(page, author_declaration)

            # ------ Set schedule time ------
            if enable_timer and publish_date and publish_date != 0:
                await self._set_schedule_time(page, publish_date)

            # ------ Click publish ------
            while True:
                try:
                    publish_btn = page.get_by_text("发布", exact=True)
                    if await publish_btn.count() > 0:
                        await publish_btn.click()

                    await asyncio.sleep(1)
                    confirm_btn = page.get_by_text("确认发布")
                    if await confirm_btn.count() > 0:
                        await confirm_btn.click()

                    await page.wait_for_url(_KS_MANAGE_URL_PATTERN, timeout=5000)
                    logger.info("[kuaishou] video published successfully")
                    break
                except Exception as exc:
                    logger.info(f"[kuaishou] publish retry: {exc}")
                    await asyncio.sleep(1)

            upload_success = True
        finally:
            if upload_success:
                try:
                    await context.storage_state(path=cookie_path)
                    logger.info("[kuaishou] cookie updated")
                except Exception:
                    pass
                await asyncio.sleep(2)
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helper: close guide overlay (new + old DOM)
    # ------------------------------------------------------------------

    @staticmethod
    async def _close_guide_overlay(page):
        """Dismiss novice guide overlay — supports both new and old DOM."""
        # New DOM: div[role="alertdialog"]
        tooltip = page.locator('div[role="alertdialog"]:visible')
        if await tooltip.count() > 0:
            try:
                close_btn = tooltip.locator(
                    '[data-action="skip"], [aria-label="Skip"]'
                ).first
                if await close_btn.count():
                    await close_btn.click(force=True)
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                pass

        # Old DOM: react-joyride
        joyride = page.locator(
            'div[id^="react-joyride-step"] div[role="alertdialog"]'
        )
        if await joyride.count() > 0 and await joyride.first.is_visible():
            try:
                close_btn = page.locator('div[role="alertdialog"]').locator(
                    '[aria-label="Skip"], [data-action="skip"], button[title="Skip"]'
                )
                await close_btn.click(force=True)
                await joyride.wait_for(state="hidden", timeout=5000)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helper: set thumbnail
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_thumbnail(page, thumbnail_path: str):
        """Upload custom cover image.

        Flow: hover cover area -> click "封面设置" -> modal ->
        "上传封面" tab -> upload image -> confirm.
        """
        logger.info(f"[kuaishou] setting thumbnail: {thumbnail_path}")
        try:
            # 1. Hover over cover area to reveal "封面设置" overlay
            cover_area = page.locator("div[class*='default-cover']").first
            logger.info(f"[kuaishou] hovering over cover area...")
            await cover_area.hover()
            await asyncio.sleep(1.5)

            # 2. Click "封面设置" text to open modal
            cover_editor = page.locator("div[class*='cover-full-editor']").first
            logger.info(f"[kuaishou] clicking '封面设置'...")
            await cover_editor.wait_for(state="visible", timeout=10000)
            await cover_editor.click()

            # 3. Wait for modal
            modal = page.locator('div[role="document"].ant-modal:visible')
            logger.info(f"[kuaishou] waiting for modal...")
            await modal.wait_for(state="visible", timeout=30000)
            await asyncio.sleep(1)

            # 4. Click "上传封面" tab
            upload_tab = modal.locator("div[class*='header-title-item']").nth(1)
            logger.info(f"[kuaishou] clicking '上传封面' tab...")
            await upload_tab.wait_for(state="visible", timeout=10000)
            await upload_tab.click()
            await asyncio.sleep(1)

            # 5. Find hidden file input and upload image
            file_input = modal.locator("input[type='file']")
            logger.info(f"[kuaishou] uploading cover image...")
            await file_input.wait_for(state="attached", timeout=30000)
            await file_input.set_input_files(thumbnail_path)
            logger.info(f"[kuaishou] cover image uploaded, waiting for processing...")
            await asyncio.sleep(3)

            # 6. Click "确认" or "完成" button
            confirm_btn = modal.locator("button:has-text('确认'), button:has-text('完成')").first
            logger.info(f"[kuaishou] clicking confirm button...")
            await confirm_btn.wait_for(state="visible", timeout=10000)
            await confirm_btn.click()
            await asyncio.sleep(2)

            # 7. Wait for modal to close
            try:
                await modal.wait_for(state="hidden", timeout=30000)
            except Exception:
                pass

            logger.info("[kuaishou] thumbnail set successfully")
        except Exception as exc:
            logger.info(f"[kuaishou] thumbnail failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Helper: set image cover (image note)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_cover(page, cover_path: str):
        """点击「编辑封面」按钮 → 上传封面图 → 确认。"""
        logger.info("[kuaishou] setting image cover: %s", cover_path)
        try:
            edit_btn = page.get_by_text("编辑封面", exact=True)
            await edit_btn.wait_for(state="visible", timeout=10000)
            await edit_btn.click()
            await asyncio.sleep(2)

            modal = page.locator('div[role="document"].ant-modal:visible')
            await modal.wait_for(state="visible", timeout=30000)
            await asyncio.sleep(1)

            upload_tab = modal.locator("div[class*='header-title-item']").nth(1)
            await upload_tab.wait_for(state="visible", timeout=10000)
            await upload_tab.click()
            await asyncio.sleep(1)

            file_input = modal.locator("input[type='file']")
            await file_input.wait_for(state="attached", timeout=30000)
            await file_input.set_input_files(cover_path)
            await asyncio.sleep(3)

            confirm_btn = modal.locator("button:has-text('确认'), button:has-text('完成')").first
            await confirm_btn.wait_for(state="visible", timeout=10000)
            await confirm_btn.click()
            await asyncio.sleep(2)

            try:
                await modal.wait_for(state="hidden", timeout=30000)
            except Exception:
                pass
            logger.info("[kuaishou] image cover set successfully")
        except Exception as exc:
            logger.info(f"[kuaishou] image cover failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Helper: set image music (image note)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_music(page, music_id: str, music_title: str = ""):
        """点击「添加音乐」→ 抽屉内搜索 → 按 musicId/music_title 匹配 → 点「添加」。"""
        logger.info("[kuaishou] setting image music: id=%s, title=%s", music_id, music_title)
        try:
            # 点击「添加音乐」按钮（和音乐搜索组件保持一致：找 div:text-is 的父级）
            text_div = page.locator("div:text-is('添加音乐')").first
            await text_div.wait_for(state="visible", timeout=10000)
            await text_div.locator("xpath=..").click()
            await asyncio.sleep(2)

            drawer = page.locator('div.ant-drawer-content-wrapper:visible').first
            await drawer.wait_for(state="visible", timeout=10000)
            await asyncio.sleep(1)

            search_input = drawer.locator("input[placeholder='搜索音乐']").first
            await search_input.click()
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(music_title or music_id)
            await asyncio.sleep(4)

            # 匹配音乐卡片：在抽屉里找包含目标标题的卡片，点其「添加」按钮
            target_card = None
            if music_title:
                # 精确匹配标题
                title_div = drawer.locator(f"div:text-is('{music_title}')").first
                if await title_div.count():
                    target_card = title_div.locator("xpath=ancestor::div[contains(@class,'item') or contains(@class,'card')][1]")
                    if not await target_card.count():
                        target_card = title_div.locator("xpath=..")

            if target_card is None or not await target_card.count():
                # fallback：取第一个结果卡片
                all_cards = drawer.locator("div[class*='item'], div[class*='card']")
                if await all_cards.count():
                    target_card = all_cards.first
                    logger.warning("[kuaishou] music title not exact match, using first card")

            if target_card and await target_card.count():
                add_btn = target_card.locator("div:has-text('添加'), button:has-text('添加')").last
                await add_btn.click(force=True)
                await asyncio.sleep(2)
                logger.info("[kuaishou] music added")
            else:
                logger.warning("[kuaishou] no music card found")

            close_btn = page.locator("div.ant-drawer-close").first
            if await close_btn.count():
                await close_btn.click(force=True)
        except Exception as exc:
            logger.info(f"[kuaishou] image music failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Helper: set author declaration (ant-select dropdown)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_author_declaration(page, author_declaration: str):
        """Set author declaration via ant-select dropdown."""
        logger.info(f"[kuaishou] setting author declaration: {author_declaration}")
        try:
            select_clicked = False

            # Strategy 1: placeholder-based
            for placeholder in ['为作品添加补充说明', '补充说明', '请选择']:
                decl_input = page.locator(
                    f"input[placeholder*='{placeholder}']"
                )
                if await decl_input.count():
                    wrapper = decl_input.locator(
                        "xpath=ancestor::div[contains(@class, 'ant-select')]"
                    ).first
                    await wrapper.click()
                    select_clicked = True
                    break

            # Strategy 2: label-based
            if not select_clicked:
                for label_text in ['作者声明', '补充说明', '声明']:
                    label = page.locator(f"label:text('{label_text}')")
                    if await label.count():
                        wrapper = label.locator(
                            "xpath=following-sibling::div//div[contains(@class, 'ant-select')]"
                        ).first
                        if await wrapper.count():
                            await wrapper.click()
                            select_clicked = True
                            break

            # Strategy 3: scan all ant-select components
            if not select_clicked:
                all_selects = page.locator("div.ant-select")
                count = await all_selects.count()
                for i in range(count):
                    sel = all_selects.nth(i)
                    input_el = sel.locator("input").first
                    if await input_el.count():
                        ph = await input_el.get_attribute("placeholder") or ""
                        if any(kw in ph for kw in ['补充', '声明', '说明', '选择']):
                            await sel.click()
                            select_clicked = True
                            break

            if not select_clicked:
                logger.info("[kuaishou] author declaration dropdown not found, skipping")
                return

            await asyncio.sleep(1)

            # Select matching option
            option = page.locator(
                f"div.ant-select-item-option:has-text('{author_declaration}')"
            ).first
            await option.wait_for(state="visible", timeout=5000)
            await option.click()
            logger.info(f"[kuaishou] author declaration set: {author_declaration}")
            await asyncio.sleep(1)
        except Exception as exc:
            logger.info(f"[kuaishou] author declaration failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Helper: set schedule time (ant-radio + ant-picker)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Set scheduled publish time via ant-radio and ant-picker."""
        logger.info(f"[kuaishou] setting schedule time: {publish_date}")
        date_str = publish_date.strftime("%Y-%m-%d %H:%M:%S")

        # Select the "scheduled" radio option (second one)
        await page.locator("label:text('发布时间')").locator(
            "xpath=following-sibling::div"
        ).locator(".ant-radio-input").nth(1).click()
        await asyncio.sleep(1)

        # Open picker and type date
        await page.locator(
            'div.ant-picker-input input[placeholder="选择日期时间"]'
        ).click()
        await asyncio.sleep(1)
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(date_str)
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)
