"""
Kuaishou platform implementation — 100% CloakBrowser.

Uses ``BasePlatform`` browser entry points and shared utilities from
``backend/impl/_utils.py``.
"""

import asyncio
import threading
import time
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger
logger = get_channel_logger("kuaishou")

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_user_profile,
)
from ..base_platform import BasePlatform

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KS_LOGIN_URL = "https://cp.kuaishou.com"
_KS_UPLOAD_URL = "https://cp.kuaishou.com/article/publish/video"
_KS_MANAGE_URL_PATTERN = "**/article/manage/video?status=2&from=publish**"
_KS_UPLOAD_URL_PATTERN = "**/article/publish/video**"
_COOKIE_INVALID_SELECTOR = "div.names div.container div.name:text('机构服务')"

# 快手平台最多添加 4 个标签(图集和视频统一)
_KS_MAX_TAGS = 4

# 特殊作者声明值：表示「无需添加声明」(与前端 config/platforms.js DECLARATION_NONE 对齐)。
# 取此值或空时跳过 _set_author_declaration，不去快手发布页查找下拉选项，
# 避免因页面上无匹配项而 wait_for 超时。视频和图集发布共用此约定。
_DECLARATION_NONE = "内容无需添加声明"


class KuaishouPlatform(BasePlatform):
    platform_id = 4
    platform_key = "kuaishou"
    platform_name = "快手"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    platform_cookie_domain = ".kuaishou.com"

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
        success = False
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
            # 无限等扫码确认（不设超时，浏览器由用户自己关）
            while True:
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
            success = True
        except Exception as exc:
            logger.info(f"[kuaishou] login error: {exc}")
            status_queue.put('{"status": "0", "error": "' + str(exc) + '"}')
        finally:
            try:
                # 释放 context 资源
                await context.close()
            except Exception:
                pass
            # 成功才关浏览器（失败/异常时留着让用户看现场）
            if success:
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
        # 作者声明：前端 aiContent 经 image_publish_bp 透传为 ai_content 或 author_declaration
        # 两者都接收，与 publish_video 保持一致
        author_declaration = kwargs.get("ai_content", "") or kwargs.get("author_declaration", "")
        music_id = kwargs.get("music_id", "")
        music_title = kwargs.get("music_title", "")
        enable_timer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        activities = kwargs.get("activities", []) or []
        dry_run = kwargs.get("dry_run", True)

        logger.info("=" * 60)
        logger.info("[发布图集] 开始快手图集发布流程")
        logger.info("=" * 60)

        # 标签上限校验:快手最多 4 个
        if len(tags) > _KS_MAX_TAGS:
            logger.error(
                "[发布校验] 快手标签超过上限: 当前 %d 个, 最多 %d 个",
                len(tags), _KS_MAX_TAGS,
            )
            raise ValueError(
                f"快手标签最多 {_KS_MAX_TAGS} 个, 当前 {len(tags)} 个"
            )

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 图片数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 封面: %s", cover_path or "无")
        logger.info("[发布参数] 作者声明: %s", author_declaration or "无")
        logger.info("[发布参数] 音乐ID: %s, 音乐标题: %s", music_id or "无", music_title or "无")
        logger.info("[发布参数] 定时发布: %s", enable_timer)
        logger.info("[发布策略] 模式: %s", "演练(dry_run)" if dry_run else "正式发布")

        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(f) for f in files]

        if cover_path and not Path(cover_path).is_file():
            logger.warning("[发布参数] 封面文件不存在: %s", cover_path)
            cover_path = ""

        if activities:
            activity_tags = " ".join([f"#{act}" for act in activities])
            desc = f"{desc} {activity_tags}".strip()

        for cookie_index, cookie_path in enumerate(account_paths):
            cookie_name = Path(cookie_path).name
            nick = get_account_name_by_cookie_file(cookie_name)
            with bind_account_name(nick or "-"):
                logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
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

        logger.info("=" * 60)
        logger.info("[发布图集] 图集发布流程完成!")
        logger.info("=" * 60)
        return True

    async def _upload_image_note(
        self, *, title, file_paths, tags, account_file, desc="", cover_path="",
        author_declaration="", music_id="", music_title="",
        enable_timer=False, schedule_time_str="", dry_run=True,
    ):
        """Upload image note to one Kuaishou account."""
        logger.info("[上传图集] 开始上传图集 (%d 张图片)", len(file_paths))
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()

                # 1. 打开图文 tab
                logger.info("[上传图集] 正在打开图集上传页面...")
                await page.goto(
                    "https://cp.kuaishou.com/article/publish/video?tabType=2",
                    wait_until="domcontentloaded", timeout=60000,
                )
                await page.wait_for_url(
                    "**/article/publish/video?tabType=2**", timeout=60000,
                )
                logger.info("[上传图集] 图集上传页面已打开")
                await asyncio.sleep(2)

                # 2. 上传图片（file chooser 多选）
                logger.info("[上传图集] 正在上传 %d 张图片...", len(file_paths))
                upload_btn = page.locator("button[class^='_upload-btn']:visible").first
                await upload_btn.wait_for(state="visible", timeout=10000)
                async with page.expect_file_chooser() as fc_info:
                    await upload_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(file_paths)
                await asyncio.sleep(2)

                # 3. 等编辑页加载（URL 不会变，等描述输入框出现即可）
                logger.info("[上传图集] 等待编辑页加载...")
                await page.locator("#work-description-edit").wait_for(state="visible", timeout=30000)
                logger.info("[上传图集] 编辑页已加载, URL: %s", page.url)
                await asyncio.sleep(1)

                # 4. 关闭引导弹层
                await self._close_guide_overlay(page)

                # 5. 填描述（标题拼首行 + 描述 + 标签）
                full_desc = f"{title}\n\n{desc}" if title else desc
                logger.info("[填写简介] 开始填写简介: %s", full_desc[:50])
                desc_editor = page.locator("#work-description-edit").first
                await desc_editor.wait_for(state="visible", timeout=15000)
                await desc_editor.click()
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")
                await page.keyboard.type(full_desc[:500])
                # 标签输入(打字机 + 等下拉 + 选 _active_ 高亮项 + 空格兜底)
                # 图集路径已定位 #work-description-edit,传 element 让 helper 用
                # press_sequentially 自动 focus + 触发 React onChange(最稳)。
                await self._input_tags(
                    page, tags or [], max_n=_KS_MAX_TAGS, element=desc_editor
                )
                await asyncio.sleep(0.5)

                logger.info("[填写简介] 简介填写完成. 封面=%s, 音乐ID=%s", cover_path, music_id)

                # 6. 设置封面
                if cover_path:
                    logger.info("[设置封面] 开始设置封面...")
                    await self._set_image_cover(page, cover_path)

                # 7. 设置音乐
                if music_id:
                    logger.info("[设置音乐] 开始设置音乐: %s", music_id)
                    await self._set_image_music(page, music_id, music_title)

                # 8. 作者声明（值为「无需声明」或空时跳过，不去页面找下拉项）
                if author_declaration and author_declaration != _DECLARATION_NONE:
                    logger.info("[作者声明] 开始设置作者声明: %s", author_declaration)
                    await self._set_author_declaration(page, author_declaration)
                elif author_declaration == _DECLARATION_NONE:
                    logger.info("[作者声明] 选择「内容无需添加声明」，跳过设置")

                # 9. 定时发布
                if enable_timer and schedule_time_str:
                    publish_date = parse_schedule_time(
                        schedule_time_str, 1, enable_timer, 1, None, 0
                    )[0]
                    if publish_date != 0:
                        logger.info("[定时发布] 开始设置定时发布...")
                        await self._set_schedule_time(page, publish_date)
                        logger.info("[定时发布] 定时发布设置完成")

                logger.info("[填写完成] 表单填写完成, 模式: %s", "演练(dry_run)" if dry_run else "正式发布")

                if not dry_run:
                    logger.info("[发布] 正在点击发布按钮...")
                    publish_btn = page.get_by_text("发布", exact=True)
                    await publish_btn.first.click()
                    await page.wait_for_url(
                        "**/article/manage/video?status=2&from=publish**",
                        timeout=60000,
                    )
                    logger.info("[发布] 图集发布成功!")
                    await context.storage_state(path=account_file)
                    logger.info("[发布] Cookie状态已更新")
                else:
                    logger.info("=" * 40)
                    logger.info("[发布] [演练模式] 模拟点击发布! 发布成功!")
                    logger.info("=" * 40)
                    # dry_run 模式保留浏览器窗口，方便核对表单填写结果
                    logger.info(
                        "[发布] dry_run=True, 保留浏览器窗口供核对表单 (不关闭 context/browser)"
                    )
            finally:
                if not dry_run:
                    await context.close()
        finally:
            if not dry_run:
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
        logger.info("=" * 60)
        logger.info("[发布视频] 开始快手视频发布流程")
        logger.info("=" * 60)

        # 标签上限校验:快手最多 4 个
        tags = kwargs.get("tags", []) or []
        if len(tags) > _KS_MAX_TAGS:
            logger.error(
                "[发布校验] 快手标签超过上限: 当前 %d 个, 最多 %d 个",
                len(tags), _KS_MAX_TAGS,
            )
            raise ValueError(
                f"快手标签最多 {_KS_MAX_TAGS} 个, 当前 {len(tags)} 个"
            )

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

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
        # 作者声明：前端 aiContent 字段经 app.py 透传为 ai_content
        # （参见 services/draft_merge.py DECLARATION_PLATFORMS['kuaishou']='aiContent'）
        # author_declaration 仅作别名兼容旧调用
        author_declaration = kwargs.get("ai_content", "") or kwargs.get("author_declaration", "")

        # 优先使用竖版封面，其次横版，最后通用封面
        cover_path = thumbnail_portrait_path or thumbnail_landscape_path or thumbnail_path

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_files))
        logger.info("[发布参数] 定时发布: %s", enable_timer)
        logger.info("[发布参数] 封面: %s", cover_path or "无")
        logger.info("[发布参数] 作者声明: %s", author_declaration or "无")

        publish_dates = parse_schedule_time(
            schedule_time_str, len(files), enable_timer,
            videos_per_day, daily_times, start_days,
        )
        logger.info("[发布策略] 发布策略: %s", "scheduled" if enable_timer and schedule_time_str else "immediate")

        # 构建封面完整路径
        if cover_path:
            # cover_path 已是绝对路径
            cover_path = str(cover_path)
            logger.info("[发布参数] 封面路径: %s", cover_path)

        for idx, file_name in enumerate(files):
            # file_name 已是绝对路径
            video_path = str(file_name)
            pub_date = publish_dates[idx] if idx < len(publish_dates) else 0
            logger.info("-" * 40)
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s", idx + 1, len(files), video_path)

            for cookie_index, cookie_file in enumerate(account_files):
                cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
                nick = get_account_name_by_cookie_file(cookie_file)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_files), nick or "未知")
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

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

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
            logger.info("[上传视频] 开始上传视频: %s", title)
            logger.info("[上传视频] 正在上传视频文件...")

            # ------ Upload video via file chooser ------
            upload_button = page.locator("button[class^='_upload-btn']")
            await upload_button.wait_for(state="visible", timeout=10000)

            async with page.expect_file_chooser() as fc_info:
                await upload_button.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(video_path)
            logger.info("[上传视频] 视频文件已选择，等待上传完成...")

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
            logger.info("[填写简介] 开始填写简介与标签...")
            await page.get_by_text("描述").locator("xpath=following-sibling::div").click()
            # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
            await clear_and_type(page, desc or title)
            await page.keyboard.press("Enter")
            logger.info("[填写简介] 简介填写完成")

            # 标签输入(打字机 + 等下拉 + 选 _active_ 高亮项 + 空格兜底)
            # 视频路径的容器是 get_by_text + xpath 形式,这里不传 element,
            # _input_tags 内部用 page.keyboard.type(delay=150),要求描述框已聚焦
            # (前面 614 行的 click 已经把焦点带过来了)。
            await self._input_tags(page, tags, max_n=_KS_MAX_TAGS)


            # ------ Wait for upload to complete (no timeout — wait indefinitely) ------
            retry = 0
            while True:
                try:
                    if await page.locator("text=上传中").count() == 0:
                        logger.info("[上传视频] 视频上传成功!")
                        break
                    if retry % 15 == 0:
                        logger.info("[上传视频] 仍在上传中... (第 %d 次重试)", retry)
                    if await page.locator("text=上传失败").count():
                        logger.info("[上传视频] 上传失败，正在重试...")
                        await page.locator(
                            'div.progress-div [class^="upload-btn-input"]'
                        ).set_input_files(video_path)
                except Exception:
                    pass
                await asyncio.sleep(2)
                retry += 1

            # ------ Set thumbnail ------
            logger.info("[设置封面] 封面路径: %s", thumbnail_path)
            if thumbnail_path:
                logger.info("[设置封面] 开始设置视频封面...")
                await self._set_thumbnail(page, thumbnail_path)
                logger.info("[设置封面] 封面设置完成")
            else:
                logger.info("[设置封面] 未提供封面路径, 跳过封面设置")

            # ------ Set author declaration（值为「无需声明」或空时跳过）------
            if author_declaration and author_declaration != _DECLARATION_NONE:
                logger.info("[作者声明] 开始设置作者声明: %s", author_declaration)
                await self._set_author_declaration(page, author_declaration)
            elif author_declaration == _DECLARATION_NONE:
                logger.info("[作者声明] 选择「内容无需添加声明」，跳过设置")

            # ------ Set schedule time ------
            if enable_timer and publish_date and publish_date != 0:
                logger.info("[定时发布] 开始设置定时发布...")
                await self._set_schedule_time(page, publish_date)
                logger.info("[定时发布] 定时发布设置完成")

            # ------ Click publish ------
            logger.info("[发布] 正在点击发布按钮...")
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
                    logger.info("[发布] 视频发布成功! 页面跳转到: %s", page.url)
                    break
                except Exception as exc:
                    logger.info("[发布] 发布重试: %s", exc)
                    await asyncio.sleep(1)

            upload_success = True
        finally:
            if upload_success:
                try:
                    await context.storage_state(path=cookie_path)
                    logger.info("[发布] Cookie状态已更新")
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
    # Helper: input tags (typewriter + dropdown select + space fallback)
    # ------------------------------------------------------------------

    async def _input_tags(self, page, tags, max_n: int = _KS_MAX_TAGS, *, element=None):
        """逐字输入标签(打字机效果),然后等下拉出现 → 选默认高亮项(_active_)。
        失败退路:按下空格确认(同 xhs/zhihu)。

        CLAUDE.md L70-112 推荐 press_sequentially(..., delay=150) 配合单独 Space
        触发话题联想。快手自带「打字机联想」机制,输入 #xxx 后会弹出下拉,
        _active_ 项即默认高亮的推荐话题,选择该话题即可。

        # 号通过 CDP ``Input.dispatchKeyEvent`` 直接发 keydown/keyup,显式指定
        ``text='#' / key='#' / modifiers=8(Shift 位)``,绕过 Playwright 的 keyboard 抽象。
        之所以不用 ``keyboard.press("Shift+3")`` 或 ``down/up`` 序列:
        Playwright 这两个 API 在 Shift 修饰时实测只发出 key='3' 而不是 #,
        快手页面因此识别成数字 3,无法触发 # 的话题识别与键盘样式。
        CDP 层面我们直接告诉 Chromium "这次按键的 text 是 # 且带 Shift 修饰",
        Chromium 会原样派发 DOM keydown 事件(event.key='#' + event.shiftKey=true)。

        输入 # 之后必须等一小段(500ms)再继续输入标签内容,让 React 的
        onKeyDown / onChange 处理完首轮 setState,激活 # 触发的「话题识别状态」:
        此时输入框会把后续字符识别为「话题名」并渲染话题芯片样式 + 弹出联想下拉;
        若立即接着打 tag,会被当作普通文本插入,样式不会切换。

        Args:
            page: Playwright 页面
            tags: 标签数组(裸字符串)
            max_n: 最多输入几个标签(快手目前是 4,见 _KS_MAX_TAGS)
            element: 已定位好的输入框容器;若 None 则用 page.keyboard.type。
                     传 element 时改用 press_sequentially(自动 focus,触发 React onChange)。
        """
        if not tags:
            return
        # CDP session 提到循环外,每个标签复用同一个连接
        cdp = await page.context.new_cdp_session(page)
        for tag in tags[:max_n]:
            text = f"#{tag}"
            # 1. 通过 CDP Input.dispatchKeyEvent 直接发 keydown/keyup,显式指定
            #    text='#' / key='#' / modifiers=8(Shift 位),保证插入的字符是 #
            #    且 React 能读到 event.key='#' + event.shiftKey=true。
            #    之所以不用 keyboard.press("Shift+3") 或 down/up 序列:
            #    Playwright 这两个 API 在 Shift 修饰时实测只发出 key='3' 而不是 #,
            #    快手页面因此识别成数字 3,无法触发 # 的话题识别与键盘样式。
            #    CDP 层面我们绕过 Playwright 的 keyboard 抽象,直接告诉 Chromium
            #    "这次按键的 text 是 # 且带 Shift 修饰",Chromium 会原样派发 DOM
            #    keydown 事件(event.key='#' + event.shiftKey=true)。
            logger.info("[填写标签] CDP dispatchKeyEvent 输入 # (key='#' shiftKey=true)")
            await cdp.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "key": "#",
                "code": "Digit3",
                "text": "#",
                "modifiers": 8,                # 8 = Shift(1 << 3)
                "windowsVirtualKeyCode": 51,   # VK_3
            })
            await cdp.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": "#",
                "code": "Digit3",
                "modifiers": 8,
                "windowsVirtualKeyCode": 51,
            })
            # 2. 输入 # 后等一小会,让 React onKeyDown/onChange 完成首轮处理、
            #    激活 # 触发的「话题识别状态」(渲染话题芯片样式 + 弹出联想下拉)
            #    实测 500ms 比较稳:太短 React 内部 setState 还没提交,后续字符会被
            #    当作普通文本插入;太长则下拉打开后又被关闭。
            logger.info("[填写标签] 等待 React 完成 # 处理 (500ms)")
            await asyncio.sleep(0.5)
            # 3. 再用打字机逐字输入标签内容(150ms / 字符,触发 React 监听)
            logger.info("[填写标签] 打字机输入标签内容 - press_sequentially: '%s'", tag)
            if element is not None:
                await element.press_sequentially(tag, delay=150)
            else:
                await page.keyboard.type(tag, delay=150)
            # 3. 等 React 监听完成,激活下拉
            await asyncio.sleep(2)

            # 3. 检测下拉 + 点击 _active_ 高亮项
            dropdown = page.locator('div[class*="_dropdown-container_"]').first
            try:
                await dropdown.wait_for(state="visible", timeout=3000)
                active = page.locator(
                    'div[class*="_topic-item_"][class*="_active_"]'
                ).first
                if await active.count() and await active.is_visible():
                    try:
                        tag_name_el = active.locator('span[class*="_at-tag-name_"]').first
                        tag_name = (await tag_name_el.text_content() or "").strip()
                    except Exception:
                        tag_name = ""
                    await active.click()
                    logger.info("[填写标签] 选中下拉高亮项: #%s", tag_name or "?")
                    await asyncio.sleep(0.5)
                    continue  # 成功选中,跳过空格兜底
            except Exception as exc:
                logger.info("[填写标签] 下拉未出现 / 点击失败 (%s),改用空格确认", exc)

            # 4. 退路:按下空格确认(同 xhs/zhihu),确保 #xxx 至少变成话题芯片
            await page.keyboard.press("Space")
            await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # Helper: set thumbnail
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_thumbnail(page, thumbnail_path: str):
        """Upload custom cover image.

        Flow: hover cover area -> click "封面设置" -> modal ->
        "上传封面" tab -> upload image -> confirm.
        """
        logger.info("[封面] 开始设置视频封面: %s", thumbnail_path)
        try:
            # 1. Hover over cover area to reveal "封面设置" overlay
            cover_area = page.locator("div[class*='default-cover']").first
            logger.info("[封面] 正在悬停封面区域...")
            await cover_area.hover()
            await asyncio.sleep(1.5)

            # 2. Click "封面设置" text to open modal
            cover_editor = page.locator("div[class*='cover-full-editor']").first
            logger.info("[封面] 正在点击 '封面设置'...")
            await cover_editor.wait_for(state="visible", timeout=10000)
            await cover_editor.click()

            # 3. Wait for modal
            modal = page.locator('div[role="document"].ant-modal:visible')
            logger.info("[封面] 等待弹窗出现...")
            await modal.wait_for(state="visible", timeout=30000)
            await asyncio.sleep(1)

            # 4. Click "上传封面" tab
            upload_tab = modal.locator("div[class*='header-title-item']").nth(1)
            logger.info("[封面] 正在点击 '上传封面' tab...")
            await upload_tab.wait_for(state="visible", timeout=10000)
            await upload_tab.click()
            await asyncio.sleep(1)

            # 5. Find hidden file input and upload image
            file_input = modal.locator("input[type='file']")
            logger.info("[封面] 正在上传封面图片...")
            await file_input.wait_for(state="attached", timeout=30000)
            await file_input.set_input_files(thumbnail_path)
            logger.info("[封面] 封面图片已上传, 等待处理...")
            await asyncio.sleep(3)

            # 6. Click "确认" or "完成" button
            confirm_btn = modal.locator("button:has-text('确认'), button:has-text('完成')").first
            logger.info("[封面] 正在点击确认按钮...")
            await confirm_btn.wait_for(state="visible", timeout=10000)
            await confirm_btn.click()
            await asyncio.sleep(2)

            # 7. Wait for modal to close
            try:
                await modal.wait_for(state="hidden", timeout=30000)
            except Exception:
                pass

            logger.info("[封面] 封面设置成功")
        except Exception as exc:
            logger.info("[封面] 封面设置失败 (非致命): %s", exc)

    # ------------------------------------------------------------------
    # Helper: set image cover (image note)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_cover(page, cover_path: str):
        """点击「编辑封面」按钮 → 上传封面图 → 确认。"""
        logger.info("[封面] 开始设置图集封面: %s", cover_path)
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
            logger.info("[封面] 图集封面设置成功")
        except Exception as exc:
            logger.info("[封面] 图集封面设置失败 (非致命): %s", exc)

    # ------------------------------------------------------------------
    # Helper: set image music (image note)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_music(page, music_id: str, music_title: str = ""):
        """点击「添加音乐」→ 抽屉内搜索 → 按 musicId/music_title 匹配 → 点「添加」。"""
        logger.info("[设置音乐] 开始设置图集音乐: id=%s, 标题=%s", music_id, music_title)
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
                    logger.warning("[设置音乐] 音乐标题未精确匹配, 使用第一个卡片")

            if target_card and await target_card.count():
                add_btn = target_card.locator("div:has-text('添加'), button:has-text('添加')").last
                await add_btn.click(force=True)
                await asyncio.sleep(2)
                logger.info("[设置音乐] 音乐已添加")
            else:
                logger.warning("[设置音乐] 未找到音乐卡片")

            close_btn = page.locator("div.ant-drawer-close").first
            if await close_btn.count():
                await close_btn.click(force=True)
        except Exception as exc:
            logger.info("[设置音乐] 图集音乐设置失败 (非致命): %s", exc)

    # ------------------------------------------------------------------
    # Helper: set author declaration (ant-select dropdown)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_author_declaration(page, author_declaration: str):
        """Set author declaration via ant-select dropdown.

        新版 DOM 结构(label 与 ant-select 为兄弟节点,placeholder 在
        ``span.ant-select-selection-placeholder`` 上,而非 input):
        ::

            <label>作者声明<img/></label>
            <div class="ant-select ...">
              <div class="ant-select-selector">
                <input ... style="opacity: 0;"/>            <!-- 无 placeholder -->
                <span class="ant-select-selection-placeholder">为作品添加补充说明</span>
              </div>
            </div>

        行为约定:
        - author_declaration 为空或等于 _DECLARATION_NONE 时直接跳过(已在上层守卫,此处防御)。
        - 打开下拉框后若没有匹配的选项(快手改版/该账号无此声明),主动收起下拉框并跳过,
          不视为错误 —— 用户要求「没找到匹配项就不强制选择」。
        """
        # 防御:空或「无需声明」直接跳过(正常情况下上层调用点已守卫)
        if not author_declaration or author_declaration == _DECLARATION_NONE:
            logger.info("[作者声明] 无需设置作者声明，跳过")
            return

        logger.info("[作者声明] 开始设置作者声明: %s", author_declaration)
        try:
            select_clicked = False

            # Strategy 1: label 兄弟节点定位(新版 DOM 首选)
            # label 与 div.ant-select 为同级兄弟,直接取后续兄弟里的 ant-select 本身
            if not select_clicked:
                for label_text in ['作者声明', '补充说明', '声明']:
                    label = page.locator(f"label:has-text('{label_text}')")
                    if await label.count():
                        wrapper = label.locator(
                            "xpath=following-sibling::div[contains(@class, 'ant-select')][1]"
                        ).first
                        if await wrapper.count():
                            await wrapper.click()
                            select_clicked = True
                            break

            # Strategy 2: 占位符 span 定位(新版 DOM 的占位符在 span 上)
            if not select_clicked:
                for placeholder in ['为作品添加补充说明', '补充说明', '请选择']:
                    ph_span = page.locator(
                        f"span.ant-select-selection-placeholder:has-text('{placeholder}')"
                    )
                    if await ph_span.count():
                        wrapper = ph_span.locator(
                            "xpath=ancestor::div[contains(@class, 'ant-select')][1]"
                        ).first
                        if await wrapper.count():
                            await wrapper.click()
                            select_clicked = True
                            break

            # Strategy 3: 兼容旧版 DOM —— input 上的 placeholder
            if not select_clicked:
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

            if not select_clicked:
                logger.info("[作者声明] 未找到作者声明下拉框, 跳过")
                return

            await asyncio.sleep(1)

            # Select matching option
            # 先用短超时探测匹配项是否存在;不存在则收起下拉框并跳过(非错误)。
            option = page.locator(
                f"div.ant-select-item-option:has-text('{author_declaration}')"
            ).first
            if not await option.count():
                logger.info(
                    "[作者声明] 下拉框中未找到匹配选项「%s」，收起并跳过",
                    author_declaration,
                )
                # 点击空白处收起下拉框，避免遮挡后续操作
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                return
            await option.click()
            logger.info("[作者声明] 作者声明已设置: %s", author_declaration)
            await asyncio.sleep(1)
        except Exception as exc:
            logger.info("[作者声明] 作者声明设置失败 (非致命): %s", exc)

    # ------------------------------------------------------------------
    # Helper: set schedule time (ant-radio + ant-picker)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Set scheduled publish time via ant-radio and ant-picker."""
        logger.info("[定时发布] 设置定时发布时间: %s", publish_date)
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
        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        await clear_and_type(page, date_str)
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)
