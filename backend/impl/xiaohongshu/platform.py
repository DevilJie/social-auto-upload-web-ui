"""Xiaohongshu platform implementation — CloakBrowser."""

import asyncio
import os
import threading
import time
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._browser import create_browser, create_context, create_browser_sync, create_context_sync
from .._utils import (
    get_account_name_by_cookie_file,
    scrape_user_profile,
    save_login_result,
    parse_schedule_time,
)

from util._logger import bind_account_name, get_channel_logger
from ..base_platform import BasePlatform

logger = get_channel_logger("xiaohongshu")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_XHS_LOGIN_URL = "https://creator.xiaohongshu.com/login"
_XHS_CREATOR_URL = "https://creator.xiaohongshu.com/"
_XHS_PUBLISH_VIDEO_URL = (
    "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video"
)
_XHS_PUBLISH_IMAGE_URL = (
    "https://creator.xiaohongshu.com/publish/publish?from=menu&target=image"
)
_XHS_LOGIN_BOX_SELECTOR = "div[class*='login-box']"
_XHS_LOGIN_SWITCH_SELECTOR = "img.css-wemwzq"
_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
_PUBLISH_STRATEGY_SCHEDULED = "scheduled"


# ======================================================================
# XiaohongshuPlatform
# ======================================================================

class XiaohongshuPlatform(BasePlatform):
    platform_id = 1
    platform_key = "xiaohongshu"
    platform_name = "小红书"

    # ------------------------------------------------------------------
    # login()
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Xiaohongshu login via QR code scan.

        Opens the creator page, switches to QR mode by clicking
        ``img.css-wemwzq``, extracts the QR code from the 3rd image,
        monitors URL change for login completion, then delegates to
        ``save_login_result`` for profile scraping + cookie + DB write.
        """
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if page.url != original_url:
                url_changed_event.set()

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(_XHS_CREATOR_URL)

                # Switch to QR-code login mode
                await page.locator(_XHS_LOGIN_SWITCH_SELECTOR).click()

                # QR is the 3rd image on the page
                img_locator = page.get_by_role("img").nth(2)
                src = await img_locator.get_attribute("src")
                original_url = page.url
                logger.info(f"[xhs] QR code src: {src}")
                status_queue.put(src)

                page.on(
                    "framenavigated",
                    lambda frame: (
                        asyncio.create_task(_on_url_change())
                        if frame == page.main_frame
                        else None
                    ),
                )

                # 不设超时——扫码登录可能耗时几分钟，浏览器由用户自己关
                await url_changed_event.wait()
                logger.info("[xhs] login page navigation detected")

                # Login succeeded -- scrape profile, save cookie, write DB
                await save_login_result(
                    context, page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
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
    # check_cookie()
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        Opens the creator home page and checks for login redirect.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        if not os.path.exists(cookie_path):
            return False

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(_XHS_CREATOR_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(2)

                if _XHS_LOGIN_URL in page.url:
                    logger.info("[xhs] cookie expired, needs re-login")
                    return False

                logger.info("[xhs] cookie valid")
                return True
            except Exception as exc:
                logger.info(f"[xhs] cookie check error: {exc}")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile()
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Xiaohongshu creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _XHS_CREATOR_URL

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                name, avatar = await scrape_user_profile(page)
                return name, avatar
            except Exception as e:
                logger.info(f"[xhs] sync profile failed: {e}")
                return "", ""
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center()
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Xiaohongshu creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _XHS_CREATOR_URL

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
    # publish_video()
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Xiaohongshu using CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional) -- enable scheduled publishing
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_path`` (*str*, optional)
        - ``desc`` (*str*, optional) -- description
        - ``schedule_time_str`` (*str*, optional)
        - ``ai_content`` (*str*, optional) -- AI content declaration
        """
        logger.info("=" * 60)
        logger.info("[发布视频] 开始小红书视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", [])
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
        ai_content = kwargs.get("ai_content", "")

        # Resolve file paths
        account_paths = [Path(BASE_DIR / "cookiesFile" / f) for f in account_files]
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        file_paths = [Path(f) for f in files]

        # XHS is a portrait-first platform: prefer portrait cover,
        # then landscape, then generic thumbnail.
        effective_cover = thumbnail_portrait_path or thumbnail_landscape_path or thumbnail_path
        if effective_cover:
            # 已是绝对路径
            effective_cover = str(effective_cover)

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_files))
        logger.info("[发布参数] 定时发布: %s", enable_timer)
        logger.info("[发布参数] 封面: %s", effective_cover or "无")

        # Parse schedule times
        publish_datetimes = parse_schedule_time(
            schedule_time_str, len(file_paths), enable_timer,
            videos_per_day, daily_times, start_days,
        )
        # XHS compat: if no schedule, pass 0
        if not enable_timer or not schedule_time_str:
            publish_datetimes = 0 if not enable_timer else publish_datetimes

        strategy = (
            _PUBLISH_STRATEGY_SCHEDULED
            if enable_timer and schedule_time_str
            else _PUBLISH_STRATEGY_IMMEDIATE
        )
        logger.info("[发布策略] 发布策略: %s", strategy)

        for index, file_path in enumerate(file_paths):
            logger.info("-" * 40)
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s", index + 1, len(file_paths), file_path)
            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")

                    pub_date = (
                        publish_datetimes
                        if not isinstance(publish_datetimes, list)
                        else publish_datetimes[index]
                    )

                    asyncio.run(
                        _publish_single_video(
                            title=title,
                            file_path=str(file_path),
                            tags=tags,
                            publish_date=pub_date,
                            account_file=str(cookie_path),
                            thumbnail_path=effective_cover,
                            desc=desc,
                            ai_content=ai_content,
                            publish_strategy=strategy,
                        )
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
        return True

    # ------------------------------------------------------------------
    # publish_image()
    # ------------------------------------------------------------------

    async def publish_image(self, **kwargs) -> bool:
        """
        小红书图文发布

        参数：
        - title (str): 标题，最多20字
        - files (list[str]): 图片文件路径列表
        - tags (list[str]): 标签列表，最多10个
        - account_file (list[str]): Cookie文件名
        - desc (str): 描述，最多1000字
        - enableTimer (bool): 是否启用定时发布
        - schedule_time_str (str): 定时发布时间
        - ai_content (str): 内容类型声明
        - dry_run (bool): 是否模拟发布，默认True

        返回：
        - bool: 发布是否成功
        """
        logger.info("=" * 60)
        logger.info("[发布图集] 开始小红书图集发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get('title', '')
        files = kwargs.get('files', [])
        tags = kwargs.get('tags', [])[:10]  # 最多10个标签
        account_files = kwargs.get('account_file', [])
        desc = kwargs.get('desc', '')[:1000]  # 最多1000字
        enableTimer = kwargs.get('enableTimer', False)
        schedule_time_str = kwargs.get('schedule_time_str', '')
        ai_content = kwargs.get('ai_content', '')
        is_original = kwargs.get('is_original', False)
        dry_run = kwargs.get('dry_run', True)

        if not files:
            logger.error("[发布图集] 没有图片文件")
            return False

        if not account_files:
            logger.error("[发布图集] 没有账号文件")
            return False

        # 截断标题
        title = title[:20]

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 图片数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_files))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 原创声明: %s", is_original)
        logger.info("[发布参数] AI内容声明: %s", ai_content or "无")
        logger.info("[发布策略] 模式: %s", "演练(dry_run)" if dry_run else "正式发布")

        # 截断标题
        title = title[:20]

        # Resolve cookie file paths (same as publish_video)
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_files]

        # Parse schedule times
        publish_datetimes = parse_schedule_time(
            schedule_time_str, len(files), enableTimer,
            kwargs.get('videos_per_day', 1), kwargs.get('daily_times'), kwargs.get('start_days', 0),
        )
        if not enableTimer or not schedule_time_str:
            publish_datetimes = 0 if not enableTimer else publish_datetimes

        success_count = 0
        total = len(account_paths)
        for index, cookie_path in enumerate(account_paths):
            cookie_name = Path(cookie_path).name
            nick = get_account_name_by_cookie_file(cookie_name)
            with bind_account_name(nick or "-"):
                logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", index + 1, total, nick or "未知")
                pub_date = (
                    publish_datetimes
                    if not isinstance(publish_datetimes, list)
                    else publish_datetimes[index]
                )
                try:
                    result = await _publish_single_image(
                        title=title,
                        files=files,
                        tags=tags,
                        account_file=cookie_path,
                        desc=desc,
                        enableTimer=enableTimer,
                        schedule_time_str=schedule_time_str,
                        publish_date=pub_date,
                        ai_content=ai_content,
                        is_original=is_original,
                        dry_run=dry_run,
                    )
                    if result:
                        success_count += 1
                except Exception as e:
                    logger.error("[发布图集] 账号 %s 发布失败: %s", cookie_path, e)

        logger.info("[发布图集] 图集发布完成: %d/%d 成功", success_count, total)
        logger.info("=" * 60)
        logger.info("[发布图集] 图集发布流程完成!")
        logger.info("=" * 60)
        return success_count > 0


# ======================================================================
# Internal publish helper
# ======================================================================

async def _publish_single_video(
    title: str,
    file_path: str,
    tags: list,
    publish_date,
    account_file: str,
    thumbnail_path: str = "",
    desc: str = "",
    ai_content: str = "",
    publish_strategy: str = _PUBLISH_STRATEGY_IMMEDIATE,
):
    """Upload and publish one video to Xiaohongshu using CloakBrowser."""

    browser = await create_browser(headless=False)
    try:
        context = await create_context(browser, storage_state=account_file)
        await context.grant_permissions(["geolocation"])
        try:
            page = await context.new_page()
            await _upload_video_content(
                page=page,
                title=title,
                file_path=file_path,
                tags=tags,
                desc=desc,
                thumbnail_path=thumbnail_path,
                ai_content=ai_content,
                publish_date=publish_date,
                publish_strategy=publish_strategy,
            )
            await context.storage_state(path=account_file)
            logger.info("[发布] Cookie状态已更新")
        finally:
            await context.close()
    finally:
        await browser.close()


async def _publish_single_image(
    title: str,
    files: list,
    tags: list,
    account_file: str,
    desc: str = "",
    enableTimer: bool = False,
    schedule_time_str: str = "",
    publish_date=None,
    ai_content: str = "",
    is_original: bool = False,
    dry_run: bool = True,
) -> bool:
    """Upload and publish one image set to Xiaohongshu using CloakBrowser."""
    browser = await create_browser(headless=False)
    try:
        context = await create_context(browser, storage_state=account_file)
        await context.grant_permissions(["geolocation"])
        try:
            page = await context.new_page()

            # Navigate to image publish page
            logger.info("[上传图集] 正在打开图集发布页面...")
            await page.goto(_XHS_PUBLISH_IMAGE_URL, wait_until="networkidle")
            await asyncio.sleep(3)  # 等待页面完全加载
            logger.info("[上传图集] 图集发布页面已打开")

            # 等待上传区域出现
            logger.info("[上传图集] 等待上传区域加载...")
            try:
                await page.wait_for_selector('.upload-wrapper, .upload-input, input[type="file"]', timeout=15000)
                logger.info("[上传图集] 上传区域已加载")
            except Exception as e:
                logger.warning("[上传图集] 未找到上传区域, 尝试继续: %s", e)

            # Upload images
            file_paths = [str(f) for f in files]
            if not await _upload_images(page, file_paths):
                logger.error("[上传图集] 图片上传失败")
                return False

            # Wait for page readiness
            await asyncio.sleep(2)

            # Fill title, description, tags
            logger.info("[填写标题] 开始填写标题、简介与标签...")
            await _fill_title(page, title)
            await _fill_desc(page, desc)
            await _fill_tags(page, tags)

            # Set original declaration (原创声明)
            if is_original:
                logger.info("[原创声明] 开始设置原创声明...")
                await _set_original_declaration(page)

            # Set content declaration (内容类型声明)
            if ai_content:
                logger.info("[内容声明] 开始设置内容类型声明: %s", ai_content)
                await _set_content_declaration(page, ai_content)

            # Set schedule time
            is_scheduled = enableTimer and publish_date and publish_date != 0
            if is_scheduled:
                logger.info("[定时发布] 开始设置定时发布...")
                await _set_schedule_time(page, publish_date)
                logger.info("[定时发布] 定时发布设置完成")

            # Wait for publish button to hydrate
            await _wait_for_page_ready(page)

            if not dry_run:
                # Click publish
                btn_text = "定时发布" if is_scheduled else "发布"
                logger.info("[发布] 正在点击发布按钮...")
                await _click_publish_button(page, btn_text)

                # Wait for page navigation after click
                current_url = page.url
                await asyncio.sleep(3)
                new_url = page.url
                logger.info("[发布] 页面URL变化: %s -> %s", current_url, new_url)

                if "success" in new_url.lower() or "publish/publish" not in new_url:
                    logger.info("[发布] 图集发布成功: %s", title)
                else:
                    logger.error("[发布] 页面未跳转到成功页: %s", new_url)
                    return False
            else:
                logger.info("[发布] [演练模式] 图集发布演练完成: %s", title)

            # Save cookies
            await context.storage_state(path=account_file)
            logger.info("[发布] Cookie状态已更新")
            return True
        except Exception as e:
            logger.error("[发布图集] 图集发布出错: %s", e)
            return False
        finally:
            await context.close()
    except Exception as e:
        logger.error("[发布图集] 图集发布浏览器错误: %s", e)
        return False
    finally:
        await browser.close()


# ======================================================================
# Page readiness detection
# ======================================================================

async def _wait_for_page_ready(page, timeout: int = 120) -> bool:
    """Poll until xhs-publish-btn is ready (submit-disabled="false").

    XHS uses closed shadow DOM which cannot be pierced by Playwright
    locators.  Instead, check the ``submit-disabled`` attribute on the
    ``<xhs-publish-btn>`` host element — it flips from "true" to "false"
    once the video has finished server-side processing.
    """
    logger.info("[发布就绪] 等待上传后页面完全就绪...")
    start = time.time()
    last_log = 0
    while time.time() - start < timeout:
        el = page.locator("xhs-publish-btn")
        if await el.count() > 0:
            disabled = await el.first.get_attribute("submit-disabled")
            if disabled == "false":
                elapsed = int(time.time() - start)
                logger.info("[发布就绪] 页面已就绪 (submit-disabled=false, 等待 %ds)", elapsed)
                return True
        elapsed = int(time.time() - start)
        if elapsed - last_log >= 15:
            logger.info("[发布就绪] 仍在等待页面就绪... (%ds)", elapsed)
            last_log = elapsed
        await asyncio.sleep(1)
    logger.error("[发布就绪] 页面在 %ds 后仍未就绪", timeout)
    try:
        await page.screenshot(path="debug_page_not_ready.png")
        logger.info("[发布就绪] 已保存 debug_page_not_ready.png")
    except Exception:
        pass
    return False


# ======================================================================
# Core upload logic -- mirrors XiaoHongShuVideo.upload_video_content
# ======================================================================

async def _upload_video_content(
    page,
    title: str,
    file_path: str,
    tags: list,
    desc: str,
    thumbnail_path: str,
    ai_content: str,
    publish_date,
    publish_strategy: str,
):
    """All browser interaction for a single XHS video upload."""

    logger.info("[上传视频] 开始上传视频: %s", title)
    await page.goto(_XHS_PUBLISH_VIDEO_URL)
    await page.wait_for_url(_XHS_PUBLISH_VIDEO_URL)
    logger.info("[上传视频] 正在上传视频文件...")

    # --- Upload video file ---
    await page.locator(
        "div[class^='upload-content'] input[class='upload-input']"
    ).set_input_files(file_path)

    # Poll for upload completion:
    #   - "上传中" 字样: div.uploading 在主 DOM 树，page.locator 可直接匹配
    #   - 发布按钮 disabled: <button class="ce-btn bg-red"> 在 closed shadow DOM，
    #     必须用 CDP DOM.getFlattenedDocument { pierce: true } 穿透读取
    #     （与 _click_publish_button 同样的方法）
    cdp = await page.context.new_cdp_session(page)
    await cdp.send("DOM.enable")
    try:
        while True:
            try:
                uploading_count = await page.locator(
                    'div.uploading:has-text("上传中")'
                ).count()

                flattened = await cdp.send("DOM.getFlattenedDocument", {
                    "depth": -1,
                    "pierce": True,
                })
                publish_disabled = True
                for node in flattened.get("nodes", []):
                    if node.get("localName") != "button":
                        continue
                    attrs = node.get("attributes") or []
                    attr_dict = {}
                    for i in range(0, len(attrs), 2):
                        attr_dict[attrs[i]] = attrs[i + 1]
                    cls = attr_dict.get("class") or ""
                    if "ce-btn" in cls and "bg-red" in cls:
                        publish_disabled = "disabled" in attr_dict
                        break

                if uploading_count == 0 and not publish_disabled:
                    logger.info(
                        "[上传视频] 视频上传成功 "
                        "(上传完成, 发布按钮已可用)"
                    )
                    break

                logger.info(
                    "[上传视频] 仍在上传中 "
                    "(uploading_nodes=%s, publish_disabled=%s), 等待...",
                    uploading_count, publish_disabled,
                )
            except Exception as e:
                logger.info("[上传视频] 上传状态检查: %s", e)
            await asyncio.sleep(2)
    finally:
        await cdp.detach()

    # --- Fill title (20 char limit) ---
    logger.info("[填写标题] 开始填写标题、简介与标签...")
    await _fill_title(page, title)
    await _fill_desc(page, desc)
    await _fill_tags(page, tags)
    logger.info("[填写标题] 标题: %s", title)

    # --- Set cover / thumbnail ---
    logger.info("[设置封面] 开始设置视频封面...")
    await _set_thumbnail(page, thumbnail_path)

    # --- Set schedule time ---
    if publish_strategy == _PUBLISH_STRATEGY_SCHEDULED and publish_date != 0:
        logger.info("[定时发布] 开始设置定时发布...")
        await _set_schedule_time(page, publish_date)
        logger.info("[定时发布] 定时发布设置完成")

    # --- Set AI content declaration ---
    logger.info("[内容声明] 开始设置内容类型声明: %s", ai_content)
    await _set_content_declaration(page, ai_content)

    # --- Set original declaration (原创声明) ---
    logger.info("[原创声明] 开始设置原创声明...")
    await _set_original_declaration(page)

    # --- Wait for publish button to hydrate ---
    await _wait_for_page_ready(page)

    # --- Click publish ---
    btn_text = "定时发布" if publish_strategy == _PUBLISH_STRATEGY_SCHEDULED else "发布"
    logger.info("[发布] 正在点击发布按钮...")
    await _click_publish_button(page, btn_text)

    # Wait for page navigation after click
    current_url = page.url
    await asyncio.sleep(3)
    new_url = page.url
    logger.info("[发布] 页面URL变化: %s -> %s", current_url, new_url)

    if "success" in new_url.lower() or "publish/publish" not in new_url:
        logger.info("[发布] 视频发布成功! 页面跳转到: %s", new_url)
    else:
        logger.error("[发布] 页面未跳转到成功页: %s", new_url)


# ======================================================================
# Individual fill helpers
# ======================================================================

async def _click_publish_button(page, btn_text: str) -> None:
    """Click the publish button. Playwright locators pierce shadow DOM by default."""
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(1)

    # xhs-publish-btn uses CLOSED shadow DOM.  CDP's getFlattenedDocument
    # with pierce=True returns ALL nodes including those inside closed
    # shadow trees — unlike DOM.querySelector which cannot search inside
    # closed shadow DOM.
    cdp = await page.context.new_cdp_session(page)
    try:
        await cdp.send("DOM.enable")
        flattened = await cdp.send("DOM.getFlattenedDocument", {
            "depth": -1,
            "pierce": True,
        })
        btn_node_id = 0
        for node in flattened.get("nodes", []):
            if node.get("localName") != "button":
                continue
            attrs = node.get("attributes") or []
            # attrs is [key, val, key, val, ...]
            for i in range(0, len(attrs), 2):
                if attrs[i] == "class" and "bg-red" in (attrs[i + 1] or ""):
                    btn_node_id = node["nodeId"]
                    break
            if btn_node_id:
                break

        if not btn_node_id:
            logger.error("[发布] CDP: 在扁平化DOM中未找到发布按钮")
            return

        await cdp.send("DOM.scrollIntoViewIfNeeded", {"nodeId": btn_node_id})
        box_model = await cdp.send("DOM.getBoxModel", {"nodeId": btn_node_id})
        if not box_model or "model" not in box_model:
            logger.error("[发布] CDP: 无法获取发布按钮的盒子模型")
            return
        quad = box_model["model"]["content"]
        # content quad: [x1,y1, x2,y2, x3,y3, x4,y4]
        x = (quad[0] + quad[4]) / 2
        y = (quad[1] + quad[5]) / 2
        logger.info("[发布] CDP: 在 (%.0f, %.0f) 处点击发布按钮", x, y)
        await page.mouse.click(x, y)
        logger.info("[发布] 已通过CDP扁平化DOM点击发布按钮")
    finally:
        await cdp.detach()


async def _fill_title(page, title: str) -> None:
    """Fill the title input (max 20 characters)."""
    container = page.locator('input[placeholder*="填写标题"]')
    await container.fill(title[:20])


async def _fill_desc(page, desc: str) -> None:
    """Fill the description field."""
    if not desc:
        return
    desc_el = page.locator('p[data-placeholder*="输入正文描述"]')
    await desc_el.click()
    await page.keyboard.press("Backspace")
    await page.keyboard.press("Control+KeyA")
    await page.keyboard.press("Delete")
    await page.keyboard.type(desc)
    await page.keyboard.press("Enter")


async def _fill_tags(page, tags: list) -> None:
    """Add tags via keyboard + auto-complete dropdown."""
    if not tags:
        return

    # Ensure the desc area is focused so tags appear in the right place
    desc_el = page.locator('p[data-placeholder*="输入正文描述"]')
    if await desc_el.count() and await desc_el.is_visible():
        await desc_el.click()

    for tag in tags:
        # 输入 # 标签
        await page.keyboard.type("#" + tag, delay=30)
        # 等待一下让输入完成
        await asyncio.sleep(0.5)
        # 按空格触发标签识别
        await page.keyboard.press("Space")
        # 等待标签被识别
        await asyncio.sleep(1)


async def _set_thumbnail(page, thumbnail_path: str) -> None:
    """Upload a custom cover image via the cover modal.

    New XHS UI (2026): the cover modal has a hidden file input directly
    accessible; there is no '上传封面' tab anymore.  The file input is
    ``input[type=file][accept*="image"]`` with ``display: none``.
    """
    if not thumbnail_path:
        return
    if not os.path.exists(thumbnail_path):
        logger.info("[封面] 封面不存在: %s, 跳过", thumbnail_path)
        return

    logger.info("[封面] 开始设置封面图片")

    try:
        # The cover editor modal opens only after hovering the cover
        # preview then clicking the "修改封面" overlay that appears.
        # Step 1: hover the cover preview to reveal the operator overlay
        cover_sel = 'div[style*="background-image"]'
        cover_loc = page.locator(cover_sel).first
        try:
            await cover_loc.wait_for(state="attached", timeout=10_000)
            await cover_loc.hover()
            await page.wait_for_timeout(1000)
            logger.info("[封面] 已悬停封面预览, 查找操作按钮...")

            # Step 2: click the operator overlay
            op_loc = page.locator("div.operator.pointer").first
            await op_loc.click(force=True, timeout=5_000)
            logger.info("[封面] 已点击封面操作遮罩")
        except Exception as e:
            logger.info("[封面] 封面悬停/点击失败: %s, 跳过", e)
            return

        # Find the cover modal — retry once with an extra click if needed
        modal_selectors = [
            "div.d-modal.cover-modal",
            "div.cover-modal",
            "div[class*='cover-modal']",
            "div.d-modal",
        ]
        modal = None
        for attempt in range(2):
            await page.wait_for_timeout(3000)
            for sel in modal_selectors:
                if await page.locator(sel).count() > 0:
                    modal = page.locator(sel).first
                    break
            if modal:
                break
            if attempt == 0:
                logger.info("[封面] 第1次未找到封面弹窗, 重试...")
                try:
                    await cover_loc.hover()
                    await page.wait_for_timeout(500)
                    await page.locator("div.operator.pointer").first.click(force=True, timeout=5_000)
                except Exception:
                    pass

        if not modal:
            logger.info("[封面] 重试后仍未找到封面弹窗, 跳过")
            try:
                await page.screenshot(path="debug_cover_modal_missing.png")
                logger.info("[封面] 已保存 debug_cover_modal_missing.png")
            except Exception:
                pass
            return

        # Set the file directly on the hidden file input
        file_input = modal.locator('input[type="file"][accept*="image"]').first
        await file_input.wait_for(state="attached", timeout=10000)
        logger.info("[封面] 正在上传封面: %s", os.path.basename(thumbnail_path))
        await file_input.set_input_files(thumbnail_path)
        await page.wait_for_timeout(3000)

        # Click confirm button
        confirm_selectors = [
            "button.mojito-button:has-text('确定')",
            "button:has-text('确定')",
            ".d-modal-footer button:has-text('确定')",
        ]
        confirm_button = None
        for sel in confirm_selectors:
            if await modal.locator(sel).count() > 0:
                confirm_button = modal.locator(sel).first
                break

        if confirm_button:
            await confirm_button.click()
            try:
                await modal.wait_for(state="hidden", timeout=15000)
                logger.info("[封面] 封面设置成功")
            except Exception:
                logger.info("[封面] 封面弹窗未关闭, 继续执行")
        else:
            logger.info("[封面] 未找到确定按钮, 跳过封面")
    except Exception as e:
        logger.info("[封面] 封面上传失败: %s", e)


async def _upload_images(page, files: list[str]) -> bool:
    """Upload images to the image-text publish page.

    Parameters
    ----------
    page : playwright.async_api.Page
        The Playwright page object.
    files : list[str]
        List of image file paths to upload.

    Returns
    -------
    bool
        True if all images were uploaded successfully, False otherwise.
    """
    if not files:
        logger.warning("[上传图集] 没有图片可上传")
        return False

    try:
        logger.info("[上传图集] 正在上传 %d 张图片...", len(files))

        # 等待页面加载完成
        await asyncio.sleep(2)

        # 小红书图文发布页面的图片上传 input
        # DOM 结构: input.upload-input[type="file"][accept=".jpg,.jpeg,.png,.webp"]
        file_input = page.locator('input.upload-input[type="file"]')

        # 等待 input 出现
        try:
            await file_input.wait_for(state="attached", timeout=10000)
            logger.info("[上传图集] 已找到上传input")
        except Exception:
            logger.info("[上传图集] 未找到上传input, 尝试其他选择器")

        # 如果找不到，尝试其他选择器
        if await file_input.count() == 0:
            file_input = page.locator('input[type="file"][accept*=".jpg"]')

        if await file_input.count() == 0:
            file_input = page.locator('input[type="file"][multiple]')

        if await file_input.count() == 0:
            file_input = page.locator('input[type="file"]')

        if await file_input.count() > 0:
            # 使用找到的 input 元素上传文件
            logger.info("[上传图集] 通过file input上传")
            await file_input.first.set_input_files(files)
            logger.info("[上传图集] 已通过file input上传 %d 张图片", len(files))
        else:
            # 使用 expect_file_chooser 模式作为备选
            logger.info("[上传图集] 尝试文件选择器方式")
            upload_btn = page.locator('button:has-text("上传图片")')

            if await upload_btn.count() == 0:
                upload_btn = page.locator('.upload-button').first

            if await upload_btn.count() == 0:
                upload_btn = page.locator('button.bg-red').first

            if await upload_btn.count() > 0:
                logger.info("[上传图集] 点击上传按钮")
                async with page.expect_file_chooser(timeout=10000) as fc_info:
                    await upload_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(files)
                logger.info("[上传图集] 已通过文件选择器上传 %d 张图片", len(files))
            else:
                # 最后尝试直接设置所有 file input
                all_inputs = await page.query_selector_all('input[type="file"]')
                logger.info("[上传图集] 找到 %d 个file input", len(all_inputs))
                if all_inputs:
                    await all_inputs[0].set_input_files(files)
                    logger.info("[上传图集] 已通过第一个file input上传 %d 张图片", len(files))
                else:
                    logger.error("[上传图集] 未找到任何上传机制")
                    return False

        # Wait for images to finish uploading (check image count)
        expected_count = len(files)
        timeout_per_image = 30
        max_wait = max(120, min(expected_count * timeout_per_image, 600))
        logger.info("[上传图集] 等待 %d 张图片上传完成 (最多 %ds)", expected_count, max_wait)

        for i in range(max_wait):
            # 检查已上传的图片数量
            # 小红书的图片预览区域
            uploaded = await page.query_selector_all('.upload-wrapper img, .image-item img, .preview img, [class*="image"] img')
            if len(uploaded) >= expected_count:
                logger.info("[上传图集] 全部 %d 张图片上传完成", expected_count)
                return True
            if i % 10 == 0:
                logger.info("[上传图集] 正在上传图片: %d/%d", len(uploaded), expected_count)
            await asyncio.sleep(1)

        logger.warning(
            "[上传图集] 图片上传超时, 已上传 %d/%d", len(uploaded), expected_count
        )
        return len(uploaded) > 0

    except Exception as e:
        logger.error("[上传图集] 图片上传失败: %s", e)
        return False


async def _set_schedule_time(page, publish_date) -> None:
    """Enable timed publishing and set the target date/time."""
    logger.info("[定时发布] 设置定时发布时间: %s", publish_date)
    await (
        page.locator(".custom-switch-card")
        .filter(has_text="定时发布")
        .locator(".d-switch")
        .click()
    )
    await asyncio.sleep(1)
    date_str = publish_date.strftime("%Y-%m-%d %H:%M")
    time_input = page.locator(".d-datepicker-input-filter input.d-text")
    await time_input.fill(str(date_str))
    await asyncio.sleep(1)


async def _set_content_declaration(page, ai_content: str) -> None:
    """Set AI content declaration via d-select dropdown."""
    if not ai_content:
        return

    logger.info("[内容声明] 设置内容类型声明: %s", ai_content)
    try:
        # Click the declaration dropdown trigger
        select_wrapper = page.locator(
            '.d-select-placeholder:has-text("添加内容类型声明")'
        ).first
        if await select_wrapper.count() > 0:
            await select_wrapper.click()
        else:
            await page.locator(".d-select-wrapper").first.click()
        await asyncio.sleep(1)

        # Click the target option
        target_option = page.locator(
            f'.d-option .d-option-name:has-text("{ai_content}")'
        )
        if await target_option.count() > 0:
            await target_option.first.click()
            logger.info("[内容声明] 内容类型声明已设置: %s", ai_content)
        else:
            logger.info("[内容声明] 未找到声明选项: %s", ai_content)

        await asyncio.sleep(1)
    except Exception as exc:
        logger.info("[内容声明] 内容声明设置失败 (非致命): %s", exc)


async def _set_original_declaration(page) -> None:
    """Enable the 原创声明 (original declaration) switch and accept terms.

    Flow:
    1. Click the switch next to '原创声明'
    2. A modal appears with a checkbox '我已阅读并同意 ...'
    3. Check the checkbox
    4. Click '声明原创' button
    """
    logger.info("[原创声明] 开始设置原创声明")
    try:
        # Find the 原创声明 switch
        switch_card = page.locator(".custom-switch-card").filter(
            has_text="原创声明"
        )
        switch = switch_card.locator(".d-switch")
        if await switch.count() == 0:
            logger.info("[原创声明] 未找到原创声明开关, 跳过")
            return

        # Check if already enabled (the d-switch-checked class)
        switch_box = switch.first
        classes = await switch_box.get_attribute("class") or ""
        if "d-switch-checked" in classes:
            logger.info("[原创声明] 原创声明已开启")
            return

        await switch_box.click()
        await page.wait_for_timeout(1500)

        # Agreement modal should appear
        modal = page.locator("div.d-modal.d-modal-centered")
        if await modal.count() == 0:
            logger.info("[原创声明] 未找到原创声明弹窗, 跳过")
            return
        modal = modal.first

        # Check the agreement checkbox
        checkbox = modal.locator(".d-checkbox-simulator")
        if await checkbox.count() > 0:
            await checkbox.first.click()
            await page.wait_for_timeout(500)

        # Click '声明原创' button
        confirm_btn = modal.locator('button:has-text("声明原创")')
        if await confirm_btn.count() > 0:
            await confirm_btn.first.click()
            await page.wait_for_timeout(1000)
            logger.info("[原创声明] 原创声明已设置")
        else:
            logger.info("[原创声明] 未找到声明原创按钮")

    except Exception as exc:
        logger.info("[原创声明] 原创声明设置失败 (非致命): %s", exc)
