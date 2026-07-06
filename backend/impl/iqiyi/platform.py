"""
iQiyi (爱奇艺) platform implementation — CloakBrowser.

Login URL: https://creator.iqiyi.com/
Publish URL: https://creator.iqiyi.com/publish/video/wemedia
"""

import asyncio
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger
from .._browser import create_browser_sync, create_context_sync
from .._utils import clear_and_type, get_account_name_by_cookie_file, parse_schedule_time, save_login_result
from ..base_platform import BasePlatform

logger = get_channel_logger("iqiyi")

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

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
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
        url = _LOGIN_URL

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
    # publish_video — full iQiyi upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to iQiyi via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
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
        logger.info("=" * 60)
        logger.info("[发布视频] 开始爱奇艺视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

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

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 创作声明: %s", creation_declaration or "无")
        logger.info("[发布策略] 发布策略: %s", "scheduled" if enableTimer and schedule_time_str else "immediate")

        # Resolve full paths
        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]

        cover_path = ""
        for p in [thumbnail_portrait_path, thumbnail_path, thumbnail_landscape_path]:
            if p:
                # 已是绝对路径
                cover_path = str(p)
                break

        landscape_cover = ""
        if thumbnail_landscape_path:
            # 已是绝对路径
            landscape_cover = str(thumbnail_landscape_path)

        portrait_cover = ""
        if thumbnail_portrait_path:
            # 已是绝对路径
            portrait_cover = str(thumbnail_portrait_path)

        # Parse schedule times
        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(file_paths),
            enableTimer,
            kwargs.get("videos_per_day", 1),
            kwargs.get("daily_times"),
            kwargs.get("start_days", 0),
        )

        overall_success = True
        for file_index, file_path in enumerate(file_paths):
            logger.info("-" * 40)
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s", file_index + 1, len(file_paths), file_path)
            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                    ok = await self._upload_one_video(
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
                    if not ok:
                        overall_success = False

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
        return overall_success

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

                # 注册上传完成请求监听器（必须在 set_input_files 之前注册）
                upload_done = asyncio.Event()

                def _on_iqiyi_request(request):
                    if (
                        "mp-api.iqiyi.com/v-tool/api/1.0/upload/record"
                        in request.url
                        and not upload_done.is_set()
                    ):
                        upload_done.set()

                page.on("request", _on_iqiyi_request)

                # Step 1: Upload video file via input[type=file]
                logger.info("[上传视频] 开始上传视频: %s", file_path)
                file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择, 等待上传完成...")

                # Step 1.5: 等待视频上传到服务器完成（监听 /upload/record 请求）
                await self._wait_video_upload_complete(page, upload_done)
                await asyncio.sleep(2)

                # Step 2: Wait for the publish form to appear after upload
                await page.wait_for_selector(
                    '[class*="wemedia-catalog-form"]',
                    timeout=120000,
                )
                logger.info("[上传视频] 视频上传成功! 发布表单已就绪")
                await asyncio.sleep(3)

                # Step 3: Fill title
                await self._fill_title(page, title or desc)

                # Step 4: Fill description (tags 以 #XXX 格式追加)
                full_desc = desc or ""
                if tags:
                    tag_str = " ".join(f"#{t}" for t in tags)
                    full_desc = f"{full_desc} {tag_str}".strip()
                await self._fill_description(page, full_desc)

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
                logger.info("[上传视频] Step 8: cover_path=%s, landscape_cover=%s", cover_path, landscape_cover)
                if cover_path or landscape_cover:
                    logger.info(">>> Calling _upload_cover <<<")
                    await self._upload_cover(
                        page,
                        portrait_path=cover_path,
                        landscape_path=landscape_cover,
                    )
                else:
                    logger.warning("[上传视频] Step 8: SKIPPED — no cover paths provided")

                # Step 9: Handle scheduled publishing
                if enableTimer and publish_date != 0:
                    await self._set_schedule_time(page, publish_date)

                # Step 10: Click publish / submit
                publish_ok = await self._click_publish(page)

                # Save updated cookie state regardless
                await context.storage_state(path=account_file)
                logger.info("[上传视频] Cookie state updated after publish")

                if not publish_ok:
                    logger.error("[上传视频] Publish failed for %s", account_file)
                    return False
                return True
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Upload wait helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_video_upload_complete(
        page,
        upload_done: asyncio.Event,
    ) -> None:
        """等待视频上传到服务器完成。

        监听 ``/v-tool/api/1.0/upload/record`` HTTP 请求被触发
        （caller 负责在 ``set_input_files`` 之前注册监听器）。这是
        服务端确认上传完成的权威信号——DOM 提示可能提前消失，不能
        作为完成依据。

        无超时:视频可能很大(≤16G),一直等到上传完成请求到达。
        """
        await upload_done.wait()
        logger.info(
            "检测到 /upload/record 请求，视频上传完成"
        )

    # ------------------------------------------------------------------
    # Form field helpers
    # ------------------------------------------------------------------

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
            logger.warning("[填写标题] 未找到标题输入框")
            return

        await title_input.wait_for(state="visible", timeout=10000)
        await title_input.click()
        await asyncio.sleep(0.3)

        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        # 传 element= 让 clear_and_type 走 fill('') 稳定路径(原生 <input> 元素)
        await clear_and_type(page, title[:30], element=title_input)
        logger.info("[填写标题] 标题已填写: %s", title[:30])

    @staticmethod
    async def _fill_description(page, desc: str):
        """Fill the video description."""
        if not desc:
            return

        desc_textarea = page.locator(
            'textarea[placeholder*="作品简介"]'
        ).first
        if await desc_textarea.count() == 0:
            logger.warning("[填写简介] Description textarea not found")
            return

        await desc_textarea.wait_for(state="visible", timeout=5000)
        await desc_textarea.click()
        await asyncio.sleep(0.3)

        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        # 传 element= 让 clear_and_type 走 fill('') 稳定路径(原生 <textarea> 元素)
        await clear_and_type(page, desc[:450], element=desc_textarea)
        logger.info("[填写简介] Description filled: %s", desc[:50])

    @staticmethod
    async def _set_creation_declaration(page, declaration: str):
        """Set the creation declaration (required — radio button).

        ``declaration`` can be a label (e.g. "含AI生成内容") or a value ("1").
        """
        # Determine the radio value to click
        value = CREATION_DECLARATION_MAP.get(declaration, declaration)

        logger.info("[设置声明] Setting creation declaration to value=%s", value)

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
            logger.warning("[风险提示] Unknown risk warning: %s", warning)
            return

        logger.info("[风险提示] Setting risk warning: %s", warning)

        try:
            # Click the select trigger to open the dropdown
            select_trigger = page.locator(
                '.form-select-full .el-input__inner'
            ).first
            if await select_trigger.count() == 0:
                logger.warning("[风险提示] Risk warning select not found")
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
                logger.info("[风险提示] Risk warning set to: %s", warning)
                await asyncio.sleep(0.5)
            else:
                logger.warning("[风险提示] Risk warning option not found: %s", warning)
        except Exception as e:
            logger.warning(
                "Failed to set risk warning (non-blocking): %s", e
            )

    @staticmethod
    async def _click_cash_activity(page):
        """Click the cash activity (打卡挑战赛) radio to enable it."""
        logger.info("[现金活动] Clicking cash activity")
        try:
            activity = page.locator(
                '.activity-radio-option:not(.is-checked)'
            ).first
            if await activity.count() > 0:
                await activity.click()
                logger.info("[现金活动] Cash activity clicked")
                await asyncio.sleep(0.5)
            else:
                logger.info("[现金活动] Cash activity already checked or not found")
        except Exception as e:
            logger.warning("[现金活动] Failed to click cash activity (non-blocking): %s", e)

    @staticmethod
    async def _upload_cover(
        page,
        portrait_path=None,
        landscape_path=None,
        **kwargs,
    ):
        """Upload cover images on the iQiyi publish page.

        Dialog DOM structure (image-crop-dialog):
          - Tab bar: "竖封面" (portrait, default active) | "横封面" (landscape)
          - Two ``.crop-content`` panels — first visible (portrait), second hidden (landscape)
          - Each panel has a hidden ``input[type=file]`` (via Plupload/moxie shim)
          - Footer: "完成" (confirm) | "设置横封面" (alternative switch, NOT used here)

        Workflow:
          1. Click "选择封面" trigger → opens the crop dialog
          2. Upload portrait cover via the visible file input (first panel)
          3. Wait for server-side upload to complete
          4. Click the "横封面" tab to switch to the landscape panel
          5. Upload landscape cover via the now-visible file input (second panel)
          6. Wait for server-side upload to complete
          7. Click "完成" to confirm and close the dialog
        """
        portrait_path = portrait_path or kwargs.get("cover_path")
        landscape_path = landscape_path or kwargs.get("landscape_path")

        logger.info("[设置封面] 封面上传: 竖版=%s, landscape=%s", portrait_path, landscape_path)

        try:
            # ---------------------------------------------------------------
            # Step 1: Click "选择封面" to open the cover crop dialog
            # ---------------------------------------------------------------
            logger.info("[设置封面] Step 1: Opening cover dialog...")
            trigger = page.locator('div.main-edit-bar').first
            if await trigger.count() == 0:
                logger.warning("'选择封面' trigger not found, aborting cover upload")
                return
            await trigger.scroll_into_view_if_needed()
            await trigger.wait_for(state="visible", timeout=10000)
            await trigger.evaluate("el => el.click()")

            dialog = page.locator('.image-crop-dialog')
            await dialog.wait_for(state="visible", timeout=10000)
            logger.info("[设置封面] Step 1: Cover dialog opened")
            await asyncio.sleep(2)

            # ---------------------------------------------------------------
            # Step 2: Upload portrait cover (竖封面)
            # ---------------------------------------------------------------
            if portrait_path:
                logger.info("[设置封面] Step 2: Uploading portrait cover: %s", portrait_path)
                # The first visible .crop-content panel contains the portrait upload
                portrait_panel = page.locator(
                    '.crop-content:not([style*="display: none"])'
                ).first
                await portrait_panel.wait_for(state="visible", timeout=5000)

                upload_btn = portrait_panel.locator('.upload-btn-wrap').first
                async with page.expect_file_chooser() as fc_info:
                    await upload_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(portrait_path)
                logger.info("[设置封面] Step 2: Portrait file set, waiting for upload...")
                await asyncio.sleep(10)
                logger.info("[设置封面] Step 2: Portrait upload complete")
            else:
                logger.info("[设置封面] Step 2: SKIPPED — no portrait_path")

            # ---------------------------------------------------------------
            # Step 3: Switch to landscape tab and upload (横封面)
            # ---------------------------------------------------------------
            if landscape_path:
                logger.info("[设置封面] Step 3: Switching to landscape tab...")
                landscape_tab = page.locator('.tab-item:has-text("横封面")').first
                if await landscape_tab.count() > 0:
                    await landscape_tab.click()
                    logger.info("[设置封面] Step 3: Landscape tab clicked")
                    await asyncio.sleep(2)

                    logger.info("[设置封面] Step 3: Uploading landscape cover: %s", landscape_path)
                    landscape_panel = page.locator(
                        '.crop-content:not([style*="display: none"])'
                    ).first
                    await landscape_panel.wait_for(state="visible", timeout=5000)

                    upload_btn = landscape_panel.locator('.upload-btn-wrap').first
                    async with page.expect_file_chooser() as fc_info:
                        await upload_btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(landscape_path)
                    logger.info("[设置封面] Step 3: Landscape file set, waiting for upload...")
                    await asyncio.sleep(10)
                    logger.info("[设置封面] Step 3: Landscape upload complete")
                else:
                    logger.warning("[设置封面] Step 3: Landscape tab not found")
            else:
                logger.info("[设置封面] Step 3: SKIPPED — no landscape_path")

            # ---------------------------------------------------------------
            # Step 4: Click "完成" to confirm
            # ---------------------------------------------------------------
            logger.info("[设置封面] Step 4: Clicking '完成'...")
            done_btn = page.locator('button:has-text("完成")').first
            if await done_btn.count() > 0:
                await done_btn.click()
                logger.info("[设置封面] Step 4: '完成' clicked — cover upload complete")
                await asyncio.sleep(2)
            else:
                logger.warning("[设置封面] Step 4: '完成' button not found")
        except Exception as e:
            logger.warning("[设置封面] 封面上传失败: %s", e, exc_info=True)

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Enable scheduled publishing and set the date/time."""
        logger.info("[定时发布] Setting schedule time: %s", publish_date)
        try:
            # Click "定时发布" radio
            schedule_radio = page.locator(
                '.form-publish-block .el-radio-group '
                'label:has-text("定时发布")'
            ).first
            if await schedule_radio.count() > 0:
                await schedule_radio.click()
                logger.info("[定时发布] Schedule radio selected")
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
                logger.warning("[定时发布] Schedule date input not found")
        except Exception as e:
            logger.warning(
                "Schedule time setup failed (non-blocking): %s", e
            )

    @staticmethod
    async def _click_publish(page) -> bool:
        """Click the publish button and wait for navigation to the success page.

        **点击前先等待视频上传完成**:爱奇艺发布页的上传区域 ``.up-phone-card``
        在上传过程中会显示(含进度条/速度/剩余时间/取消按钮),上传完成后
        该区域会消失。为确保点发布时视频已真正上传完毕,会:

          1. 等待 ``.up-phone-card`` 不再可见(上传区域消失)
          2. 额外等 3 秒(让后端完成转码/校验等收尾)

        成功判定（两层，任一满足即返回 True）：
          1. URL 离开发布页（不再包含 /publish/video/wemedia）
             **且** 页面出现成功关键词（"发布成功" / "已发布" / "提交成功" / "发布完成"）
          2. URL 跳转到包含 success / published / done 的成功路径

        仅 URL 变化但页面无成功标志时，判定为失败（避免误判跳转到
        内容管理页 / 错误页的情况）。
        """
        # ---- 点击前:等待视频上传区域消失 ----
        # .up-phone-card 是上传进度卡片(含"上传过程中请不要删除/移动文件"提示、
        # 进度条、已上传/速度/剩余时间、取消上传按钮)。上传完成后该卡片消失。
        try:
            upload_card = page.locator('.up-phone-card').first
            if await upload_card.count() > 0:
                logger.info(
                    "[iqiyi] 检测到上传区域 .up-phone-card,等待其消失后再点发布"
                )
                # 轮询等待卡片消失(最长 30 分钟,大文件慢网络留余量)
                deadline = asyncio.get_event_loop().time() + 1800
                last_percent = -1
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        if await upload_card.count() == 0:
                            break
                        # 卡片仍可见,打印进度(便于排查卡住)
                        try:
                            percent_el = upload_card.locator(
                                '.up-progress-percent'
                            ).first
                            if await percent_el.count() > 0:
                                percent_text = await percent_el.text_content()
                                percent_text = (percent_text or '').strip()
                                if percent_text and percent_text != last_percent:
                                    last_percent = percent_text
                                    logger.info(
                                        "[iqiyi] 视频上传中 %s,等待完成...",
                                        percent_text,
                                    )
                        except Exception:
                            pass
                    except Exception:
                        break
                    await asyncio.sleep(5)
                else:
                    logger.warning(
                        "[iqiyi] 等待上传区域消失超时(30min),仍尝试点击发布"
                    )
                logger.info("[iqiyi] 上传区域已消失,额外等待 3s 后点击发布")
                await asyncio.sleep(3)
            else:
                logger.info("[iqiyi] 未检测到上传区域(可能已上传完),直接点发布")
        except Exception as e:
            logger.info(
                "[iqiyi] 等待上传区域异常(忽略,继续点发布): %s", e
            )

        logger.info("[发布] Clicking publish button")
        try:
            publish_btn = page.locator(
                'button:has-text("发布"), '
                'button:has-text("提交"), '
                'button[type="submit"]'
            ).first

            await publish_btn.wait_for(state="visible", timeout=10000)
            await publish_btn.click()
            logger.info("[发布] Publish button clicked, waiting for navigation")

            # 等待 URL 离开发布页（最多 60s）
            try:
                await page.wait_for_function(
                    '!window.location.href.includes("/publish/video/wemedia")',
                    timeout=60000,
                )
            except Exception:
                logger.warning(
                    "Publish failed — still on publish page after 60s timeout. "
                    "URL: %s", page.url
                )
                return False

            logger.info("[发布] URL 离开发布页: %s", page.url)
            await asyncio.sleep(3)  # 等跳转后的页面稳定

            # 判定 1: URL 包含 success / published / done 路径
            current_url = page.url.lower()
            if any(kw in current_url for kw in ("/success", "published", "/done")):
                logger.info("[发布] URL 命中成功路径关键词: %s", page.url)
                logger.info("[发布] Video published successfully")
                return True

            # 判定 2: 页面文本包含成功关键词
            success_keywords = ("发布成功", "已发布", "提交成功", "发布完成")
            for kw in success_keywords:
                try:
                    if await page.get_by_text(kw, exact=False).count() > 0:
                        logger.info("页面文本命中成功关键词: %r", kw)
                        logger.info("[发布] Video published successfully")
                        return True
                except Exception:
                    continue

            # 所有判定都不满足 → 视为跳转到了非成功页（如内容管理页）
            logger.warning(
                "URL 已离开发布页，但未检测到成功标志（关键词 %s）"
                "。当前 URL: %s",
                success_keywords, page.url,
            )
            return False
        except Exception as e:
            logger.warning("[发布] Publish click failed: %s", e)
            raise
