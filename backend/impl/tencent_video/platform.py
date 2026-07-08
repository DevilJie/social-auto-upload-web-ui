"""
Tencent Video (腾讯视频) platform implementation — CloakBrowser.

Login URL: https://mp.v.qq.com/
Profile page: https://mp.v.qq.com/homepage
Publish URL: https://mp.v.qq.com/publishVideo/video
"""

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger
from .._browser import create_browser_sync, create_context_sync
from .._utils import clear_and_type, get_account_name_by_cookie_file, parse_schedule_time, save_login_result
from ..base_platform import BasePlatform

logger = get_channel_logger("tencent_video")

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

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    platform_cookie_domain = ".qq.com"

    def _parse_cookie_to_storage_state(self, cookie_str):
        cookies = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair: continue
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(), "value": value.strip(),
                "domain": self.platform_cookie_domain, "path": "/",
                "expires": expires, "httpOnly": True, "secure": False, "sameSite": "Lax",
            })
        return cookies, []

    # ------------------------------------------------------------------
    # login — open browser, wait for user to log in manually
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if "homepage" in page.url:
                url_changed_event.set()

        browser = await self.create_browser(login_mode=True)
        success = False
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

                # 不设超时——扫码登录可能耗时几分钟，浏览器由用户自己关
                await url_changed_event.wait()
                logger.info("Homepage detected — login successful")

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=_scrape_tencent_video_profile,
                    account_id=account_id,
                )
                success = True
            finally:
                # 释放 context 资源
                await context.close()
        finally:
            # 成功才关浏览器（失败/异常时留着让用户看现场）
            if success:
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
        url = _HOME_URL

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
    # publish_video — full Tencent Video upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Tencent Video via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
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
        logger.info("=" * 60)
        logger.info("[发布视频] 开始腾讯视频发布流程")
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
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        creation_declaration = kwargs.get("creation_declaration", "")
        desc = kwargs.get("desc", "")

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 创作声明: %s", creation_declaration or "无")
        logger.info("[发布策略] 发布策略: %s", "scheduled" if enableTimer and schedule_time_str else "immediate")

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file]
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            # thumbnail_landscape_path 已是绝对路径
            thumbnail_landscape_path = str(thumbnail_landscape_path)

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
            logger.info("-" * 40)
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s", file_index + 1, len(file_paths), file_path)
            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
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

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
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

                # 注册上传完成请求监听器（必须在 set_input_files 之前注册）
                upload_done = asyncio.Event()

                def _on_tx_request(request):
                    if (
                        "trpc.creator_center.backend.VideoFusion/UploadNotify"
                        in request.url
                        and not upload_done.is_set()
                    ):
                        upload_done.set()

                page.on("request", _on_tx_request)

                # Step 1: Upload video file via input[type=file]
                # [FIX 2026-06-10] 腾讯视频 SPA：networkidle 后还要等表单 JS 渲染完毕
                # 之前在 networkidle 后直接找 input，找不到（form 还没渲染）
                logger.info("[上传视频] 开始上传视频: %s (exists=%s)", file_path, os.path.exists(file_path))
                # 先等 publish form 渲染：找"上传视频"或上传区域的提示文字
                try:
                    await page.wait_for_selector(
                        'text=上传视频, input[type="file"], [dt-mpid*="upload"], div[class*="uploadArea"], div[class*="Upload"]',
                        timeout=15000,
                    )
                    logger.info("[上传视频] Publish form rendered, input area found")
                except Exception as e:
                    logger.warning("[DEBUG] Publish form wait timeout: %s", e)

                # 用 attached 状态找 input（不要求 visible，hidden 的也行）
                await page.wait_for_selector(
                    'input[type="file"]',
                    state='attached',
                    timeout=15000,
                )
                file_input = page.locator('input[type="file"]').first
                input_count = await page.locator('input[type="file"]').count()
                logger.info("[上传视频] Found %d file input(s) on page", input_count)
                if input_count == 0:
                    # [DEBUG 2026-06-10] 把 page state 全 dump 出来排查
                    current_url = page.url
                    page_title = await page.title()
                    body_text = (await page.locator('body').text_content() or '')[:500]
                    logger.error("[上传视频] No file input found, cannot upload video")
                    logger.error("[DEBUG] current_url=%s page_title=%s body_excerpt=%s", current_url, page_title, body_text)
                    try:
                        html_excerpt = (await page.content())[:2000]
                        logger.error("[DEBUG] html_excerpt=%s", html_excerpt)
                    except Exception as e:
                        logger.error("[DEBUG] failed to get html: %s", e)
                    raise Exception("未找到视频上传入口")
                await file_input.set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择, 等待上传完成...")

                # Step 2: Wait for the publish form to appear after upload
                # The form title "视频1" signals upload is done
                # (timeout=0 means wait indefinitely — video may be very large)
                await page.wait_for_selector(
                    'div[class*="formTitle"]:has-text("视频")',
                    timeout=0,
                )
                logger.info("[上传视频] 视频上传成功! 发布表单已就绪")
                await asyncio.sleep(2)

                # Step 2.5: 等待真正的上传完成 HTTP 请求（formTitle 只是
                # UI 提示，不是后端完成的权威信号）
                # 无超时:视频可能很大(≤16G),一直等到 UploadNotify 到达
                await upload_done.wait()
                logger.info(
                    "视频上传完成（检测到 UploadNotify 请求）"
                )

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
                logger.info("[上传视频] Cookie state updated after publish")
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
            logger.warning("[填写标题] Title field not found")
            return

        title_div = title_container.locator(
            'div.ProseMirror.ExEditor-cc-title-input'
        ).first
        if await title_div.count() == 0:
            logger.warning("[填写标题] Title contenteditable div not found")
            return

        await title_div.wait_for(state="visible", timeout=10000)
        await title_div.click()
        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        await clear_and_type(page, title[:80])
        logger.info("[填写标题] 标题已填写: %s", title[:80])

    @staticmethod
    async def _upload_cover(page, cover_path: str):
        """Upload cover image via the cover modal."""
        logger.info("[设置封面] Uploading cover image: %s", cover_path)
        try:
            # Click the "上传横版封面" button area to open the modal
            upload_area = page.locator(
                'div[class*="uploadAddArea"]:has-text("上传横版封面")'
            ).first
            if await upload_area.count() == 0:
                logger.warning("[设置封面] Cover upload area not found")
                return

            await upload_area.wait_for(state="visible", timeout=10000)
            await upload_area.click()
            await asyncio.sleep(1)

            # Wait for the ReactModal to appear
            modal = page.locator('div.ReactModal__Content').first
            await modal.wait_for(state="visible", timeout=10000)
            logger.info("[设置封面] Cover upload modal opened")

            # Find the hidden file input inside the modal by id
            # The input is: <input accept=".jpg,.jpeg,.png,.webp" id="uploadCoverBtn" type="file">
            cover_input = modal.locator('input#uploadCoverBtn')
            await cover_input.wait_for(state="attached", timeout=10000)

            # Use evaluate to set the file since input is display:none
            await cover_input.evaluate(
                "el => el.style.display = 'block'"
            )
            await cover_input.set_input_files(cover_path)
            logger.info("[设置封面] Cover image uploaded to modal")
            await asyncio.sleep(3)

            # Click the "使用" button to confirm the cover
            # From the DOM: button with dt-mpid="上传封面确定"
            use_btn = modal.locator(
                'button[dt-mpid="上传封面确定"]'
            ).first
            if await use_btn.count() > 0:
                await use_btn.click()
                logger.info("[设置封面] Cover confirmed with '上传封面确定' button")
                await asyncio.sleep(1)
            else:
                # Fallback: try any "使用" button
                use_btn_fallback = modal.locator(
                    'button:has-text("使用")'
                ).first
                if await use_btn_fallback.count() > 0:
                    await use_btn_fallback.click()
                    logger.info("[设置封面] Cover confirmed with '使用' button")
                    await asyncio.sleep(1)
                else:
                    logger.warning("[设置封面] Cover '使用' button not found in modal")
        except Exception as e:
            logger.warning("[设置封面] Cover upload failed (non-blocking): %s", e)

    @staticmethod
    async def _set_creation_declarations(page, declarations: list):
        """Check the specified creation declaration checkboxes."""
        logger.info("[设置声明] Setting creation declarations: %s", declarations)
        for decl in declarations:
            if decl not in CREATION_DECLARATIONS:
                logger.warning("[设置声明] Unknown declaration: %s", decl)
                continue
            try:
                # Find the checkbox by its label text
                checkbox = page.locator(
                    f'label[class*="checkboxItem"]:has-text("{decl}")'
                ).first
                if await checkbox.count() == 0:
                    logger.warning("[设置声明] Declaration checkbox not found: %s", decl)
                    continue

                await checkbox.wait_for(state="visible", timeout=5000)
                # Check if already checked
                chk_input = checkbox.locator('input[type="checkbox"]')
                if await chk_input.is_checked():
                    logger.info("[设置声明] Declaration already checked: %s", decl)
                    continue

                await checkbox.click()
                logger.info("[设置声明] Declaration checked: %s", decl)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(
                    "Failed to set declaration '%s' (non-blocking): %s",
                    decl, e,
                )

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Enable scheduled publishing and set the date/time."""
        logger.info("[定时发布] Setting schedule time: %s", publish_date)
        try:
            # Find the toggle switch - check if already enabled
            switch = page.locator('button[role="switch"]').first
            if await switch.count() > 0:
                is_checked = await switch.get_attribute("aria-checked")
                if is_checked != "true":
                    await switch.click()
                    logger.info("[定时发布] Scheduled publish toggled ON")
                    await asyncio.sleep(1)

            # Click the datetime trigger to open the picker
            datetime_trigger = page.locator(
                'div[class*="dateTimeSelect"]'
            ).first
            if await datetime_trigger.count() == 0:
                logger.warning("[定时发布] Datetime trigger not found")
                return

            await datetime_trigger.click()
            await asyncio.sleep(1)

            # Wait for the popup to appear
            popup = page.locator('div[class*="popupWrap"]').first
            if await popup.count() == 0:
                logger.warning("[定时发布] Datetime popup not found")
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
                logger.info("[定时发布] Schedule time confirmed: %s", publish_date)
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
        logger.info("[发布] Clicking publish button")
        publish_btn = page.locator(
            'button[dt-mpid="video_submit_click"]'
        ).first
        await publish_btn.wait_for(state="visible", timeout=10000)

        # Check if button is disabled before clicking
        disabled = await publish_btn.get_attribute("disabled")
        if disabled is not None:
            logger.warning("[发布] Publish button is disabled, waiting for it to enable...")
            await page.wait_for_function(
                "document.querySelector('button[dt-mpid=\"video_submit_click\"]')"
                " && !document.querySelector('button[dt-mpid=\"video_submit_click\"]').disabled",
                timeout=30_000,
            )

        await publish_btn.click()
        logger.info("[发布] Publish button clicked, waiting for publish result")

        # Wait up to 60s for success indicators
        success = False
        for i in range(60):
            try:
                # Check for success text on the page
                success_text = page.locator(
                    'text=提交成功, text=发布成功, text=投稿成功'
                ).first
                if await success_text.count() > 0 and await success_text.is_visible():
                    logger.info("[发布] Publish success text detected!")
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

            # After 5s, if button is still enabled and visible, retry click
            if i == 5:
                try:
                    still_enabled = await publish_btn.is_enabled()
                    if still_enabled:
                        logger.info("[发布] Button still enabled after 5s, retrying click...")
                        await publish_btn.click()
                except Exception:
                    pass

            await asyncio.sleep(1)

        if success:
            logger.info("[发布] Video published successfully")
        else:
            logger.error("[发布] Publish indicator not found within 60s timeout")
            raise Exception("发布失败：未检测到发布成功信号（页面未跳转，无成功文本）")

        await asyncio.sleep(2)
